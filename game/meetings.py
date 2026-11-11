"""Saved, game-owned timelines inside the existing private-room round budget."""
from __future__ import annotations
import copy
import math
import random
from .catalog import stable
from . import flavor, stage_labels, meeting_rules

ROUND_SECONDS = 50
MAX_STAGES = 4


def identity(state, owner, wave):
    return f"{state['day']}:{wave}:{owner}"


def linked_offers(night, owner, ident):
    return [d for d in night['decisions'] if d.get('meeting_id') == ident
            and d.get('worker') == owner and d.get('choice') == 'accept']


def eligible_outcomes(activity, extras=(), version=meeting_rules.VERSION):
    """Version old saved meetings separately from newly selected game facts."""
    if type(version) is not int or version not in (1, meeting_rules.VERSION):
        raise ValueError('Unsupported meeting rules version.')
    if version == meeting_rules.VERSION:
        return tuple(sorted(meeting_rules.outcome_weights(activity, extras, version=version)))
    # Version 1 applies only to already-saved plans. Keep their committed facts
    # and future seeded outcome stable; all newly created meetings use v2.
    if activity not in stage_labels.catalog(original=True)['activities']:
        return ()
    outcomes = [key for key in stage_labels.catalog()['outcomes'] if key.startswith('external_')]
    if activity.endswith('__vaginal'):
        outcomes.append('internal_vaginal')
    if activity.endswith('__anal'):
        outcomes.append('internal_anal')
    if activity in ('blowjob__worker_gives', 'deepthroat__worker_gives', 'sixty_nine__shared'):
        outcomes.append('oral_mouth')
    if activity == 'deepthroat__worker_gives':
        outcomes.append('oral_throat')
    return tuple(sorted(outcomes))


def begin_round(state, results, force=False):
    n = state['night']; wave = n['wave'] + 1
    n['meeting_round'] = wave; n['meetings'] = {}
    for owner, role in n['assignments'].items():
        if role != 'room':
            continue
        ident = identity(state, owner, wave)
        offers = linked_offers(n, owner, ident)
        kinds = {d['kind'] for d in offers}
        result = results[owner]
        if not result['served'] and not offers:
            n['meetings'][owner] = {'id': ident, 'owner': owner, 'round': wave,
                                   'rules_version': meeting_rules.VERSION,
                                   'waiting': flavor.activity(result['reason'], state, owner, wave)}
            continue
        # Independent random stream: stage count, activities and duration cannot
        # consume booking, payment, energy or card-progression random draws.
        rng = random.Random(stable((state['seed'], ident, 'meeting-timing-v2')))
        count = rng.randint(1, MAX_STAGES)
        activity_rng = random.Random(stable((state['seed'], ident, 'meeting-activities-v2')))
        activities = meeting_rules.choose_activities(activity_rng, count, kinds, version=meeting_rules.VERSION)
        count = len(activities)
        start = (wave - 1) * ROUND_SECONDS if force else max((wave - 1) * ROUND_SECONDS, n['elapsed'])
        end = wave * ROUND_SECONDS
        scale = (end - start) / ROUND_SECONDS
        arrival, finishing, cleanup = (rng.uniform(2, 4), rng.uniform(5, 8), rng.uniform(3, 5))
        active = ROUND_SECONDS - arrival - finishing - cleanup
        weights = [rng.uniform(.8, 1.4) for _ in activities]
        at = start + arrival * scale
        segments = [{'slot': 'meeting.arrival', 'start': start, 'end': at}]
        for index, (activity, weight) in enumerate(zip(activities, weights), 1):
            until = at + (6 + (active - 6 * count) * weight / sum(weights)) * scale
            if index == count:
                until = end - (finishing + cleanup) * scale
            segments.append({'slot': 'meeting.stage', 'stage_index': index,
                             'stage_count': count, 'activity_id': activity, 'start': at, 'end': until})
            at = until
        segments.extend([
            {'slot': 'meeting.finishing', 'start': at, 'end': end - cleanup * scale},
            {'slot': 'meeting.cleanup', 'start': end - cleanup * scale, 'end': end},
            {'slot': 'meeting.complete', 'start': end, 'end': end},
        ])
        n['meetings'][owner] = {'id': ident, 'owner': owner, 'round': wave,
            'rules_version': meeting_rules.VERSION,
            'start': start, 'end': end, 'segments': segments,
            'offers': [d['id'] for d in offers],
            'requested_outcome': 'internal_vaginal' if 'creampie_extra' in kinds else None}


