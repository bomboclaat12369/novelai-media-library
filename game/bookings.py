"""Independent booking clocks for new nights. Older nights use meetings.py."""
from __future__ import annotations
import copy
import random
from .catalog import stable
from . import department_ops, meeting_rules as rules, stage_labels
from .meeting_rules import BOOKING_RULES_VERSION

NIGHT_SECONDS = 180
# All pacing ranges below use the original four-minute clock as their unit.
REFERENCE_NIGHT_SECONDS = 240
MIN_BOOKING = 18
REQUEST_COOLDOWN = 12
MAX_CLIENT_REQUESTS = 4
NO_FINISH_CHANCE = .0005
REPEAT_CHANCES = {1: .18, 2: .015}
GROUP_OFFERS = ('second_worker', 'second_client')
CLIENT_EXTRAS = ('anal_extra', 'creampie_extra', 'extension', 'second_round', 'third_round') + GROUP_OFFERS


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
    events = [{'id': f"{state['day']}-venue-{i}", 'kind': kind, 'at': at,
             'until': min(n['duration'], at + 20 * scale), 'choice': None,
             'copy': flavor.event(kind, state, state['day'] - 1)}
            for i, (kind, at) in enumerate(zip(kinds, times))]
    active = [c for c in m.reservations(state) if c.get('operations')]
    # Use the existing two venue decision slots. Favor contracts that have had
    # fewer opportunities so parallel projects and suites each get a turn.
    rows = []
    for dept in ('studio', 'resort'):
        pool = [c for c in active if c['department'] == dept]
        if pool:
            rng.shuffle(pool)
            rows.append(department_ops.offer_for(state, min(pool, key=lambda c: len(c.get('decisions', [])))))
    rows.sort(key=lambda row: row['kind'] != 'resort_private')
    for i, row in enumerate(rows):
        events[i].update(row)
        if row['kind'] == 'resort_private':
            events[i]['at'] = min(events[i]['at'], n['duration'] * .64)
            events[i]['until'] = events[i]['at'] + 20 * scale
    return events


def initialize(state, catalog, labels):
    n = state['night']
    if 'booking_counts' in n:
        return
    if hasattr(labels,'event'):
        for decision in n['decisions']:
            labels.event(decision,catalog,rng_for(state,decision['id'],'offer-text'))
    rooms = [owner for owner, role in n['assignments'].items() if role == 'room']
    n.update(meetings={}, booking_history=[], booking_counts={p: 0 for p in rooms},
             next_arrivals={p: 0 for p in rooms}, next_request_at=0, client_request_count=0)
    process(state, catalog, labels, False)


def extras(meeting, client='original'):
    return {offer['kind'] for offer in meeting['paid_extras'] if offer.get('client','original') == client}


def permissions(meeting, client, cycle):
    allowed=extras(meeting,client)
    if meeting['rules_version']>=6 and str(cycle) not in meeting['outcome_requests']:
        allowed.discard('creampie_extra')
    return allowed


def partner_for(state, meeting):
    night = state['night']
    reserved = {m['group']['partner'] for m in night['meetings'].values()
                if m.get('group',{}).get('partner') and not m.get('completed')}
    lounge_reserved = any(d['kind']=='lounge_round' and d['choice'] is None for d in night['decisions'])
    eligible = [p for p, role in night['assignments'].items() if p!=meeting['owner'] and p not in reserved
                and (role=='rest' or (role=='lounge' and not lounge_reserved)) and state['people'][p]['energy']>=10]
    return min(eligible,key=lambda p:(night['assignments'][p]!='rest',-state['people'][p]['energy'],p),default=None)


def guest_for(meeting, kind, at):
    if kind in ('second_round','third_round'):
        segment = next((s for s in meeting['segments'] if s['slot']=='meeting.finishing' and s['end']==at),{})
    else:
        segment = current_segment(meeting, at) or {}
    return segment.get('client','original')


def later_guest(meeting, client):
    if client=='original':
        return [s for s in meeting['segments'] if s.get('client')=='joining']
    return []


def participants(meeting, segment):
    group=meeting.get('group')
    if not group or segment['start']<group['start']: return {}
    if group['kind']=='second_worker':
        return {'lineup':'two_workers_one_client','workers':segment.get('workers','both'),'clients':'original'}
    clients='both' if segment['slot'] in ('meeting.cleanup','meeting.complete') else segment.get('client','original')
    return {'lineup':'one_worker_two_clients','workers':'original','clients':clients}


