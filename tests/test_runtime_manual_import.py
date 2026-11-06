import copy,hashlib,io,unittest,uuid
from PIL import Image
import test_runtime_solo_imports as solo
import test_runtime_stability as fixtures

class ManualImportTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image
    post=fixtures.RuntimeStabilityTests.post
    draft=solo.IndividualImportTests.draft
    apply=solo.IndividualImportTests.apply
    def search(self,**body):return self.store.manual_search({'character_id':self.character['id'],**body})
    def choice(self,draft,target,action='keep'):
        draft['draft']['state']={'duplicate_choices':{draft['draft']['source_catalog']['image-0']['sha']:{'action':action,'target':target['id'],'target_sha':target['sha256'],'operation':uuid.uuid4().hex,'library_instance':self.store.tracking.diagnostics()['instance'],'library_id':self.store.duplicate_catalog()['library_id']}}}
        return next(iter(draft['draft']['state']['duplicate_choices'].values()))
    def png(self,color):
        data=io.BytesIO();Image.new('RGB',(120,160),color).save(data,format='PNG');return data.getvalue()

    def test_set_purgatory_preserves_images_details_battle_history_and_restore(self):
        item=self.import_image(1);cat=self.store.add_set_category(self.character['id'],'Outfits');group=self.store.create_set(self.character['id'],'White Dress',[item['id']],categories=[cat['id']],aliases=['Summer'])
        self.store.update_set(group['id'],favorite=True,notes='Keep this');before=copy.deepcopy(item);details=copy.deepcopy(group)
        code,held=self.post('/api/sets/'+group['id'],{'in_purgatory':True});self.assertEqual(code,200);self.assertTrue(held['in_purgatory']);self.assertEqual(item,before)
        self.assertEqual(self.search(kind='sets',placement='main')['rows'],[]);self.assertEqual(self.search(kind='sets',placement='purgatory')['rows'][0]['id'],group['id'])
        board=fixtures.RUNTIME['BattleRankings'](self.store);self.assertNotIn(group['id'],board._entries(self.character['id'],'sets'))
        self.store.update_set(group['id'],in_purgatory=False);self.assertIn(group['id'],board._entries(self.character['id'],'sets'))
        for field in ('media_ids','categories','aliases','notes','favorite','cover_media_id'):self.assertEqual(group[field],details[field])
        with self.assertRaisesRegex(ValueError,'Purgatory'):self.store.update_set(group['id'],in_purgatory='false')

    def test_manual_search_category_unassigned_owner_and_pagination(self):
        a=self.import_image(1);b=self.import_image(2);c=self.import_image(3)
        category=self.store.add_category(self.character['id'],'Beach');self.store.set_categories(b['id'],[category['id']])
        group=self.store.create_set(self.character['id'],'White Dress',[a['id']],aliases=['Summer sunset'])
        self.store.set_purgatory(c['id'],True)
        self.assertEqual([r['id'] for r in self.search(kind='sets',query='sunset')['rows']],[group['id']])
        self.assertEqual([r['id'] for r in self.search(kind='images',query='white dress')['rows']],[a['id']])
        self.assertEqual([r['id'] for r in self.search(kind='images',category=category['id'])['rows']],[b['id']])
        self.assertEqual({r['id'] for r in self.search(kind='images',placement='unassigned')['rows']},{b['id'],c['id']})
        other=self.store.add_character('Other');self.assertEqual(self.store.manual_search({'character_id':other['id']})['total'],0)
        self.assertEqual(self.search(kind='images',media_ids=[])['total'],0)
        self.assertEqual(self.search(kind='images',offset=60)['rows'],[])

    def test_manual_group_rechecks_membership_and_character(self):
        a=self.import_image(1);b=self.import_image(2);body={'character_id':self.character['id'],'media_ids':[a['id'],b['id']],'name':'Manual Set'}
        result=self.store.manual_group(body);self.assertEqual(result['media_ids'],[a['id'],b['id']])
        with self.assertRaisesRegex(ValueError,'now belongs'):self.store.manual_group(body)
        other=self.store.add_character('Other');body['character_id']=other['id']
        with self.assertRaises((ValueError,KeyError)):self.store.manual_group(body)
        self.assertEqual(len(self.store.data['sets']),1)

    def test_keep_duplicate_preserves_identity_original_metadata_and_tracks_choice(self):
        target=self.import_image(1);self.store.set_favorite(target['id'],True);before=copy.deepcopy(target)
        draft=self.draft(count=1);self.choice(draft,target);plan=self.store.organizer_preview(draft)
        self.assertEqual(plan['imports'],[]);out=self.store.organizer_apply({'token':plan['token']})
        self.assertEqual(out['individuals']['image-0']['id'],target['id']);self.assertEqual(len(self.store.data['media']),1)
        for key in ('sha256','stored_rel','favorite','id'):self.assertEqual(target[key],before[key])

    def test_stale_duplicate_target_and_wrong_library_rejected(self):
        target=self.import_image(1);draft=self.draft(count=1);choice=self.choice(draft,target);choice['target_sha']='0'*64
        self.assertTrue(self.store.organizer_preview(draft)['issues']);choice['target_sha']=target['sha256'];choice['library_instance']='other'
        self.assertTrue(self.store.organizer_preview(draft)['issues'])

    def test_replace_duplicate_byte_exact_preserves_crop_and_is_resumable(self):
        target=self.store.import_bytes(self.png('red'),'before.png',self.character['id'],[],{'kind':'local'},'image/png')[0]
        self.store.set_crop(target['id'],.1,.1);group=self.store.create_set(self.character['id'],'Original',[target['id']]);self.store.set_favorite(target['id'],True)
        draft=self.draft(count=1);record=draft['draft']['source_catalog']['image-0'];from pathlib import Path
        path=Path(record['path']);path.write_bytes(self.png('blue'));record['sha']=hashlib.sha256(path.read_bytes()).hexdigest();choice=self.choice(draft,target,'replace')
        plan=self.store.organizer_preview(draft);self.store.organizer_import({'token':plan['token'],'id':'image-0'})
        self.assertEqual(target['sha256'],record['sha']);self.assertEqual(target['crop_top'],.1);self.assertTrue(target['favorite']);self.assertEqual(group['media_ids'],[target['id']]);self.assertTrue(path.exists())
        plan2=self.store.organizer_preview(draft);self.assertFalse(plan2['imports']);out=self.store.organizer_apply({'token':plan2['token']});self.assertEqual(out['individuals']['image-0']['id'],target['id']);self.assertEqual(len(self.store.data['media']),1)
        self.assertEqual(self.store.duplicate_operation(choice['operation'],choice['library_id'])['state'],'applied')
        self.store.duplicate_undo(choice['operation'],choice['library_id']);self.assertEqual((self.store.root/target['stored_rel']).read_bytes(),self.png('red'));self.assertTrue(target['favorite'])

    def test_two_sources_cannot_silently_overwrite_choices_for_one_target(self):
        target=self.import_image(1);draft=self.draft(count=2);choice=self.choice(draft,target);second=draft['draft']['source_catalog']['image-1']['sha'];draft['draft']['state']['duplicate_choices'][second]=copy.deepcopy(choice)
        self.assertTrue(any('Multiple' in x for x in self.store.organizer_preview(draft)['issues']))
        for choice in draft['draft']['state']['duplicate_choices'].values():choice['action']='replace'
        self.assertTrue(any('Multiple' in x for x in self.store.organizer_preview(draft)['issues']))

    def test_set_status_transfer_keeps_existing_image_placement(self):
        target=self.import_image(1);group=self.store.create_set(self.character['id'],'Keep',[target['id']]);self.store.set_purgatory(target['id'],True)
        draft={'character_id':self.character['id'],'draft':{'format':'folder-organizer-2','scope':'held','source_catalog':{},'sets':[{'id':'local','library_id':group['id'],'saved':True,'name':'Keep','members':[],'in_purgatory':True,'purgatory_edited':True}]}}
        plan=self.store.organizer_preview(draft);self.store.organizer_apply({'token':plan['token']});self.assertTrue(group['in_purgatory']);self.assertTrue(target['in_purgatory']);self.assertEqual(group['media_ids'],[target['id']])

    def test_stale_workbench_details_cannot_restore_a_held_set(self):
        item=self.import_image(1);group=self.store.create_set(self.character['id'],'Held',[item['id']]);self.store.update_set(group['id'],in_purgatory=True)
        draft={'character_id':self.character['id'],'draft':{'format':'folder-organizer-2','scope':'stale','source_catalog':{},'sets':[{'id':'local','library_id':group['id'],'saved':True,'name':'Held','members':[],'in_purgatory':False}]}}
        plan=self.store.organizer_preview(draft);self.store.organizer_apply({'token':plan['token']});self.assertTrue(group['in_purgatory'])

    def test_bulk_set_purgatory_validates_all_before_one_atomic_write(self):
        a=self.store.create_set(self.character['id'],'A',[]);b=self.store.create_set(self.character['id'],'B',[])
        from unittest.mock import patch
        body={'character_id':self.character['id'],'set_ids':[a['id'],b['id']],'in_purgatory':True}
        with patch.object(self.store,'save',wraps=self.store.save) as save:
            self.store.bulk_set_purgatory(body);self.assertEqual(save.call_count,1)
        body.update(set_ids=[a['id'],'missing'],in_purgatory=False)
        with self.assertRaisesRegex(ValueError,'Sets changed'):self.store.bulk_set_purgatory(body)
        self.assertTrue(a['in_purgatory']);self.assertTrue(b['in_purgatory'])
