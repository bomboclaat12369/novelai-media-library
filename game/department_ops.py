"""Playable production and guest services on the existing six-beat night."""
from __future__ import annotations

import math
import random
from .catalog import stable


SUITE_BOOKING_RULES = 6
BRIEFS = {
    'portrait': ('photo', 'Make a portrait spread with a consistent look.', 'service'),
    'editorial': ('photo', 'Build a fashion story across two shooting nights.', 'loyalty'),
    'campaign': ('photo', 'Deliver a coordinated advertising campaign.', 'tips'),
    'solo_film': ('film', 'Direct a solo adult film from blocking through the final cut.', 'efficiency'),
    'feature_film': ('film', 'Shoot a multi-scene adult feature. A co-star can share the lead.', 'service'),
    'commission': ('photo', 'Shoot a four-night print campaign for a single client. On set, the client may offer cash for one of the delivery vouchers.', 'efficiency'),
}
STAGES = {
    'photo': ('Set the lighting', 'Block the poses', 'Shoot the first look', 'Change the setup', 'Shoot the selects', 'Review the contact sheet'),
    'film': ('Light the set', 'Block the scene', 'Roll the first take', 'Change the camera setup', 'Shoot the pickups', 'Review the footage'),
    'resort': ('Welcome the guest', 'Prepare the suite', 'Host the afternoon service', 'Check in with the guest', 'Host the evening service', 'Close the guest folio'),
    'commission': ('Review the client brief', 'Light the campaign set', 'Shoot the lead image', 'Photograph a second layout', 'Choose the print selects', 'Review the client proofs'),
    'vip': ('Welcome the VIP guest', 'Walk through the suite', 'Host a private lunch', 'Review guest preferences', 'Host the evening reception', 'Review the guest folio'),
}
SERVICE_PLANS = {
    'standard': 'Standard service', 'privacy': 'Quiet suite', 'dining': 'Private dining', 'leisure': 'Hosted activities',
}
PREFERENCES = {'privacy': 'Peace and privacy', 'dining': 'Good food', 'leisure': 'Things to do'}


def event_rule(title, detail, accept, **effects):
    return {'title': title, 'detail': detail, 'options': [{'id': 'accept', 'label': accept},
            {'id': 'decline', 'label': 'Keep the original plan'}], 'default': 'decline', **effects}


EVENTS = {
    'studio_pickup': event_rule('Shoot another look?', 'Use 6 lead energy for a pickup. It improves the material and adds 5 points to the delivery chance.',
                                'Shoot the pickup · 6 energy', energy=6),
    'studio_press': event_rule('Release a preview?', 'Use 5 lead energy on a publicity preview. Gain 2 reputation and promote the Club through the next two nights.',
                               'Make the preview · 5 energy', energy=5, reputation_gain=2, promotion_nights=2),
    'studio_cut': event_rule('Deliver an alternate cut?', 'Use 7 lead energy to edit a second cut. The distributor adds $55 when the project delivers.',
                             'Cut a second version · 7 energy', energy=7, extra_fee=55),
    'studio_cover': event_rule('Take the cover commission?', 'The magazine adds $90 for a cover-ready photo set. Its stricter brief lowers delivery odds by 12 percentage points. Rework earns no cover bonus.',
                               'Shoot for the cover', success_fee=90, chance_cost=12),
    'studio_license': event_rule('License the campaign photos?', 'The client offers $80 when the project settles, including on rework. A successful delivery will earn one Standard pack voucher instead of two.',
                                 'License the photos', extra_fee=80, voucher_cost=1),
    'resort_request': event_rule('A guest has a request', 'Spend $18 on a personal request to raise guest satisfaction by 12 points.',
                                 'Arrange it · $18', cost=18, satisfaction_gain=12),
    'resort_private': event_rule('A guest wants a private booking', 'The guest offers $65 for a private booking with their host. It costs 8 energy. Any overlapping suite service earns less and costs 2 satisfaction.',
                                 'Take the booking · +$65 at completion', revenue=65, energy=8),
    'resort_farewell': event_rule('Arrange a VIP farewell?', 'Put $60 toward a farewell reception. The guest pays an extra $160 at checkout if satisfaction reaches 90/100.',
                                  'Arrange the farewell · $60', cost=60, success_fee=160, satisfaction_target=90),
}


