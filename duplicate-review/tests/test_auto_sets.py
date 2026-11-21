import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import numpy as np
from test_organizer import fixture
from organizer import Organizer
from set_matching import match_sets, WEIGHTS
import tracking


def descriptor(*directions):
    unit = np.zeros((3,768),np.float32)
    if len(directions)==1:
        directions = directions*3
    for row, direction in enumerate(directions):
        if isinstance(direction, int):
            unit[row,direction] = 1
        else:
            for axis,weight in direction.items():
                unit[row,axis] = weight
        unit[row] *= np.sqrt(WEIGHTS[row])/np.linalg.norm(unit[row])
    return unit.ravel()


def inventory(axes, sources):
    items = {}
    for ident,source in sources.items():
        items[ident] = {'sha':ident,'sources':{source:{'kind':'forum'}}}
    return items, {i:descriptor(axis) for i,axis in axes.items()}


class MatcherTests(unittest.TestCase):
    def test_new_and_cross_post_addition_require_independent_evidence(self):
        axes = {'a':0,'b':0,'c':0,'d':1,'e':1,'f':1}
        axes.update({str(n):n for n in range(2,11)})
        sources = {i:'forum:'+('started' if i in 'ab' else 'another' if i=='c' else 'shoot' if i in 'def' else i) for i in axes}
        items,vectors = inventory(axes,sources)
        groups = {'X':{'members':['a','b']}}
        def plan():
            return match_sets(items,vectors,groups,set(),set())
        self.assertEqual(set(plan()['add']['X']),{'c'})
        self.assertEqual(plan()['add']['X']['c']['posts'],[])
        self.assertEqual([set(c['members']) for c in plan()['new']],[set('def')])
        groups['X']['auto_members'] = ['a']
        self.assertFalse(plan()['add'])
        groups['X'].pop('auto_members')
        items['b']['copies'] = [{'sha':'a'}]
        self.assertFalse(plan()['add'])
        items['b']['copies'] = []
        groups['Y'] = {'members':['2','3']}
        vectors['2'] = vectors['a']
        self.assertFalse(plan()['add'])

    def test_long_post_ten_neighbors_and_a_cut_at_the_real_boundary(self):
        ids = ['photo-%03d'%n for n in range(320)]
        axes = {i:n+5 for n,i in enumerate(ids)}
        core = ids[56:66]
        for i in core:axes[i]=0
        items,vectors = inventory(axes,{i:'forum:long' for i in ids})
        def plan(groups=None,excluded=(),mixed=()):
            return match_sets(items,vectors,groups or {},set(excluded),set(mixed),{'forum:long':ids})
        drafts = plan()['new']
        self.assertEqual([set(g['members']) for g in drafts],[set(core)])
        self.assertEqual(drafts[0]['original_order'],{'forum:long':[57,66]})
        self.assertFalse(plan(mixed=['forum:long'])['new'])
        self.assertFalse(plan({'X':{'members':core[:2]},'Y':{'members':[core[-1]]}})['add'])
        self.assertFalse(plan({'X':{'members':core[:2]}})['add'])
        self.assertFalse(plan({'X':{'members':core[:3]}})['add'])
        items[core[0]]['sources']['forum:other-post']={'kind':'forum'}
        self.assertFalse(plan({'X':{'members':core[:3]}})['new'])
        vectors[core[-1]] = descriptor(0,0,77)
        self.assertEqual(set(plan()['new'][0]['members']),set(core[:-1]))
        del vectors[core[4]]
        self.assertNotIn(core[4],{i for g in plan()['new'] for i in g['members']})

    def test_held_ambiguous_and_unseen_photos_never_auto_group(self):
        ids = list('abcdefghijklm')
        items,vectors = inventory({i:(0 if i in 'abc' else n+1) for n,i in enumerate(ids)},
                                  {i:'forum:one' if i in 'abc' else 'forum:'+i for i in ids})
        def plan(excluded=()):
            return match_sets(items,vectors,{},set(excluded),set())['new']
        self.assertEqual(len(plan()),1)
        self.assertFalse(plan('b'))
        vectors['e'] = vectors['a']
        self.assertFalse(plan())  # A look-alike in an unassigned post competes too.
        vectors['e'] = descriptor(5)
        vectors['b'] = np.zeros(2304,dtype=np.float32)
        self.assertFalse(plan())


class OrganizerAutoSetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine,self.bulk,self.org,self.ids = fixture(self.temp.name)

    def act(self,action,**params):
        return self.org.mutate(action,{'job':'fixture-job','revision':self.org.state()['revision'],**params})

    def test_draft_selection_history_noop_reopen_and_batch_undo(self):
        before = self.org.sets()
        self.org.page('post','post:1',order='original')
        self.act('draft',ids=[self.ids[3]],new_name='My next shoot')
        result = self.act('auto_sets')['auto_result']
        self.assertEqual((result['created_sets'],result['new_members'],result['remaining']),(2,12,4))
        self.assertEqual(self.org.state()['view']['id'],'post:1')
        self.assertEqual(self.org.state()['selection'],[self.ids[3]])
        self.assertEqual(self.org.state()['new_name'],'My next shoot')
        self.assertEqual(set(self.org.page('unmatched','unmatched')['ids']),set(self.ids[2:6]))
        self.assertEqual(self.act('auto_sets')['auto_result']['matched'],0)
        self.org = Organizer(self.engine,self.bulk)
        self.org.bind()
        exported = self.org.export()
        self.assertEqual(len([g for g in exported['sets'] if g.get('auto_members')]),2)
        events = [e for e in exported['tracking']['events'] if e['kind']=='decision.automatic_set_match']
        self.assertEqual(len(events),1)
        self.assertTrue(events[0]['payload']['source_hashes'])
        self.act('undo')
        self.assertEqual(self.org.sets(),before)
        with self.org.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM tracking_events WHERE kind='decision.undo_automatic_set_match'").fetchone()[0],1)

    def test_pending_library_additions_are_removable_and_removed_photos_stay_manual(self):
        # Leave just one unassigned near the two confirmed Library exemplars.
        for n in range(3,6):self.org.vector_by_id[self.ids[n]]=descriptor(n)
        result = self.act('auto_sets')
        self.assertEqual(result['auto_result']['added_members'],1)
        target='library:existing'
        self.assertIn(self.ids[2],self.org.sets()[target]['auto_pending'])
        with self.assertRaisesRegex(ValueError,'preserved'):
            self.act('remove',target=target,ids=[self.ids[0]])
        self.act('remove',target=target,ids=[self.ids[2]])
        self.assertEqual(self.act('auto_sets')['auto_result']['added_members'],0)
        self.assertIn(self.ids[2],self.org.page('unmatched','unmatched')['ids'])
        self.act('undo')
        self.assertIn(self.ids[2],self.org.sets()[target]['auto_pending'])

    def test_import_cannot_move_auto_match_out_of_a_later_manual_library_set(self):
        self.act('auto_sets')
        ident=self.ids[7]
        def companion(route,body=None):
            if route=='/api/library':return {'characters':[{'id':'owner'}]}
            if route=='/api/organizer/preview':return {'token':'preview','conflicts':[{'id':ident}]}
            raise AssertionError(route)
        with patch.object(self.engine.library,'request',side_effect=companion):
            preview=self.org.transfer('preview',{'job':'fixture-job','character_id':'owner'})
            self.assertEqual(preview['protected_auto_conflicts'],1)
            with self.assertRaisesRegex(ValueError,'Skip conflicts'):
                self.org.transfer('apply',{'job':'fixture-job','token':'preview','conflicts':'move'})

    def test_stale_collection_revision_and_concurrent_scan(self):
        with self.assertRaises(ValueError):self.org.mutate('auto_sets',{'job':'elsewhere','revision':0})
        with self.assertRaises(ValueError):self.org.index(match_request={'job':'fixture-job','revision':98})
        with self.assertRaises(ValueError):self.org.mutate('auto_sets',{'job':'fixture-job','revision':98})
        self.org.job['running']=True
        with self.assertRaises(ValueError):self.act('auto_sets')
        self.assertEqual(len(self.org.sets()),1)

    def test_two_windows_and_failed_journal_write_leave_one_consistent_batch(self):
        with patch.object(tracking.journal(),'event',side_effect=RuntimeError('simulated journal failure')):
            with self.assertRaisesRegex(RuntimeError,'journal failure'):
                self.act('auto_sets')
        self.assertEqual(len(self.org.sets()),1)
        self.assertEqual(self.org.state()['revision'],0)
        other = Organizer(self.engine,self.bulk)
        other.bind()
        def match(org):
            try:return org.mutate('auto_sets',{'job':'fixture-job','revision':0})['auto_result']['created_sets']
            except ValueError as error:
                self.assertIn('another window',str(error))
                return 0
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(match,[self.org,other])),[0,2])
        self.assertEqual(len(self.org.sets()),3)

    def test_review_reopens_old_matches_and_preserves_the_manual_selection(self):
        with self.org.db() as db:
            group={'id':'old','name':'Old draft','members':self.ids[4:8],
                   'auto_members':self.ids[5:8],'auto_pending':self.ids[5:8]}
            db.execute('INSERT INTO sets VALUES (?,?,?)',(self.org.scope,'old',json.dumps(group)))
            tracking.journal().event(db,'decision.automatic_set_match',self.org.scope,
                {'sets':[{'id':'old','kind':'new','members':self.ids[5:8]}]})
        self.act('draft',ids=[self.ids[3]],new_name='Unfinished')
        body={'job':'fixture-job','period':'latest','target':'old'}
        page=self.org.review_matches(body)
        self.assertEqual((page['total'],page['sets'][0]['name']),(3,'Old draft'))
        self.assertEqual([r['id'] for r in page['examples']],[self.ids[4]])
        self.act('confirm_matches',target='old',ids=[self.ids[5]])
        self.assertTrue(self.org.review_matches(body)['photos'][0]['reviewed'])
        self.act('remove',target='old',ids=[self.ids[6]],match_review=True)
        self.assertEqual(self.org.state()['selection'],[self.ids[3]])
        self.assertEqual(self.org.state()['new_name'],'Unfinished')
        self.assertIn(self.ids[6],self.org.page('unmatched','unmatched')['ids'])
        self.assertEqual(self.org.review_matches(body)['total'],2)
        self.act('undo')
        self.assertEqual(self.org.review_matches(body)['total'],3)
        self.assertEqual(self.org.state()['selection'],[self.ids[3]])
        with self.assertRaises(ValueError):
            self.act('remove',target='old',ids=[self.ids[4]],match_review=True)
        with self.assertRaises(ValueError):self.org.review_matches({'job':'another'})

    def test_preparation_cannot_commit_after_cancellation_or_another_edit(self):
        body={'job':'fixture-job','revision':0}
        first=self.org.prepare_matches(body)
        self.org.match_preparation.thread.join(10)
        self.org.match_progress(first['token'],cancel=True)
        with self.assertRaises(ValueError):self.act('auto_sets',match_token=first['token'])
        self.assertEqual(len(self.org.sets()),1)
        second=self.org.prepare_matches(body)
        self.org.match_preparation.thread.join(10)
        self.act('draft',ids=[self.ids[8]])
        with self.assertRaisesRegex(ValueError,'selection changed'):self.act('auto_sets',match_token=second['token'])
        self.assertEqual(len(self.org.sets()),1)
        self.act('draft',ids=[])
        third=self.org.prepare_matches(body)
        self.org.match_preparation.thread.join(10)
        self.org.load_vectors()
        with self.assertRaises(ValueError):self.act('auto_sets',match_token=third['token'])
        self.assertEqual(len(self.org.sets()),1)
