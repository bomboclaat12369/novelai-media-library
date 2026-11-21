"""Explicit save migrations and bounded validation for recovery imports."""
from __future__ import annotations
import copy
import math
from . import engine, evolution, management, meetings, wardrobe

SCHEMA = 2


def recover_management_receipts(state):
    """Reconstruct recorded results without awarding cash or spending energy again."""
    for contract in state['contracts']:
        if contract['department'] == 'resort' and contract['status'] == 'completed' and 'checkout_bonus_paid' not in contract:
            contract['checkout_bonus_paid'] = management.resort_checkout_bonus(contract['spec'], contract['satisfaction'])

    shifts = list(state['reports'])
    if state.get('night'):
        shifts.append(state['night'])
    for shift in shifts:
        # Through 1.4.0 a lounge round paid $40 and cost 6 energy. Only
        # attribute it when the recorded offer explains the full discrepancy.
        earnings = shift.get('earnings')
        decisions = shift.get('decisions')
        if not isinstance(earnings, dict) or not isinstance(decisions, list) or not all(type(v) is int for v in earnings.values()):
            continue
        if shift.get('revenue') != sum(earnings.values()) + 40:
            continue
        lounge = [d for d in decisions if isinstance(d, dict) and d.get('kind') == 'lounge_round' and d.get('choice') == 'accept']
        if len(lounge) != 1 or 'host_credit' in lounge[0]:
            continue
        owner = lounge[0].get('worker')
        assignments = shift.get('assignments')
        if not isinstance(owner, str) or owner not in earnings or not isinstance(assignments, dict) or assignments.get(owner) != 'lounge':
            continue
        earnings[owner] += 40
        spent = shift.get('energy_spent')
        if isinstance(spent, dict) and type(spent.get(owner)) in (int, float):
            spent[owner] += 6
        lounge[0]['host_credit'] = {'revenue': 40, 'energy': 6}
        state.setdefault('journal', []).append({'kind': 'lounge_receipt_corrected', 'day': shift.get('day', state['day']),
                                               'decision': lounge[0].get('id'), 'worker': owner, 'revenue': 40, 'energy': 6})


def recover_reward_receipts(state, history):
    """Rebuild legacy reports from recorded awards, without awarding or spending vouchers."""
    missing = {r['day']: r for r in state['reports'] if 'voucher_rewards' not in r}
    if not missing:
        return
    for report in missing.values():
        report['voucher_rewards'] = []
    for contract in state['contracts']:
        report = missing.get(contract['end'])
        if report and contract['department']=='studio' and contract['status']=='completed' and contract.get('success') is True:
            amount = contract['spec'].get('packs',0)
            if type(amount) is int and amount > 0:
                report['voucher_rewards'].append({'source':'studio','contract':contract['id'],'amount':amount})
    seen = set()
    for event in history:
        milestone, amount, day = event.get('milestone'), event.get('standard_vouchers'), event.get('day')
        if event.get('kind')!='milestone_earned' or type(day) is not int or day not in missing:
            continue
        if not isinstance(milestone,str) or milestone in seen or type(amount) is not int or amount < 1:
            continue
        seen.add(milestone)
        missing[day]['voucher_rewards'].append({'source':'milestone','milestone':milestone,'amount':amount})


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
    state.setdefault('wardrobe', wardrobe.empty())
    return state


def validate(state, catalog):
    """Reject malformed recovery data before creating or replacing any live state."""
    def integer(value, low=0, high=10**12):
        return type(value) is int and low <= value <= high

    def finite(value, low=0, high=10**12):
        return type(value) in (int, float) and math.isfinite(value) and low <= value <= high

    try:
        wardrobe.validate(state)
        for report in state['reports']:
            rewards=report.get('voucher_rewards',[])
            if not isinstance(rewards,list): raise ValueError('Invalid voucher history.')
            for reward in rewards:
                if not isinstance(reward,dict) or not integer(reward.get('amount'),1): raise ValueError('Invalid voucher amount.')
                if reward.get('source')=='studio' and integer(reward.get('contract'),1): continue
                if reward.get('source')=='milestone' and isinstance(reward.get('milestone'),str): continue
                raise ValueError('Invalid voucher source.')
        if 'collection_target' in state and state['collection_target'] not in catalog['people']:
            raise ValueError('Unknown collection target.')
        if not integer(state['day'], 1) or not finite(state['cash'], -10**12): raise ValueError()
        if state['phase'] not in ('prepare', 'night'): raise ValueError()
        if type(state['preferred_night_speed']) is not int or state['preferred_night_speed'] not in engine.NIGHT_SPEEDS:
            raise ValueError()
        if not integer(state['seed'], -10**18, 10**18) or not integer(state['pack_counter']): raise ValueError()
        if not isinstance(state['people'], dict) or len(state['people']) < 2: raise ValueError()
        if not isinstance(state['owned'], dict) or len(state['owned']) > 250000: raise ValueError()
        for ident, own in state['owned'].items():
            if ident not in catalog['cards'] or not integer(own['copies'], 1) or not integer(own['xp']) or not integer(own['uses']) or not integer(own['mastery'], 0, 5): raise ValueError()
            if 'duo_side' in own and (catalog['cards'][ident].get('source') != 'duo' or own['duo_side'] not in evolution.DUO_SIDES):
                raise ValueError()
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
            if 'checkout_bonus_paid' in c and not integer(c['checkout_bonus_paid']): raise ValueError()
        if state['phase']=='night':
            n=state['night']
            if not finite(n['elapsed'],0,300) or not integer(n['wave'],0,6) or type(n['speed']) is not int or n['speed'] not in engine.NIGHT_SPEEDS: raise ValueError()
            if not finite(n['revenue']) or not isinstance(n['decisions'],list): raise ValueError()
            if not finite(n['department_revenue']) or not finite(n['decision_costs']): raise ValueError()
            if any(role not in (*engine.ROLES,'studio','resort') for role in n['assignments'].values()): raise ValueError()
        meetings.validate(state)
        if state['pending_pack']:
            pack=state['pending_pack']
            if pack['type'] not in engine.PACKS or len(pack['results'])!=5: raise ValueError()
            if any(c['id'] not in state['owned'] for c in pack['results']): raise ValueError()
            for result in pack['results']:
                if 'duo_side' in result and (catalog['cards'][result['id']].get('source') != 'duo' or result['duo_side'] not in evolution.DUO_SIDES):
                    raise ValueError()
            if any(not integer(i,0,4) for i in pack.get('revealed',[])): raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError):
        raise engine.RuleError('The recovery file contains invalid or incomplete game data.') from None
    return state
