"""Pure game rules shared by the playable prototype and seeded simulations."""
from __future__ import annotations
import copy
import math
import random
from .catalog import stable

VERSION = '0.1.0'
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
    pool = [c for c in available(catalog) if c['owner'] == owner]
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
    return {'schema':1, 'version':VERSION, 'seed':int(seed), 'day':1, 'cash':600,
            'phase':'prepare', 'people':people, 'owned':owned,
            'facilities':{'rooms':1,'lounge':1,'recovery':0,'reception':0},
            'pricing':'standard', 'pending_pack':None, 'pack_counter':0, 'night':None,
            'reports':[], 'totals':{'revenue':0,'expenses':0,'packs':0,'services':0,'recovery_grants':0},
            'journal':[]}


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
    return len(state['people'])*30 + upkeep(state)


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
        if sum(p['role']==role for p in state['people'].values()) > state['facilities'][key]:
            raise RuleError('More girls are assigned than available positions. Use Auto assign or adjust the plan.')
    if state['pending_pack']:
        raise RuleError('Finish opening your pack first.')
    state['phase'] = 'night'
    demand, factor = forecast(state)
    state['night'] = {'elapsed':0,'wave':0,'paused':False,'speed':1,'demand':demand,
                      'demand_factor':factor,'revenue':0,'served':0,'missed':0,'log':[],
                      'earnings':{p:0 for p in state['people']}, 'energy_spent':{p:0 for p in state['people']}}
    record(state,'night_started',pricing=state['pricing'],assignments=copy.deepcopy(state['people']))


