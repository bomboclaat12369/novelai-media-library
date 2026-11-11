"""Independent booking clocks for new nights. Older nights use meetings.py."""
from __future__ import annotations
import copy
import random
from .catalog import stable
from . import meeting_rules as rules, stage_labels
from .meeting_rules import BOOKING_RULES_VERSION

NIGHT_SECONDS = 180
# All pacing ranges below use the original four-minute clock as their unit.
REFERENCE_NIGHT_SECONDS = 240
MIN_BOOKING = 18
REQUEST_COOLDOWN = 12
MAX_CLIENT_REQUESTS = 4
NO_FINISH_CHANCE = .0005
REPEAT_CHANCES = {1: .18, 2: .015}
CLIENT_EXTRAS = ('anal_extra', 'creampie_extra', 'extension', 'second_round', 'third_round')


def rng_for(state, *parts):
    return random.Random(stable((state['seed'], state['day'], *parts, 'bookings-v3')))


def clock_scale(night):
    return night['duration'] / REFERENCE_NIGHT_SECONDS


def next_wave_at(night):
    return (night['wave'] + 1) * night['duration'] / 6


def prepare_events(state):
    """Venue-wide choices also have saved, randomly selected trigger times."""
    from . import management as m, flavor
    n = state['night']; rng = rng_for(state, 'venue-events')
    scale = clock_scale(n)
    times = sorted(rng.sample(range(28, REFERENCE_NIGHT_SECONDS - 24), 2))
    if times[1] - times[0] < REQUEST_COOLDOWN:
        times[1] = times[0] + REQUEST_COOLDOWN
    times = [at * scale for at in times]
    business = ['promotion']
    if any(m.assignment(state, p) == 'lounge' for p in state['people']):
        business.append('lounge_round')
    kinds = [rng.choice(business), rng.choice(m.TEAM_CHOICES)]
    rng.shuffle(kinds)
    return [{'id': f"{state['day']}-venue-{i}", 'kind': kind, 'at': at,
             'until': min(n['duration'], at + 20 * scale), 'choice': None,
             'copy': flavor.event(kind, state, state['day'] - 1)}
            for i, (kind, at) in enumerate(zip(kinds, times))]


def initialize(state, catalog, labels):
    n = state['night']
    if 'booking_counts' in n:
        return
    rooms = [owner for owner, role in n['assignments'].items() if role == 'room']
    n.update(meetings={}, booking_history=[], booking_counts={p: 0 for p in rooms},
             next_arrivals={p: 0 for p in rooms}, next_request_at=0, client_request_count=0)
    process(state, catalog, labels, False)


def extras(meeting):
    return {offer['kind'] for offer in meeting['paid_extras']}


def plan(state, meeting, start, end, cycle, *, arrival=False, require_anal=False,
         require_finish=False, previous=None, count=None):
    """Only unentered time is planned; stored labels never get regenerated."""
    rng = rng_for(state, meeting['id'], cycle, len(meeting['paid_extras']), start, 'plan')
    scale = clock_scale(state['night'])
    arrival_time = rng.uniform(1.5, 2.8) * scale if arrival else 0
    cleanup_time = rng.uniform(2, 3.5) * scale
    finishing_time = 0 if meeting['no_finish'] else rng.uniform(3, 4.5) * scale
    active_time = end - start - arrival_time - cleanup_time - finishing_time
    maximum = min(4, max(1, int(active_time / (4 * scale))))
    count = min(maximum, count or rng.randint(1, maximum))
    if require_anal and require_finish:
        count = max(2, count)
    activities = rules.choose_activities(rng, count, extras(meeting), require_anal=require_anal,
        require_finish=require_finish, previous=previous, allow_mode_switch=True,
        prefer_oral_close=meeting['rules_version'] >= 4 and not meeting['no_finish'], version=meeting['rules_version'])
    weights = [rng.uniform(.8, 1.4) for _ in activities]
    segments = []; at = start
    if arrival:
        segments.append({'slot': 'meeting.arrival', 'start': at, 'end': at + arrival_time, 'cycle': cycle})
        at += arrival_time
    active_end = end - cleanup_time - finishing_time
    for index, (activity, weight) in enumerate(zip(activities, weights), 1):
        until = at + active_time * weight / sum(weights)
        if index == len(activities):
            until = active_end
        segments.append({'slot': 'meeting.stage', 'start': at, 'end': until, 'cycle': cycle,
                         'stage_index': index, 'stage_count': len(activities), 'activity_id': activity})
        at = until
    if not meeting['no_finish']:
        segments.append({'slot': 'meeting.finishing', 'start': at, 'end': end - cleanup_time, 'cycle': cycle})
    segments.extend([{'slot': 'meeting.cleanup', 'start': end - cleanup_time, 'end': end, 'cycle': cycle},
                     {'slot': 'meeting.complete', 'start': end, 'end': end, 'cycle': cycle}])
    return segments