def cast(contract):
    partner = contract['spec'].get('costar')
    return (contract['owner'], partner) if partner else (contract['owner'],)


def reservation_nights(contract):
    """Completed shifts keep their recorded dates when recovery moves the remaining work."""
    calendar = range(contract['start'], contract['end'] + 1)
    if not contract.get('operations'):
        return list(calendar)
    completed = [row['day'] for row in contract.get('work_log', ()) if row['wave'] == 6]
    return completed + list(calendar[contract['nights']:])


def returning_guests(state):
    latest = {}
    for contract in state['contracts']:
        guest = contract.get('guest')
        if guest and contract['status'] != 'cancelled':
            latest[guest['id']] = contract
    return {key: c['guest'] for key, c in latest.items() if c['status'] == 'completed' and c.get('return_invited')}


def guest_offer(state, requested=None):
    from .engine import RuleError
    if requested:
        previous = returning_guests(state).get(requested)
        if not previous:
            raise RuleError('That guest is no longer available to return.')
        return {**previous, 'visit': previous['visit'] + 1}
    number = state['contract_counter'] + 1
    rng = random.Random(stable((state['seed'], number, 'resort-guest')))
    first = rng.choice(('Adrian', 'Alex', 'Cameron', 'Drew', 'Elliot', 'Jesse', 'Jordan', 'Morgan', 'Robin', 'Sam'))
    last = rng.choice(('Banks', 'Blair', 'Ellis', 'Ford', 'Hayes', 'Lane', 'Reed', 'Shaw', 'Vale', 'Wells'))
    return {'id': f'guest-{number}', 'name': f'{first} {last}', 'preference': rng.choice(tuple(PREFERENCES)), 'visit': 1}


def configure_quote(state, dept, kind, owner, spec, options):
    from .engine import RuleError
    if dept == 'studio':
        medium, brief, specialty = BRIEFS[kind]
        costar = options.get('costar') or None
        if costar and (kind != 'feature_film' or costar == owner or costar not in state['people']):
            raise RuleError('Choose a different team member as the feature co-star.')
        spec.update(medium=medium, brief=brief, preferred_specialty=specialty)
        if costar:
            spec.update(costar=costar, fee=spec['fee'] + 35 * spec['days'], pay=round(spec['pay'] * 1.3))
    else:
        plan = options.get('service_plan') or 'standard'
        if plan not in SERVICE_PLANS:
            raise RuleError('Choose an available service plan.')
        guest = guest_offer(state, options.get('guest'))
        spec.update(service_plan=plan, guest_offer=guest)
        if plan == 'privacy':
            spec['energy'] -= 3
            spec['rate'] -= 6
        elif plan == 'dining':
            spec['fee'] += 12 * spec['days']
        elif plan == 'leisure':
            spec['energy'] += 4
            spec['rate'] += 10
        if guest['visit'] > 1:
            spec['rate'] += 10


def stage_name(contract, day, wave):
    medium = contract['spec'].get('medium', 'photo') if contract['department'] == 'studio' else 'resort'
    if day == contract['end'] and wave == 6:
        return {'photo': 'Deliver the selects', 'film': 'Deliver the final cut', 'resort': 'Check the guest out'}[medium]
    if medium == 'resort' and day > contract['start'] and wave == 1:
        return 'Review the guest itinerary'
    return STAGES.get(contract['kind'], STAGES[medium])[wave-1]


def delivery_chance(contract):
    return min(.99, max(0, contract['spec']['success_chance'] + contract.get('chance_bonus', 0) - contract.get('chance_penalty', 0)))


def event_kinds(contract):
    if contract['department'] == 'resort':
        standard = ('resort_request', 'resort_private')
        return standard + ('resort_farewell',) if contract['kind'] == 'vip' else standard
    if contract['spec']['medium'] == 'film':
        return ('studio_cut', 'studio_press', 'studio_pickup')
    standard = ('studio_pickup', 'studio_press', 'studio_cover')
    return standard + ('studio_license',) if contract['kind'] == 'commission' else standard


def valid_recorded_event(contract, kind):
    # Older releases used different rotations for the original department decisions.
    if kind in ('studio_license', 'resort_farewell'):
        return kind in event_kinds(contract)
    return kind in EVENTS and kind.startswith(contract['department'] + '_')