def advance(state, elapsed, labels):
    n = state['night']
    for owner, meeting in n.get('meetings', {}).items():
        if 'waiting' in meeting:
            continue
        version = meeting.get('rules_version', 1)
        extras = {d['kind'] for d in linked_offers(n, owner, meeting['id'])}
        recent = state.setdefault('stage_label_recent', {}).setdefault(owner, [])
        for index, segment in enumerate(meeting['segments']):
            if segment['start'] > elapsed or 'label' in segment:
                continue
            slot = segment['slot']
            if slot == 'meeting.arrival':
                facts = {'activity_id': meeting['segments'][1]['activity_id']}
            elif slot == 'meeting.stage':
                if version == meeting_rules.VERSION and not meeting_rules.activity_allowed(segment['activity_id'], extras, version=version):
                    raise ValueError('This activity requires a paid extra for this meeting.')
                meeting['actual_activity_id'] = segment['activity_id']
                facts = {key: segment[key] for key in ('activity_id', 'stage_index', 'stage_count')}
            else:
                facts = {'activity_id': meeting.get('actual_activity_id')}
                if slot == 'meeting.finishing':
                    eligible = eligible_outcomes(facts['activity_id'], extras, version)
                    rng = random.Random(stable((state['seed'], meeting['id'], f'meeting-outcome-v{version}')))
                    requested = meeting.get('requested_outcome')
                    if eligible:
                        meeting['outcome_id'] = (meeting_rules.choose_outcome(facts['activity_id'], extras, rng, requested, version=version)
                            if version == meeting_rules.VERSION else requested if requested in eligible else rng.choice(eligible))
                if meeting.get('outcome_id'):
                    facts['outcome_id'] = meeting['outcome_id']
            rng = random.Random(stable((state['seed'], meeting['id'], index, 'meeting-text-v1')))
            segment['label'] = labels.choose(slot, facts, rng, recent)
            if segment['label']['id']:
                recent[:] = (recent + [segment['label']['id']])[-12:]


def complete_round(state, results):
    from .engine import record
    n = state['night']
    for owner, meeting in n.get('meetings', {}).items():
        if 'waiting' in meeting or meeting.get('completed'):
            continue
        meeting['completed'] = True
        # Actual accounting remains authoritative, including an accepted extra
        # in a round with no ordinary booking.
        from .management import DECISIONS
        extras = sum(DECISIONS[d['kind']]['revenue'] for d in n['decisions']
                     if d['id'] in meeting['offers'] and d['choice'] == 'accept')
        value = results[owner].get('value', 0) + extras
        label = meeting['segments'][-1]['label']
        n.setdefault('last_meetings', {})[owner] = {'id': meeting['id'], 'label': copy.deepcopy(label), 'value': value}
        record(state, 'meeting_completed', meeting=copy.deepcopy(meeting), value=value)


def views(state, catalog):
    n = state.get('night')
    if (n and n.get('stage_tracking') == 2) or (not n and state.get('reports') and 'booking_history' in state['reports'][-1]):
        from .booking_state import views as booking_views
        return booking_views(state, catalog)
    if not n or not n.get('stage_tracking'):
        return {}
    result = {}
    for owner, meeting in n.get('meetings', {}).items():
        name = catalog['people'][owner]['name']
        if 'waiting' in meeting:
            view = {'phase': 'Between bookings', 'text': meeting['waiting'], 'progress': None}
        else:
            entered = [s for s in meeting['segments'] if s['start'] <= n['elapsed'] and 'label' in s]
            if not entered:
                continue
            segment = entered[-1]; slot = segment['slot']
            phase = f"Stage {segment['stage_index']} of {segment['stage_count']}" if slot == 'meeting.stage' else {
                'meeting.arrival': 'Arrival', 'meeting.finishing': 'Finishing',
                'meeting.cleanup': 'Cleanup', 'meeting.complete': 'Complete'}[slot]
            view = {'phase': phase, 'slot': slot, 'text': segment['label']['text'].replace('{worker}', name),
                    'progress': round(min(1, max(0, (n['elapsed'] - meeting['start']) / (meeting['end'] - meeting['start']))) * 100, 2),
                    'remaining': max(0, math.ceil(meeting['end'] - n['elapsed']))}
        last = n.get('last_meetings', {}).get(owner)
        if last:
            view['last'] = {'text': last['label']['text'].replace('{worker}', name), 'value': last['value']}
        result[owner] = view
    return result