def start_booking(state, catalog, owner):
    from .engine import resolve_club_round, record
    n = state['night']; at = n['elapsed']; n['next_arrivals'].pop(owner, None)
    scale = clock_scale(n)
    if n['duration'] - at < MIN_BOOKING * scale:
        return
    n['booking_counts'][owner] += 1; sequence = n['booking_counts'][owner]
    ident = f"{state['day']}:booking:{owner}:{sequence}"
    rng = rng_for(state, ident, 'booking')
    result = resolve_club_round(state, catalog, sequence, owners={owner}, rng=rng_for(state, ident, 'payment'))[owner]
    if not result['served']:
        n['meetings'][owner] = {'owner': owner, 'waiting': n['activities'][owner]['status']}
        # Refreshments can restore energy later; exhaustion must not disable
        # the room permanently for the remainder of this night.
        n['next_arrivals'][owner] = min(n['duration'], at + rng.uniform(16, 29) * scale)
        return
    pace = rng.random()
    if pace < .14:
        duration = rng.uniform(18, 27)
    elif pace > .88:
        duration = rng.uniform(52, 68)
    else:
        duration = rng.triangular(28, 51, 37)
    end = min(n['duration'], at + duration * scale)
    no_finish = rng.random() < NO_FINISH_CHANCE
    meeting = {'id': ident, 'owner': owner, 'sequence': sequence, 'rules_version': n.get('booking_rules_version', 3),
               'start': at, 'end': end, 'base_value': result['value'],
               'paid_extras': [], 'finish_count': 0, 'repeat_checked': [], 'outcome_requests': {},
               'no_finish': no_finish, 'client_funds': 0 if no_finish else rng.choices([0, 70, 140, 280], [15, 30, 35, 20])[0]}
    meeting['segments'] = plan(state, meeting, at, meeting['end'], 1, arrival=True)
    stages = [s for s in meeting['segments'] if s['slot'] == 'meeting.stage']
    queue_request(state, meeting, stages, rng, .28)
    n['meetings'][owner] = meeting
    record(state, 'booking_started', meeting=ident, owner=owner, value=result['value'], start=at, end=meeting['end'])


def current_segment(meeting, elapsed):
    return next((s for s in meeting['segments'] if s['start'] <= elapsed < s['end']), None)


def queue_request(state, meeting, stages, rng, chance):
    # Request times belong to a booking, never to the currently viewed room.
    tried = {d['kind'] for d in state['night']['decisions'] if d.get('meeting_id') == meeting['id']}
    kinds = [k for k in ('anal_extra', 'creampie_extra', 'extension') if k not in tried]
    if stages and kinds and not meeting['no_finish'] and rng.random() < chance:
        first = stages[0]
        at = max(state['night']['next_request_at'], first['start'] + (first['end'] - first['start']) * rng.uniform(.25, .75))
        if at < first['end']:
            meeting['request_candidate'] = {'at': at, 'kinds': rng.sample(kinds, len(kinds))}