def offer_for(state, contract):
    day = state['day']
    choices = event_kinds(contract)
    offset = stable((state['seed'], contract['id'], 'department-offer'))
    kind = choices[(offset + contract['nights']) % len(choices)]
    spec = EVENTS[kind]
    title, detail = spec['title'], spec['detail']
    if kind == 'resort_request':
        guest = contract['guest']
        request = {'privacy': 'a private breakfast in the suite', 'dining': 'a tasting menu', 'leisure': 'an evening excursion'}[guest['preference']]
        detail = f"{guest['name']} asks for {request}. It costs $18 and raises satisfaction by 12 points."
    if kind == 'resort_private':
        title = contract['guest']['name'] + ' wants a private booking'
    return {'id': f"{day}-department-{contract['id']}", 'kind': kind, 'contract': contract['id'],
            'worker': contract['owner'], 'department': contract['department'], 'choice': None,
            'contract_title': contract['spec']['name'], 'guest_name': contract.get('guest', {}).get('name'),
            'copy': {'title': title, 'detail': detail}}


def resolve_offer(state, decision, choice, automatic):
    from .engine import RuleError, record
    n = state['night']
    c = next((row for row in state['contracts'] if row['id'] == decision['contract']), None)
    kind = decision['kind']
    if not c or c['status'] != 'active' or state['day'] not in reservation_nights(c) or decision['worker'] != c['owner'] or not valid_recorded_event(c, kind):
        raise RuleError('This contract is no longer in progress.')
    rule = EVENTS[kind]
    worker = state['people'][c['owner']]
    result = 'Kept the original plan'
    if choice == 'accept':
        energy, cost = rule.get('energy', 0), rule.get('cost', 0)
        if worker['energy'] < energy:
            raise RuleError(f'The host needs {energy} energy for this option.')
        if state['cash'] + n['revenue'] - n['decision_costs'] < cost:
            raise RuleError('The till cannot cover this request.')
        worker['energy'] -= energy
        n['energy_spent'][c['owner']] += energy
        n['decision_costs'] += cost
        if kind == 'studio_pickup':
            c['quality'] += .8
            c['chance_bonus'] = min(.15, c.get('chance_bonus', 0) + .05)
            result = 'Pickup shot · better material and delivery odds'
        elif kind == 'studio_press':
            state['reputation'] += rule['reputation_gain']
            through = state['day'] + rule['promotion_nights']
            state['promotion_until'] = max(state['promotion_until'], through)
            result = 'Preview released · Club publicity through night ' + str(through)
        elif kind == 'studio_cut':
            c['delivery_extra'] = c.get('delivery_extra', 0) + rule['extra_fee']
            result = 'Alternate cut commissioned · +$55 on delivery'
        elif kind == 'studio_cover':
            c['cover_fee'] = rule['success_fee']
            c['chance_penalty'] = rule['chance_cost'] / 100
            result = 'Cover commissioned · $90 on successful delivery'
        elif kind == 'studio_license':
            c['license_fee'] = rule['extra_fee']
            c['delivery_vouchers'] = c['spec']['packs'] - rule['voucher_cost']
            result = 'Photos licensed · $80 at settlement and one voucher on successful delivery'
        elif kind == 'resort_request':
            before = c['satisfaction']
            c['satisfaction'] = min(100, before + rule['satisfaction_gain'])
            c['service_cost'] = c.get('service_cost', 0) + cost
            result = f"Guest request fulfilled · {before} → {c['satisfaction']} satisfaction"
        elif kind == 'resort_farewell':
            c['service_cost'] = c.get('service_cost', 0) + cost
            c['farewell_fee'] = rule['success_fee']
            c['farewell_target'] = rule['satisfaction_target']
            result = 'Farewell reserved · $60 spent, $160 at checkout with 90 satisfaction'
        elif kind == 'resort_private':
            start_private(state, c, decision)
            result = 'Private booking started · $65 payable on completion'
    decision.update(choice=choice, automatic=automatic, result=result)
    c.setdefault('decisions', []).append({'id': decision['id'], 'day': state['day'], 'elapsed': n['elapsed'],
                                         'kind': kind, 'choice': choice, 'result': result})
    n['log'].append(c['spec']['name'] + ' · ' + result)
    record(state, 'department_decision', contract=c['id'], decision=decision['id'], opportunity=kind,
           choice=choice, automatic=automatic, worker=c['owner'], result=result)


