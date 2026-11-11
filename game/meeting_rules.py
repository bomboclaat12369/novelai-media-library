"""Game-owned eligibility and relative selection weights; never writing prompts.

These are adjustable game-balance values, not measured population frequencies.
The writing catalog registers IDs; it cannot grant permissions or set weights.
"""
from __future__ import annotations
from . import stage_labels

VERSION = 2
BOOKING_RULES_VERSION = 5

# Select a family first. Its variants share that family's probability mass.
POSITION_FAMILIES = {
    'missionary': (32, {'missionary': 90, 'standing_missionary': 4,
                        'sideways_missionary': 5, 'missionary__splits': 1}),
    'doggy': (26, {'doggy': 94, 'standing_doggy': 6}),
    'cowgirl': (18, {'cowgirl': 98, 'cowgirl__splits': 2}),
    'reverse_cowgirl': (9, {'reverse_cowgirl': 98, 'reverse_cowgirl__splits': 2}),
    'spooning': (8, {'spooning': 100}),
    'prone_bone': (5, {'prone_bone': 98, 'prone_bone__splits': 2}),
    'mating_press': (1.5, {'mating_press': 100}),
    'amazon': (.25, {'amazon': 100}),
    'piledriver': (.25, {'piledriver': 100}),
}
BLOWJOB = 'blowjob__worker_gives'
LEGACY_SUPPORT_WEIGHTS = {
    'kissing__shared': 24,
    'oral_vulva__worker_receives': 12,
    BLOWJOB: 22,
    'deepthroat__worker_gives': 2,
    'sixty_nine__shared': 4,
    'rimjob__worker_gives': 1,
    'rimjob__worker_receives': 1,
    'fingering_vaginal__worker_receives': 10,
    'fingering_anal__worker_receives': 1,
    'prostate_massage__worker_gives': 1,
    'handjob__worker_gives': 10,
    'breast_sucking__worker_receives': 6,
    'breast_play__worker_receives': 6,
}
SUPPORT_WEIGHTS = {
    **LEGACY_SUPPORT_WEIGHTS,
    'rimjob__worker_gives': 4,
    'rimjob__worker_receives': 4,
    stage_labels.CLIENT_LED_ORAL: 1,
}
PAID_ANAL_SUPPORT = frozenset({
    'rimjob__worker_gives', 'rimjob__worker_receives',
    'fingering_anal__worker_receives', 'prostate_massage__worker_gives',
})
FINISHING_SUPPORT = frozenset({
    BLOWJOB, 'deepthroat__worker_gives', stage_labels.CLIENT_LED_ORAL,
    'sixty_nine__shared', 'handjob__worker_gives',
})
ORAL_SWITCH_CHANCE = .25
ORAL_CLOSE_OUTCOMES = {'external_face': 18, 'external_breasts': 7, 'oral_mouth': 75}

# Compatibility profiles describe the recorded final activity. No implicit
# repositioning is inserted to make an otherwise ineligible outcome fit.
FRONT = {'external_stomach': 55, 'external_breasts': 25, 'external_vulva': 20}
REAR = {'external_back': 55, 'external_buttocks': 45}
POSITION_OUTCOMES = {
    'missionary': FRONT, 'cowgirl': FRONT, 'mating_press': FRONT,
    'amazon': FRONT, 'piledriver': FRONT,
    'doggy': REAR, 'prone_bone': REAR, 'reverse_cowgirl': REAR, 'spooning': REAR,
}
DEEP_ORAL_OUTCOMES = {'external_face': 20, 'oral_mouth': 30, 'oral_throat': 50}
SUPPORT_OUTCOMES = {
    BLOWJOB: {'external_face': 40, 'external_breasts': 15, 'oral_mouth': 45},
    'deepthroat__worker_gives': DEEP_ORAL_OUTCOMES,
    stage_labels.CLIENT_LED_ORAL: DEEP_ORAL_OUTCOMES,
    'sixty_nine__shared': {'oral_mouth': 100},
    'handjob__worker_gives': {'external_stomach': 55, 'external_breasts': 30, 'external_vulva': 15},
}


def weighted_choice(weights, rng):
    keys = sorted(key for key, weight in weights.items() if weight > 0)
    if not keys:
        raise ValueError('No eligible meeting choice.')
    return rng.choices(keys, weights=[weights[key] for key in keys], k=1)[0]


def position_family(activity):
    if not isinstance(activity, str) or activity not in stage_labels.catalog()['activities']:
        return None
    stem, _, mode = activity.rpartition('__')
    if mode not in ('vaginal', 'anal'):
        return None
    return next((family for family, (_, variants) in POSITION_FAMILIES.items() if stem in variants), None)


