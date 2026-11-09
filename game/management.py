"""Shared calendar, department contracts and configurable business progression.

All choices here are game rules, never attributes inferred from library photos.
Department reservations are inclusive day ranges on the club's one clock.
"""
from __future__ import annotations
import copy
import random
from .catalog import stable

PROFILES = {
    'host': {'name': 'Welcoming', 'focus': 'club', 'bonus': .04},
    'creator': {'name': 'Methodical', 'focus': 'studio', 'bonus': .04},
    'concierge': {'name': 'Attentive', 'focus': 'resort', 'bonus': .04},
}
PROJECTS = {
    'portrait': {'name': 'Portrait session', 'days': 1, 'fee': 45, 'pay': 205, 'packs': 0, 'energy': 30, 'risk': .05},
    'editorial': {'name': 'Editorial series', 'days': 2, 'fee': 110, 'pay': 480, 'packs': 1, 'energy': 30, 'risk': .12},
    'campaign': {'name': 'Feature campaign', 'days': 3, 'fee': 240, 'pay': 850, 'packs': 1, 'energy': 32, 'risk': .18},
}
STAYS = {
    'retreat': {'name': 'Quiet retreat', 'days': 2, 'fee': 60, 'rate': 155, 'energy': 27, 'expectation': 55},
    'weekend': {'name': 'Signature weekend', 'days': 3, 'fee': 110, 'rate': 190, 'energy': 32, 'expectation': 65},
    'residence': {'name': 'Private residence', 'days': 4, 'fee': 220, 'rate': 240, 'energy': 38, 'expectation': 78},
}
DEPARTMENTS = {
    'studio': {'name': 'Studio', 'price': 650, 'upkeep': 14, 'capacity': 1},
    'resort': {'name': 'Resort', 'price': 1250, 'upkeep': 24, 'capacity': 1},
}
DECISIONS = {
    'booking': {'title': 'A last-minute private booking', 'detail': 'A regular offers $55 for extra attention. A working club host spends 10 energy.',
                'options': [{'id': 'accept', 'label': 'Accept · +$55, −10 energy'}, {'id': 'decline', 'label': 'Keep the prepared schedule'}], 'default': 'decline'},
    'hospitality': {'title': 'Put something back into the team', 'detail': 'A $25 refreshment break restores 12 energy to everyone working. Or keep cash available for tomorrow.',
                    'options': [{'id': 'refresh', 'label': 'Host a break · −$25, +12 energy'}, {'id': 'decline', 'label': 'Keep the cash reserve'}], 'default': 'decline'},
    'promotion': {'title': 'A local showcase invitation', 'detail': 'Spend $35 on a feature to add two reputation and improve demand for the next three nights.',
                  'options': [{'id': 'promote', 'label': 'Book the feature · −$35'}, {'id': 'decline', 'label': 'Grow by word of mouth'}], 'default': 'decline'},
}


def ensure(state):
    """Add schema-2 fields without overwriting any earned schema-1 values."""
    state.setdefault('departments', {'studio': 0, 'resort': 0})
    state.setdefault('contracts', [])
    state.setdefault('contract_counter', 0)
    state.setdefault('reputation', 0)
    state.setdefault('loyalty', 0)
    state.setdefault('promotion_until', 0)
    state.setdefault('saved_plans', {})
    state.setdefault('pack_vouchers', 0)
    state.setdefault('milestones', [])
    state.setdefault('narrative', {'schema': 1, 'characters': {}, 'events': [], 'choices': {}})
    state['totals'].setdefault('studio_completed', 0)
    state['totals'].setdefault('resort_completed', 0)
    state['totals'].setdefault('contract_revenue', 0)
    for owner, worker in state['people'].items():
        worker.setdefault('profile', tuple(PROFILES)[stable(owner) % len(PROFILES)])
        worker.setdefault('skills', {'club': 0, 'studio': 0, 'resort': 0})
        worker.setdefault('training', 'club')
    if state.get('night'):
        state['night'].setdefault('decisions', [])
        state['night'].setdefault('department_revenue', 0)
        state['night'].setdefault('decision_costs', 0)
        state['night'].setdefault('activities', {})
    return state


def reservations(state, owner=None, day=None):
    day = state['day'] if day is None else day
    return [c for c in state['contracts'] if c['status'] == 'active' and c['start'] <= day <= c['end']
            and (owner is None or c['owner'] == owner)]


def assignment(state, owner, day=None):
    booked = reservations(state, owner, day)
    return booked[0]['department'] if booked else state['people'][owner]['role']