def start_private(state, contract, decision):
    from . import bookings
    n = state['night']
    start = n['elapsed']
    rng = bookings.rng_for(state, decision['id'], 'suite-duration')
    end = min(n['duration'], start + rng.uniform(27, 42) * bookings.clock_scale(n))
    meeting = {'id': decision['id'] + '-private', 'owner': contract['owner'], 'day': state['day'],
               'start': start, 'end': end, 'rules_version': SUITE_BOOKING_RULES,
               'no_finish': False, 'paid_extras': [], 'outcome_requests': {}, 'value': EVENTS['resort_private']['revenue']}
    meeting['segments'] = bookings.plan(state, meeting, start, end, 1, arrival=True)
    contract.setdefault('private_bookings', []).append(meeting)
    n.setdefault('suite_contracts', []).append(contract['id'])


def current_private(state):
    ids = state['night'].get('suite_contracts', ())
    if not ids:
        return
    for c in state['contracts']:
        if c['id'] in ids:
            yield c, c['private_bookings'][-1]


def advance_private(state, labels):
    from . import bookings
    from .engine import record
    n = state['night']
    for c, meeting in current_private(state):
        if meeting.get('completed'):
            continue
        bookings.enter_labels(state, meeting, labels)
        if n['elapsed'] < meeting['end']:
            continue
        meeting['completed'] = True
        value = meeting['value']
        c['revenue'] += value
        n['revenue'] += value
        n['department_revenue'] += value
        n['earnings'][c['owner']] += value
        n['log'].append(f"{c['guest']['name']} · private booking complete · +${value}")
        record(state, 'resort_private_completed', contract=c['id'], booking=meeting['id'], worker=c['owner'], value=value)


def validate_private(c, state):
    from . import bookings, meeting_rules, stage_labels
    visits = c.get('private_bookings', [])
    if not isinstance(visits, list) or len(visits) > c['spec']['days']:
        raise ValueError('Invalid suite booking history.')
    accepted = {d['id']:d for d in c.get('decisions', []) if d['kind'] == 'resort_private' and d['choice'] == 'accept'}
    ids = set()
    for m in visits:
        ident = m['id']
        decision = accepted.get(ident.removesuffix('-private')) if isinstance(ident, str) and ident.endswith('-private') else None
        if not decision or decision['day'] != m['day'] or ident in ids or m['owner'] != c['owner'] or m['value'] != 65:
            raise ValueError('Invalid private booking receipt.')
        ids.add(ident)
        if m['rules_version'] != SUITE_BOOKING_RULES or m['no_finish'] is not False or m['paid_extras'] != [] or m['outcome_requests'] != {}:
            raise ValueError('Invalid suite booking terms.')
        segments = m['segments']
        if not isinstance(segments, list) or not 5 <= len(segments) <= 8:
            raise ValueError('Invalid suite stage count.')
        slots = [s['slot'] for s in segments]
        if slots != ['meeting.arrival']+['meeting.stage']*(len(slots)-4)+['meeting.finishing','meeting.cleanup','meeting.complete']:
            raise ValueError('Invalid suite stage sequence.')
        start = m['start']
        if not 0 <= start < m['end'] <= bookings.NIGHT_SECONDS:
            raise ValueError('Invalid private booking time.')
        last_activity = None
        missing_label = False
        for s in segments:
            if s['start'] != start or not start <= s['end'] <= m['end'] or s['cycle'] != 1:
                raise ValueError('Invalid suite stage timing.')
            if (s['end'] == start) != (s['slot'] == 'meeting.complete'):
                raise ValueError('Invalid suite stage duration.')
            start = s['end']
            if s['slot'] == 'meeting.stage':
                last_activity = s['activity_id']
                if last_activity not in stage_labels.catalog()['activities'] or meeting_rules.requires_anal_extra(last_activity):
                    raise ValueError('Invalid suite activity.')
            label = s.get('label')
            if label is None:
                missing_label = True
            elif missing_label or not isinstance(label, dict) or not stage_labels.valid_text(label.get('text')):
                raise ValueError('Invalid suite label.')
            if s['slot'] == 'meeting.finishing' and label and s.get('outcome_id') not in meeting_rules.outcome_weights(last_activity, (), version=m['rules_version']):
                raise ValueError('Invalid suite finish.')
        if start != m['end'] or m.get('completed') and missing_label:
            raise ValueError('Incomplete suite booking receipt.')
        if not m.get('completed') and (m['day'] != state['day'] or c['id'] not in (state.get('night') or {}).get('suite_contracts', [])):
            raise ValueError('Missing active suite booking.')
    if len(accepted) != len(visits):
        raise ValueError('An accepted private booking is missing.')


