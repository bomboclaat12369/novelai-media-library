"""Read models and recovery checks for independent booking timelines."""
from __future__ import annotations
import math
from . import bookings, department_ops, meeting_rules as rules, stage_labels


def phase(segment):
    return f"Stage {segment['stage_index']}" if segment['slot'] == 'meeting.stage' else {
        'meeting.arrival': 'Arrival', 'meeting.finishing': 'Finishing',
        'meeting.cleanup': 'Cleanup', 'meeting.complete': 'Complete'}[segment['slot']]


def timeline(meeting, name, elapsed, people=None):
    partner=(people or {}).get(meeting.get('group',{}).get('partner'),{}).get('name','')
    return [{'text': s['label']['text'].replace('{worker}',partner if s.get('workers')=='joining' else name).replace('{partner}',partner),
             'participants':participant_caption(meeting,s,name,partner), 'phase': phase(s), 'cycle': s['cycle'],
             'at': round(s['start'] - meeting['start'], 1),
             'status': ('paused' if meeting.get('pending_request') else 'current')
                       if not meeting.get('completed') and s['start'] <= elapsed < s['end'] else 'done'}
            for s in meeting.get('segments', []) if 'label' in s]


def participant_caption(meeting, segment, name, partner):
    facts=bookings.participants(meeting,segment)
    if not facts: return ''
    if facts['lineup']=='two_workers_one_client':
        return {'both':name+' + '+partner,'original':name,'joining':partner}[facts['workers']]
    if facts['clients']=='both': return 'Both clients'
    return 'Second client' if facts['clients']=='joining' else 'First client'


def views(state, catalog):
    n = state.get('night'); report = state.get('reports', [{}])[-1] if state.get('reports') else {}
    history = n.get('booking_history', []) if n else report.get('booking_history', [])
    current = n.get('meetings', {}) if n else {}
    result = {}
    for owner in state['people']:
        name = catalog['people'][owner]['name']; meeting = current.get(owner, {})
        elapsed = n['elapsed'] if n else report.get('duration', bookings.NIGHT_SECONDS)
        rows = timeline(meeting, name, elapsed, catalog['people'])
        view = {'phase': 'Between bookings', 'text': meeting.get('waiting', 'Waiting for the next client.'),
                'progress': None, 'timeline': rows, 'history': []}
        if rows:
            view.update(phase=rows[-1]['phase'], text=rows[-1]['text'], booking_number=meeting['sequence'],
                        finish_count=meeting['finish_count'],
                        remaining=max(0, math.ceil(meeting['end'] - elapsed)),
                        progress=round(min(1, max(0, (elapsed - meeting['start']) / (meeting['end'] - meeting['start']))) * 100, 2))
            if meeting.get('pending_request'):
                view.update(phase='Client request', text='Waiting for your choice.')
                view['timeline'].append({'text': 'Client request pending', 'phase': 'Request',
                    'cycle': meeting['finish_count'] + 1, 'at': round(elapsed - meeting['start'], 1), 'status': 'current'})
        for past in reversed(history):
            if past['owner'] != owner or past['id'] == meeting.get('id'):
                continue
            view['history'].append({'id': past['id'], 'number': past['sequence'], 'value': past['value'],
                'duration': round(past['end'] - past['start']), 'finish_count': past['finish_count'],
                'reason': past['completion_reason'], 'timeline': timeline(past, name, elapsed, catalog['people'])})
        serving=next((m for m in current.values() if m.get('group',{}).get('partner')==owner and not m.get('completed')),None)
        if serving:
            view.update(phase='Group booking', text='Joined '+catalog['people'][serving['owner']]['name']+' in a private room.')
        if meeting or serving or view['history']:
            result[owner] = view
    return result


