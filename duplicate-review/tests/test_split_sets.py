import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_organizer import fixture
from match_history import MatchHistory
from organizer import Organizer
from organizer_splits import comparison
from split_sets import compare_sets
import tracking


def seed_legacy(org, ids):
    """Two old automatic drafts that share an original shoot; neither name proves origin."""
    with org.db() as db:
        entries=[]
        for key,name,members in [('a','Spring Studio',ids[6:9]),('b','Window Session',ids[9:12])]:
            g={'id':key,'name':name,'members':members,'auto_members':members,'auto_pending':members,
               'auto_reviewed':members[:1],'colors':[],'categories':[],'favorite':key=='b',
               'library_id':None,'created':1,'updated':1}
            db.execute('INSERT INTO sets VALUES (?,?,?)',(org.scope,key,json.dumps(g)))
            entries.append({'id':key,'kind':'new','members':members})
        tracking.journal().event(db,'decision.automatic_set_match',org.scope,
                {'sets':entries,'source_hashes':{i:org.catalog[i]['sha'] for i in ids[6:12]}})


class Splits(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine,self.bulk,self.org,self.ids=fixture(self.tmp.name)
        self.engine.library.request=lambda *args,**kwargs: (_ for _ in ()).throw(ValueError('Offline fixture'))

    def act(self,action,**args):
        return self.org.mutate(action,dict(job='fixture-job',revision=self.org.state().get('revision',0),**args))

    def page(self,**args):
        return comparison(self.org,dict(job='fixture-job',**args))

    def decide(self,action,page,keep=None):
        return self.act(action,left=page['left']['id'],right=page['right']['id'],keep=keep or page['keep'],stamp=page['stamp'])

    def search(self,kind,origin):
        return {r['id'] for r in self.org.manual_search({'job':'fixture-job','source':'inventory','kind':kind,'match_origin':origin})['rows']}

    def test_older_batches_rename_move_remove_export_merge_and_undo(self):
        seed_legacy(self.org,self.ids)
        self.act('draft',ids=[self.ids[15]],new_name='Unfinished')
        p=self.page()
        self.assertEqual(p['total'],1)
        self.assertIn('positions',p['reason'])
        before=self.org.sets()
        self.decide('combine_split',p,'a')
        after=self.org.sets()
        self.assertNotIn('b',after)
        self.assertEqual(after['a']['members'],self.ids[6:12])
        self.assertEqual(after['a']['auto_reviewed'],[self.ids[6],self.ids[9]])
        self.assertEqual(after['a']['merged_sources'],['b'])
        self.assertTrue(after['a']['favorite'])
        self.assertEqual(self.org.state()['selection'],[self.ids[15]])
        self.assertEqual(self.org.state()['new_name'],'Unfinished')
        self.assertEqual(self.search('sets','automatic'),{'a'})
        self.assertEqual(self.search('images','automatic'),set(self.ids[6:12]))
        self.assertEqual(self.org.review_matches({'job':'fixture-job','period':'latest','target':'a'})['count'],6)
        self.assertEqual(self.search('images','approved'),set())
        history=self.org.export(False)['match_history']
        self.assertEqual(set(history['auto_created_sets']),{'a','b'})
        self.assertEqual(history['auto_placed_photos'][self.ids[9]][0]['set'],'b')
        self.act('undo')
        self.assertEqual(self.org.sets(),before)
        self.act('set_details',target='a',name='Renamed')
        self.act('remove',target='a',ids=[self.ids[6]],match_review=True)
        self.act('save',ids=[self.ids[6]],name='Shoot 700')
        self.org=Organizer(self.engine,self.bulk);self.org.bind()
        self.assertEqual(self.search('images','automatic'),set(self.ids[6:12]))
        self.assertEqual(self.search('sets','automatic'),{'a','b'})
        self.assertEqual(len(self.search('sets','contains')),3)
        self.assertFalse(self.org.sets()[next(k for k,v in self.org.sets().items() if v['name']=='Shoot 700')].get('auto_members'))

    def test_keep_separate_stale_requests_and_completed_transfer(self):
        seed_legacy(self.org,self.ids)
        p=self.page()
        self.decide('separate_split',p)
        self.assertFalse(self.page()['total'])
        self.act('undo')
        self.assertEqual(self.page()['total'],1)
        with self.assertRaisesRegex(ValueError,'changed'):
            self.act('combine_split',left='a',right='b',keep='a',stamp='wrong')
        self.decide('combine_split',self.page(),'a')
        with self.assertRaises(ValueError):
            self.decide('combine_split',p,'a')
        with self.org.db() as db:
            g=json.loads(db.execute('SELECT data FROM sets WHERE scope=? AND id=?',(self.org.scope,'a')).fetchone()[0])
            g.update(applied_at=10,library_id='transferred')
            db.execute('UPDATE sets SET data=? WHERE scope=? AND id=?',(json.dumps(g),self.org.scope,'a'))
        with self.assertRaisesRegex(ValueError,'Library'):self.act('undo')
        self.assertNotIn('b',self.org.sets())

    def test_strict_holds_second_fragment_on_rerun_and_supports_both_decisions(self):
        cores=[{'members':self.ids[6:9]},{'members':self.ids[9:12]}]
        def nominate(items,vectors,groups,excluded,*args):
            taken={i for g in groups.values() for i in g['members']} | excluded
            return {'new':[g for g in cores if not taken.intersection(g['members'])],'add':{}}
        with patch('organizer_auto_sets.match_sets',side_effect=nominate),patch('organizer_auto_sets.source_matches',return_value=[]):
            counts=self.act('auto_sets')['auto_result']
            self.assertEqual((counts['created_sets'],counts['held_fragments']),(1,1))
            self.assertEqual(self.act('auto_sets')['auto_result']['matched'],0)
        p=self.page()
        self.assertTrue(p['fragment'])
        self.assertEqual(p['right']['count'],3)
        self.assertEqual(len(self.search('images','automatic')),3)
        self.decide('separate_split',p)
        self.assertFalse(self.page()['total'])
        self.assertEqual(len(self.search('sets','automatic')),1)
        self.act('undo')
        self.assertTrue(self.page()['fragment'])
        self.decide('combine_split',self.page())
        self.assertFalse(self.page()['total'])
        self.assertEqual(len(self.org.sets()[p['keep']]['members']),6)
        self.assertEqual(len(self.search('images','automatic')),3)
        self.assertEqual(len(self.search('images','approved')),3)
        self.act('undo');self.act('undo')
        self.assertEqual(len(self.org.sets()),1)
        self.assertFalse(self.page()['total'])
        self.assertEqual(len(self.search('images','automatic')),3)

    def test_same_post_or_duplicate_copies_alone_do_not_nominate_a_pair(self):
        o=self.org;g={'a':{'members':self.ids[6:9]},'b':{'members':self.ids[12:15]}}
        for i in self.ids[12:15]:o.catalog[i]['sources']=o.catalog[self.ids[6]]['sources']
        self.assertFalse(compare_sets(o.catalog,o.vector_by_id,g,g,set()))
        g['b']['members']=self.ids[9:12]
        for a,b in zip(g['a']['members'],g['b']['members']):o.catalog[b]['copies']=[{'sha':o.catalog[a]['sha']}]
        self.assertFalse(compare_sets(o.catalog,o.vector_by_id,g,g,set()))

    def test_library_filters_use_stable_source_identities_before_pagination(self):
        seed_legacy(self.org,self.ids)
        with self.org.db() as db:
            raw=db.execute("SELECT data FROM sets WHERE scope=? AND id='a'",(self.org.scope,)).fetchone()[0]
            g=dict(json.loads(raw),library_id='linked-set')
            db.execute("UPDATE sets SET data=? WHERE scope=? AND id='a'",(json.dumps(g),self.org.scope))
        self.org.import_catalog=lambda body:{'character_id':'owner'}
        self.engine.library.catalog=lambda owner:{'files':[{'sha':h,'id':'lib-'+h} for h in self.ids]}
        calls=[]
        def request(route,body):
            calls.append(body)
            return {'library_instance':'test','rows':[]}
        self.engine.library.request=request
        for kind,wanted in [('sets',{'linked-set'}),('images',{'lib-'+h for h in self.ids[6:12]})]:
            self.org.manual_search({'job':'fixture-job','source':'library','kind':kind,'match_origin':'automatic'})
            self.assertEqual(set(calls[-1]['media_ids']),wanted)
