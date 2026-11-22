import copy
import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_organizer import fixture
from engine import sha256, stat_key
from organizer import Organizer
from organizer_likely_sets import load_page
from likely_sets import propose, ranking_weights, review_queue
from set_matching import WEIGHTS
import tracking


def split_source_posts(bulk, ids):
    for n, ident in enumerate(ids):
        if n % 6 < 3 and n != 2:
            continue
        row = bulk.current['source_catalog'][ident]
        post = 'forum:second-' + str(n//6)
        origin = {'key':post,'kind':'forum','label':'Second post '+str(n//6+1),'path':row['path']}
        row['sources'] = {post: origin}
        row['origins'] = [origin]
    bulk.persist()


def add_post_extra(bulk, name='Extra portrait', sources=None):
    catalog = bulk.current['source_catalog']
    if sources is None:
        sources = {p: origin for item in catalog.values() for p, origin in item.get('sources', {}).items()
                   if origin.get('kind') in ('forum', 'instagram') and not origin.get('quarantine')}
    folder = Path(bulk.current['config']['roots'][0])
    path = folder / (name + '.jpg')
    Image.new('RGB', (80, 120), (50, 90, len(name))).save(path)
    digest = sha256(path)
    origins = {p: dict(origin, key=p, path=str(path)) for p, origin in sources.items()}
    catalog[digest] = dict(id=digest, sha=digest, path=str(path), stamp=stat_key(path),
                           sources=origins, origins=list(origins.values()), copies=[])
    bulk.persist()
    return digest


class RankingTests(unittest.TestCase):
    def test_broader_suggestions_cover_additional_photos_and_require_separate_approval(self):
        profile = np.zeros((4,3,768),np.float32)
        profile[:2,:,0] = 1
        profile[2,:,1] = 1
        profile[3,:,1:3] = [.712, (1-.712**2)**.5]
        vectors = {str(n):(v*np.sqrt(WEIGHTS)[:,None]).ravel() for n,v in enumerate(profile)}
        items = {i:{'sha':i,'path':i+'.jpg','sources':{'forum:'+i:{'kind':'forum'}}} for i in vectors}
        # Two different source posts also place the borderline pair together in an ordered compilation.
        for i in ('2','3'):
            items[i]['sources']['forum:compilation']={'kind':'forum'}
        close=review_queue(items,vectors,{},set(),set())[0]
        broad=review_queue(items,vectors,{},set(),set(),breadth='broader')[0]
        self.assertEqual([set(g['members']) for g in close],[{'0','1'}])
        self.assertEqual([set(g['members']) for g in broad],[{'2','3'}])
        self.assertTrue(broad[0]['source_links'])
        self.assertFalse(review_queue(items,vectors,{},set(),set(),[broad[0]['key']],'broader')[0])
        for i in ('2','3'):
            del items[i]['sources']['forum:compilation']
        self.assertFalse(review_queue(items,vectors,{},set(),set(),breadth='broader')[0])

    def test_local_weight_choice_uses_other_sets_for_check_and_needs_manual_examples(self):
        # The fit and validation cohorts contain different Sets and every true match crosses posts.
        labels, ids, homes = {}, [], []
        rows = np.zeros((3, 60*4, 768), np.float32)
        for group in range(60):
            for view in range(4):
                idx = 4*group+view
                ident = str(idx)
                labels[ident] = 'set'+str(group)
                ids.append(ident)
                homes.append('post'+str(view))
                rows[0,idx,group] = 1
                rows[1:,idx,(group + 1 + view) % 8] = 1
        blend, report = ranking_weights(rows,ids,homes,labels)
        self.assertTrue(report['adapted'])
        self.assertGreater(blend[0],WEIGHTS[0])
        self.assertGreater(report['candidate'],report['baseline'])
        self.assertGreaterEqual(report['held_out_sets'],6)
        _, empty = ranking_weights(rows,ids,homes,{})
        self.assertFalse(empty['adapted'])

    def test_second_list_can_use_a_shared_survivor_between_two_distinct_post_windows(self):
        items={}
        for i,posts in [('left',['p']),('link',['p','q']),('right',['q'])]:
            items[i]={'sha':i,'path':i+'.jpg','sources':{'forum:'+p:{'kind':'forum'} for p in posts}}
        data=np.zeros((2,3,768),np.float32)
        data[0,:,0]=1
        data[1,:,0:2]=[.71,(1-.71**2)**.5]
        vectors={i:(v*np.sqrt(WEIGHTS)[:,None]).ravel() for i,v in zip(('left','right'),data)}
        rows,_=review_queue(items,vectors,{},set(),set(),breadth='broader')
        self.assertEqual([set(r['members']) for r in rows],[{'left','right'}])
        self.assertEqual(rows[0]['source_links'][0]['survivor_sha'],'link')
        items['link']['copies']=[{'sha':'left'}]
        self.assertFalse(review_queue(items,vectors,{},set(),set(),breadth='broader')[0])

    def test_sources_are_distinct_and_duplicate_paths_never_make_extra_witnesses(self):
        ids = ['p'+str(n) for n in range(7)]
        descriptor = np.zeros((3,768),np.float32)
        descriptor[:,0] = np.sqrt(WEIGHTS)
        vectors = {i:descriptor.ravel() for i in ids}
        items = {i:{'sha':i,'path':i+'.jpg','sources':{'forum:one':{'kind':'forum'}}} for i in ids}
        def matches(held=(), mixed=(), groups=None):
            return propose(items,vectors,groups or {},set(held),set(mixed))[0]
        self.assertFalse(matches())
        items[ids[0]]['sources']['forum:alias']={'kind':'forum'}
        # If every photo has the very same reposts, they still share one primary post.
        for item in items.values():item['sources']['forum:alias']={'kind':'forum'}
        self.assertFalse(matches())
        for n,i in enumerate(ids):
            items[i]['sources']={'forum:'+str(n%2):{'kind':'forum'}}
        items['p2']['copies']=[{'sha':'p0'}]
        groups=matches()
        proposed=[i for g in groups for i in g['members']]
        self.assertEqual(len(proposed),len(set(proposed)))
        self.assertFalse({'p2','p0'}<=set(proposed))
        self.assertFalse(matches(mixed=['forum:1']))
        proposed=matches(groups={'prior':{'members':['p0']}})
        self.assertNotIn('p2',[i for g in proposed for i in g['members']])
        self.assertNotIn('p5',[i for g in matches(held=['p5']) for i in g['members']])


class ReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.engine,self.bulk,self.org,self.ids = fixture(temp.name)
        split_source_posts(self.bulk,self.ids)
        self.org.bound=None
        self.org.bind()
        self.job = self.bulk.current['id']

    def get(self, **body):
        return load_page(self.org,dict(job=self.job,**body))

    def act(self, action, **body):
        return self.org.mutate(action,dict(job=self.job,revision=self.org.state().get('revision',0),**body))

    def find(self, predicate):
        first = self.get()
        for n in range(first['total']):
            page = self.get(session=first['session'],offset=n)
            if predicate(page):return page
        self.fail('Expected a reviewable group')

    def test_partial_approval_is_manual_transaction_and_keeps_original_review_context(self):
        self.act('draft',ids=[self.ids[2]],new_name='Work in progress')
        baseline=self.org.sets()
        page=self.find(lambda p:not p['destination'] and len(p['photos'])>=3)
        self.assertEqual(self.org.sets(),baseline)
        self.assertGreaterEqual(len({p['source_key'] for p in page['photos']}),2)
        ids=[p['id'] for p in page['photos']]
        signed={'session':page['session'],'key':page['key']}
        self.act('approve_likely',**signed,ids=ids[:-1],target='',name='Two posts')
        groups=self.org.sets()
        created=next(g for g in groups.values() if g['name']=='Two Posts')
        self.assertEqual(set(created['members']),set(ids[:-1]))
        self.assertFalse(created.get('auto_members'))
        self.assertIn(ids[-1],self.org.page('unmatched','unmatched')['ids'])
        self.assertEqual(self.org.state()['selection'],[self.ids[2]])
        self.assertEqual(self.org.state()['new_name'],'Work in progress')
        with self.org.db() as db:
            raw=db.execute("SELECT payload FROM tracking_events WHERE kind='decision.approved_likely_group'").fetchone()
        event=json.loads(raw[0])
        self.assertEqual(set(event['selected']),set(ids[:-1]))
        self.assertEqual(set(event['source_hashes']),set(ids))
        self.assertTrue(event['rule'] and event['analysis_recipe'])
        self.assertLess(self.get(session=page['session'])['total'],page['total'])
        with self.assertRaises(ValueError):self.act('approve_likely',**signed,ids=ids,target='',name='Second copy')
        self.act('undo')
        self.assertEqual(self.org.sets(),baseline)
        self.assertEqual(self.org.state()['selection'],[self.ids[2]])

    def test_post_browsing_and_details_are_one_undoable_approval(self):
        extra = add_post_extra(self.bulk)
        unrelated = add_post_extra(self.bulk, 'Unrelated', {'lonely': {'kind':'forum','label':'Different post'}})
        self.org.bind()
        category = self.org.category_action('create_category', {'job':self.job,'name':'Editorial'})['category']['id']
        page = self.find(lambda p: not p['destination'])
        signed = {'session':page['session'], 'key':page['key']}
        ids = [p['id'] for p in page['photos']]
        before = self.org.sets()
        self.assertGreaterEqual(len(page['source_posts']), 2)
        for post in page['source_posts']:
            photos = self.get(**signed, source_post=post['id'])['photos']
            self.assertNotIn(unrelated, [p['id'] for p in photos])
            self.assertFalse(set(ids).intersection(p['id'] for p in photos))
        post = page['photos'][0]['source_key']
        extra_page = self.get(**signed, source_post=post)
        self.assertTrue(any(p['id'] == extra and not p['unavailable_reason'] for p in extra_page['photos']))
        with self.assertRaises(ValueError): self.get(**signed, source_post='lonely')
        with self.assertRaises(ValueError): self.act('approve_likely', **signed, ids=[*ids, unrelated])
        with self.assertRaises(ValueError): self.act('approve_likely', **signed, ids=[*ids, extra], set_details={'colors':'invalid'})
        self.assertEqual(self.org.sets(), before)
        self.act('approve_likely', **signed, ids=[ids[0], extra], set_details={
            'name':'Edited shoot','colors':['Blue'],'favorite':True,'categories':[category]})
        saved = next(g for g in self.org.sets().values() if g['name'] == 'Edited Shoot')
        self.assertEqual(saved['members'], [ids[0], extra])
        self.assertTrue(saved['favorite'])
        self.assertEqual(saved['colors'], ['Blue'])
        self.assertEqual(saved['categories'], [category])
        with self.org.db() as db:
            evidence = json.loads(db.execute("SELECT payload FROM tracking_events WHERE kind='decision.approved_likely_group'").fetchone()[0])
        self.assertEqual(set(evidence['manual_post_additions']), {extra})
        self.assertIn(post, evidence['manual_post_additions'][extra])
        self.assertEqual(evidence['source_hashes'][extra], extra)
        self.act('undo')
        self.assertEqual(self.org.sets(), before)
        match = self.find(lambda p: bool(p['destination']))
        target = match['destination']
        original = before[target]
        selected = match['photos'][0]['id']
        self.act('approve_likely', session=match['session'], key=match['key'], ids=[selected], target=target,
                 set_details={'name':'Reviewed original', 'favorite':True})
        updated = self.org.sets()[target]
        self.assertEqual(updated['name'], 'Reviewed Original')
        self.assertEqual(updated['members'], original['members'] + [selected])
        self.assertEqual(updated['categories'], original['categories'])
        self.assertEqual(updated['library_id'], original['library_id'])
        self.act('undo')
        self.assertEqual(self.org.sets(), before)

    def test_finish_partial_sets_uses_one_destination_and_approval_with_undo(self):
        with self.org.db() as db:
            group = {'id':'partial', 'name':'Partial', 'members':self.ids[9:11], 'auto_members':self.ids[9:11]}
            db.execute('INSERT INTO sets VALUES (?,?,?)', (self.org.scope, 'partial', json.dumps(group)))
        before = self.org.sets()
        page = self.get(breadth='partial')
        self.assertEqual(self.org.sets(), before)
        self.assertEqual(page['destination'], 'partial')
        self.assertEqual([p['id'] for p in page['photos']], self.ids[11:12])
        self.assertEqual({p['id'] for p in page['references']}, set(self.ids[9:11]))
        self.act('approve_likely', session=page['session'], key=page['key'], ids=self.ids[11:12], target='partial')
        self.assertEqual(set(self.org.sets()['partial']['members']), set(self.ids[9:12]))
        self.assertEqual(set(self.org.sets()['partial']['auto_members']), set(self.ids[9:11]))
        self.act('undo')
        self.assertEqual(self.org.sets(), before)

    def test_approve_checked_photos_as_a_held_set(self):
        page=self.get()
        members=[p['id'] for p in page['photos']][:2]
        self.act('approve_likely',session=page['session'],key=page['key'],ids=members,target='',name='Held shoot',hold_for_review=True)
        group=next(g for g in self.org.sets().values() if g['name']=='Held Shoot')
        self.assertTrue(group['under_review'])
        self.assertEqual(group['members'],members)
        self.act('undo')
        self.assertNotIn(group['id'],self.org.sets())

    def test_dismiss_survives_restart_and_undo_and_does_not_reject_photos(self):
        page=self.get()
        self.act('dismiss_likely',session=page['session'],key=page['key'])
        self.org=Organizer(self.engine,self.bulk);self.org.bind()
        self.assertEqual(self.get()['total'],page['total']-1)
        self.assertIn(page['photos'][0]['id'],self.org.page('unmatched','unmatched')['ids'])
        self.act('undo')
        self.assertEqual(self.get()['total'],page['total'])

    def test_existing_target_shows_references_and_late_memberships_or_edits_block_approval(self):
        page=self.find(lambda p:bool(p['destination']))
        rows=[p['id'] for p in page['photos']]
        self.assertTrue(page['references'])
        signed={'session':page['session'],'key':page['key'],'target':page['destination']}
        with self.assertRaises(ValueError):
            self.act('approve_likely',**signed,ids=rows+[page['references'][0]['id']])
        self.act('draft',ids=[rows[0]])
        with self.assertRaises(ValueError):self.act('approve_likely',**signed,ids=rows)
        self.act('draft',ids=[])
        self.org.refresh_library_placement(force=True)
        real=copy.deepcopy(self.org.library_placement)
        real['set_ids_by_sha']={self.org.catalog[rows[0]]['sha']:{'another-library-set'}}
        with patch.object(self.org,'refresh_library_placement'),patch.object(self.org,'library_placement',real):
            with self.assertRaises(ValueError):self.act('approve_likely',**signed,ids=rows)
        old=set(self.org.sets()[page['destination']]['members'])
        self.act('approve_likely',**signed,ids=rows)
        self.assertEqual(set(self.org.sets()[page['destination']]['members']),old|set(rows))
        self.assertFalse(self.org.sets()[page['destination']].get('auto_members'))
        self.act('undo')
        self.assertEqual(set(self.org.sets()[page['destination']]['members']),old)

    def test_applied_library_transfer_cannot_be_undone_as_a_draft(self):
        page=self.find(lambda p:not p['destination'])
        self.act('approve_likely',session=page['session'],key=page['key'],target='',name='Applied',
                 ids=[p['id'] for p in page['photos']])
        gid=self.org.state()['undo']['id']
        with self.org.db() as db:
            raw=db.execute('SELECT data FROM sets WHERE scope=? AND id=?',(self.org.scope,gid)).fetchone()[0]
            group=dict(json.loads(raw),applied_at=1234)
            db.execute('UPDATE sets SET data=? WHERE scope=? AND id=?',(json.dumps(group),self.org.scope,gid))
        with self.assertRaisesRegex(ValueError,'checkpoint'):self.act('undo')
        self.assertIn(gid,self.org.sets())

    def test_two_windows_cannot_double_assign_and_failed_journaling_is_atomic(self):
        p=self.find(lambda g:not g['destination'])
        request={'job':self.job,'session':p['session'],'key':p['key'],'target':'','name':'One Set',
                 'ids':[r['id'] for r in p['photos']],'revision':0}
        with patch.object(tracking.journal(),'event',side_effect=RuntimeError('journal unavailable')):
            with self.assertRaises(RuntimeError):self.org.mutate('approve_likely',request)
        self.assertEqual(self.org.state().get('revision',0),0)
        other=Organizer(self.engine,self.bulk);other.bind()
        p2=load_page(other,{'job':self.job})
        def run(args):
            org,body=args
            try:org.mutate('approve_likely',body);return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(run,[(self.org,request),(other,dict(request,session=p2['session']))]))
        self.assertEqual(sorted(outcomes),[False,True])
        self.assertEqual(sum(g['name']=='One Set' for g in self.org.sets().values()),1)
