"""Exercise both departments on the same night, including a mid-booking restore."""
from pathlib import Path
from copy import deepcopy
import json
import random
import tempfile
import unittest

from game import booking_state, bookings, catalog, engine, management, migrations, writing
from game.store import GameStore


class DepartmentOperations(unittest.TestCase):
    def setUp(self):
        self.cat = catalog.demo_catalog()
        self.state = engine.new_game(self.cat, ['demo-0','demo-1'], 19)
        self.state.update(cash=12000, day=7)
        self.state['totals'].update(services=32, studio_completed=2)
        for department in ('studio','resort'):
            self.act('department', kind=department)
        for owner in ('demo-2','demo-3'):
            self.act('hire', owner=owner)

    def act(self, action, **body):
        self.state = engine.command(self.state, self.cat, action, body)

    def restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=GameStore(Path(tmp)/'scratch.sqlite3', self.cat)
            doc=store.export()
            doc['save']={'revision':1,'state':self.state}
            renewed=store.restore(doc)
            self.state=renewed.read()['state']
            self.assertEqual(self.state, GameStore(renewed.path,self.cat).read()['state'])

    def test_premium_bookings_earn_their_unlocks_and_settle_elected_terms(self):
        for owner in self.state['people']:
            self.act('plan', owner=owner, role='rest')
        guest = None
        receipts = []
        for _ in range(15):
            goals = management.booking_goals(self.state)
            if all(g['current'] >= g['target'] for g in goals.values()):
                break
            if goals['commission']['current'] < 6:
                with self.assertRaisesRegex(engine.RuleError, '6 successful Studio shoots'):
                    self.act('schedule', department='studio', kind='commission', owner='demo-0')
                self.act('schedule', department='studio', kind='portrait', owner='demo-0')
            if goals['vip']['current'] < 3:
                with self.assertRaisesRegex(engine.RuleError, '3 completed return visits'):
                    self.act('schedule', department='resort', kind='vip', owner='demo-2')
                if not any(c['status']=='active' and c['department']=='resort' for c in self.state['contracts']):
                    quote = management.contract_quote(self.state, 'resort', 'retreat', 'demo-2', {'guest':guest})
                    self.act('schedule', department='resort', kind='retreat', owner='demo-2', guest=guest,
                             service_plan=quote['guest_offer']['preference'])
                    guest = self.state['contracts'][-1]['guest']['id']
                    self.assertEqual(management.booking_goals(self.state)['vip']['current'], goals['vip']['current'])
            self.act('start')
            self.act('finish')
            receipts.extend(self.state['reports'][-1].get('booking_unlocks', []))
        self.assertCountEqual(receipts, ['commission', 'vip'])
        self.assertEqual(management.booking_goals(self.state)['vip']['current'], 3)
        self.restore()
        career = self.state
        for accept, delivered, final_satisfaction in ((True, True, 90), (True, False, 89), (False, True, 90)):
            with self.subTest(accept=accept, delivered=delivered, satisfaction=final_satisfaction):
                self.state = deepcopy(career)
                next_id = self.state['contract_counter'] + 1
                low, high = (0, .5) if delivered else (.99, 1)
                self.state['seed'] = next(seed for seed in range(10000)
                    if low < random.Random(catalog.stable((seed, 'project', next_id))).random() < high)
                self.act('schedule', department='studio', kind='commission', owner='demo-1')
                self.act('schedule', department='resort', kind='vip', owner='demo-3')
                for shift in range(4):
                    self.act('start')
                    while self.state['night']:
                        night=self.state['night']
                        if shift==2 and night['wave']==5:
                            # Final standard service adds one point. Exercise both sides of the checkout target.
                            self.state['contracts'][-1]['satisfaction'] = final_satisfaction-1
                        self.act('advance', seconds=30, stop_at_decision=True)
                        night=self.state['night']
                        if not night or not night['paused']:
                            continue
                        event=next(d for d in night['decisions'] if d['choice'] is None and d['at']<=night['elapsed']<d['until'])
                        special = event['kind'] in ('studio_license','resort_farewell')
                        choice='accept' if special and accept else 'decline'
                        self.act('decision', decision=event['id'], choice=choice)
                        cost = 60 if choice=='accept' and event['kind']=='resort_farewell' else 0
                        self.assertEqual(self.state['night']['decision_costs'],night['decision_costs']+cost)
                        if special and accept:
                            self.restore()
                            with self.assertRaises(engine.RuleError):
                                self.act('decision', decision=event['id'], choice='accept')
                            self.act('pause', paused=False)
                    self.assertFalse(self.state['reports'][-1].get('booking_unlocks'))
                shoot, stay = self.state['contracts'][-2:]
                self.assertEqual((shoot['success'],stay['satisfaction']), (delivered,final_satisfaction))
                self.assertEqual(sum(d['kind']=='studio_license' for d in shoot['decisions']), 1)
                self.assertEqual(sum(d['kind']=='resort_farewell' for d in stay['decisions']), 1)
                self.assertEqual(shoot['work_log'][2]['stage'], 'Shoot the lead image')
                self.assertEqual(stay['work_log'][2]['stage'], 'Host a private lunch')
                base=round(shoot['spec']['pay']*min(1.25,shoot['quality']/24)*(1 if delivered else .55))
                self.assertEqual(shoot['revenue'], base+(80 if accept else 0))
                vouchers = sum(row['amount'] for row in self.state['reports'][-1]['voucher_rewards'] if row.get('contract')==shoot['id'])
                self.assertEqual(vouchers, (1 if accept else 2) if delivered else 0)
                farewell = 160 if accept and final_satisfaction>=90 else 0
                self.assertEqual(stay.get('farewell_bonus_paid',0), farewell)
                self.assertEqual(stay.get('service_cost',0), 60 if accept else 0)
                self.assertEqual(stay['revenue'],sum(w['earned'] for w in stay['work_log']) + stay['checkout_bonus_paid'] + farewell)
                self.assertEqual(sum(r['earnings']['demo-3'] for r in self.state['reports'][-4:]),stay['revenue'])
                self.restore()

    def test_recovery_preserves_worked_nights_and_moves_only_the_remaining_shifts(self):
        self.act('schedule', department='studio', owner='demo-0', kind='feature_film', costar='demo-1')
        self.act('schedule', department='resort', owner='demo-2', kind='weekend')
        self.act('schedule', department='studio', owner='demo-0', kind='portrait', start=10)
        for expected in ([7,10,11], [7,10,13]):
            self.act('start')
            while self.state['night']:
                self.act('advance', seconds=180, stop_at_decision=True)
                night = self.state['night']
                if not night:
                    break
                event = next(d for d in night['decisions'] if d['choice'] is None and d['at'] <= night['elapsed'] < d['until'])
                self.act('decision', decision=event['id'], choice='accept' if event['kind']=='resort_private' else 'decline')
            self.state['cash'] = 0
            receipts = json.dumps(self.state['reports'], sort_keys=True)
            self.act('recovery')
            film, stay, future = self.state['contracts']
            dates = management.derived(self.state)['reservation_nights']
            self.assertEqual((dates[film['id']], dates[stay['id']], dates[future['id']]), (expected, expected, [expected[-1]+1]))
            self.assertFalse(management.reservations(self.state, day=self.state['day']-1))
            self.assertEqual(management.reservations(self.state,'demo-1',day=7), [film])
            self.restore()
            self.assertEqual(json.dumps(self.state['reports'], sort_keys=True), receipts)
        self.act('start')
        self.act('finish')
        film, stay, future = self.state['contracts']
        for job in (film,stay):
            self.assertEqual(job['status'], 'completed')
            self.assertEqual([row['day'] for row in job['work_log'] if row['wave']==6], [7,10,13])
            self.assertEqual((job['nights'],len(job['work_log'])), (3,18))
        self.assertEqual([m['value'] for m in stay['private_bookings'] if m['completed']], [65])
        self.assertEqual(film['revenue']+stay['revenue'], sum(r['department_revenue'] for r in self.state['reports']))
        self.assertEqual((future['status'], future['start'], future['nights']), ('active',14,0))
        self.restore()
        self.state['reports'][0]['day'] = 9
        with self.assertRaisesRegex(ValueError, 'Invalid department request'):
            booking_state.validate_reports(self.state)

    def test_fully_staffed_night_restores_all_offers_and_resumes_at_saved_speed(self):
        self.state.update(cash=100000, day=9, seed=91)
        roster = list(self.cat['people'])[:14]
        for owner in roster:
            if owner not in self.state['people']:
                self.act('hire', owner=owner)
        for department, kind, crew in [('studio', 'portrait', roster[2:8]), ('resort', 'retreat', roster[8:14])]:
            for _ in range(len(crew) - self.state['departments'][department]):
                self.act('department', kind=department)
            for owner in crew:
                self.act('schedule', department=department, owner=owner, kind=kind)
        self.act('start')
        self.act('speed', speed=8)
        night = self.state['night']
        offers = night['decisions']
        self.assertEqual(len(offers), 17)
        self.assertEqual({d['contract'] for d in offers if 'contract' in d}, {c['id'] for c in self.state['contracts']})
        gap = bookings.REQUEST_COOLDOWN * bookings.clock_scale(night)
        self.assertTrue(all(b['at'] - a['at'] >= gap for a, b in zip(offers, offers[1:])))
        self.assertTrue(all(d['at'] <= .64 * night['duration'] for d in offers if d['kind'] == 'resort_private'))
        answered = set()
        while self.state['night']:
            self.act('advance', seconds=180, stop_at_decision=True)
            night = self.state['night']
            if not night:
                break
            self.assertTrue(night['paused'])
            pending = [d for d in night['decisions'] if d['choice'] is None and d['at'] <= night['elapsed'] < d['until']]
            self.assertEqual(len(pending), 1)
            event = pending[0]
            self.assertNotIn(event['id'], answered)
            if len(answered) == 7:
                self.restore()
                self.assertEqual(night, self.state['night'])
            self.act('decision', decision=event['id'], choice='decline')
            self.assertFalse(self.state['night']['paused'])
            self.assertEqual(self.state['night']['speed'], 8)
            answered.add(event['id'])
        report = self.state['reports'][-1]
        self.assertEqual({d['id'] for d in report['decisions']}, answered)
        self.assertTrue(all(d['choice'] == 'decline' and not d['automatic'] for d in report['decisions']))
        self.assertEqual(report['decision_costs'], 0)
        booking_state.validate_reports(self.state)
        self.restore()

    def test_shared_production_and_guest_lifecycle(self):
        self.act('schedule',department='studio',owner='demo-0',kind='feature_film',costar='demo-1')
        quote=management.contract_quote(self.state,'resort','retreat','demo-2')
        self.act('schedule',department='resort',owner='demo-2',kind='retreat',service_plan=quote['guest_offer']['preference'])
        self.assertEqual(management.assignment(self.state,'demo-1'),'studio')
        with self.assertRaises(engine.RuleError):
            self.act('schedule',department='resort',owner='demo-1',kind='retreat')
        self.assertEqual(self.state['contracts'][0]['spec']['pay'],1170)
        guest=self.state['contracts'][1]['guest']['id']
        offers=set();restored=False
        for _ in range(3):
            self.act('auto');self.act('start')
            while self.state['night']:
                self.act('advance',seconds=180,stop_at_decision=True)
                n=self.state['night']
                if not n: break
                decision=next(d for d in n['decisions'] if not d['choice'] and d['at']<=n['elapsed']<d['until'])
                choice='accept' if 'contract' in decision else 'decline'
                if choice=='accept': offers.add(decision['kind'])
                self.act('decision',decision=decision['id'],choice=choice)
                if decision['kind']=='resort_private':
                    self.act('advance',seconds=4,stop_at_decision=True)
                    booking=self.state['contracts'][1]['private_bookings'][-1]
                    self.assertTrue(any('label' in s for s in booking['segments']))
                    self.assertFalse(booking.get('completed'))
                    self.restore()
                    self.assertEqual(self.state['contracts'][1]['private_bookings'][-1],booking)
                    restored=True
                    if not any(d['choice'] is None and d['at']<=self.state['night']['elapsed']<d['until'] for d in self.state['night']['decisions']):
                        self.act('pause',paused=False)
            migrations.validate(self.state,self.cat)
        self.assertTrue(restored)
        self.assertTrue({'studio_cut','studio_pickup','studio_press','resort_request','resort_private'}<=offers)
        film, stay=self.state['contracts']
        reports=self.state['reports']
        for r in reports:
            costs=r['costs']
            self.assertEqual(costs,{'payroll':120,'upkeep':engine.recurring_costs(self.state)['upkeep'],
                                    'training':r['training_cost'],'decisions':r['decision_costs']})
            self.assertEqual(r['expenses'],sum(costs.values()))
            self.assertEqual(r['profit'],r['revenue']-r['expenses'])
            by_venue={role:sum(r['earnings'][p] for p in r['assignments'] if r['assignments'][p]==role)
                      for role in ('room','lounge','studio','resort')}
            self.assertEqual(sum(by_venue.values()),r['revenue'])
            self.assertEqual(by_venue['studio']+by_venue['resort'],r['department_revenue'])
        self.assertEqual(reports[-1]['earnings']['demo-0']+reports[-1]['earnings']['demo-1'],film['revenue'])
        self.assertEqual(sum(r['earnings']['demo-2'] for r in reports[:2]),stay['revenue'])
        legacy_reports=json.loads(json.dumps(self.state))
        del legacy_reports['reports'][0]['costs']
        migrations.validate(legacy_reports,self.cat)
        legacy_reports['reports'][1]['costs']['payroll']+=1
        with self.assertRaises(engine.RuleError):migrations.validate(legacy_reports,self.cat)
        self.assertEqual([len(c['work_log']) for c in (film,stay)],[18,12])
        self.assertEqual(self.state['people']['demo-1']['skills']['studio'],54)
        self.assertEqual((film['delivery_extra'],stay['service_cost']),(55,18))
        self.assertEqual(len(stay['private_bookings']),1)
        booking=stay['private_bookings'][0]
        self.assertTrue(booking['completed'])
        self.assertTrue(all('label' in s for s in booking['segments']))
        self.assertEqual(stay['revenue'],sum(e['earned'] for e in stay['work_log'])+65+stay['checkout_bonus_paid'])
        self.assertIn(guest,management.ops.returning_guests(self.state))
        self.act('schedule',department='resort',owner='demo-2',kind='weekend',guest=guest)
        self.assertEqual(self.state['contracts'][-1]['guest']['visit'],2)
        self.assertNotIn(guest,management.ops.returning_guests(self.state))
        self.assertEqual(self.state['contracts'][-1]['spec']['rate'],management.STAYS['weekend']['rate']+10)
        self.restore()

    def test_cast_energy_block_and_legacy_contract(self):
        self.state['people']['demo-1']['energy']=1
        before=self.state['cash']
        with self.assertRaises(engine.RuleError):
            self.act('schedule',department='studio',owner='demo-0',kind='feature_film',costar='demo-1')
        self.assertEqual(self.state['cash'],before)
        self.act('schedule',department='studio',owner='demo-0',kind='portrait')
        c=self.state['contracts'][0]
        for key in ('preferred_specialty','medium','brief'):del c['spec'][key]
        del c['operations']
        self.act('start')
        self.assertFalse(any('contract' in d for d in self.state['night']['decisions']))
        self.act('finish')
        self.assertEqual(self.state['contracts'][0]['status'],'completed')
        self.restore()

    def test_photo_cover_uses_the_real_brief_and_pays_only_on_success(self):
        self.act('schedule',department='studio',owner='demo-0',kind='campaign')
        entry={'id':'photo.cover','slot':'event.studio_cover','when':{},'title':'{worker} on {contract_title}',
               'text':'A {success_fee} bonus for {chance_cost} points of risk.','dialogue':[]}
        pack={'format':'after-hours-writing-pack','schema_version':1,'context_version':4,'pack_id':'cover','entries':[entry]}
        with self.assertRaises(ValueError):
            writing.parse(json.dumps({**pack,'context_version':2}).encode())
        with tempfile.TemporaryDirectory() as folder:
            shelf=writing.Shelf(folder)
            shelf.install(json.dumps(pack).encode())
            for _ in range(3):
                self.act('start')
                while self.state['night']:
                    self.act('advance',seconds=180,stop_at_decision=True)
                    night=self.state['night']
                    if not night: break
                    event=next(d for d in night['decisions'] if not d['choice'] and d['at']<=night['elapsed']<d['until'])
                    kind=event['kind']
                    if kind=='studio_cover':
                        shelf.event(event,self.cat,random.Random(1))
                        self.assertEqual(event['copy']['title'],self.cat['people']['demo-0']['name']+' on Feature campaign')
                        self.assertIn('90 bonus for 12 points',event['copy']['detail'])
                    self.assertNotEqual(kind,'studio_cut')
                    self.act('decision',decision=event['id'],choice='accept' if kind=='studio_cover' else 'decline')
        shoot=self.state['contracts'][0]
        self.assertEqual(shoot['cover_fee'],90)
        self.assertAlmostEqual(management.ops.delivery_chance(shoot),shoot['spec']['success_chance']-.12)
        base=round(shoot['spec']['pay']*min(1.25,shoot['quality']/18)*(1 if shoot['success'] else .55))
        self.assertEqual(shoot['revenue'],base+(90 if shoot['success'] else 0))
        self.restore()