def validate_contract(c, state):
    if 'operations' not in c:
        return
    if type(c['operations']) is not int or c['operations'] != 1:
        raise ValueError('Unknown department rules.')
    spec = c['spec']
    if c['department'] == 'studio':
        if spec['medium'] != BRIEFS[c['kind']][0] or len(set(cast(c))) != len(cast(c)) or any(p not in state['people'] for p in cast(c)):
            raise ValueError('Invalid production cast.')
        if spec.get('costar') and c['kind'] != 'feature_film':
            raise ValueError('Invalid co-star.')
    else:
        guest = c['guest']
        if not isinstance(guest['id'], str) or not isinstance(guest['name'], str) or guest['preference'] not in PREFERENCES or type(guest['visit']) is not int or guest['visit'] < 1 or spec['service_plan'] not in SERVICE_PLANS:
            raise ValueError('Invalid resort guest.')
    work = c.get('work_log', [])
    if not isinstance(work, list) or len(work) > 6 * spec['days'] or any(type(row['day']) is not int or type(row['wave']) is not int or not 1 <= row['wave'] <= 6 or type(row['worked']) is not bool or not isinstance(row['stage'], str) for row in work):
        raise ValueError('Invalid department work log.')
    beats = [(row['day'],row['wave']) for row in work]
    if beats != sorted(set(beats)):
        raise ValueError('Invalid shift history order.')
    nights = reservation_nights(c)
    if (c['nights'] > spec['days'] or len(nights) != spec['days'] or nights != sorted(set(nights)) or nights[0] < 1 or nights[-1] != c['end']
            or any(day > c['start'] + i for i, day in enumerate(nights))):
        raise ValueError('Invalid reservation nights.')
    decisions = c.get('decisions', [])
    if not isinstance(decisions,list) or len(decisions) > spec['days'] or len({d['id'] for d in decisions}) != len(decisions):
        raise ValueError('Invalid department decisions.')
    for decision in decisions:
        if not valid_recorded_event(c, decision['kind']) or decision['choice'] not in ('accept','decline') or not isinstance(decision['result'], str):
            raise ValueError('Invalid department decision.')
    for kind, fields in (('studio_license', ('license_fee', 'delivery_vouchers')), ('resort_farewell', ('farewell_fee', 'farewell_target'))):
        offers = [d for d in decisions if d['kind'] == kind]
        accepted = bool(offers and offers[0]['choice'] == 'accept')
        if len(offers) > 1 or any((key in c) != accepted for key in fields):
            raise ValueError('Invalid premium booking terms.')
        if accepted and any(type(c[key]) is not int or c[key] < 0 for key in fields):
            raise ValueError('Invalid premium booking amounts.')
    if 'delivery_vouchers' in c and not 0 <= c['delivery_vouchers'] < spec['packs']:
        raise ValueError('Invalid licensed delivery voucher count.')
    if 'farewell_target' in c and not 0 < c['farewell_target'] <= 100:
        raise ValueError('Invalid farewell satisfaction target.')
    settled_farewell = c['status'] == 'completed' and 'farewell_fee' in c
    if ('farewell_bonus_paid' in c) != settled_farewell:
        raise ValueError('Invalid farewell checkout receipt.')
    if settled_farewell and (type(c['farewell_bonus_paid']) is not int or c['farewell_bonus_paid'] != (c['farewell_fee'] if c['satisfaction'] >= c['farewell_target'] else 0)):
        raise ValueError('Invalid farewell bonus.')
    for row in [*work, *decisions]:
        elapsed = row.get('elapsed', 0)
        if row['day'] not in nights or type(elapsed) not in (int, float) or not 0 <= elapsed <= 180:
            raise ValueError('Invalid department history time.')
    if c['department'] == 'resort':
        validate_private(c, state)
    for key in ('delivery_extra','service_cost','chance_bonus','chance_penalty','cover_fee','cover_bonus_paid'):
        value = c.get(key, 0)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid department receipt.')