def plan(state, meeting, start, end, cycle, *, arrival=False, require_anal=False,
         require_finish=False, previous=None, count=None, client='original', closes=True):
    """Only unentered time is planned; stored labels never get regenerated."""
    rng = rng_for(state, meeting['id'], cycle, len(meeting['paid_extras']), start, 'plan')
    scale = clock_scale(state['night'])
    arrival_time = rng.uniform(1.5, 2.8) * scale if arrival else 0
    cleanup_time = rng.uniform(2, 3.5) * scale if closes else 0
    finishing_time = 0 if meeting['no_finish'] else rng.uniform(3, 4.5) * scale
    active_time = end - start - arrival_time - cleanup_time - finishing_time
    maximum = min(4, max(1, int(active_time / (4 * scale))))
    count = min(maximum, count or rng.randint(1, maximum))
    if require_anal and require_finish:
        count = max(2, count)
    activities = rules.choose_activities(rng, count, permissions(meeting,client,cycle), require_anal=require_anal,
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
    if closes:
        segments.extend([{'slot': 'meeting.cleanup', 'start': end - cleanup_time, 'end': end, 'cycle': cycle},
                         {'slot': 'meeting.complete', 'start': end, 'end': end, 'cycle': cycle}])
    if client=='joining':
        for segment in segments: segment['client']=client
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
    if not stages: return
    client=stages[0].get('client','original')
    decisions=[d for d in state['night']['decisions'] if d.get('meeting_id') == meeting['id']]
    tried = {d['kind'] for d in decisions if d.get('client','original')==client
             and (d['kind']!='creampie_extra' or meeting['rules_version']<6 or d['cycle']==stages[0]['cycle'])}
    kinds = [k for k in ('anal_extra', 'creampie_extra', 'extension') if k not in tried]
    regular=bool(kinds) and rng.random()<chance
    group_rng=rng_for(state,meeting['id'],len(decisions),'group-offer')
    group=(meeting['rules_version']>=6 and not meeting.get('group') and not any(d['kind'] in GROUP_OFFERS for d in decisions)
           and group_rng.random()<.055)
    if not meeting['no_finish'] and (regular or group):
        first = stages[0]
        at = max(state['night']['next_request_at'], first['start'] + (first['end'] - first['start']) * rng.uniform(.25, .75))
        if at < first['end']:
            options=group_rng.sample(GROUP_OFFERS,2) if group else []
            meeting['request_candidate'] = {'at': at, 'kinds': options+(rng.sample(kinds,len(kinds)) if regular else [])}


def request_allowed(state, meeting, kind, extra_time=0):
    from .management import DECISIONS
    n = state['night']; spec = DECISIONS[kind]; at = n['elapsed']
    scale = clock_scale(n)
    client=guest_for(meeting,kind,at)
    funds=meeting.get('joining_funds',0) if client=='joining' else meeting['client_funds']
    if (meeting.get('completed') or meeting['no_finish'] or
            (kind!='second_client' and funds < spec['revenue']) or state['people'][meeting['owner']]['energy'] < spec['energy']):
        return False
    if kind in ('second_round', 'third_round'):
        expected = 1 if kind == 'second_round' else 2
        finishing = [s for s in meeting['segments'] if s['slot']=='meeting.finishing' and s.get('outcome_id') and s.get('client','original')==client and s['end']<=at]
        after=later_guest(meeting,client)
        return (len(finishing)==expected and finishing[-1]['end']==at and extra_time >= MIN_BOOKING*scale
                and (meeting['end'] if after else at)+extra_time<=n['duration'])
    current = current_segment(meeting, at)
    if not current or current['slot'] != 'meeting.stage':
        return False
    if kind in GROUP_OFFERS:
        if meeting['rules_version']<6 or meeting.get('group') or meeting['finish_count'] or any(
                d['kind'] in GROUP_OFFERS and d.get('meeting_id')==meeting['id'] and d['choice'] is not None for d in n['decisions']):
            return False
        remaining=meeting['end']-current['end']
        if kind=='second_worker':
            return remaining>=10*scale and partner_for(state,meeting) is not None
        return remaining>=24*scale
    if kind == 'extension':
        return kind not in extras(meeting,client) and extra_time >= 12 * scale and meeting['end'] + extra_time <= n['duration']
    if kind in permissions(meeting,client,current['cycle']):
        return False
    # Leave an actual unentered activity window; never rewrite the action on screen.
    still_owes_anal = 'anal_extra' in extras(meeting,client) and not any(
        s.get('client','original')==client and s.get('activity_id', '').endswith('__anal') and 'label' in s for s in meeting['segments'])
    needs_two = ((kind == 'creampie_extra' and still_owes_anal) or
                 (kind == 'anal_extra' and str(current['cycle']) in meeting['outcome_requests']))
    following=later_guest(meeting,client)
    end=following[0]['start'] if following else meeting['end']
    return end-current['end'] >= (16 if needs_two else 13)*scale


def offer(state, meeting, kind, catalog=None):
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
    client=guest_for(meeting,kind,at)
    partner=partner_for(state,meeting) if kind=='second_worker' else None
    partner_name=catalog['people'][partner]['name'] if catalog and partner else 'the other worker'
    detail = {
        'anal_extra': 'This client wants the anal extra for the rest of this booking. Switching back is still allowed.',
        'creampie_extra': 'This client wants the creampie extra for the upcoming finish.',
        'extension': 'This client wants more time. This extends the booking without buying another finish.',
        'second_round': 'This client has finished once and wants to pay for a second round.',
        'third_round': 'This client has finished twice and wants to pay for one last round.',
        'second_worker': f'The client wants {partner_name} to join for the rest of the booking. The second worker spends 10 energy.',
        'second_client': 'A second client wants to join this booking. His fee covers his first round. Both clients keep their own extras.',
    }[kind]
    current=current_segment(meeting,at)
    cycle=meeting['finish_count']+1 if kind in ('second_round','third_round') else current['cycle']
    suffix=':joining' if client=='joining' else ''
    if kind=='creampie_extra' and cycle>1 and meeting['rules_version']>=6: suffix+=':'+str(cycle)
    decision = {'id': f"{meeting['id']}:{kind}{suffix}", 'kind': kind, 'at': at, 'until': min(n['duration'], at + 20 * scale),
                'choice': None, 'worker': meeting['owner'], 'meeting_id': meeting['id'],
                'extra_time': extra_time, 'cycle': cycle,
                'copy': {'title': spec['title'], 'detail': detail + f" +${spec['revenue']}, {spec['energy']} energy."}}
    if client=='joining' or kind=='second_client': decision['client']='joining'
    if partner: decision['partner']=partner
    n['decisions'].append(decision); n['client_request_count'] += 1
    n['next_request_at'] = at + REQUEST_COOLDOWN * scale
    meeting['pending_request'] = decision['id']
    return decision


def replan_paid(state, meeting, decision):
    """Keep every entered stage. Reserve the second guest's time when the first buys a change."""
    kind=decision['kind']; at=state['night']['elapsed']; cycle=decision['cycle']
    client=guest_for(meeting,kind,at)
    following=later_guest(meeting,client)
    repeats=kind in ('second_round','third_round')
    if repeats:
        kept=[s for s in meeting['segments'] if s['end']<=at and s['slot']!='meeting.complete']
        start=at
        previous=meeting.get('actual_activity_id')
    else:
        current=current_segment(meeting,at)
        kept=[s for s in meeting['segments'] if s['start']<=current['start']]
        start=current['end']; previous=current['activity_id']
    end=following[0]['start'] if following else meeting['end']
    if repeats or kind=='extension':
        extra=decision['extra_time']
        if repeats and not following: end=at
        end+=extra
        for s in following:
            s['start']+=extra;s['end']+=extra
            if repeats: s['cycle']+=1
        meeting['end']=following[-1]['end'] if following else end
    if kind=='creampie_extra': meeting['outcome_requests'][str(cycle)]='internal_vaginal'
    if kind in GROUP_OFFERS:
        group={'kind':kind,'at':at,'start':start}
        if kind=='second_worker': group['partner']=decision['partner']
        meeting['group']=group
        if kind=='second_client':
            switch=start+(end-start)*.48
            following=plan(state,meeting,switch,end,cycle+1,client='joining')
            end=switch
    owes_anal='anal_extra' in extras(meeting,client) and not any(
        s.get('client','original')==client and s.get('activity_id','').endswith('__anal') for s in kept)
    tail=plan(state,meeting,start,end,cycle,client=client,closes=not following,require_anal=owes_anal,
              require_finish=str(cycle) in meeting['outcome_requests'],previous=previous)
    offset=sum(s['slot']=='meeting.stage' and s['cycle']==cycle for s in kept)
    stages=[s for s in tail if s['slot']=='meeting.stage']
    for s in stages:
        s['stage_index']+=offset; s['stage_count']+=offset
    meeting['segments']=kept+tail+following
    queue_request(state,meeting,stages,rng_for(state,meeting['id'],kind,'next-request'),.20)


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
        if kind=='second_worker' and partner_for(state,meeting)!=decision.get('partner'):
            raise RuleError('The quoted second worker is unavailable.')
        if kind=='second_client':
            meeting['joining_funds']=rng_for(state,meeting['id'],'second-wallet').choice((75,145,215,280))
        wallet='joining_funds' if decision.get('client')=='joining' else 'client_funds'
        meeting[wallet] -= spec['revenue']
        state['people'][meeting['owner']]['energy'] = round(state['people'][meeting['owner']]['energy'] - spec['energy'], 2)
        n['energy_spent'][meeting['owner']] += spec['energy']
        n['revenue'] += spec['revenue']; n['earnings'][meeting['owner']] += spec['revenue']
        receipt={'id':decision['id'],'kind':kind,'at':at,'value':spec['revenue'],'cycle':decision['cycle']}
        if 'client' in decision: receipt['client']=decision['client']
        if 'partner' in decision:
            partner=decision['partner'];receipt['partner']=partner
            state['people'][partner]['energy']-=spec['partner_energy']
            n['energy_spent'][partner]+=spec['partner_energy']
            state['people'][partner]['xp']+=4;state['people'][partner]['skills']['club']+=2
        if kind=='second_client': n['served']+=1
        meeting['paid_extras'].append(receipt)
        replan_paid(state,meeting,decision)
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
            if segment.get('client')=='joining' and not meeting.get('joining_request_planned'):
                meeting['joining_request_planned']=True
                queue_request(state,meeting,[segment],rng_for(state,meeting['id'],'joining-request'),.28)
            facts = {k: segment[k] for k in ('activity_id', 'stage_index', 'stage_count')}
        else:
            facts['activity_id'] = meeting.get('actual_activity_id')
            if slot == 'meeting.finishing':
                segment['activity_id'] = facts['activity_id']
                segment['outcome_id'] = rules.choose_outcome(facts['activity_id'], permissions(meeting,segment.get('client','original'),segment['cycle']),
                    rng_for(state, meeting['id'], segment['cycle'], 'outcome'),
                    meeting['outcome_requests'].get(str(segment['cycle'])),
                    prefer_oral_close=meeting['rules_version'] >= 4, version=meeting['rules_version'])
                meeting['outcome_id'] = segment['outcome_id']
            if meeting.get('outcome_id'):
                facts['outcome_id'] = meeting['outcome_id']
        group=participants(meeting,segment)
        if group.get('lineup')=='two_workers_one_client':
            if slot=='meeting.stage':
                last=index+1<len(meeting['segments']) and meeting['segments'][index+1]['slot']=='meeting.finishing'
                protected=rules.requires_anal_extra(segment['activity_id']) or (last and str(segment['cycle']) in meeting['outcome_requests'])
                actor='original' if protected else rng_for(state,meeting['id'],index,'worker-turn').choice(('original','joining','both','both'))
            elif slot=='meeting.finishing':
                actor=meeting['segments'][index-1].get('workers','original')
            else:
                actor='both'
                facts={}  # Shared cleanup has no joint activity or outcome claim.
            segment['workers']=actor;group['workers']=actor
        if group.get('clients')=='both': facts={}
        if slot == 'meeting.complete' and meeting['no_finish']:
            segment['label'] = {'id': None, 'pack': None,
                'text': "{worker}'s client leaves with blue balls. He's out of time and can't afford more."}
        else:
            segment['label'] = labels.choose(slot, {**facts,**group}, rng_for(state, meeting['id'], index, 'text'), recent)
        if segment['label']['id']:
            recent[:] = (recent + [segment['label']['id']])[-12:]


def process(state, catalog, labels, interactive):
    """Process one exact clock boundary. Stop before a pending continuation."""
    from . import management as m
    from .engine import record, resolve_club_round
    n = state['night']; at = n['elapsed']
    if n.get('suite_contracts'):
        department_ops.advance_private(state, labels)
    scale = clock_scale(n)
    def handle(decision, new=False):
        if not decision:
            return False
        if new and hasattr(labels,'event'):
            labels.event(decision,catalog,rng_for(state,decision['id'],'offer-text'))
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
                client_round=sum(s.get('client','original')==segment.get('client','original') and s['cycle']<=cycle for s in finished)
                if rng_for(state, meeting['id'], cycle, 'repeat').random() < REPEAT_CHANCES.get(client_round, 0):
                    if handle(offer(state, meeting, 'second_round' if client_round==1 else 'third_round',catalog),True):
                        return True
        candidate = meeting.get('request_candidate')
        if candidate and candidate['at'] <= at:
            meeting.pop('request_candidate')
            for kind in candidate['kinds']:
                decision = offer(state, meeting, kind,catalog)
                if decision:
                    if handle(decision,True):
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
        lounge.difference_update(m['group']['partner'] for m in n['meetings'].values()
                                if m.get('group',{}).get('partner') and not m.get('completed'))
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
        if n.get('suite_contracts'):
            for _, booking in department_ops.current_private(state):
                if not booking.get('completed'):
                    boundaries.extend(s['start'] for s in booking['segments'])
        for meeting in n['meetings'].values():
            if 'segments' in meeting and not meeting.get('completed'):
                boundaries.extend(s[key] for s in meeting['segments'] for key in ('start', 'end'))
                if meeting.get('request_candidate'):
                    boundaries.append(meeting['request_candidate']['at'])
        n['elapsed'] = min(t for t in boundaries if t > n['elapsed'])
    if n['elapsed'] >= n['duration']:
        settle(state)
