"""Pure game rules shared by the playable prototype and seeded simulations."""
from __future__ import annotations
import copy
import math
import random
from .catalog import stable
from . import management as m
from . import evolution, flavor
from . import meetings, stage_labels, bookings

VERSION = '1.2.0-local'
NIGHT_SPEEDS = (1, 2, 4, 8)
PACKS = {'standard': {'name':'Standard','price':100,'count':5},
         'spotlight': {'name':'Girl spotlight','price':200,'count':5},
         'themed': {'name':'Themed','price':200,'count':5},
         'premium': {'name':'Premium','price':400,'count':5},
         'collector': {'name':'Collector','price':600,'count':5}}
UPGRADES = {'rooms': {'name':'Private room','base':350,'step':180,'max':6},
            'lounge': {'name':'Lounge position','base':300,'step':220,'max':3},
            'recovery': {'name':'Recovery suite','base':300,'step':280,'max':3},
            'reception': {'name':'Reception','base':400,'step':320,'max':3}}
ROLES = ('room', 'lounge', 'rest', 'train')
PRICES = {'accessible': (.9, .99), 'standard': (1, .92), 'premium': (1.25, .68)}


class RuleError(ValueError):
    pass


def available(catalog):
    return [c for c in catalog['cards'].values() if c.get('available', True)]


def starter(catalog, owner):
    pool = [c for c in available(catalog) if c['owner'] == owner and c.get('source') not in evolution.SET_CARDS]
    if not pool:
        raise RuleError('This girl has no currently eligible cards.')
    return min(pool, key=lambda c: (c['rarity'], c['id']))['id']


def new_game(catalog, selected, seed=1):
    if not isinstance(selected, list) or len(selected) != 2 or len(set(selected)) != 2:
        raise RuleError('Choose two different starting girls.')
    if any(p not in catalog['people'] for p in selected):
        raise RuleError('Choose girls from this catalog.')
    people, owned = {}, {}
    for i, owner in enumerate(selected):
        card = starter(catalog, owner)
        owned[card] = {'copies':1, 'mastery':0, 'xp':0, 'uses':0, 'acquired_day':1}
        people[owner] = {'energy':100, 'xp':0, 'card':card, 'role':'room' if i == 0 else 'lounge', 'hired_day':1}
    return m.ensure({'schema':2, 'version':VERSION, 'seed':int(seed), 'day':1, 'cash':600,
            'phase':'prepare', 'people':people, 'owned':owned,
            'facilities':{'rooms':1,'lounge':1,'recovery':0,'reception':0},
            'pricing':'standard', 'pending_pack':None, 'pack_counter':0, 'night':None,
            'reports':[], 'totals':{'revenue':0,'expenses':0,'packs':0,'services':0,'recovery_grants':0},
            'journal':[]})


def record(state, kind, **details):
    state['journal'].append({'day':state['day'], 'kind':kind, **details})


def hire_cost(state):
    return 220 + max(0, len(state['people']) - 2) * 55


def upgrade_cost(state, kind):
    rule = UPGRADES[kind]
    initial = 1 if kind in ('rooms','lounge') else 0
    return rule['base'] + max(0, state['facilities'][kind] - initial) * rule['step']


def upkeep(state):
    f = state['facilities']
    return 20 + f['rooms']*8 + f['lounge']*8 + (f['recovery']+f['reception'])*6


def recurring_cost(state):
    return len(state['people'])*30 + upkeep(state) + m.department_upkeep(state)


def budget_check(state, cost):
    if state['cash'] < cost:
        raise RuleError('Not enough cash for this purchase.')


def prep_only(state):
    if state['phase'] != 'prepare':
        raise RuleError('Finish the current night before changing the plan.')


def forecast(state):
    day = random.Random(stable((state['seed'],state['day'],'demand'))).random()
    return ('Busy',1.04) if day > .72 else ('Quiet',.78) if day < .2 else ('Steady',.94)


def auto_assign(state):
    prep_only(state)
    ranked = sorted(state['people'], key=lambda p:(-state['people'][p]['energy'],p))
    room_left, lounge_left = state['facilities']['rooms'],state['facilities']['lounge']
    for owner in ranked:
        worker = state['people'][owner]
        if m.reservations(state, owner):
            continue
        if worker['energy'] < 34:
            worker['role'] = 'rest'
        elif room_left:
            worker['role'] = 'room'; room_left -= 1
        elif lounge_left:
            worker['role'] = 'lounge'; lounge_left -= 1
        else:
            worker['role'] = 'rest'