def request_allowed(state, meeting, kind, extra_time=0):
    from .management import DECISIONS
    n = state['night']; spec = DECISIONS[kind]; at = n['elapsed']
    scale = clock_scale(n)
    if (meeting.get('completed') or meeting['no_finish'] or
            meeting['client_funds'] < spec['revenue'] or state['people'][meeting['owner']]['energy'] < spec['energy']):
        return False
    if kind in ('second_round', 'third_round'):
        expected = 1 if kind == 'second_round' else 2
        finishing = [s for s in meeting['segments'] if s['slot'] == 'meeting.finishing' and s.get('outcome_id')]
        return (meeting['finish_count'] == expected and finishing and finishing[-1]['end'] == at
                and extra_time >= MIN_BOOKING * scale and at + extra_time <= n['duration'])
    current = current_segment(meeting, at)
    if not current or current['slot'] != 'meeting.stage':
        return False
    if kind == 'extension':
        return kind not in extras(meeting) and extra_time >= 12 * scale and meeting['end'] + extra_time <= n['duration']
    if kind in extras(meeting):
        return False
    # Leave an actual unentered activity window; never rewrite the action on screen.
    still_owes_anal = 'anal_extra' in extras(meeting) and not any(
        s.get('activity_id', '').endswith('__anal') and 'label' in s for s in meeting['segments'])
    needs_two = ((kind == 'creampie_extra' and still_owes_anal) or
                 (kind == 'anal_extra' and str(current['cycle']) in meeting['outcome_requests']))
    return meeting['end'] - current['end'] >= (16 if needs_two else 13) * scale


def offer(state, meeting, kind):
    from .management import DECISIONS
    n = state['night']; at = n['elapsed']
    if at < n['next_request_at'] or n['client_request_count'] >= MAX_CLIENT_REQUESTS:
        return None
    rng = rng_for(state, meeting['id'], kind, meeting['finish_count'], 'request')
    scale = clock_scale(n)
    extra_time = 0
    if kind in ('second_round', 'third_round'):
        extra_time = rng.uniform(18, 30) * scale
    elif kind == 'extension':
        extra_time = rng.uniform(15, 25) * scale
    if not request_allowed(state, meeting, kind, extra_time):
        return None
    spec = DECISIONS[kind]
    detail = {
        'anal_extra': 'This client wants the anal extra for the rest of this booking. Switching back is still allowed.',
        'creampie_extra': 'This client wants the creampie extra for the upcoming finish.',
        'extension': 'This client wants more time. This extends the booking without buying another finish.',
        'second_round': 'This client has finished once and wants to pay for a second round.',
        'third_round': 'This client has finished twice and wants to pay for one last round.',
    }[kind]
    decision = {'id': f"{meeting['id']}:{kind}", 'kind': kind, 'at': at, 'until': min(n['duration'], at + 20 * scale),
                'choice': None, 'worker': meeting['owner'], 'meeting_id': meeting['id'],
                'extra_time': extra_time, 'cycle': meeting['finish_count'] + 1,
                'copy': {'title': spec['title'], 'detail': detail + f" +${spec['revenue']}, {spec['energy']} energy."}}
    n['decisions'].append(decision); n['client_request_count'] += 1
    n['next_request_at'] = at + REQUEST_COOLDOWN * scale
    meeting['pending_request'] = decision['id']
    return decision


