import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import Engine
from bulk.sources import source_of
from bulk.grouping import propose
from bulk.workbench import Workbench


def unit(axis):
    a=np.zeros(768,np.float32);a[axis]=1;return a


class FakeEncoder:
    MODEL_SHA='fixture';SCENE_RECIPE='fixture'
    def _encode(self,path):
        # Same-shoot fixture filenames begin with A/B; cache tests need no model download.
        return unit(0 if Path(path).name.startswith('A') else 1)
    def _encode_scene(self,path):
        a=self._encode(path);return np.stack([a,a])


def create(path,color):
    path.parent.mkdir(parents=True,exist_ok=True);Image.new('RGB',(160,240),color).save(path)


class Sources(unittest.TestCase):
    def test_batch_and_date_independent_forum_identity(self):
        a=source_of(r'C:\Mikayla\_Duplicate_Review_Quarantine\abc\Mikayla-Images-By-Post\2024-10-01 - Post 3672997\A.jpg','smg')
        b=source_of(r'C:\Mikayla\_Duplicate_Review_Quarantine\def\Mikayla-Videos-And-ImagePond\2026-02-16 - Post 3672997\B.jpg','smg')
        self.assertEqual(a['key'],b['key']);self.assertTrue(a['quarantine']);self.assertNotEqual(a['path'],b['path'])
        c=source_of('/other/2024-10-01 - Post 4826641/A.jpg','smg')
        self.assertNotEqual(a['key'],c['key'])
        self.assertNotEqual(a['key'],source_of('/other/Post 3672997/A.jpg','another-forum')['key'])

    def test_ig_case_sensitive_shortcode(self):
        a=source_of(r'C:\SMG\Mikayla\_Duplicate_Review_Quarantine\abc\Mikayla IG\mikaylademaiter\DVaoHqNjuu-\1.jpg')
        b=source_of('/SMG/other IG/MIKAYLADEMAITER/DVaoHqNjuu-/2.jpg')
        self.assertEqual(a['key'],b['key']);self.assertEqual(a['kind'],'instagram')
        self.assertNotEqual(a['key'],source_of('/SMG/other IG/mikaylademaiter/dvaohqnjuu-/2.jpg')['key'])
        self.assertEqual(source_of('/random/dvaohqnjuu-/2.jpg')['kind'],'folder')


