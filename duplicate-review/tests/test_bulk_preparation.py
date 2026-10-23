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
        groups,_,_=propose(self.items(2,False),o,scene)
        self.assertEqual(len(groups),1)

    def test_bridge_does_not_merge_distinct_groups(self):
        o=np.stack([unit(0),unit(0),(.87*unit(0)+.493*unit(1)),unit(1),unit(1)]);o/=np.linalg.norm(o,axis=1,keepdims=True)
        scene=np.stack([np.stack([unit(i+10),unit(i+10)]) for i in range(5)])
        groups,_,_=propose(self.items(5),o,scene)
        self.assertTrue(all(len(g['members'])<5 for g in groups))


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