def advance(state, catalog, seconds):
    if state['phase'] != 'night' or state['night']['paused']:
        return
    if not isinstance(seconds, (float,int)) or not math.isfinite(seconds) or seconds < 0:
        raise RuleError('Invalid time step.')
    night = state['night']
    night['elapsed'] = min(300, night['elapsed'] + seconds)
    while night['wave'] < min(6, int(night['elapsed']//50)):
        night['wave'] += 1
        rng = random.Random(stable((state['seed'],state['day'],night['wave'])))
        multiplier, acceptance = PRICES[state['pricing']]
        for owner, worker in state['people'].items():
            if worker['role'] not in ('room','lounge'):
                continue
            card = catalog['cards'][worker['card']]
            own = state['owned'][worker['card']]
            strength = .06 + card['rarity']*.015 + own['mastery']*.01
            energy_cost = 8*(1-strength if card['specialty']=='efficiency' else 1)
            if worker['energy'] < energy_cost:
                night['missed'] += 1
                continue
            accept = min(.995, acceptance*night['demand_factor'] + .018*state['facilities']['reception']
                         + (strength*.5 if card['specialty'] in ('service','loyalty') else 0))
            if rng.random() > accept:
                night['missed'] += 1
                continue
            value = (24 if worker['role']=='room' else 14) * multiplier * rng.uniform(.92,1.08)
            value *= 1 + min(.20,worker['xp']//100*.01)
            value *= 1 + (strength if card['specialty']=='tips' else strength*.35)
            value = round(value)
            worker['energy'] = round(worker['energy']-energy_cost,2)
            worker['xp'] += 4
            own['xp'] += 3; own['uses'] += 1
            own['mastery'] = min(5,own['xp']//90)
            night['energy_spent'][owner] += energy_cost
            night['earnings'][owner] += value
            night['revenue'] += value; night['served'] += 1
        message = f"Service round {night['wave']}: ${night['revenue']} earned so far."
        night['log'].append(message)
        record(state,'service_round',wave=night['wave'],revenue=night['revenue'],served=night['served'])
    if night['elapsed'] >= 300:
        settle(state)


def settle(state):
    if state['phase'] != 'night' or state['night']['wave'] != 6:
        raise RuleError('This night is not ready to settle.')
    night = state['night']
    expense = recurring_cost(state)
    training_cost = sum(p['role']=='train' for p in state['people'].values())*15
    expense += training_cost
    for worker in state['people'].values():
        recovery = (70 + state['facilities']['recovery']*6) if worker['role'] in ('rest','train') else (28 + state['facilities']['recovery']*2)
        worker['energy'] = min(100,round(worker['energy'] + recovery,2))
        if worker['role']=='train': worker['xp'] += 22
    state['cash'] += night['revenue']-expense
    report = {'day':state['day'],'revenue':night['revenue'],'expenses':expense,
              'profit':night['revenue']-expense,'served':night['served'],'missed':night['missed'],
              'earnings':night['earnings'],'demand':night['demand']}
    state['reports'] = (state['reports']+[report])[-40:]
    for key, value in [('revenue',night['revenue']),('expenses',expense),('services',night['served'])]:
        state['totals'][key] += value
    record(state,'night_settled',**{k:v for k,v in report.items() if k!='day'})
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


def buy_pack(state,catalog,pack,target=None):
    prep_only(state)
    if state['pending_pack']: raise RuleError('Finish opening your previous pack first.')
    if pack not in PACKS: raise RuleError('Unknown pack.')
    spec = PACKS[pack]
    budget_check(state,spec['price'])
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
    state['cash']-=spec['price'];state['totals']['packs']+=1
    state['pending_pack']={'id':state['pack_counter'],'type':pack,'results':results}
    record(state,'pack_bought',pack=pack,target=target,price=spec['price'],results=results)


def command(original,catalog,action,body=None):
    state=copy.deepcopy(original);body=body or {}
    state['journal']=[]
    if action=='auto': auto_assign(state)
    elif action=='plan':
        prep_only(state)
        owner=body.get('owner');role=body.get('role')
        if owner not in state['people'] or role not in ROLES: raise RuleError('Invalid assignment.')
        state['people'][owner]['role']=role
        record(state,'assignment_changed',owner=owner,role=role)
    elif action=='equip':
        prep_only(state);ident=body.get('card');owner=body.get('owner')
        if owner not in state['people'] or ident not in state['owned'] or catalog['cards'][ident]['owner']!=owner:
            raise RuleError('Equip an owned card of this girl.')
        state['people'][owner]['card']=ident
        record(state,'card_equipped',owner=owner,card=ident)
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
        if kind not in UPGRADES or state['facilities'][kind]>=UPGRADES[kind]['max']: raise RuleError('This facility is at its prototype maximum.')
        cost=upgrade_cost(state,kind);budget_check(state,cost)
        state['cash']-=cost;state['facilities'][kind]+=1
        record(state,'facility_upgraded',facility=kind,cost=cost,level=state['facilities'][kind])
    elif action=='mastery':
        prep_only(state);ident=body.get('card');item=state['owned'].get(ident)
        if not item or item['copies']<2: raise RuleError('Keep the first copy; an extra copy is needed.')
        if item['mastery']>=5: raise RuleError('This card has reached the prototype mastery limit.')
        item['copies']-=1;item['xp']+=30;item['mastery']=min(5,item['xp']//90)
        record(state,'duplicate_used',card=ident,xp=30)
    elif action=='pack': buy_pack(state,catalog,body.get('pack'),body.get('target'))
    elif action=='reveal_done':
        if state['pending_pack']:
            record(state,'pack_reveal_completed',pack_id=state['pending_pack']['id'])
            state['pending_pack']=None
    elif action=='start': start_night(state)
    elif action=='advance': advance(state,catalog,body.get('seconds',0))
    elif action=='finish':
        if state['phase']!='night': raise RuleError('No night is in progress.')
        state['night']['paused']=False;advance(state,catalog,300)
    elif action in ('pause','speed'):
        if state['phase']!='night': raise RuleError('No night is in progress.')
        if action=='pause': state['night']['paused']=body['paused'] if type(body.get('paused')) is bool else not state['night']['paused']
        else:
            speed=body.get('speed')
            if speed not in (1,2,4): raise RuleError('Choose 1x, 2x or 4x speed.')
            state['night']['speed']=speed
    elif action=='recovery':
        prep_only(state)
        if state['cash']>=recurring_cost(state): raise RuleError('Recovery is available when the next night is unaffordable.')
        # A deliberately visible, recoverable setback; no deletion or mandatory reset.
        state['cash']=recurring_cost(state)+100
        for worker in state['people'].values(): worker['energy']=100
        state['day']+=2;state['totals']['recovery_grants']+=1
        record(state,'recovery_break',days=2,cash=state['cash'])
    else: raise RuleError('Unknown game action.')
    return state