def requires_anal_extra(activity):
    return isinstance(activity, str) and (activity.endswith('__anal') or activity in PAID_ANAL_SUPPORT)


def supporting_weights(version):
    return SUPPORT_WEIGHTS if version >= 5 else LEGACY_SUPPORT_WEIGHTS


def activity_allowed(activity, extras, *, version=BOOKING_RULES_VERSION):
    return (isinstance(activity, str) and activity in stage_labels.catalog()['activities']
            and (position_family(activity) is not None or activity in supporting_weights(version))
            and (not requires_anal_extra(activity) or 'anal_extra' in extras))


def choose_position(rng, mode, previous=None, allow_mode_switch=False):
    registered = stage_labels.catalog()['activities']
    previous_family = (None if allow_mode_switch and previous and not previous.endswith('__' + mode)
                       else position_family(previous))
    candidates = {family: {stem + '__' + mode: weight for stem, weight in variants.items()
                          if stem + '__' + mode in registered}
                  for family, (_, variants) in POSITION_FAMILIES.items() if family != previous_family}
    families = {family: POSITION_FAMILIES[family][0] for family, variants in candidates.items() if variants}
    family = weighted_choice(families, rng)
    return weighted_choice(candidates[family], rng)


def choose_activities(rng, count, extras, *, require_anal=None, require_finish=None,
                      previous=None, allow_mode_switch=False, prefer_oral_close=False, version=BOOKING_RULES_VERSION):
    """Resolve permissions before sampling. The last stage has a valid ending."""
    if type(count) is not int or not 1 <= count <= 4:
        raise ValueError('Choose one to four meeting stages.')
    paid_anal, paid_finish = 'anal_extra' in extras, 'creampie_extra' in extras
    require_anal = paid_anal if require_anal is None else require_anal
    require_finish = paid_finish if require_finish is None else require_finish
    if (require_anal and not paid_anal) or (require_finish and not paid_finish):
        raise ValueError('A requested activity or outcome requires its paid extra.')
    if require_anal and require_finish:
        count = max(2, count)
    required_anal = rng.randrange(count - int(require_finish)) if require_anal else None
    activities = []
    weights = supporting_weights(version)
    for index in range(count):
        final = index == count - 1
        force_mode = 'anal' if index == required_anal else 'vaginal' if final and require_finish else None
        previous = activities[-1] if activities else previous
        support = {activity: weight for activity, weight in weights.items()
                   if activity != previous and (not final or activity in FINISHING_SUPPORT)
                   and activity_allowed(activity, extras, version=version)}
        # Early supporting activity is optional; no numbered stage implies a
        # particular act. Later stages favor the main position pool.
        support_chance = .40 if index == 0 and count > 1 else .15
        if force_mode is None and support and rng.random() < support_chance:
            activity = weighted_choice(support, rng)
        elif (prefer_oral_close and final and force_mode is None and BLOWJOB in support and position_family(previous)
              and rng.random() < ORAL_SWITCH_CHANCE):
            # Some clients switch from a position to oral for the last stage.
            activity = BLOWJOB
        else:
            mode = force_mode or weighted_choice({'vaginal': 60, 'anal': 40 if paid_anal else 0}, rng)
            activity = choose_position(rng, mode, previous, allow_mode_switch)
        activities.append(activity)
    return activities


def outcome_weights(activity, extras, *, prefer_oral_close=False, version=BOOKING_RULES_VERSION):
    if not activity_allowed(activity, extras, version=version):
        return {}
    if prefer_oral_close and activity == BLOWJOB:
        return ORAL_CLOSE_OUTCOMES.copy()
    family = position_family(activity)
    weights = dict(POSITION_OUTCOMES[family] if family else SUPPORT_OUTCOMES.get(activity, {}))
    if activity.endswith('__vaginal') and 'creampie_extra' in extras:
        weights['internal_vaginal'] = 100
    if activity.endswith('__anal') and 'anal_extra' in extras:
        weights['internal_anal'] = 30
    return weights


def choose_outcome(activity, extras, rng, requested=None, *, prefer_oral_close=False, version=BOOKING_RULES_VERSION):
    weights = outcome_weights(activity, extras, prefer_oral_close=prefer_oral_close, version=version)
    if requested is not None:
        if requested not in weights:
            raise ValueError('The paid outcome does not match the final activity.')
        return requested
    return weighted_choice(weights, rng) if weights else None