def skill_bonus(worker, department):
    profile = PROFILES.get(worker.get('profile'), PROFILES['host'])
    return min(.16, worker.get('skills', {}).get(department, 0) / 1500) + (profile['bonus'] if profile['focus'] == department else 0)


def unlocks(state):
    return {'studio': state['day'] >= 4 and state['totals']['services'] >= 18,
            'resort': bool(state['departments']['studio']) and state['totals']['studio_completed'] >= 2}


def department_upkeep(state):
    return sum(DEPARTMENTS[k]['upkeep'] * level for k, level in state.get('departments', {}).items())


def contract_quote(state, department, kind, owner):
    from .engine import RuleError
    table = PROJECTS if department == 'studio' else STAYS if department == 'resort' else {}
    if kind not in table or owner not in state['people']:
        raise RuleError('Choose a project/package and a member of your team.')
    spec = table[kind]
    worker = state['people'][owner]
    bonus = skill_bonus(worker, department)
    return {**spec, 'quality_bonus': round(bonus, 3),
            'success_chance': round(min(.99, 1 - spec.get('risk', 0) + bonus / 2), 3),
            'estimated_pay': round(spec.get('pay', spec.get('rate', 0) * spec['days']) * (1 + bonus))}


def schedule(state, department, body):
    from .engine import RuleError, budget_check, record
    if not state['departments'].get(department):
        raise RuleError('Open this department in Expansion first.')
    owner, kind = body.get('owner'), body.get('kind')
    spec = contract_quote(state, department, kind, owner)
    start = body.get('start', state['day'])
    if type(start) is not int or not state['day'] <= start <= state['day'] + 14:
        raise RuleError('Schedule within the next fourteen nights.')
    end = start + spec['days'] - 1
    # Check every day, not only today's assignment; future double bookings matter.
    for day in range(start, end + 1):
        if reservations(state, owner, day):
            raise RuleError('This person is already reserved on one of these nights.')
        if sum(c['department'] == department for c in reservations(state, day=day)) >= state['departments'][department]:
            raise RuleError('The department is at capacity on one of these nights.')
    if state['people'][owner]['energy'] < spec['energy']:
        raise RuleError('Rest this person before reserving a new project or stay.')
    budget_check(state, spec['fee'])
    state['cash'] -= spec['fee']
    state['totals']['expenses'] += spec['fee']
    state['contract_counter'] += 1
    state['contracts'].append({'id': state['contract_counter'], 'department': department,
        'kind': kind, 'owner': owner, 'start': start, 'end': end, 'status': 'active',
        'spec': spec, 'quality': 0, 'nights': 0, 'revenue': 0, 'satisfaction': 65,
        'last_day': None, 'card': None})
    record(state, 'contract_scheduled', department=department, project_kind=kind, owner=owner,
           start=start, end=end, cost=spec['fee'], contract=state['contract_counter'])


