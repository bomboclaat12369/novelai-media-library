import copy, io, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import Engine,sha256,stat_key,fingerprint
from bulk.workbench import Workbench
from organizer import Organizer


def fixture(root):
    root=Path(root);engine=Engine(root/'state');bulk=Workbench(engine);catalog={}
    for n in range(18):
        path=root/'images'/('Post '+str(n//6+1))/(str(n)+'.jpg');path.parent.mkdir(parents=True,exist_ok=True)
        im=Image.new('RGB',(600,900),[(57,91,122),(125,82,65),(73,112,83)][n//6]);draw=ImageDraw.Draw(im)
        draw.rectangle((80+n*7,160,450,750),fill=(180,150+n*3,115));draw.text((30,30),'Photo '+str(n),fill='white');im.save(path)
        digest=sha256(path);source={'key':'post:'+str(n//6+1),'kind':'forum','label':'2025-01-0'+str(n//6+1)+' · Post '+str(n//6+1),'path':str(path),'quarantine':False}
        catalog[digest]={'id':digest,'path':str(path),'stamp':stat_key(path),'sha':digest,'origins':[source],'sources':{source['key']:source},'copies':[],'reference':False,'existing_sets':['existing'] if n<2 else []}
        w,h,ph,mh,sketch=fingerprint(path)
        with engine.db() as db:db.execute('INSERT INTO cache(path,stamp,algorithm,sha,w,h,ph,mh,sketch,size,pixel) VALUES (?,?,?,?,?,?,?,?,?,?,?)',(str(path),stat_key(path),1,digest,w,h,ph,mh,sketch,path.stat().st_size,digest))
    ids=list(catalog);origin={'key':'post:recovered','kind':'forum','label':'Recovered post · no remaining originals','path':str(root/'old-copy.jpg'),'original_path':str(root/'old-copy.jpg'),'quarantine_path':str(root/'quarantine/old-copy.jpg'),'quarantine':True}
    catalog[ids[0]]['origins'].append(origin);catalog[ids[0]]['sources'][origin['key']]=origin
    path=root/'quarantine'/'unresolved.jpg';path.parent.mkdir(exist_ok=True);Image.new('RGB',(600,900),'#513d66').save(path);digest=sha256(path)
    source={'key':'post:1','kind':'forum','label':'2025-01-01 · Post 1','path':str(path),'quarantine':True,'original_path':str(root/'old-unresolved.jpg'),'quarantine_path':str(path)}
    catalog['q:'+digest]={'id':'q:'+digest,'sha':digest,'path':str(path),'stamp':stat_key(path),'quarantine_only':True,'origins':[source],'sources':{source['key']:source},'copies':[]}
    bulk.current={'id':'fixture-job','config':{'roots':[str(root/'images')]},'running':False,'phase':'Duplicate history ready','inventory_complete':True,'inventory_only':True,'source_catalog':catalog,'items':{},'proposals':[],'library_sets':{'existing':{'id':'existing','name':'Existing shoot'}},'inventory':{'unlinked_quarantine':1},'history_matches':{},'issues':[]};bulk.persist()
    org=Organizer(engine,bulk);org.bind()
    # Existing compatible features: no model or image reanalysis is needed.
    for n,ident in enumerate(ids):
        v=np.zeros((3,768),np.float32);v[:,n//6]=1
        with bulk.db() as db:db.execute('INSERT OR REPLACE INTO vectors VALUES (?,?,?)',(ident,org.recipe,v.tobytes()))
    org.load_vectors()
    return engine,bulk,org,ids

def add_instagram(bulk,ids):
    for n,number in enumerate([10,2,1]):
        for folder in ['IG','IG done']:
            path=rf'C:\collection\{folder}\test_account\P2\P2_{number}.jpg'
            origin={'key':'instagram:test_account:P2','kind':'instagram','label':'test_account / P2','path':path,'original_path':path,'quarantine_path':rf'C:\quarantine\{folder}\P2_{number}.jpg','quarantine':True}
            item=bulk.current['source_catalog'][ids[n]]
            item['origins'].append(origin);item['sources'][origin['key']]=origin
    # The same keepers can have a different filename order in a second post.
    for n,number in enumerate([1,2]):
        origin={'key':'instagram:test_account:P10','kind':'instagram','label':'test_account / P10','path':rf'C:\IG\test_account\P10\P10_{number}.jpg','quarantine':True}
        item=bulk.current['source_catalog'][ids[n]]
        item['origins'].append(origin);item['sources'][origin['key']]=origin
    bulk.persist()


class OrganizerTests(unittest.TestCase):
    def test_original_post_order_uses_keepers_without_inventory_or_image_reads(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp);add_instagram(bulk,ids);org.bound=None
            before=copy.deepcopy(bulk.current)
            with patch.object(Engine,'start',side_effect=AssertionError('No rescan')),patch.object(Workbench,'start',side_effect=AssertionError('No inventory')),patch('organizer.load_image',side_effect=AssertionError('No image decode')):
                ig=[p for p in org.summary()['posts'] if p['kind']=='instagram']
                self.assertEqual(len(ig),2)
                self.assertEqual(next(p for p in ig if p['id'].endswith(':P2'))['count'],3)
                page=org.page('post','instagram:test_account:P2',order='original')
                self.assertEqual(page['ids'],[ids[2],ids[1],ids[0]])
                self.assertEqual([i['display_name'] for i in page['images']],['P2_1.jpg','P2_2.jpg','P2_10.jpg'])
                for image in page['images']:
                    self.assertEqual(image['path'],before['source_catalog'][image['id']]['path'])
                    self.assertFalse(image['quarantined'])
                second=org.page('post','instagram:test_account:P10',order='original')
                self.assertEqual(second['ids'],ids[:2])
                by_keeper=org.page('post','instagram:test_account:P2',order='filename')
                self.assertEqual(by_keeper['ids'],ids[:3])
                org.mutate('save',{'job':'fixture-job','revision':0,'name':'IG shoot','ids':page['ids']})
                saved=next(g for g in org.sets().values() if g['name']=='IG shoot')
                self.assertEqual(set(saved['members']),set(ids[:3]))
                reopened=Organizer(engine,Workbench(engine))
                self.assertEqual(reopened.page('post','instagram:test_account:P2',order='original')['ids'],page['ids'])
            self.assertEqual(bulk.current,before)

    def test_saved_inventory_drafts_and_undo_survive_reopen_without_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp);before=copy.deepcopy(bulk.current)
            with patch.object(Engine,'start',side_effect=AssertionError('No rescan')),patch.object(Workbench,'start',side_effect=AssertionError('No inventory')),patch('organizer.load_image',side_effect=AssertionError('No image decode')):
                state=org.summary();self.assertEqual(state['images'],18);self.assertEqual(state['indexed'],18)
                recovered=org.page('post','post:recovered');self.assertEqual(recovered['ids'],[ids[0]])
                self.assertFalse(recovered['images'][0]['quarantined'])
                org.mutate('draft',{'job':'fixture-job','ids':[ids[2]],'target':''})
                result=org.mutate('save',{'job':'fixture-job','revision':0,'name':'My shoot','ids':[ids[2],ids[3]]})
                self.assertEqual(len(result['sets']),2)
                org2=Organizer(Engine(Path(temp)/'state'),Workbench(engine));reopened=org2.summary()
                self.assertEqual(reopened['state']['revision'],1);self.assertEqual(reopened['indexed'],18)
                self.assertEqual(reopened['state']['view']['id'],'post:recovered')
                org2.mutate('undo',{'job':'fixture-job','revision':1});self.assertEqual(len(org2.sets()),1)
                self.assertEqual(org2.state()['selection'],[ids[2],ids[3]])
                self.assertEqual(org2.index()['remaining'],0)
            self.assertEqual(bulk.current,before)

    def test_quarantine_is_evidence_and_rejects_stale_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp);q=next(i for i in org.catalog if i.startswith('q:'))
            with self.assertRaisesRegex(ValueError,'surviving'):org.mutate('save',{'job':'fixture-job','revision':0,'name':'Bad','ids':[q]})
            with self.assertRaisesRegex(ValueError,'another window'):org.mutate('save',{'job':'fixture-job','revision':99,'name':'Bad','ids':[ids[0]]})
            result=org.related({'ids':[ids[0]]});self.assertIn('post:recovered',[p['id'] for p in result['posts']]);self.assertTrue(result['sets']);self.assertNotIn(q,[i['id'] for i in result['images']])
            target=result['images'][0]['id'];org.mutate('reject',{'job':'fixture-job','revision':0,'ids':[target],'context':result['context']})
            self.assertNotIn(target,[i['id'] for i in org.related({'ids':[ids[0]]})['images']])

    def test_thumbnail_reuses_disk_cache_across_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp);first=org.preview(ids[0],1000)
            with patch('organizer.load_image',side_effect=AssertionError('Cached thumbnail must not decode again')):
                self.assertEqual(Organizer(engine,bulk).preview(ids[0],1000),first)
            image=Image.open(io.BytesIO(first));self.assertEqual(image.size,(600,900))

    def test_saved_library_additions_preserve_members_and_no_files_change(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp);before={i:Path(r['path']).read_bytes() for i,r in org.catalog.items()}
            result=org.mutate('save',{'job':'fixture-job','revision':0,'target':'library:existing','ids':[ids[3]]})
            g=next(g for g in result['sets'] if g['id']=='library:existing');self.assertEqual(set(g['members']),{ids[0],ids[1],ids[3]})
            self.assertEqual({i:Path(r['path']).read_bytes() for i,r in org.catalog.items()},before)
            self.assertEqual(bulk.current['library_sets']['existing']['name'],'Existing shoot')

    def test_visual_analysis_resumes_only_missing_features(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp);before=copy.deepcopy(bulk.current)
            with bulk.db() as db:db.execute('DELETE FROM vectors')
            org.load_vectors();encoded=[]
            class FakeEncoder:
                def __init__(self,store):pass
                def _prepare(self,ident):pass
                def _prepare_scene(self,ident):pass
                def _encode(self,path):
                    encoded.append(str(path))
                    if len(encoded)==2:org.cancel.set()
                    return np.ones(768,np.float32)
                def _encode_scene(self,path):return np.ones((2,768),np.float32)
            org.encoder_type=FakeEncoder
            org.index();org.thread.join(10)
            self.assertFalse(org.job['running']);self.assertEqual(len(org.vector_by_id),2)
            self.assertEqual(org.job['done'],2)
            self.assertIsNone(org.job['eta_seconds'])  # No ticking ETA while paused.
            org.index();org.thread.join(10)
            self.assertEqual(len(encoded),18);self.assertEqual(len(set(encoded)),18)
            self.assertEqual(len(org.vector_by_id),18);self.assertEqual(org.job['total'],16)
            self.assertEqual(org.job['eta_seconds'],0);self.assertEqual(bulk.current,before)

if __name__=='__main__':unittest.main()