def start_night(state):
    prep_only(state)
    for role, key in [('room','rooms'),('lounge','lounge')]:
        if sum(m.assignment(state, p)==role for p in state['people']) > state['facilities'][key]:
            raise RuleError('More girls are assigned than available positions. Use Auto assign or adjust the plan.')
    if state['pending_pack']:
        raise RuleError('Finish opening your pack first.')
    state['phase'] = 'night'
    demand, factor = forecast(state)
    state['night'] = {'elapsed':0,'wave':0,'paused':False,'speed':state['preferred_night_speed'],'demand':demand,
                      'demand_factor':factor,'revenue':0,'served':0,'missed':0,'log':[],
                      'earnings':{p:0 for p in state['people']}, 'energy_spent':{p:0 for p in state['people']}}
    state['night'].update(stage_tracking=2, duration=bookings.NIGHT_SECONDS,
                          booking_rules_version=bookings.BOOKING_RULES_VERSION)
    m.prepare_night(state)
    record(state,'night_started',pricing=state['pricing'],assignments=copy.deepcopy(state['people']))


def prepare_meetings(state, catalog, labels, force=False):
    night = state['night']
    if night.get('stage_tracking') == 2:
        bookings.initialize(state, catalog, labels)
        if not night['paused']:
            bookings.process(state, catalog, labels, True)
        return
    if not night.get('stage_tracking') or night['wave'] >= 6 or night.get('meeting_round') == night['wave'] + 1:
        return
    if not force and any(not d['choice'] and d['at'] <= night['elapsed'] < d['until'] for d in night['decisions']):
        return
    # The existing deterministic rules establish whether this round has a
    # booking. Run them on a copy; all real accounting still occurs at its
    # original boundary. The tracker cannot alter acceptance or payment RNG.
    preview = copy.deepcopy(state)
    results = resolve_club_round(preview, catalog, night['wave'] + 1)
    meetings.begin_round(state, results, force=force)
    meetings.advance(state, night['elapsed'], labels)