def command(state, catalog, action, body):
    from .engine import RuleError, prep_only, budget_check, record
    if action == 'decision':
        if state['phase'] != 'night': raise RuleError('This opportunity has ended.')
        decision = next((d for d in state['night']['decisions'] if d['id'] == body.get('decision')), None)
        if not decision or decision.get('choice') or not decision['at'] <= state['night']['elapsed'] < decision['until']:
            raise RuleError('This opportunity has already resolved or is not yet available.')
        resolve_decision(state, decision, body.get('choice'), False)
        return True
    handled = {'schedule', 'cancel_contract', 'department', 'save_plan', 'load_plan', 'delete_plan', 'profile', 'training', 'marketing'}
    if action not in handled: return False
    prep_only(state)
    if action == 'schedule': schedule(state, body.get('department'), body)
    elif action == 'cancel_contract':
        c = next((c for c in state['contracts'] if c['id'] == body.get('contract') and c['status'] == 'active'), None)
        if not c: raise RuleError('Choose an active reservation.')
        # Deposits are sunk; cancellation frees the shared worker immediately.
        c['status'] = 'cancelled'
        record(state, 'contract_cancelled', contract=c['id'], refund=0)
    elif action == 'department':
        kind = body.get('kind')
        if kind not in DEPARTMENTS: raise RuleError('Unknown department.')
        level = state['departments'][kind]
        if not unlocks(state)[kind]: raise RuleError('Complete this department’s milestone first.')
        if level >= 6: raise RuleError('This department has all six positions.')
        price = DEPARTMENTS[kind]['price'] * (level + 1)
        budget_check(state, price)
        state['cash'] -= price; state['departments'][kind] += 1
        record(state, 'department_expanded', department=kind, level=level + 1, cost=price)
    elif action in ('save_plan', 'load_plan', 'delete_plan'):
        name = str(body.get('name', '')).strip()[:40]
        if not name: raise RuleError('Name this plan.')
        if action == 'save_plan':
            if name not in state['saved_plans'] and len(state['saved_plans']) >= 12: raise RuleError('Keep up to twelve plans; replace or remove one first.')
            state['saved_plans'][name] = {'pricing': state['pricing'], 'people': {p: {k: w[k] for k in ('role', 'card', 'training')} for p, w in state['people'].items()}}
        elif name not in state['saved_plans']: raise RuleError('This plan is no longer available.')
        elif action == 'delete_plan': del state['saved_plans'][name]
        else:
            plan = state['saved_plans'][name]
            state['pricing'] = plan['pricing']
            for p, values in plan['people'].items():
                if p in state['people']:
                    state['people'][p].update({k: v for k, v in values.items() if k in ('role','card','training') and (k != 'card' or v in state['owned'])})
        record(state, action, name=name)
    elif action in ('profile', 'training'):
        worker = state['people'].get(body.get('owner'))
        if not worker: raise RuleError('Choose a team member.')
        value = body.get('value')
        if value not in (PROFILES if action == 'profile' else ('club', 'studio', 'resort')): raise RuleError('Choose an available game focus.')
        worker[action] = value
        record(state, action + '_changed', owner=body['owner'], value=value)
    elif action == 'marketing':
        if state['promotion_until'] >= state['day'] + 3: raise RuleError('Your current campaign is still running.')
        budget_check(state, 150)
        state['cash'] -= 150; state['promotion_until'] = state['day'] + 3
        state['reputation'] += 3
        record(state, 'marketing_campaign', cost=150, through=state['promotion_until'])
    return True


def prepare_night(state):
    ensure(state)
    n = state['night']
    first = 'booking' if state['day'] % 2 else 'promotion'
    n['decisions'] = [{'id': f"{state['day']}-{i}", 'kind': kind, 'at': at, 'until': at + 50, 'choice': None}
                      for i, (kind, at) in enumerate(((first, 100), ('hospitality', 200)))]
    n['department_revenue'] = 0; n['decision_costs'] = 0; n['activities'] = {}
    n['assignments'] = {p: assignment(state, p) for p in state['people']}
    for c in reservations(state):
        c['card'] = state['people'][c['owner']]['card']


def resolve_decision(state, decision, choice, automatic=False):
    from .engine import RuleError, record
    spec = DECISIONS[decision['kind']]
    if choice not in [o['id'] for o in spec['options']]: raise RuleError('Choose one of the offered options.')
    n = state['night']
    if choice == 'accept':
        team = [w for p, w in state['people'].items() if assignment(state, p) in ('room', 'lounge') and w['energy'] >= 10]
        if not team: raise RuleError('No club host has the energy for this booking.')
        max(team, key=lambda w: w['energy'])['energy'] -= 10
        n['revenue'] += 55
    if choice in ('refresh', 'promote'):
        cost = 25 if choice == 'refresh' else 35
        if state['cash'] + n['revenue'] - n['decision_costs'] < cost: raise RuleError('Keep enough cash for this decision.')
        n['decision_costs'] += cost
        if choice == 'refresh':
            for p, w in state['people'].items():
                if assignment(state, p) not in ('rest', 'train'): w['energy'] = min(100, w['energy'] + 12)
        else:
            state['reputation'] += 2; state['promotion_until'] = max(state['promotion_until'], state['day'] + 3)
    decision['choice'] = choice; decision['automatic'] = automatic
    n['log'].append(spec['title'] + ': ' + next(o['label'] for o in spec['options'] if o['id'] == choice))
    record(state, 'business_decision', decision=decision['id'], opportunity=decision['kind'], choice=choice, automatic=automatic)


