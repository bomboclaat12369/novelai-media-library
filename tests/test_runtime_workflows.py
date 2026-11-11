"""Recovery, organizer transfer, video-frame and ranking concurrency regressions."""
import copy,hashlib,json,random,shutil,subprocess,threading,unittest
from pathlib import Path
from unittest.mock import patch
import test_runtime_stability as fixtures

class WorkflowTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image
    post=fixtures.RuntimeStabilityTests.post

    def draft(self,existing=False):
        path=self.store.root/'external'/'photo.png';path.parent.mkdir();path.write_bytes(b'new unique source')
        catalog={'new':{'id':'new','path':str(path),'sha':hashlib.sha256(path.read_bytes()).hexdigest(),'origins':[]}}
        members=['new']
        if existing:
            item=self.import_image(1);catalog['old']={'id':'old','path':str(self.store.root/item['stored_rel']),'sha':item['sha256']};members.append('old')
            self.store.create_set(self.character['id'],'Old set',[item['id']])
        draft={'format':'folder-organizer-2','scope':'fixture','config':{'roots':[str(path.parent)]},'source_catalog':catalog,
            'sets':[{'id':'draft','name':'New set','members':members,'colors':['Blue'],'categories':[],'saved':True,'favorite':True}]}
        return {'character_id':self.character['id'],'draft':draft}

    def test_failed_set_write_restores_memory_and_later_save(self):
        item=self.import_image(1);group=self.store.create_set(self.character['id'],'Original',[item['id']]);before=copy.deepcopy(self.store.data)
        with patch.object(self.store,'_write_atomic',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.store.update_set(group['id'],name='Must not stick',media_ids=[])
        self.assertEqual(self.store.data,before)
        self.store.save();reopened=type(self.store)(self.store.root)
        self.assertEqual(reopened.set_item(group['id'])['name'],'Original')
        self.assertEqual(reopened.set_item(group['id'])['media_ids'],[item['id']])
        self.assertEqual(self.store.diagnostics()['recent_errors'][-1]['operation'],'metadata_save')

    def test_transfer_import_resume_moves_and_repeated_apply(self):
        draft=self.draft(True);plan=self.store.organizer_preview(draft)
        self.assertEqual(len(plan['imports']),1);self.assertEqual(len(plan['conflicts']),1)
        body={'token':plan['token'],'id':'new'}
        first=self.store.organizer_import(body);second=self.store.organizer_import(body)
        self.assertEqual(first['id'],second['id']);self.assertTrue(second['reused'])
        self.assertFalse(self.store.media_item(first['id'])['in_all'])
        result=self.store.organizer_apply({'token':plan['token'],'conflicts':'move'})
        self.assertEqual(self.store.organizer_apply({'token':plan['token'],'conflicts':'move'}),result)
        new=self.store.set_item(result['mapping']['draft']);self.assertEqual(len(new['media_ids']),2)
        old=next(g for g in self.store.data['sets'] if g['name']=='Old Set');self.assertEqual(old['media_ids'],[])
        again=self.store.organizer_preview(draft);self.assertEqual(again['imports'],[])
        self.store.organizer_apply({'token':again['token'],'conflicts':'move'})
        self.assertEqual(len(self.store.data['media']),2);self.assertEqual(len(self.store.data['sets']),2)

    def test_opening_battles_preserves_pending_import_preview(self):
        draft = self.draft(True)
        token = self.store.organizer_preview(draft)['token']
        owner = self.character['id']
        self.assertNotIn('collection', self.store.character(owner))
        self.store.collection_request('state', {'character_id': owner})
        earned = copy.deepcopy(self.store.character(owner)['collection'])
        self.store.organizer_import({'token': token, 'id': 'new'})
        result = self.store.organizer_apply({'token': token})
        self.assertEqual(result['sets'], 1)
        self.assertEqual(self.store.character(owner)['collection'], earned)

    def test_transfer_skip_and_stale_preview(self):
        draft=self.draft(True);plan=self.store.organizer_preview(draft)
        self.store.organizer_import({'token':plan['token'],'id':'new'})
        self.store.update_set(self.store.data['sets'][0]['id'],name='Changed after preview')
        with self.assertRaisesRegex(ValueError,'membership changed'):self.store.organizer_apply({'token':plan['token']})
        plan=self.store.organizer_preview(draft);result=self.store.organizer_apply({'token':plan['token'],'conflicts':'skip'})
        self.assertEqual(len(self.store.set_item(result['mapping']['draft'])['media_ids']),1)
        self.assertEqual(len(self.store.data['sets'][0]['media_ids']),1)

    def test_changed_source_rejected_and_apply_failure_atomic(self):
        draft=self.draft();plan=self.store.organizer_preview(draft)
        path=Path(draft['draft']['source_catalog']['new']['path']);path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):self.store.organizer_import({'token':plan['token'],'id':'new'})
        path.write_bytes(b'new unique source');plan=self.store.organizer_preview(draft);self.store.organizer_import({'token':plan['token'],'id':'new'})
        before=copy.deepcopy(self.store.data)
        with patch.object(self.store,'_write_atomic',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.store.organizer_apply({'token':plan['token']})
        self.assertEqual(self.store.data,before)
        self.store.organizer_apply({'token':plan['token']});self.assertEqual(len(self.store.data['sets']),1)

    def test_checkpoint_restores_battles_and_metadata_with_rollback(self):
        item=self.import_image(1);self.store.battles._save({'version':1,'rating_model':self.store.battles.MODEL,'boards':{}})
        cp=self.store.create_checkpoint({});self.store.set_favorite(item['id'],True)
        plan=self.store.checkpoint_preview({'id':cp['id']});self.assertEqual(plan['missing_media'],[])
        self.store.set_crop(item['id'],.1,.1)
        with self.assertRaisesRegex(ValueError,'State changed'):self.store.checkpoint_restore({'id':cp['id'],'token':plan['token']})
        plan=self.store.checkpoint_preview({'id':cp['id']});result=self.store.checkpoint_restore({'id':cp['id'],'token':plan['token']})
        self.assertFalse(self.store.media_item(item['id'])['favorite']);self.assertEqual(self.store.media_item(item['id'])['crop_top'],0)
        self.assertTrue((self.store.backup_dir/('checkpoint-'+result['rollback']+'.zip')).exists())

    def test_checkpoint_with_originals_recovers_missing_file(self):
        item=self.import_image(2);cp=self.store.create_checkpoint({'include_media':True});path=self.store.root/item['stored_rel'];content=path.read_bytes();path.unlink()
        plan=self.store.checkpoint_preview({'id':cp['id']});self.assertEqual(plan['missing_media'],[])
        self.store.checkpoint_restore({'id':cp['id'],'token':plan['token']});self.assertEqual(path.read_bytes(),content)

    def test_restart_rolls_back_interrupted_restore(self):
        item=self.import_image(3);before=self.store.db_path.read_bytes();journal=self.store.root/'.restore-pending';journal.mkdir();(journal/'library.json').write_bytes(before);(journal/'ready').write_text('1')
        self.store.set_favorite(item['id'],True)
        reopened=type(self.store)(self.store.root);self.assertFalse(reopened.media_item(item['id'])['favorite']);self.assertFalse(journal.exists())

    def test_loop_validation_persistence_and_undo(self):
        video,_=self.store.import_bytes(b'video','clip.mp4',self.character['id'],[],{},'video/mp4')
        for loop in ({'start':4,'end':3},{'start':-1,'end':4},{'start':1,'end':float('nan')}):
            with self.assertRaises(ValueError):self.store.video_workflow(video['id'],'loop',{'loop':loop})
        saved=self.store.video_workflow(video['id'],'loop',{'loop':{'start':3,'end':4}})
        self.assertEqual(saved['video_loop'],{'start':3,'end':4})
        self.assertEqual(type(self.store)(self.store.root).media_item(video['id'])['video_loop'],saved['video_loop'])
        self.assertEqual(self.store.undo_history()['entries'][0]['label'],'Change video loop')

    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg fixture unavailable')
    def test_real_video_frame_timestamps_and_source_attachment(self):
        path=self.store.root/'fixture.mp4'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc=size=128x96:rate=10:duration=1','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True)
        video,_=self.store.import_bytes(path.read_bytes(),'clip.mp4',self.character['id'],[],{},'video/mp4')
        step=self.store.video_workflow(video['id'],'step',{'seconds':.3,'direction':1});self.assertAlmostEqual(step['seconds'],.4)
        prev=self.store.video_workflow(video['id'],'step',{'seconds':.3,'direction':-1});self.assertAlmostEqual(prev['seconds'],.2)
        frame=self.store.video_workflow(video['id'],'frame',{'seconds':.35})['video_match_frame'];self.assertAlmostEqual(frame['seconds'],.3)
        self.assertEqual(frame['video_sha256'],video['sha256']);self.assertEqual(len(self.store.data['media']),1)
        self.assertTrue((self.store.root/frame['stored_rel']).is_file())
        draft={'format':'folder-organizer-2','scope':'video-test','source_catalog':{'v':{'id':'v','sha':video['sha256'],'path':str(path),'frame_seconds':.2}},
               'sets':[{'id':'clip-set','name':'Clip set','members':['v'],'saved':True}]}
        plan=self.store.organizer_preview({'character_id':self.character['id'],'draft':draft})
        self.assertEqual(plan['imports'],[])
        self.store.organizer_apply({'token':plan['token']})
        frame=self.store.media_item(video['id'])['video_match_frame'];self.assertAlmostEqual(frame['seconds'],.2)
        cp=self.store.create_checkpoint({})
        target=self.store.root/frame['stored_rel'];data=target.read_bytes();target.unlink()
        plan=self.store.checkpoint_preview({'id':cp['id']})
        self.store.checkpoint_restore({'id':cp['id'],'token':plan['token']})
        self.assertEqual(target.read_bytes(),data)

    def test_vote_releases_library_lock_and_rejects_stale_snapshot(self):
        for i in range(4):self.import_image(i)
        battle=self.store.battles;state=battle.request('start',{'character_id':self.character['id'],'kind':'images'})
        entered=threading.Event();finish=threading.Event();errors=[];original=battle._fit_history
        def slow(board):entered.set();self.assertTrue(finish.wait(5));return original(board)
        def vote():
            try:battle.request('vote',{'character_id':self.character['id'],'kind':'images','revision':state['revision'],'pair_id':state['session']['pair']['id'],'outcome':'left'})
            except Exception as e:errors.append(e)
        with patch.object(battle,'_fit_history',side_effect=slow):
            worker=threading.Thread(target=vote);worker.start();self.assertTrue(entered.wait(3))
            acquired=self.store.lock.acquire(timeout=1);self.assertTrue(acquired,'Vote blocked library metadata')
            if acquired:
                try:self.store.set_favorite(self.store.data['media'][0]['id'],True)
                finally:self.store.lock.release()
            finish.set();worker.join(5);self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors),1);self.assertIn('not saved',str(errors[0]));self.assertEqual(battle.request('state',{'character_id':self.character['id'],'kind':'images'})['votes'],0)

if __name__=='__main__':unittest.main()