def validate(state):
    """Reject invented paid permissions, reordered history and incompatible facts."""
    from .management import DECISIONS
    n = state['night']
    duration = n.get('duration')
    version = n.get('booking_rules_version', 3)
    if duration not in (bookings.REFERENCE_NIGHT_SECONDS, bookings.NIGHT_SECONDS):
        raise ValueError('Invalid booking clock.')
    if type(version) is not int or not 3 <= version <= bookings.BOOKING_RULES_VERSION:
        raise ValueError('Invalid booking rules.')
    def number(value, low=0, high=duration):
        return type(value) in (int, float) and math.isfinite(value) and low <= value <= high
    def integer(value, low=0, high=100):
        return type(value) is int and low <= value <= high
    def label(value, both=False):
        text=value.get('text') if isinstance(value,dict) else None
        if both and isinstance(text,str) and text.count('{partner}')<=1: text=text.replace('{partner}','partner')
        return isinstance(value, dict) and stage_labels.valid_text(text) and (
            value.get('id') is None or isinstance(value['id'], str) and 1 <= len(value['id']) <= 128)
    if type(n['stage_tracking']) is not int or not number(n['elapsed']):
        raise ValueError('Invalid booking clock.')
    rooms = {p for p, role in n['assignments'].items() if role == 'room'}
    if not isinstance(n['meetings'], dict) or set(n['meetings']) - rooms:
        raise ValueError('Invalid room bookings.')
    if set(n['booking_counts']) != rooms or any(not integer(v) for v in n['booking_counts'].values()):
        raise ValueError('Invalid booking counters.')
    if set(n['next_arrivals']) - rooms or any(not number(v, n['elapsed']) for v in n['next_arrivals'].values()):
        raise ValueError('Invalid arrival clock.')
    if not integer(n['client_request_count'], high=bookings.MAX_CLIENT_REQUESTS) or not number(
            n['next_request_at'], high=duration + bookings.REQUEST_COOLDOWN * bookings.clock_scale(n)):
        raise ValueError('Invalid request limits.')
    decisions = {d['id']: d for d in n['decisions']}
    if len(decisions) != len(n['decisions']) or len(decisions) > bookings.MAX_CLIENT_REQUESTS + 2:
        raise ValueError('Invalid request IDs.')
    for d in decisions.values():
        spec = DECISIONS.get(d['kind'])
        if not spec or not number(d['at']) or not number(d['until'], d['at']) or d['at'] == d['until']:
            raise ValueError('Invalid request clock.')
        if d['choice'] is not None and d['choice'] not in [o['id'] for o in spec['options']]:
            raise ValueError('Invalid request choice.')
        if d.get('meeting_id') and (d['worker'] not in rooms or d['kind'] not in bookings.CLIENT_EXTRAS):
            raise ValueError('Invalid request target.')
        if d['kind'] in bookings.GROUP_OFFERS and version<6:
            raise ValueError('Group bookings require the current rules.')
        if d['kind']=='second_worker' and (d.get('partner')==d['worker'] or n['assignments'].get(d.get('partner')) not in ('rest','lounge')):
            raise ValueError('Invalid joining worker.')
        if d['kind'] in department_ops.EVENTS:
            department = 'studio' if d['kind'].startswith('studio_') else 'resort'
            contract = next((c for c in state['contracts'] if c['id'] == d.get('contract')), None)
            if (type(d.get('contract')) is not int or d.get('department') != department or n['assignments'].get(d.get('worker')) != department
                    or not contract or not contract.get('operations') or contract['department'] != department or contract['owner'] != d.get('worker')
                    or not contract['start'] <= state['day'] <= contract['end']):
                raise ValueError('Invalid department request.')
        elif not d.get('meeting_id') and d['kind'] not in ('promotion', 'lounge_round', 'hospitality', 'regular_perk', 'team_meal'):
            raise ValueError('This request needs an actual booking.')
    if not isinstance(n['booking_history'], list) or len(n['booking_history']) > 100:
        raise ValueError('Invalid booking history.')
    history_ids = [m['id'] for m in n['booking_history']]
    if len(set(history_ids)) != len(history_ids):
        raise ValueError('Duplicate completed booking.')
    pending = n['paused'] and any(d['choice'] is None and d['at'] <= n['elapsed'] < d['until'] for d in decisions.values())
    all_meetings = n['booking_history'] + list(n['meetings'].values())
    partner_bookings={}
    for meeting in all_meetings:
        owner = meeting['owner']
        if owner not in rooms:
            raise ValueError('Invalid booking owner.')
        if 'waiting' in meeting:
            if not isinstance(meeting['waiting'], str) or len(meeting['waiting']) > 4096:
                raise ValueError('Invalid waiting message.')
            continue
        if type(meeting['rules_version']) is not int or meeting['rules_version'] != version:
            raise ValueError('Invalid booking rules.')
        if not integer(meeting['sequence'], 1, n['booking_counts'][owner]) or meeting['id'] != f"{state['day']}:booking:{owner}:{meeting['sequence']}":
            raise ValueError('Invalid booking identity.')
        if not number(meeting['start']) or not number(meeting['end'], meeting['start']) or meeting['end'] <= meeting['start']:
            raise ValueError('Invalid booking budget.')
        if not integer(meeting['client_funds'], high=280) or type(meeting['no_finish']) is not bool or not number(meeting['base_value'], high=10000):
            raise ValueError('Invalid client facts.')
        paid = meeting['paid_extras']
        linked = [d for d in decisions.values() if d.get('meeting_id') == meeting['id'] and d.get('worker') == owner and d['choice'] == 'accept']
        if len(paid) != len(linked) or {p['id'] for p in paid} != {d['id'] for d in linked}:
            raise ValueError('Invalid booking payments.')
        for p in paid:
            d = decisions[p['id']]
            if p['kind'] != d['kind'] or p['at'] != d['at'] or p['value'] != DECISIONS[d['kind']]['revenue'] or p['cycle'] != d['cycle']:
                raise ValueError('Invalid paid extra evidence.')
            if p.get('client','original') not in ('original','joining') or p.get('client')!=d.get('client') or p.get('partner')!=d.get('partner'):
                raise ValueError('Wrong extra participant.')
        joins=[p for p in paid if p['kind'] in bookings.GROUP_OFFERS]
        group=meeting.get('group')
        if bool(group)!=bool(joins) or len(joins)>1: raise ValueError('Invalid join receipt.')
        two_clients=bool(group and group['kind']=='second_client')
        if group:
            join=joins[0]
            if group['kind']!=join['kind'] or group['at']!=join['at'] or not number(group['start'],join['at'],meeting['end']):
                raise ValueError('Invalid join time.')
            if group.get('partner')!=join.get('partner') or two_clients!=(join.get('client')=='joining'):
                raise ValueError('Invalid group participants.')
            if not two_clients:
                partner_bookings.setdefault(group['partner'],{})[meeting['id']]=(group['at'],meeting['end'])
        if two_clients and not integer(meeting.get('joining_funds'),high=280):
            raise ValueError('Invalid second client payment.')
        if not two_clients and ('joining_funds' in meeting or any(p.get('client')=='joining' for p in paid)):
            raise ValueError('Missing second client.')
        requested = {str(p['cycle']): 'internal_vaginal' for p in paid if p['kind'] == 'creampie_extra'}
        if meeting['outcome_requests'] != requested:
            raise ValueError('Invalid requested outcome.')
        segments = meeting['segments']
        if not isinstance(segments, list) or not 4 <= len(segments) <= 64 or segments[0]['slot'] != 'meeting.arrival' or [s['slot'] for s in segments[-2:]] != ['meeting.cleanup', 'meeting.complete']:
            raise ValueError('Invalid booking stages.')
        if group and not any(s['slot']=='meeting.stage' and s['start']<=group['at']<s['end']==group['start'] for s in segments):
            raise ValueError('A group must start after the stage in progress at acceptance.')
        at = meeting['start']; actual = None; last_activity = None; outcomes = []; finishes = []; cycle = 1; planned_finishes = []
        clients_by_cycle={1:'original'}
        for i, s in enumerate(segments):
            slot = s['slot']
            client=s.get('client','original')
            if client not in ('original','joining') or (client=='joining' and (not two_clients or s['start']<group['start'])):
                raise ValueError('Invalid stage participant.')
            if slot not in stage_labels.CONDITIONS or not number(s['start']) or not number(s['end']) or abs(s['start'] - at) > 1e-6:
                raise ValueError('Invalid stage clock.')
            if s['end'] < s['start'] or (s['end'] == s['start']) != (slot == 'meeting.complete'):
                raise ValueError('Invalid stage duration.')
            if (slot == 'meeting.arrival' and i != 0) or (slot == 'meeting.cleanup' and i != len(segments) - 2) or (slot == 'meeting.complete' and i != len(segments) - 1):
                raise ValueError('Invalid closing stage order.')
            if not integer(s['cycle'], 1, 6 if two_clients else 3) or s['cycle'] not in (cycle, cycle + 1):
                raise ValueError('Invalid booking cycle.')
            if s['cycle'] > cycle:
                prior=sum(who==client for who in clients_by_cycle.values())
                authorization=(client=='joining' and prior==0 and two_clients) or any(
                    p['kind']=={1:'second_round',2:'third_round'}.get(prior) and p['at']==s['start'] and p.get('client','original')==client for p in paid)
                if segments[i-1]['slot']!='meeting.finishing' or not authorization or ('joining' in clients_by_cycle.values() and client=='original'):
                    raise ValueError('Another cycle needs its own payment.')
                cycle = s['cycle']
                clients_by_cycle[cycle]=client
            if clients_by_cycle[cycle]!=client: raise ValueError('A round changed clients.')
            permissions = {p['kind'] for p in paid if p['at']<=s['start'] and p.get('client','original')==client
                           and (version<6 or p['kind']!='creampie_extra' or p['cycle']==cycle)}
            if slot == 'meeting.stage':
                if not rules.activity_allowed(s['activity_id'], permissions, version=version) or not integer(s['stage_index'], 1, 20) or not integer(s['stage_count'], s['stage_index'], 20):
                    raise ValueError('Invalid or unpaid activity.')
                last_activity = s['activity_id']
                if 'label' in s:
                    actual = last_activity
                if s['cycle'] in planned_finishes:
                    raise ValueError('A continuation needs a new cycle.')
            if slot == 'meeting.finishing':
                eligible = rules.outcome_weights(last_activity, permissions, prefer_oral_close=version >= 4, version=version)
                if not eligible or s['cycle'] in planned_finishes or (str(s['cycle']) in requested and requested[str(s['cycle'])] not in eligible):
                    raise ValueError('Invalid planned finish.')
                planned_finishes.append(s['cycle'])
            if 'label' in s:
                if group and group['kind']=='second_worker' and s['start']>=group['start']:
                    actors=s.get('workers')
                    if actors not in ('original','joining','both'): raise ValueError('Invalid participating workers.')
                    if slot=='meeting.stage' and rules.requires_anal_extra(last_activity) and actors!='original':
                        raise ValueError('The paid activity belongs to the original worker.')
                    if slot=='meeting.finishing' and (actors!=segments[i-1].get('workers') or (str(cycle) in requested and actors!='original')):
                        raise ValueError('Invalid finishing participants.')
                elif 'workers' in s: raise ValueError('This stage has no second worker.')
                if not label(s['label'],bookings.participants(meeting,s).get('workers')=='both') or s['start'] > n['elapsed']:
                    raise ValueError('Invalid saved stage label.')
                if slot == 'meeting.finishing':
                    if s['activity_id'] != last_activity or s['outcome_id'] not in eligible:
                        raise ValueError('Incompatible or unpaid outcome.')
                    if str(s['cycle']) in requested and s['outcome_id'] != requested[str(s['cycle'])]:
                        raise ValueError('The requested outcome was not honored.')
                    outcomes.append(s['outcome_id'])
                    if s['end'] <= n['elapsed']:
                        finishes.append(s)
            elif s['start'] < n['elapsed'] or (s['start'] == n['elapsed'] and not pending):
                raise ValueError('A past stage is missing its saved label.')
            at = s['end']
        if at != meeting['end'] or segments[-1]['start'] != meeting['end'] or meeting.get('actual_activity_id') != actual:
            raise ValueError('Invalid booking progress.')
        if two_clients and 'joining' not in clients_by_cycle.values(): raise ValueError('Missing second guest round.')
        if meeting.get('outcome_id') != (outcomes[-1] if outcomes else None) or not integer(meeting['finish_count'], high=6 if two_clients else 3) or meeting['finish_count'] != len(finishes):
            raise ValueError('Invalid finish history.')
        if not meeting['no_finish'] and planned_finishes != list(range(1, cycle + 1)):
            raise ValueError('Missing planned finish.')
        for client in set(clients_by_cycle.values()):
            if 'anal_extra' in bookings.extras(meeting,client) and not any(
                    s['slot']=='meeting.stage' and s.get('client','original')==client and s['activity_id'].endswith('__anal') for s in segments):
                raise ValueError('The paid activity is missing from this booking.')
        if meeting['no_finish'] and (outcomes or paid or meeting['client_funds'] or any(s['slot'] == 'meeting.finishing' for s in segments)):
            raise ValueError('Invalid time-expired booking.')
        if meeting.get('completed'):
            if meeting['end'] > n['elapsed'] or meeting['value'] != meeting['base_value'] + sum(p['value'] for p in paid):
                raise ValueError('Invalid completed booking.')
            if meeting['completion_reason'] != ('time_expired' if meeting['no_finish'] else 'finished'):
                raise ValueError('Invalid departure reason.')
        if meeting.get('pending_request'):
            d = decisions[meeting['pending_request']]
            if d['choice'] is not None or d.get('meeting_id') != meeting['id'] or not pending:
                raise ValueError('Invalid pending client request.')
    for reservations in partner_bookings.values():
        times=sorted(reservations.values())
        if any(a[1]>b[0] for a,b in zip(times,times[1:])): raise ValueError('Overlapping group bookings.')
    for owner in rooms:
        ordered = {m['id']: m for m in all_meetings if m['owner'] == owner and 'segments' in m}
        rows = sorted(ordered.values(), key=lambda m: m['sequence'])
        if any(a['end'] > b['start'] for a, b in zip(rows, rows[1:])):
            raise ValueError('A room cannot host overlapping bookings.')
    if any(not m.get('completed') for m in n['booking_history']):
        raise ValueError('Incomplete booking in completed history.')


def validate_reports(state):
    for report in state.get('reports', []):
        if 'booking_history' not in report:
            continue
        history = report['booking_history']
        if not isinstance(history, list) or len(history) > 100:
            raise ValueError('Invalid archived booking history.')
        rooms = {p for p, role in report['assignments'].items() if role == 'room'}
        if rooms - state['people'].keys():
            raise ValueError('Unknown archived booking owner.')
        night = {'stage_tracking': 2, 'duration': report['duration'], 'elapsed': report['duration'],
                 'booking_rules_version': report.get('booking_rules_version', 3),
                 'assignments': report['assignments'], 'paused': False, 'decisions': report['decisions'],
                 'booking_history': history, 'meetings': {}, 'next_arrivals': {}, 'next_request_at': 0,
                 'client_request_count': sum(bool(d.get('meeting_id')) for d in report['decisions']),
                 'booking_counts': {p: max((m['sequence'] for m in history if m['owner'] == p), default=0) for p in rooms}}
        validate({**state, 'day': report['day'], 'night': night})