def advance_wave(state, catalog, wave):
    """Called in chronological 50-second steps, independent of browser speed."""
    from .engine import record, draw
    n = state['night']
    for decision in n['decisions']:
        if not decision['choice'] and wave * 50 >= decision['until']:
            resolve_decision(state, decision, DECISIONS[decision['kind']]['default'], True)
    for c in reservations(state):
        worker = state['people'][c['owner']]
        spec = c['spec']; department = c['department']
        energy = spec['energy'] / 6
        card = catalog['cards'][c['card']]
        if card['specialty'] == 'efficiency': energy *= .92
        worked = worker['energy'] >= energy
        if worked:
            worker['energy'] = round(worker['energy'] - energy, 2)
            worker['xp'] += 4; worker['skills'][department] += 3
            own = state['owned'][c['card']]; own['xp'] += 3; own['uses'] += 1; own['mastery'] = min(5, own['xp'] // 90)
        quality = (1 + skill_bonus(worker, department) + (.05 if card['specialty'] in ('service', 'loyalty') else 0)) if worked else .3
        c['quality'] += quality
        n['energy_spent'][c['owner']] += energy if worked else 0
        n['activities'][c['owner']] = {'department': department, 'label': spec['name'], 'status': 'In progress' if worked else 'Tired · reduced quality', 'round': wave}
        if department == 'resort':
            value = round(spec['rate'] / 6 * quality)
            c['revenue'] += value; n['revenue'] += value; n['department_revenue'] += value; n['earnings'][c['owner']] += value
            c['satisfaction'] = max(0, min(100, round(c['satisfaction'] + (2 + skill_bonus(worker, department) * 8 if worked else -9))))
        if wave != 6: continue
        if c['last_day'] == state['day']: continue
        c['last_day'] = state['day']; c['nights'] += 1
        if state['day'] != c['end']: continue
        c['status'] = 'completed'
        if department == 'studio':
            rng = random.Random(stable((state['seed'], 'project', c['id'])))
            success = rng.random() <= spec['success_chance'] and c['quality'] / (6 * c['nights']) >= .65
            payout = round(spec['pay'] * min(1.25, c['quality'] / (6 * c['nights'])) * (1 if success else .55))
            c['revenue'] = payout; c['success'] = success
            n['revenue'] += payout; n['department_revenue'] += payout; n['earnings'][c['owner']] += payout
            if success: state['pack_vouchers'] += spec['packs']
            if success and spec['days'] >= 2 and rng.random() < .2:
                pool = [x for x in catalog['cards'].values() if x['owner'] == c['owner'] and x.get('available')]
                if pool:
                    special = draw(pool, rng)['id']
                    item = state['owned'].setdefault(special, {'copies': 0, 'mastery': 0, 'xp': 0, 'uses': 0, 'acquired_day': state['day']})
                    item['copies'] += 1; item['studio_award'] = True; c['special_card'] = special
            n['log'].append(spec['name'] + f": {'delivered' if success else 'reworked at reduced fee'} · ${payout}")
        else:
            bonus = round(spec['rate'] * .3) if c['satisfaction'] >= spec['expectation'] else 0
            n['revenue'] += bonus; n['department_revenue'] += bonus; c['revenue'] += bonus
            n['earnings'][c['owner']] += bonus
            state['loyalty'] = max(0, min(100, state['loyalty'] + (3 if bonus else -1)))
            n['log'].append(spec['name'] + f": checkout · satisfaction {c['satisfaction']}/100 · bonus ${bonus}")
        state['totals'][department + '_completed'] += 1
        record(state, 'contract_completed', contract=c['id'], department=department, revenue=c['revenue'], satisfaction=c['satisfaction'], special_card=c.get('special_card'))


def after_settle(state, report):
    from .engine import record
    state['totals']['contract_revenue'] += report.get('department_revenue', 0)
    if report['profit'] > 0: state['reputation'] += 1
    if report['served'] >= 6: state['loyalty'] = min(100, state['loyalty'] + 1)
    goals = [('first_service', state['totals']['services'] >= 30),
             ('studio_delivery', state['totals']['studio_completed'] >= 1),
             ('resort_checkout', state['totals']['resort_completed'] >= 1)]
    for ident, done in goals:
        if done and ident not in state['milestones']:
            state['milestones'].append(ident); state['pack_vouchers'] += 1
            record(state, 'milestone_earned', milestone=ident, standard_vouchers=1)
    # One continuing save; repeatable seasonal goals provide later collecting rewards.
    season = state['totals']['services'] // 250
    for number in range(1, season + 1):
        ident = f'bookings-{number * 250}'
        if ident not in state['milestones']:
            state['milestones'].append(ident); state['pack_vouchers'] += 2
            record(state, 'milestone_earned', milestone=ident, standard_vouchers=2)


def derived(state):
    ensure(state)
    return {'unlocks': unlocks(state), 'reservations': reservations(state),
            'assignments': {p: assignment(state, p) for p in state['people']},
            'department_upkeep': department_upkeep(state),
            'department_costs': {k: v['price'] * (state['departments'][k] + 1) for k, v in DEPARTMENTS.items()},
            'quotes': {d: {p: {k: contract_quote(state, d, k, p) for k in table} for p in state['people']}
                       for d, table in (('studio', PROJECTS), ('resort', STAYS))}}
