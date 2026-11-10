"""Conservative image framing, review identity, manual priority and persistence."""
import copy
import io
import json
import sqlite3
import unittest
from unittest.mock import patch
import test_runtime_stability as fixtures

R=fixtures.RUNTIME


class AutomaticFramingTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    post=fixtures.RuntimeStabilityTests.post

    def photo(self, width=800, height=1000, orientation=1):
        image=R['Image'].new('RGB',(width,height),(len(self.store.data['media'])*27%255,110,90))
        buffer=io.BytesIO();exif=R['Image'].Exif();exif[274]=orientation
        image.save(buffer,format='JPEG',exif=exif)
        with patch.object(self.store,'_queue_image_thumbnail'):
            item=self.store.import_bytes(buffer.getvalue(),'photo.jpg',self.character['id'],[],{'kind':'local'},'image/jpeg')[0]
        item.update(width=width,height=height,in_all=True)
        self.store.save()
        return item

    def call(self, action='state', **body):
        return self.store.collection_request(action,{'character_id':self.character['id'],**body})

    def edit(self, action, state, item, **body):
        return self.call(action,revision=state['collection']['revision'],media_id=item['id'],**body)

    def test_only_small_side_crops_and_full_height_are_automatic(self):
        eligible=self.photo();others=[self.photo(w,h) for w,h in [(750,1000),(667,1000),(1000,1000),(840,1000),(1600,900)]]
        original=(self.store.root/eligible['stored_rel']).read_bytes();ratings=copy.deepcopy(self.store.battles._load())
        state=self.call();key='image:'+eligible['id'];frame=state['collection']['frames'][key]
        self.assertEqual(set(state['collection']['frames']),{key})
        self.assertAlmostEqual(frame['zoom'],16/15)
        self.assertEqual((frame['x'],frame['y'],frame['fit']),(0,0,'contain'))
        self.assertAlmostEqual(1000*min(840/800,1120/1000)*frame['zoom'],1120)
        self.assertEqual(frame['reference'],{'left':.1,'top':.13,'width':.8,'height':1120/1500})
        meta=state['collection']['frame_meta'][key]
        self.assertEqual((meta['algorithm'],meta['checked']),('center-height-v1',False))
        self.assertAlmostEqual(meta['side_crop_percent'],3.125)
        self.assertEqual(original,(self.store.root/eligible['stored_rel']).read_bytes())
        self.assertEqual(ratings,self.store.battles._load())
        self.assertTrue(all('image:'+m['id'] not in state['collection']['frames'] for m in others))

    def test_source_header_and_exif_are_verified(self):
        rotated=self.photo(1000,800,6)
        wrong=self.photo(800,1000,6)  # Displayed landscape, despite stored portrait dimensions.
        misleading=self.photo(600,1000);misleading.update(width=800,height=1000)
        state=self.call();meta=state['collection']['frame_meta']
        self.assertEqual(meta['image:'+rotated['id']]['dimensions'],[800,1000])
        self.assertNotIn('image:'+wrong['id'],meta)
        self.assertNotIn('image:'+misleading['id'],meta)

    def test_unknown_held_flagged_library_crops_and_missing_sources_are_skipped(self):
        examples=[self.photo() for _ in range(7)]
        examples[0]['width']=None;examples[1]['in_review']=True;examples[2]['in_purgatory']=True
        examples[3]['flagged_for_removal']=True;examples[4]['crop_top']=.02
        examples[5]['stored_rel']='missing.jpg';examples[6]['in_all']=False
        self.assertEqual(self.call()['collection']['frames'],{})

    def test_legacy_manual_default_and_profile_framing_are_preserved(self):
        a,b,c=self.photo(),self.photo(),self.photo()
        frames={'image:'+a['id']:{'x':4,'y':-8,'zoom':1.2,'fit':'fill'},
                'image:'+b['id']:{'x':0,'y':0,'zoom':1,'fit':'contain'},
                'profile:'+c['id']:{'x':0,'y':0,'zoom':1,'fit':'contain'}}
        self.character['collection']={'frames':copy.deepcopy(frames)}
        state=self.call()
        for key,value in frames.items():self.assertEqual(state['collection']['frames'][key],value)
        self.assertEqual(set(state['collection']['frame_meta']),{'image:'+c['id']})
        snapshot=self.store.db_path.read_bytes();again=self.call()
        self.assertEqual(state['collection'],again['collection']);self.assertEqual(snapshot,self.store.db_path.read_bytes())

    def test_check_and_restore_use_exact_auto_token_and_keep_manual_opt_out(self):
        item=self.photo();state=self.call();key='image:'+item['id'];token=state['collection']['frame_meta'][key]['token']
        checked=self.edit('frame-review',state,item,token=token,checked=True)
        self.assertEqual(checked['collection']['frames'],state['collection']['frames'])
        self.assertTrue(checked['collection']['frame_meta'][key]['checked'])
        with self.assertRaises(ValueError):self.edit('frame-review',state,item,token=token,checked=False)
        with self.assertRaises(ValueError):self.edit('frame-review',checked,item,token='stale',checked=True)
        with self.assertRaises(ValueError):self.edit('frame-review',checked,item,token=token,checked='yes')
        restored=self.edit('frame-default',checked,item,token=token)
        self.assertEqual(restored['collection']['frames'][key],{'x':0,'y':0,'zoom':1,'fit':'contain'})
        self.assertEqual(restored['collection']['frame_meta'][key]['reason'],'restored_default')
        new=self.photo();reopened=R['LibraryStore'](self.store.root).collection_request('state',{'character_id':self.character['id']})
        self.assertEqual(reopened['collection']['frames'][key]['zoom'],1)
        self.assertEqual(reopened['collection']['frame_meta']['image:'+new['id']]['mode'],'auto')

    def test_manual_edit_and_manual_reset_cannot_be_reapplied_automatically(self):
        item=self.photo();state=self.call();key='image:'+item['id'];token=state['collection']['frame_meta'][key]['token']
        for frame in ({'x':2,'y':-3,'zoom':1.12,'fit':'contain'},{'x':0,'y':0,'zoom':1,'fit':'contain'}):
            state=self.edit('frame',state,item,key=key,frame=frame)
            self.assertEqual(self.call()['collection']['frames'][key],frame)
            self.assertEqual(state['collection']['frame_meta'][key]['mode'],'manual')
        with self.assertRaises(ValueError):self.edit('frame-default',state,item,token=token)
        self.assertEqual(self.call()['collection']['frames'][key]['zoom'],1)

    def test_new_source_invalidates_review_and_rejects_a_stale_check(self):
        item=self.photo();state=self.call();key='image:'+item['id'];token=state['collection']['frame_meta'][key]['token']
        state=self.edit('frame-review',state,item,token=token,checked=True)
        item['sha256']='replacement-source';self.store.save()
        with self.assertRaises(ValueError):self.edit('frame-review',state,item,token=token,checked=True)
        new=self.call();meta=new['collection']['frame_meta'][key]
        self.assertFalse(meta['checked']);self.assertNotEqual(meta['token'],token)
        # A taller replacement no longer qualifies, so the old automatic crop disappears.
        R['Image'].new('RGB',(600,1000)).save(self.store.root/item['stored_rel'])
        item.update(sha256='tall-replacement',width=600,height=1000);self.store.save()
        self.assertNotIn(key,self.call()['collection']['frames'])

    def test_checkpoints_and_journal_retain_auto_and_review_evidence(self):
        item=self.photo();state=self.call();key='image:'+item['id'];token=state['collection']['frame_meta'][key]['token']
        checkpoint=self.store.create_checkpoint({})
        self.edit('frame-review',state,item,token=token,checked=True)
        preview=self.store.checkpoint_preview({'id':checkpoint['id']})
        self.store.checkpoint_restore({'id':checkpoint['id'],'token':preview['token']})
        restored=self.call();self.assertFalse(restored['collection']['frame_meta'][key]['checked'])
        self.assertEqual(restored['collection']['frame_meta'][key]['token'],token)
        with sqlite3.connect(self.store.tracking.path) as db:events=R['TrackingJournal'].rows(db)
        evidence=json.dumps(events)
        self.assertIn('center-height-v1',evidence);self.assertIn('checked_at',evidence)

    def test_failed_automatic_save_has_no_partial_state_or_history(self):
        item=self.photo();before=self.store.db_path.read_bytes()
        with sqlite3.connect(self.store.tracking.path) as db:events=R['TrackingJournal'].rows(db)
        with patch.object(self.store,'_write_atomic',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.call()
        self.assertEqual(self.store.db_path.read_bytes(),before)
        self.assertNotIn('collection',self.store.character(self.character['id']))
        with sqlite3.connect(self.store.tracking.path) as db:self.assertEqual(events,R['TrackingJournal'].rows(db))
        self.assertIn('image:'+item['id'],self.call()['collection']['frames'])

    def test_review_endpoint_rejects_other_characters(self):
        item=self.photo();state=self.call();token=state['collection']['frame_meta']['image:'+item['id']]['token']
        other=self.store.add_character('Other')
        code,_=self.post('/api/collection/frame-review',{'character_id':other['id'],'revision':'','media_id':item['id'],'token':token,'checked':True})
        self.assertEqual(code,400)
        code,result=self.post('/api/collection/frame-review',{'character_id':self.character['id'],'revision':state['collection']['revision'],'media_id':item['id'],'token':token,'checked':True})
        self.assertEqual(code,200,result)


if __name__=='__main__':unittest.main()