def resolve_request(state, decision, choice, automatic=False):
    from .engine import RuleError, record
    from .management import DECISIONS
    n = state['night']; meeting = n['meetings'].get(decision['worker'])
    if not meeting or meeting.get('id') != decision['meeting_id'] or decision.get('choice'):
        raise RuleError('This request no longer belongs to an active booking.')
    if choice not in ('accept', 'decline'):
        raise RuleError('Choose one of the offered options.')
    kind = decision['kind']; spec = DECISIONS[kind]; at = n['elapsed']
    if choice == 'accept':
        if not request_allowed(state, meeting, kind, decision['extra_time']):
            raise RuleError('This booking no longer has the time, energy or payment for that extra.')
        meeting['client_funds'] -= spec['revenue']
        state['people'][meeting['owner']]['energy'] = round(state['people'][meeting['owner']]['energy'] - spec['energy'], 2)
        n['energy_spent'][meeting['owner']] += spec['energy']
        n['revenue'] += spec['revenue']; n['earnings'][meeting['owner']] += spec['revenue']
        meeting['paid_extras'].append({'id': decision['id'], 'kind': kind, 'at': at,
                                       'value': spec['revenue'], 'cycle': decision['cycle']})
        if kind in ('second_round', 'third_round'):
            kept = [s for s in meeting['segments'] if s['end'] <= at and s['slot'] != 'meeting.complete']
            meeting['end'] = at + decision['extra_time']
            cycle = meeting['finish_count'] + 1
            tail = plan(state, meeting, at, meeting['end'], cycle, previous=meeting.get('actual_activity_id'))
        else:
            current = current_segment(meeting, at)
            kept = [s for s in meeting['segments'] if s['start'] <= current['start']]
            cycle = current['cycle']
            if kind == 'extension':
                meeting['end'] += decision['extra_time']
            if kind == 'creampie_extra':
                meeting['outcome_requests'][str(cycle)] = 'internal_vaginal'
            owes_anal = 'anal_extra' in extras(meeting) and not any(s.get('activity_id', '').endswith('__anal') for s in kept)
            tail = plan(state, meeting, current['end'], meeting['end'], cycle,
                        require_anal=owes_anal, require_finish=str(cycle) in meeting['outcome_requests'],
                        previous=current['activity_id'])
            # Stage numbers within a cycle include its already-entered actions.
            offset = sum(s['slot'] == 'meeting.stage' and s['cycle'] == cycle for s in kept)
            for segment in tail:
                if segment['slot'] == 'meeting.stage':
                    segment['stage_index'] += offset
                    segment['stage_count'] += offset
        meeting['segments'] = kept + tail
        queue_request(state, meeting, [s for s in tail if s['slot'] == 'meeting.stage'],
                      rng_for(state, meeting['id'], kind, 'next-request'), .20)
        record(state, 'booking_extra_paid', meeting=meeting['id'], worker=meeting['owner'], extra=kind,
               value=spec['revenue'], energy=spec['energy'], end=meeting['end'])
    decision['choice'] = choice; decision['automatic'] = automatic
    meeting.pop('pending_request', None)
    record(state, 'business_decision', decision=decision['id'], opportunity=kind, choice=choice,
           automatic=automatic, worker=meeting['owner'], meeting_id=meeting['id'])


def enter_labels(state, meeting, labels):
    recent = state.setdefault('stage_label_recent', {}).setdefault(meeting['owner'], [])
    for index, segment in enumerate(meeting['segments']):
        if segment['start'] > state['night']['elapsed'] or 'label' in segment:
            continue
        slot = segment['slot']; facts = {}
        if slot == 'meeting.arrival':
            facts['activity_id'] = meeting['segments'][index + 1]['activity_id']
        elif slot == 'meeting.stage':
            meeting['actual_activity_id'] = segment['activity_id']
            facts = {k: segment[k] for k in ('activity_id', 'stage_index', 'stage_count')}
        else:
            facts['activity_id'] = meeting.get('actual_activity_id')
            if slot == 'meeting.finishing':
                segment['activity_id'] = facts['activity_id']
                segment['outcome_id'] = rules.choose_outcome(facts['activity_id'], extras(meeting),
                    rng_for(state, meeting['id'], segment['cycle'], 'outcome'),
                    meeting['outcome_requests'].get(str(segment['cycle'])),
                    prefer_oral_close=meeting['rules_version'] >= 4, version=meeting['rules_version'])
                meeting['outcome_id'] = segment['outcome_id']
            if meeting.get('outcome_id'):
                facts['outcome_id'] = meeting['outcome_id']
        if slot == 'meeting.complete' and meeting['no_finish']:
            segment['label'] = {'id': None, 'pack': None,
                'text': "{worker}'s client leaves with blue balls. He's out of time and can't afford more."}
        else:
            segment['label'] = labels.choose(slot, facts, rng_for(state, meeting['id'], index, 'text'), recent)
        if segment['label']['id']:
            recent[:] = (recent + [segment['label']['id']])[-12:]