def resolve_club_round(state, catalog, wave, owners=None, rng=None):
    night = state['night']; results = {}
    rng = rng or random.Random(stable((state['seed'],state['day'],wave)))
    multiplier, acceptance = PRICES[state['pricing']]
    for owner, worker in state['people'].items():
        if owners is not None and owner not in owners:
            continue
        role = night['assignments'][owner]
        if role not in ('room','lounge'):
            continue
        card = catalog['cards'][worker['card']]
        own = state['owned'][worker['card']]
        strength = .06 + card['rarity']*.015 + own['mastery']*.01
        energy_cost = 8*(1-strength if card['specialty']=='efficiency' else 1)
        if worker['energy'] < energy_cost:
            night['missed'] += 1
            night['activities'][owner] = {'department':'club', 'label':'Paid sex' if role=='room' else 'Lounge hosting',
                'status':flavor.activity('tired',state,owner,wave), 'round':wave}
            results[owner] = {'served': False, 'reason': 'tired'}
            continue
        accept = min(.995, acceptance*night['demand_factor'] + .018*state['facilities']['reception']
                     + (strength*.5 if card['specialty']=='service' else 0)
                     + (min(.035,state['loyalty']/2000) if card['specialty']=='loyalty' else 0)
                     + (.035 if state['promotion_until'] >= state['day'] else 0))
        if rng.random() > accept:
            night['missed'] += 1
            night['activities'][owner] = {'department':'club', 'label':'Paid sex' if role=='room' else 'Lounge hosting',
                'status':flavor.activity('quiet',state,owner,wave), 'round':wave}
            results[owner] = {'served': False, 'reason': 'quiet'}
            continue
        value = (24 if role=='room' else 14) * multiplier * rng.uniform(.92,1.08)
        value *= 1 + min(.20,worker['xp']//100*.01)
        value *= 1 + m.skill_bonus(worker, 'club')
        value *= 1 + (strength if card['specialty']=='tips' else strength*.35)
        value = round(value)
        worker['energy'] = round(worker['energy']-energy_cost,2)
        worker['xp'] += 4
        worker['skills']['club'] += 2
        if card['specialty']=='loyalty': state['loyalty']=min(100,state['loyalty']+.15)
        own['xp'] += 3; own['uses'] += 1
        own['mastery'] = min(5,own['xp']//90)
        night['energy_spent'][owner] += energy_cost
        night['earnings'][owner] += value
        night['revenue'] += value; night['served'] += 1
        night['activities'][owner] = {'department':'club', 'label':'Paid sex' if role=='room' else 'Lounge hosting',
            'status':flavor.activity(role,state,owner,wave)+f' +${value}', 'round':wave}
        results[owner] = {'served': True, 'value': value}
    return results


def advance(state, catalog, seconds, stop_at_decision=False, labels=None):
    if state['phase'] != 'night' or state['night']['paused']:
        return
    if not isinstance(seconds, (float,int)) or not math.isfinite(seconds) or seconds < 0:
        raise RuleError('Invalid time step.')
    night = state['night']
    labels = labels or stage_labels.bundled()
    if night.get('stage_tracking') == 2:
        bookings.advance(state, catalog, seconds, labels, stop_at_decision)
        return
    target = min(300, night['elapsed'] + seconds)
    decision = next((d for d in sorted(night['decisions'],key=lambda d:d['at'])
                     if not d['choice'] and night['elapsed'] < d['until'] and target >= d['at']),None) if stop_at_decision else None
    target = max(night['elapsed'],decision['at']) if decision else target
    if decision: night['paused']=True
    while night['wave'] < min(6, int(target//50)):
        prepare_meetings(state, catalog, labels, force=True)
        night['elapsed'] = (night['wave'] + 1) * 50
        meetings.advance(state, night['elapsed'], labels)
        night['wave'] += 1
        results = resolve_club_round(state, catalog, night['wave'])
        meetings.complete_round(state, results)
        m.advance_wave(state,catalog,night['wave'])
        message = flavor.activity('round',state,'venue',night['wave'])+f" Round {night['wave']}: ${night['revenue']} earned so far."
        night['log'].append(message)
        record(state,'service_round',wave=night['wave'],revenue=night['revenue'],served=night['served'])
    # Create the next plan at the processed boundary, before catching its
    # display up to the requested time. Polling frequency must not shorten it.
    if target < 300:
        prepare_meetings(state, catalog, labels)
    night['elapsed'] = target
    if night['elapsed'] >= 300:
        settle(state)
    else:
        meetings.advance(state, target, labels)


def settle(state):
    if state['phase'] != 'night' or state['night']['wave'] != 6:
        raise RuleError('This night is not ready to settle.')
    night = state['night']
    expense = recurring_cost(state)
    training_cost = sum(night['assignments'][p]=='train' for p in state['people'])*15
    expense += training_cost + night['decision_costs']
    for owner, worker in state['people'].items():
        role=night['assignments'][owner]
        recovery = (70 + state['facilities']['recovery']*6) if role in ('rest','train') else (28 + state['facilities']['recovery']*2)
        worker['energy'] = min(100,round(worker['energy'] + recovery,2))
        if role=='train':
            worker['xp'] += 22
            worker['skills'][worker['training']] += 35
    state['cash'] += night['revenue']-expense
    report = {'day':state['day'],'revenue':night['revenue'],'expenses':expense,
              'profit':night['revenue']-expense,'served':night['served'],'missed':night['missed'],
              'earnings':night['earnings'],'demand':night['demand'],
              'department_revenue':night['department_revenue'], 'training_cost':training_cost,
              'decision_costs':night['decision_costs'], 'decisions':copy.deepcopy(night['decisions']),
              'activity':night['log'][-12:], 'assignments':night['assignments']}
    if night.get('stage_tracking') == 2:
        report['booking_history'] = copy.deepcopy(night['booking_history'])
        report['duration'] = night['duration']
        report['booking_rules_version'] = night.get('booking_rules_version', 3)
    state['reports'] = (state['reports']+[report])[-40:]
    for key, value in [('revenue',night['revenue']),('expenses',expense),('services',night['served'])]:
        state['totals'][key] += value
    record(state,'night_settled',**{k:v for k,v in report.items() if k!='day'})
    m.after_settle(state,report)
    state['phase']='prepare';state['day']+=1
    state['night']=None


def pool_for(catalog, pack, target=None):
    pool = available(catalog)
    if pack == 'spotlight': pool = [c for c in pool if c['owner']==target]
    if pack == 'themed': pool = [c for c in pool if target in c['categories']]
    if not pool: raise RuleError('This pack currently has no eligible cards.')
    return pool


def draw(pool, rng, minimum=0):
    owners = sorted({c['owner'] for c in pool})
    owner = rng.choice(owners)
    owner_pool = [c for c in pool if c['owner']==owner]
    tiers = sorted({c['rarity'] for c in owner_pool if c['rarity']>=minimum})
    if not tiers:
        tiers = [max(c['rarity'] for c in owner_pool)]
    tier = rng.choices(tiers,weights=[(55,27,12,5,1)[t] for t in tiers])[0]
    return rng.choice([c for c in owner_pool if c['rarity']==tier])


def buy_pack(state,catalog,pack,target=None,voucher=False):
    prep_only(state)
    if state['pending_pack']: raise RuleError('Finish opening your previous pack first.')
    if pack not in PACKS: raise RuleError('Unknown pack.')
    spec = PACKS[pack]
    price=spec['price']
    if voucher:
        if pack!='standard' or state['pack_vouchers']<1: raise RuleError('A Standard pack voucher is required.')
        price=0
    budget_check(state,price)
    pool = pool_for(catalog,pack,target)
    special = None
    if pack=='collector':
        special=[c for c in pool if c['id'] not in state['owned']]
        if not special: raise RuleError('Collection complete: no missing cards remain in this pool.')
    if pack=='premium':
        special=[c for c in pool if c['rarity']>=3]
        if not special: raise RuleError('This catalog has no Epic or Legendary cards for the advertised guarantee.')
    state['pack_counter'] += 1
    rng=random.Random(stable((state['seed'],'pack',state['pack_counter'])))
    results=[]
    for i in range(spec['count']):
        card=draw(special if i==0 and special is not None else pool,rng)
        ident=card['id']; is_new=ident not in state['owned']
        if is_new: state['owned'][ident]={'copies':0,'mastery':0,'xp':0,'uses':0,'acquired_day':state['day']}
        state['owned'][ident]['copies']+=1
        results.append({'id':ident,'new':is_new})
    state['cash']-=price;state['totals']['packs']+=1
    if voucher: state['pack_vouchers']-=1
    state['pending_pack']={'id':state['pack_counter'],'type':pack,'results':results}
    record(state,'pack_bought',pack=pack,target=target,price=price,voucher=voucher,results=results)


def command(original,catalog,action,body=None,labels=None):
    state=copy.deepcopy(original);body=body or {}
    m.ensure(state)
    state['journal']=[]
    if m.command(state,catalog,action,body): pass
    elif action=='auto': auto_assign(state)
    elif action=='plan':
        prep_only(state)
        owner=body.get('owner');role=body.get('role')
        if owner not in state['people'] or role not in ROLES: raise RuleError('Invalid assignment.')
        if m.reservations(state,owner): raise RuleError('This worker is reserved by a department tonight. Cancel that reservation to reassign her.')
        state['people'][owner]['role']=role
        record(state,'assignment_changed',owner=owner,role=role)
    elif action=='equip':
        prep_only(state);ident=body.get('card');owner=body.get('owner')
        if owner not in state['people'] or ident not in state['owned'] or catalog['cards'][ident]['owner']!=owner:
            raise RuleError('Equip an owned card of this girl.')
        state['people'][owner]['card']=ident
        record(state,'card_equipped',owner=owner,card=ident)
    elif action=='duo_side':
        ident = body.get('card')
        side = body.get('side')
        if ident not in state['owned'] or catalog['cards'][ident].get('source') != 'duo' or side not in evolution.DUO_SIDES:
            raise RuleError('Choose the front or back of an owned Duo.')
        if 'index' in body:
            index = body['index']
            pack = state['pending_pack']
            if not pack or type(index) is not int or index not in pack.get('revealed', []) or pack['results'][index]['id'] != ident:
                raise RuleError('Reveal this Duo in the current pack before flipping it.')
            pack['results'][index]['duo_side'] = side
        state['owned'][ident]['duo_side'] = side
    elif action=='price':
        prep_only(state)
        if body.get('pricing') not in PRICES: raise RuleError('Unknown price policy.')
        state['pricing']=body['pricing'];record(state,'price_policy',pricing=state['pricing'])
    elif action=='hire':
        prep_only(state);owner=body.get('owner')
        if owner not in catalog['people'] or owner in state['people']: raise RuleError('Choose an available recruit.')
        candidates=[i for i in state['owned'] if catalog['cards'][i]['owner']==owner]
        cost=0 if candidates else hire_cost(state)
        budget_check(state,cost)
        card=candidates[0] if candidates else starter(catalog,owner)
        state['owned'].setdefault(card,{'copies':1,'mastery':0,'xp':0,'uses':0,'acquired_day':state['day']})
        state['people'][owner]={'energy':100,'xp':0,'card':card,'role':'rest','hired_day':state['day']}
        state['cash']-=cost;record(state,'hired',owner=owner,cost=cost,card=card)
    elif action=='upgrade':
        prep_only(state);kind=body.get('kind')
        if kind not in UPGRADES or state['facilities'][kind]>=UPGRADES[kind]['max']: raise RuleError('This facility is fully upgraded.')
        cost=upgrade_cost(state,kind);budget_check(state,cost)
        state['cash']-=cost;state['facilities'][kind]+=1
        record(state,'facility_upgraded',facility=kind,cost=cost,level=state['facilities'][kind])
    elif action=='mastery':
        prep_only(state);ident=body.get('card');item=state['owned'].get(ident)
        if not item or item['copies']<2: raise RuleError('Keep the first copy; an extra copy is needed.')
        if item['mastery']>=5: raise RuleError('This card has reached its mastery limit.')
        item['copies']-=1;item['xp']+=30;item['mastery']=min(5,item['xp']//90)
        record(state,'duplicate_used',card=ident,xp=30)
    elif action=='pack': buy_pack(state,catalog,body.get('pack'),body.get('target'),body.get('voucher') is True)
    elif action=='reveal':
        if not state['pending_pack']: raise RuleError('No pack is waiting to be revealed.')
        pack=state['pending_pack']
        if body.get('all') is True: pack['revealed']=list(range(len(pack['results'])))
        else:
            index=body.get('index')
            if type(index) is not int or not 0<=index<len(pack['results']): raise RuleError('Choose a card in this pack.')
            pack['revealed']=sorted(set(pack.get('revealed',[])+[index]))
    elif action=='reveal_done':
        if state['pending_pack']:
            record(state,'pack_reveal_completed',pack_id=state['pending_pack']['id'])
            state['pending_pack']=None
    elif action=='start': start_night(state)
    elif action=='advance':
        advance(state,catalog,body.get('seconds',0),stop_at_decision=body.get('stop_at_decision',False),labels=labels)
    elif action=='finish':
        if state['phase']!='night': raise RuleError('No night is in progress.')
        state['night']['paused']=False
        advance(state,catalog,state['night'].get('duration',300),labels=labels)
    elif action in ('pause','speed'):
        if state['phase']!='night': raise RuleError('No night is in progress.')
        if action=='pause':
            paused=body['paused'] if type(body.get('paused')) is bool else not state['night']['paused']
            if not paused and any(not d['choice'] and d['at']<=state['night']['elapsed']<d['until'] for d in state['night']['decisions']):
                raise RuleError('Choose an event option to keep the night going.')
            state['night']['paused']=paused
        else:
            speed=body.get('speed')
            if type(speed) is not int or speed not in NIGHT_SPEEDS: raise RuleError('Choose 1x, 2x, 4x or 8x speed.')
            state['night']['speed']=speed
            state['preferred_night_speed']=speed
    elif action=='recovery':
        prep_only(state)
        if state['cash']>=recurring_cost(state): raise RuleError('Recovery is available when the next night is unaffordable.')
        # A deliberately visible, recoverable setback; no deletion or mandatory reset.
        state['cash']=recurring_cost(state)+100
        for worker in state['people'].values(): worker['energy']=100
        # A recovery break must not strand reservations on dates that were skipped.
        for contract in state['contracts']:
            if contract['status']=='active':
                contract['start']+=2;contract['end']+=2
        state['day']+=2;state['totals']['recovery_grants']+=1
        record(state,'recovery_break',days=2,cash=state['cash'])
    else: raise RuleError('Unknown game action.')
    if action in ('start', 'decision') and state['phase'] == 'night':
        prepare_meetings(state, catalog, labels or stage_labels.bundled())
    return m.ensure(state)