class Grouping(unittest.TestCase):
    def items(self,n,shared=True):
        return [{'id':str(i),'sources':{'forum:smg:1':{'kind':'forum'}} if shared else {},'reference':False} for i in range(n)]

    def test_mixed_post_splits_and_partial_outfit_context(self):
        # Three A images: two matching outfits plus one different appearance in
        # the same scene. Three unrelated B images share the very same post.
        o=np.stack([unit(0),unit(0),unit(2),unit(1),unit(1),unit(1)])
        scene=np.stack([np.stack([unit(0),unit(0)])]*3+[np.stack([unit(1),unit(1)])]*3)
        groups,singles,_=propose(self.items(6),o,scene)
        ids={frozenset(r['index'] for r in g['members']) for g in groups}
        self.assertEqual(ids,{frozenset([0,1,2]),frozenset([3,4,5])});self.assertFalse(singles)

    def test_source_alone_never_groups_compilation(self):
        o=np.stack([unit(i) for i in range(10)]);scene=np.stack([np.stack([unit(i),unit(i)]) for i in range(10)])
        groups,singles,_=propose(self.items(10),o,scene)
        self.assertFalse(groups);self.assertEqual(len(singles),10)

    def test_original_outfit_match_not_diluted_by_context(self):
        o=np.stack([unit(0),unit(0)]);scene=np.stack([np.stack([unit(i),unit(i)]) for i in (2,3)])
        items=self.items(2,False)
        for item in items:item['clothing_cue']={'state':'present'}
        groups,_,_=propose(items,o,scene)
        self.assertEqual(len(groups),1)

    def test_bridge_does_not_merge_distinct_groups(self):
        o=np.stack([unit(0),unit(0),(.87*unit(0)+.493*unit(1)),unit(1),unit(1)]);o/=np.linalg.norm(o,axis=1,keepdims=True)
        scene=np.stack([np.stack([unit(i+10),unit(i+10)]) for i in range(5)])
        groups,_,_=propose(self.items(5),o,scene)
        self.assertTrue(all(len(g['members'])<5 for g in groups))


    def test_bare_or_uncertain_appearance_cannot_group_unrelated_settings(self):
        o=np.stack([unit(0)]*5)
        # Only members 3 and 4 share a scene. All five look alike to the outfit encoder.
        scene=np.stack([np.stack([unit(i),unit(i)]) for i in (5,6,7,7,8)])
        items=self.items(5)
        for i,item in enumerate(items):item['clothing_cue']={'state':'limited' if i%2 else 'uncertain'}
        groups,singles,_=propose(items,o,scene)
        self.assertEqual([{r['index'] for r in g['members']} for g in groups],[{2,3}])
        self.assertEqual(set(singles),{0,1,4})

    def scene_from_gram(self,full,outer):
        def vectors(gram):
            a=np.linalg.cholesky(np.array(gram,dtype=np.float64)).astype(np.float32)
            return np.pad(a,((0,0),(0,768-a.shape[1])))
        return np.stack([vectors(full),vectors(outer)],axis=1)

    def test_consistent_post_reunites_fragments_without_all_to_all_matches(self):
        full=[[1,.94,.69,.75],[.94,1,.75,.76],[.69,.75,1,.94],[.75,.76,.94,1]]
        outer=[[1,.98,.88,.88],[.98,1,.88,.88],[.88,.88,1,.98],[.88,.88,.98,1]]
        scene=self.scene_from_gram(full,outer);o=np.stack([unit(i) for i in range(4)])
        stats={};groups,singles,_=propose(self.items(4),o,scene,lambda **k:stats.update(k))
        self.assertEqual([{r['index'] for r in g['members']} for g in groups],[{0,1,2,3}])
        self.assertFalse(singles);self.assertEqual(stats['grouping_changes']['fragment_merges'],1)
        # Without the shared consistent source, these weaker scene links cannot seed/merge a set.
        groups,_,_=propose(self.items(4,False),o,scene)
        self.assertTrue(all(len(g['members'])<4 for g in groups))

    def test_mixed_post_retains_two_coherent_shoots(self):
        full=np.array([[1,.94,.69,.75],[.94,1,.75,.76],[.69,.75,1,.94],[.75,.76,.94,1]])
        outer=np.array([[1,.98,.88,.88],[.98,1,.88,.88],[.88,.88,1,.98],[.88,.88,.98,1]])
        blank=np.zeros((4,4))
        scene=self.scene_from_gram(np.block([[full,blank],[blank,full]]),np.block([[outer,blank],[blank,outer]]))
        o=np.stack([unit(i) for i in range(8)]);stats={}
        groups,singles,_=propose(self.items(8),o,scene,lambda **k:stats.update(k))
        self.assertEqual({frozenset(r['index'] for r in g['members']) for g in groups},{frozenset(range(4)),frozenset(range(4,8))})
        self.assertFalse(singles)
        profile=stats['source_profiles']['forum:smg:1']
        self.assertFalse(profile['coherent']);self.assertEqual(sorted(profile['coherent_subgroups']),[4,4])

    def test_unassigned_gets_two_independent_core_supports(self):
        full=[[1,.95,.95,.74],[.95,1,.95,.74],[.95,.95,1,.68],[.74,.74,.68,1]]
        outer=[[1,.98,.98,.88],[.98,1,.98,.88],[.98,.98,1,.88],[.88,.88,.88,1]]
        scene=self.scene_from_gram(full,outer);o=np.stack([unit(i) for i in range(4)])
        stats={};groups,singles,_=propose(self.items(4),o,scene,lambda **k:stats.update(k))
        self.assertEqual(len(groups),1);self.assertEqual(len(groups[0]['members']),4);self.assertFalse(singles)
        self.assertEqual(stats['grouping_changes']['unassigned_attached'],1)