def validate(state):
    """Validate saved timelines, without requiring the originating text pack."""
    from .booking_state import validate_reports
    validate_reports(state)
    recent = state.get('stage_label_recent', {})
    if not isinstance(recent, dict) or any(owner not in state['people'] or not isinstance(ids, list)
            or len(ids) > 12 or any(not isinstance(i, str) or not 1 <= len(i) <= 128 for i in ids)
            for owner, ids in recent.items()):
        raise ValueError('Invalid recent label history.')
    n = state.get('night')
    if not n or 'stage_tracking' not in n:
        return
    if n['stage_tracking'] == 2:
        from .booking_state import validate as validate_bookings
        return validate_bookings(state)
    if type(n['stage_tracking']) is not int or n['stage_tracking'] != 1:
        raise ValueError('Unsupported meeting tracker version.')
    def number(v):
        return type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 300
    def label(value):
        return (isinstance(value, dict) and stage_labels.valid_text(value.get('text'))
                and (value.get('id') is None or (isinstance(value['id'], str) and 1 <= len(value['id']) <= 128)))
    if type(n.get('meeting_round')) is not int or not 0 <= n['meeting_round'] <= min(6, n['wave'] + 1):
        raise ValueError('Invalid meeting round.')
    if not isinstance(n.get('meetings', {}), dict) or len(n.get('meetings', {})) > len(state['people']):
        raise ValueError('Invalid meetings.')
    for owner, meeting in n.get('meetings', {}).items():
        version = meeting.get('rules_version', 1)
        if type(version) is not int or version not in (1, meeting_rules.VERSION):
            raise ValueError('Unsupported meeting rules version.')
        if owner not in state['people'] or n['assignments'].get(owner) != 'room' or meeting['owner'] != owner:
            raise ValueError('Invalid meeting worker.')
        wave = meeting['round']
        if type(wave) is not int or wave != n['meeting_round'] or not 1 <= wave <= 6 or meeting['id'] != identity(state, owner, wave):
            raise ValueError('Invalid meeting identity.')
        if 'waiting' in meeting:
            if not isinstance(meeting['waiting'], str) or len(meeting['waiting']) > 4096:
                raise ValueError('Invalid waiting message.')
            continue
        if not number(meeting['start']) or not number(meeting['end']) or not (wave - 1) * 50 <= meeting['start'] < meeting['end'] == wave * 50:
            raise ValueError('Invalid meeting budget.')
        offers = meeting['offers']
        linked = linked_offers(n, owner, meeting['id'])
        extras = {d['kind'] for d in linked}
        if not isinstance(offers, list) or set(offers) != {d['id'] for d in linked} or len(offers) != len(linked):
            raise ValueError('Invalid meeting offer association.')
        segments = meeting['segments']; count = len(segments) - 4
        if not 1 <= count <= MAX_STAGES:
            raise ValueError('Invalid stage count.')
        expected = ['meeting.arrival'] + ['meeting.stage'] * count + ['meeting.finishing', 'meeting.cleanup', 'meeting.complete']
        at = meeting['start']; final = None; actual = None
        for index, (segment, slot) in enumerate(zip(segments, expected)):
            if segment['slot'] != slot or not number(segment['start']) or not number(segment['end']) or abs(segment['start'] - at) > 1e-6:
                raise ValueError('Invalid stage order.')
            if segment['end'] < segment['start'] or (slot != 'meeting.complete' and segment['end'] == segment['start']):
                raise ValueError('Invalid stage duration.')
            at = segment['end']
            if slot == 'meeting.stage':
                activity = segment['activity_id']
                if not isinstance(activity, str) or activity not in stage_labels.catalog(original=True)['activities']:
                    raise ValueError('Invalid saved activity.')
                if type(segment['stage_index']) is not int or segment['stage_index'] != index or type(segment['stage_count']) is not int or segment['stage_count'] != count:
                    raise ValueError('Invalid stage facts.')
                if version == meeting_rules.VERSION and not meeting_rules.activity_allowed(activity, extras, version=version):
                    raise ValueError('A stage is missing its required paid extra.')
                final = segment['activity_id']
                if segment['start'] <= n['elapsed']:
                    actual = final
            if 'label' in segment and not label(segment['label']):
                raise ValueError('Invalid saved label.')
            if ('label' in segment) != (segment['start'] <= n['elapsed']):
                raise ValueError('Saved labels must follow the meeting clock.')
        if at != meeting['end'] or segments[-1]['start'] != meeting['end']:
            raise ValueError('Completion must not add time.')
        if meeting.get('actual_activity_id') != actual:
            raise ValueError('Invalid current meeting activity.')
        finishing_entered = segments[-3]['start'] <= n['elapsed']
        eligible = eligible_outcomes(final, extras, version)
        if (meeting.get('outcome_id') is not None) != finishing_entered or (finishing_entered and meeting['outcome_id'] not in eligible):
            raise ValueError('Invalid meeting outcome.')
        expected_outcome = 'internal_vaginal' if any(d['kind'] == 'creampie_extra' for d in linked) else None
        if meeting.get('requested_outcome') != expected_outcome:
            raise ValueError('Invalid requested outcome.')
        if version == meeting_rules.VERSION:
            if not eligible:
                raise ValueError('The final activity has no compatible outcome.')
            if 'anal_extra' in extras and not any(s.get('activity_id', '').endswith('__anal') for s in segments):
                raise ValueError('The paid activity is missing from the meeting.')
            if expected_outcome and (expected_outcome not in eligible or (finishing_entered and meeting['outcome_id'] != expected_outcome)):
                raise ValueError('The paid outcome must match the final activity.')
    for owner, last in n.get('last_meetings', {}).items():
        if owner not in state['people'] or not label(last['label']) or type(last['value']) not in (int, float) or not math.isfinite(last['value']):
            raise ValueError('Invalid completed meeting.')