def process(state, catalog, labels, interactive):
    """Process one exact clock boundary. Stop before a pending continuation."""
    from . import management as m
    from .engine import record, resolve_club_round
    n = state['night']; at = n['elapsed']
    scale = clock_scale(n)
    def handle(decision):
        if not decision:
            return False
        if interactive:
            n['paused'] = True
            return True
        m.resolve_decision(state, decision, m.DECISIONS[decision['kind']]['default'], True)
        return False
    for decision in n['decisions']:
        if decision['choice'] is None and decision['at'] <= at:
            if not decision.get('meeting_id') and not decision.get('presented'):
                if at < n['next_request_at']:
                    decision['at'] = min(n['duration'] - scale, n['next_request_at'])
                    decision['until'] = min(n['duration'], decision['at'] + 20 * scale)
                    continue
                decision['presented'] = True
            n['next_request_at'] = max(n['next_request_at'], at + REQUEST_COOLDOWN * scale)
            if handle(decision):
                return True
    for owner, meeting in sorted(n['meetings'].items()):
        if 'segments' not in meeting or meeting.get('completed'):
            continue
        finished = [s for s in meeting['segments'] if s['slot'] == 'meeting.finishing' and s['end'] <= at and 'label' in s]
        meeting['finish_count'] = len(finished)
        for segment in finished:
            cycle = segment['cycle']
            if cycle not in meeting['repeat_checked']:
                meeting['repeat_checked'].append(cycle)
                if rng_for(state, meeting['id'], cycle, 'repeat').random() < REPEAT_CHANCES.get(cycle, 0):
                    if handle(offer(state, meeting, 'second_round' if cycle == 1 else 'third_round')):
                        return True
        candidate = meeting.get('request_candidate')
        if candidate and candidate['at'] <= at:
            meeting.pop('request_candidate')
            for kind in candidate['kinds']:
                decision = offer(state, meeting, kind)
                if decision:
                    if handle(decision):
                        return True
                    break
        enter_labels(state, meeting, labels)
        if meeting['end'] <= at:
            meeting['completed'] = True
            meeting['completion_reason'] = 'time_expired' if meeting['no_finish'] else 'finished'
            meeting['value'] = meeting['base_value'] + sum(p['value'] for p in meeting['paid_extras'])
            n['booking_history'].append(copy.deepcopy(meeting))
            n['log'].append(f"{catalog['people'][owner]['name']}: booking {meeting['sequence']} complete · ${meeting['value']}")
            record(state, 'meeting_completed', meeting=copy.deepcopy(meeting), value=meeting['value'])
            gap = rng_for(state, meeting['id'], 'gap').uniform(2, 7) * scale
            n['next_arrivals'][owner] = min(n['duration'], at + gap)
    for owner, due in sorted(list(n['next_arrivals'].items())):
        if due <= at:
            start_booking(state, catalog, owner)
            meeting = n['meetings'].get(owner)
            if meeting and 'segments' in meeting and not meeting.get('completed'):
                enter_labels(state, meeting, labels)
    while n['wave'] < 6 and next_wave_at(n) <= at:
        n['wave'] += 1
        lounge = {p for p, role in n['assignments'].items() if role == 'lounge'}
        resolve_club_round(state, catalog, n['wave'], owners=lounge)
        m.advance_wave(state, catalog, n['wave'])
        record(state, 'service_round', wave=n['wave'], revenue=n['revenue'], served=n['served'])
    return False


def advance(state, catalog, seconds, labels, interactive):
    from .engine import settle
    n = state['night']; target = min(n['duration'], n['elapsed'] + seconds)
    while True:
        if process(state, catalog, labels, interactive):
            return
        if n['elapsed'] >= target:
            break
        boundaries = [target, next_wave_at(n)]
        boundaries.extend(n['next_arrivals'].values())
        boundaries.extend(d['at'] for d in n['decisions'] if d['choice'] is None)
        for meeting in n['meetings'].values():
            if 'segments' in meeting and not meeting.get('completed'):
                boundaries.extend(s[key] for s in meeting['segments'] for key in ('start', 'end'))
                if meeting.get('request_candidate'):
                    boundaries.append(meeting['request_candidate']['at'])
        n['elapsed'] = min(t for t in boundaries if t > n['elapsed'])
    if n['elapsed'] >= n['duration']:
        settle(state)