class WorkbenchChecks(unittest.TestCase):
    def test_recovery_review_restart_and_readonly_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);state=root/'state';incoming=root/'incoming'
            for name,color in [('A1',(200,20,20)),('A2',(210,30,30)),('A3',(220,40,40)),('B1',(10,90,10)),('B2',(20,100,20))]:
                create(incoming/'batch-one'/'2024-10-01 - Post 3672997'/(name+'.png'),color)
            original=incoming/'batch-one'/'2024-10-01 - Post 3672997'/'A1.png'
            quarantine=incoming/'_Duplicate_Review_Quarantine'/'abc'/'batch-two'/'2025-10-01 - Post 777'/'A1.png'
            quarantine.parent.mkdir(parents=True);quarantine.write_bytes(original.read_bytes())
            before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in incoming.rglob('*.png')}
            engine=Engine(state);w=Workbench(engine,lambda _:FakeEncoder())
            w.start({'roots':[str(incoming)],'limit':200});w.thread.join(20)
            self.assertFalse(w.thread.is_alive());self.assertNotIn('error',w.status())
            self.assertEqual(w.current['inventory']['multiple_source_images'],1)
            self.assertEqual(w.current['inventory']['unlinked_quarantine'],0)
            self.assertEqual(len(w.current['proposals']),2)
            group=w.current['proposals'][0];self.assertEqual(len(group['members']),3)
            self.assertTrue(any(len(i['sources'])==2 for i in w.current['items'].values()))
            with engine.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM moves').fetchone()[0],0)
            w.review({'job':w.current['id'],'group':group['id'],'action':'accepted','name':'Red outfit','colors':['red'],'members':group['members']})
            self.assertEqual(w.status()['evaluation']['unchanged'],1)
            with self.assertRaises(ValueError):w.review({'job':'wrong','group':group['id'],'action':'accepted'})
            reopened=Workbench(engine,lambda _:FakeEncoder());self.assertEqual(reopened.status()['evaluation']['accepted'],1)
            self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in incoming.rglob('*.png')})
            # Same file contents reuse analysis across subsequent evaluations.
            reopened.start({'roots':[str(incoming)],'limit':200});reopened.thread.join(20)
            self.assertEqual(reopened.current['cached_features'],5)
            # Export contains no vectors/image bytes and explicitly describes drafts.
            exported=reopened.export();self.assertIn('No files were moved',exported['notice'])
            self.assertNotIn('vectors',exported)

    def test_model_preparation_failure_stops_once_and_cached_replay_needs_no_prepare(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);incoming=root/'incoming';engine=Engine(root/'state')
            create(incoming/'A1.png',(20,50,80));create(incoming/'A2.png',(30,60,90))
            class Encoder(FakeEncoder):
                attempts=0
                def _prepare(self,_):
                    self.attempts+=1;raise ValueError('Fixture download failure')
                def _prepare_scene(self,_):raise AssertionError('Must not reach scene preparation')
            enc=Encoder();w=Workbench(engine,lambda _:enc)
            w.start({'roots':[str(incoming)],'limit':200});w.thread.join(20)
            self.assertEqual(enc.attempts,1);self.assertIn('preparation failed',w.current['error'])
            w.encoder_factory=lambda _:FakeEncoder();w.start({'roots':[str(incoming)],'limit':200});w.thread.join(20)
            self.assertNotIn('error',w.current);ident=w.current['id'];w.encoder_factory=lambda _:enc
            w.reevaluate({'job':ident});w.thread.join(20)
            self.assertNotIn('error',w.current);self.assertEqual(enc.attempts,1);self.assertEqual(w.current['cached_features'],2)

    def test_reevaluate_preserves_cohort_reviews_and_caches_without_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);incoming=root/'incoming';engine=Engine(root/'state')
            create(incoming/'Post 1'/'A1.png',(20,50,80));create(incoming/'Post 1'/'A2.png',(30,60,90))
            w=Workbench(engine,lambda _:FakeEncoder());w.start({'roots':[str(incoming)],'limit':200});w.thread.join(20)
            original=copy.deepcopy(w.current);group=w.current['proposals'][0]
            w.review({'job':original['id'],'group':group['id'],'action':'accepted','name':'Keep this review'})
            create(incoming/'Post 1'/'B-new.png',(40,70,100))
            with patch.object(w,'inventory',side_effect=AssertionError('Must not resample')):
                w.reevaluate({'job':original['id']});w.thread.join(20)
            self.assertNotIn('error',w.current);self.assertEqual(set(w.current['items']),set(original['items']))
            self.assertEqual(w.current['cached_features'],2);self.assertEqual(w.current['comparison']['same_images'],2)
            self.assertEqual(w.status()['evaluation']['accepted'],0)
            rerun=w.current['id'];w.activate(original['id'])
            self.assertEqual(w.current['proposals'][0]['name'],'Keep this review');self.assertEqual(w.status()['evaluation']['accepted'],1)
            # Changed originals fail explicitly rather than substituting a new image or silently shrinking the cohort.
            create(incoming/'Post 1'/'A1.png',(100,110,120))
            w.reevaluate({'job':original['id']});w.thread.join(20)
            self.assertIn('error',w.current);self.assertFalse(w.current.get('complete',False))
            w.activate(rerun);self.assertEqual(len(w.current['items']),2)

    def test_new_source_links_require_verification_and_reuse_results(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);incoming=root/'incoming';engine=Engine(root/'state')
            survivor=incoming/'Post 1'/'A.png';create(survivor,(10,20,30))
            other=incoming/'_Duplicate_Review_Quarantine'/'x'/'Post 2'/'B.png';create(other,(40,50,60))
            for file in (survivor,other):
                digest=hashlib.sha256(file.read_bytes()).hexdigest()
                with engine.db() as db:
                    db.execute('INSERT INTO cache(path,sha,ph,mh) VALUES (?,?,?,?)',(str(file),digest,'0','0'))
            w=Workbench(engine,lambda _:FakeEncoder());w.current={'config':{},'issues':[]}
            config={'roots':[str(incoming)],'forum':'smg','person':'Mikayla','character_id':''}
            with patch('bulk.workbench.same_photo.verify',return_value=False) as verify:
                w.identities(w.inventory(config));self.assertEqual(verify.call_count,1)
                self.assertEqual(w.current['inventory']['unlinked_quarantine'],1)
                w.identities(w.inventory(config));self.assertEqual(verify.call_count,1)
            with w.db() as db:db.execute('DELETE FROM aliases')
            with patch('bulk.workbench.same_photo.verify',return_value=True) as verify:
                items=w.identities(w.inventory(config));self.assertEqual(verify.call_count,1)
                self.assertEqual(set(items[0]['sources']),{'forum:smg:1','forum:smg:2'})
                self.assertEqual(w.current['inventory']['newly_verified_links'],1)
                w.identities(w.inventory(config));self.assertEqual(verify.call_count,1)

    def test_visual_alias_requires_direct_verified_relationship(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);incoming=root/'incoming';engine=Engine(root/'state')
            survivor=incoming/'Post 1'/'A.png';create(survivor,(10,20,30))
            gone=incoming/'_Duplicate_Review_Quarantine'/'x'/'batch'/'Post 2'/'different.png';create(gone,(40,50,60))
            orphan=incoming/'_Duplicate_Review_Quarantine'/'y'/'batch'/'Post 3'/'discarded.png';create(orphan,(70,80,90))
            shas=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (survivor,gone,orphan)]
            with engine.db() as db:
                db.execute('INSERT INTO verified_copies VALUES (?,1)',('same-photo-1:'+shas[1]+':'+shas[0],))
                # A chain to a quarantined keeper must not become proof to the survivor.
                db.execute('INSERT INTO verified_copies VALUES (?,1)',('same-photo-1:'+shas[2]+':'+shas[1],))
            w=Workbench(engine,lambda _:FakeEncoder());w.current={'config':{},'issues':[]}
            config={'roots':[str(incoming)],'forum':'smg','person':'Mikayla','character_id':''}
            items=w.identities(w.inventory(config))
            self.assertEqual(len(items),1);self.assertEqual(set(items[0]['sources']),{'forum:smg:1','forum:smg:2'})
            self.assertEqual(w.current['inventory']['unlinked_quarantine'],1)

if __name__=='__main__':unittest.main()
