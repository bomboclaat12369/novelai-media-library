"""Focused coverage for event rotation, paid extras and team choices."""
import copy
import json
import unittest

from game import engine as g, flavor, management as m, migrations
from game.catalog import demo_catalog


class EventVariety(unittest.TestCase):
    def setUp(self):
        self.cat=demo_catalog()
        self.base=g.new_game(self.cat,['demo-0','demo-1'],123)

    def opportunity(self,kind):
        state=g.command(self.base,self.cat,'start')
        state['night']['decisions'][0].update(kind=kind,copy=flavor.event(kind,state))
        state=g.command(state,self.cat,'advance',{'seconds':100,'stop_at_decision':True})
        return state,state['night']['decisions'][0]['id']

    def test_rotation_covers_every_scenario_with_varied_saved_copy(self):
        seen={kind:set() for kind in m.DECISIONS}
        for day in range(1,25):
            state=copy.deepcopy(self.base);state['day']=day
            state=g.command(state,self.cat,'start')
            decisions=state['night']['decisions']
            self.assertEqual(len(decisions),2)
            self.assertEqual([d['at'] for d in decisions],[100,200])
            self.assertEqual(decisions[0]['kind'],m.OPPORTUNITIES[(day-1)%6])
            self.assertEqual(decisions[1]['kind'],m.TEAM_CHOICES[(day-1)%3])
            for d in decisions:seen[d['kind']].add(d['copy']['title'])
            restored=migrations.migrate(json.loads(json.dumps(state)))
            migrations.validate(restored,self.cat)
            self.assertEqual(restored['night']['decisions'],decisions)
        self.assertTrue(all(len(titles)>=4 for titles in seen.values()))
        no_hosts=copy.deepcopy(self.base)
        for w in no_hosts['people'].values():w['role']='rest'
        no_hosts=g.command(no_hosts,self.cat,'start')
        self.assertEqual(no_hosts['night']['decisions'][0]['kind'],'promotion')

    def test_paid_extras_charge_the_matching_host_and_resume_once(self):
        for kind,pay,energy,role in [('anal_extra',65,12,'room'),('creampie_extra',70,14,'room'),
                                    ('extension',85,18,None),('lounge_round',40,6,'lounge')]:
            with self.subTest(kind=kind):
                state,ident=self.opportunity(kind)
                self.assertTrue(state['night']['paused'])
                before={p:w['energy'] for p,w in state['people'].items()}
                revenue=state['night']['revenue']
                result=g.command(state,self.cat,'decision',{'decision':ident,'choice':'accept'})
                self.assertEqual(result['night']['revenue'],revenue+pay)
                changes={p:before[p]-w['energy'] for p,w in result['people'].items()}
                charged=[p for p,delta in changes.items() if delta]
                self.assertEqual(len(charged),1)
                self.assertEqual(changes[charged[0]],energy)
                if role:self.assertEqual(m.assignment(state,charged[0]),role)
                self.assertFalse(result['night']['paused'])
                with self.assertRaises(g.RuleError):g.command(result,self.cat,'decision',{'decision':ident,'choice':'accept'})

    def test_tired_room_host_cannot_charge_another_role_and_decline_is_free(self):
        for kind,energy in [('anal_extra',12),('creampie_extra',14)]:
            with self.subTest(kind=kind):
                state,ident=self.opportunity(kind)
                for p,w in state['people'].items():
                    w['energy']=energy-1 if m.assignment(state,p)=='room' else 100
                before=copy.deepcopy(state)
                with self.assertRaises(g.RuleError):g.command(state,self.cat,'decision',{'decision':ident,'choice':'accept'})
                self.assertEqual(state,before)
                declined=g.command(state,self.cat,'decision',{'decision':ident,'choice':'decline'})
                self.assertEqual(declined['people'],before['people'])
                self.assertEqual(declined['night']['revenue'],before['night']['revenue'])
                self.assertFalse(declined['night']['paused'])

    def test_meal_and_perk_costs_limits_and_insufficient_cash(self):
        for kind,choice,cost in [('team_meal','refresh',40),('regular_perk','perk',20)]:
            with self.subTest(kind=kind):
                state,ident=self.opportunity(kind)
                owners=list(state['people'])
                state['people'][owners[0]]['energy']=95
                state['people'][owners[1]].update(role='rest',energy=50)
                state['loyalty']=98
                result=g.command(state,self.cat,'decision',{'decision':ident,'choice':choice})
                self.assertEqual(result['night']['decision_costs'],cost)
                self.assertFalse(result['night']['paused'])
                self.assertEqual(result['people'][owners[1]]['energy'],50)
                self.assertEqual(result['people'][owners[0]]['energy'],100 if kind=='team_meal' else 95)
                self.assertEqual(result['loyalty'],100 if kind=='regular_perk' else 98)
                state['cash']=0;state['night']['revenue']=0
                before=copy.deepcopy(state)
                with self.assertRaises(g.RuleError):g.command(state,self.cat,'decision',{'decision':ident,'choice':choice})
                self.assertEqual(state,before)

    def test_finish_uses_free_defaults_for_every_new_event(self):
        baseline=g.command(g.command(self.base,self.cat,'start'),self.cat,'finish')
        for kind in set(m.DECISIONS)-{'booking','hospitality','promotion'}:
            with self.subTest(kind=kind):
                state=g.command(self.base,self.cat,'start')
                state['night']['decisions'][0].update(kind=kind,copy=flavor.event(kind,state))
                result=g.command(state,self.cat,'finish')
                self.assertEqual(result['cash'],baseline['cash'])
                self.assertEqual(result['reports'][-1]['decision_costs'],0)
                self.assertTrue(all(d['automatic'] and d['choice']=='decline' for d in result['reports'][-1]['decisions']))


if __name__=='__main__':unittest.main()
