"""Explicit save migrations and bounded validation for recovery imports."""
from __future__ import annotations
import copy
import math
from . import engine, management

SCHEMA = 2


def migrate(original):
    state = copy.deepcopy(original)
    version = state.get('schema')
    if type(version) is not int or version not in (1, SCHEMA):
        raise engine.RuleError('This save uses an unsupported schema. It has not been replaced.')
    if version == 1:
        management.ensure(state)
        if state.get('night'):
            # Preserve partial revenue, energy, rounds and pack results exactly.
            management.prepare_night(state)
            for decision in state['night']['decisions']:
                if decision['at'] <= state['night']['elapsed']:
                    decision.update(choice='decline', automatic=True)
        state['schema'] = SCHEMA
        state['version'] = engine.VERSION
        state.setdefault('journal', []).append({'day': state['day'], 'kind': 'save_migrated', 'from_schema': 1, 'to_schema': SCHEMA})
    management.ensure(state)
    return state


def validate(state, catalog):
    """Reject malformed recovery data before creating or replacing any live state."""
    def integer(value, low=0, high=10**12):
        return type(value) is int and low <= value <= high

    def finite(value, low=0, high=10**12):
        return type(value) in (int, float) and math.isfinite(value) and low <= value <= high

    try:
        if not integer(state['day'], 1) or not finite(state['cash'], -10**12): raise ValueError()
        if state['phase'] not in ('prepare', 'night'): raise ValueError()
        if not integer(state['seed'], -10**18, 10**18) or not integer(state['pack_counter']): raise ValueError()
        if not isinstance(state['people'], dict) or len(state['people']) < 2: raise ValueError()
        if not isinstance(state['owned'], dict) or len(state['owned']) > 250000: raise ValueError()
        for ident, own in state['owned'].items():
            if ident not in catalog['cards'] or not integer(own['copies'], 1) or not integer(own['xp']) or not integer(own['uses']) or not integer(own['mastery'], 0, 5): raise ValueError()
        for owner, worker in state['people'].items():
            if owner not in catalog['people'] or worker['card'] not in state['owned']: raise ValueError()
            if catalog['cards'][worker['card']]['owner'] != owner or not finite(worker['energy'], 0, 100) or not integer(worker['xp']): raise ValueError()
            if worker['role'] not in engine.ROLES or worker['profile'] not in management.PROFILES: raise ValueError()
            if worker['training'] not in ('club', 'studio', 'resort'): raise ValueError()
            if any(not finite(v) for v in worker['skills'].values()): raise ValueError()
        if state['pricing'] not in engine.PRICES: raise ValueError()
        for k, spec in engine.UPGRADES.items():
            if not integer(state['facilities'][k], 1 if k in ('rooms','lounge') else 0, spec['max']): raise ValueError()
        if any(not integer(state['departments'][k], 0, 6) for k in management.DEPARTMENTS): raise ValueError()
        for key in ('pack_vouchers','contract_counter','reputation'):
            if not integer(state[key]): raise ValueError()
        if not isinstance(state['narrative'], dict) or not isinstance(state['saved_plans'], dict): raise ValueError()
        if len(state['saved_plans'])>12: raise ValueError()
        for plan in state['saved_plans'].values():
            if plan['pricing'] not in engine.PRICES: raise ValueError()
            for owner, values in plan['people'].items():
                if owner not in state['people'] or values['role'] not in engine.ROLES or values['training'] not in ('club','studio','resort'): raise ValueError()
                if values['card'] not in state['owned'] or catalog['cards'][values['card']]['owner']!=owner: raise ValueError()
        for name in ('revenue','expenses','packs','services','recovery_grants','studio_completed','resort_completed','contract_revenue'):
            if not finite(state['totals'][name]): raise ValueError()
        if not finite(state['loyalty'],0,100) or not integer(state['promotion_until']): raise ValueError()
        contract_ids=set()
        for c in state['contracts']:
            if c['department'] not in management.DEPARTMENTS or c['owner'] not in state['people']: raise ValueError()
            if c['status'] not in ('active', 'completed', 'cancelled') or not integer(c['start'], 1) or not integer(c['end'], c['start']): raise ValueError()
            if c['kind'] not in (management.PROJECTS if c['department']=='studio' else management.STAYS): raise ValueError()
            if not integer(c['id'],1) or c['id'] in contract_ids or c['id']>state['contract_counter']: raise ValueError()
            contract_ids.add(c['id'])
            if not integer(c['nights'],0,4) or not finite(c['quality']) or not finite(c['revenue']) or not finite(c['satisfaction'],0,100): raise ValueError()
            spec=c['spec']
            if not integer(spec['days'],1,4) or c['end']-c['start']+1!=spec['days']: raise ValueError()
            for name in ('fee','energy','estimated_pay','success_chance'):
                if not finite(spec[name]): raise ValueError()
            if c['department']=='studio':
                if not finite(spec['pay']) or not integer(spec['packs']): raise ValueError()
            elif not finite(spec['rate']) or not finite(spec['expectation'],0,100): raise ValueError()
        if state['phase']=='night':
            n=state['night']
            if not finite(n['elapsed'],0,300) or not integer(n['wave'],0,6) or type(n['speed']) is not int or n['speed'] not in engine.NIGHT_SPEEDS: raise ValueError()
            if not finite(n['revenue']) or not isinstance(n['decisions'],list): raise ValueError()
            if not finite(n['department_revenue']) or not finite(n['decision_costs']): raise ValueError()
            if any(role not in (*engine.ROLES,'studio','resort') for role in n['assignments'].values()): raise ValueError()
        if state['pending_pack']:
            pack=state['pending_pack']
            if pack['type'] not in engine.PACKS or len(pack['results'])!=5: raise ValueError()
            if any(c['id'] not in state['owned'] for c in pack['results']): raise ValueError()
            if any(not integer(i,0,4) for i in pack.get('revealed',[])): raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError):
        raise engine.RuleError('The recovery file contains invalid or incomplete game data.') from None
    return state
