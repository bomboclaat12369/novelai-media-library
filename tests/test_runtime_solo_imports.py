"""Individual Workbench imports share library identity, placement and Rapid Review."""
import copy,hashlib,unittest
from unittest.mock import patch
import test_runtime_stability as fixtures

class IndividualImportTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image

    def draft(self,destination='main',count=2,**options):
        catalog={};rows=[]
        for n in range(count):
            path=self.store.root/('external-'+str(n)+'.png');path.write_bytes(('source image '+str(n)).encode())
            ident='image-'+str(n);catalog[ident]={'id':ident,'path':str(path),'sha':hashlib.sha256(path.read_bytes()).hexdigest(),'origins':[{'path':str(path),'key':'folder:Nikki'}]}
            rows.append({'id':ident,'character_id':self.character['id'],'options':dict(destination=destination,**options)})
        return {'character_id':self.character['id'],'draft':{'format':'folder-organizer-2','scope':'solo-test','source_catalog':catalog,'individuals':rows,'sets':[]}}

    def apply(self,draft):
        plan=self.store.organizer_preview(draft)
        self.assertFalse(plan['issues'])
        for item in plan['imports']:self.store.organizer_import({'token':plan['token'],'id':item['id']})
        return self.store.organizer_apply({'token':plan['token']})

    def test_main_without_sets_byte_exact_flags_dates_and_retry(self):
        draft=self.draft(favorite=True,featured=True,needs_replacement=True)
        result=self.apply(draft);self.assertEqual(result['sets'],0);self.assertEqual(len(result['individuals']),2)
        for key,outcome in result['individuals'].items():
            item=self.store.media_item(outcome['id']);self.assertTrue(item['in_all']);self.assertFalse(item['in_review'])
            self.assertTrue(all(item[k] for k in ('favorite','featured','needs_replacement')))
            self.assertTrue(item['main_added_at']);self.assertNotIn('organizer_pending',item['source'])
            path=draft['draft']['source_catalog'][key]['path']
            from pathlib import Path
            self.assertEqual((self.store.root/item['stored_rel']).read_bytes(),Path(path).read_bytes())
        before=copy.deepcopy(self.store.data['media']);self.apply(draft)
        self.assertEqual([i['id'] for i in self.store.data['media']],[i['id'] for i in before]);self.assertFalse(self.store.data['sets'])

    def test_category_and_ghost_semantics(self):
        ghost=self.store.add_category(self.character['id'],'Hidden');self.store.set_category_ghost(ghost['id'],True)
        regular=self.store.add_category(self.character['id'],'Dress')
        draft=self.draft('categories',count=1,categories=[ghost['id']]);out=self.apply(draft)
        item=self.store.media_item(out['individuals']['image-0']['id']);self.assertFalse(item['in_all'])
        draft['draft']['individuals'][0]['options']['categories']=[regular['id']]
        self.apply(draft);self.assertTrue(item['in_all']);self.assertEqual(set(item['categories']),{ghost['id'],regular['id']})

    def test_pending_review_persists_full_tools_and_no_duplicate_promotion(self):
        draft=self.draft('review',favorite=True);result=self.apply(draft)
        self.assertEqual(self.store.data['media'],[]);self.assertEqual(len(self.store.rapid_queue(self.character['id'])['items']),2)
        mid=result['individuals']['image-0']['id'];self.store.rapid_state({'character_id':self.character['id'],'choices':{mid:{'favorite':False,'crop_top':.1,'needs_replacement':True}},'current_id':mid})
        self.apply(draft);item=self.store.rapid_item(mid);self.assertFalse(item['favorite']);self.assertEqual(item['crop_top'],.1)
        self.assertEqual(len(self.store.data['rapid_queue']),2)
        reopened=type(self.store)(self.store.root);self.assertEqual(reopened.rapid_item(mid)['crop_top'],.1)
        reopened.resolve_rapid({'character_id':self.character['id'],'action':'main','media_ids':[mid]})
        self.assertEqual(reopened.media_item(mid)['crop_top'],.1);self.assertTrue(reopened.media_item(mid)['in_all'])

    def test_existing_identity_sets_ratings_crop_and_unchecked_flags_preserved(self):
        item=self.import_image(42);self.store.set_crop(item['id'],.1,.2);self.store.set_favorite(item['id'],True)
        group=self.store.create_set(self.character['id'],'Keep set',[item['id']]);item['custom_rating_fixture']=99;self.store.save()
        draft=self.draft('review',count=1);draft['draft']['source_catalog']['image-0'].update(sha=item['sha256'],path=str(self.store.root/item['stored_rel']))
        result=self.apply(draft)
        self.assertEqual(result['individuals']['image-0']['destination'],'existing')
        self.assertEqual(group['media_ids'],[item['id']]);self.assertEqual(item['crop_top'],.1);self.assertTrue(item['favorite']);self.assertEqual(item['custom_rating_fixture'],99)
        self.assertFalse(self.store.data.get('rapid_queue'));self.assertEqual(len(self.store.data['media']),1)

    def test_interruption_and_failed_apply_keep_copies_hidden_and_resume(self):
        draft=self.draft();plan=self.store.organizer_preview(draft);first=self.store.organizer_import({'token':plan['token'],'id':'image-0'})
        self.assertFalse(self.store.media_item(first['id'])['in_all']);self.assertNotIn('main_added_at',self.store.media_item(first['id']))
        self.store=type(self.store)(self.store.root);plan=self.store.organizer_preview(draft);self.assertEqual(len(plan['imports']),1)
        self.store.organizer_import({'token':plan['token'],'id':'image-1'});before=copy.deepcopy(self.store.data)
        with patch.object(self.store,'_write_atomic',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.store.organizer_apply({'token':plan['token']})
        self.assertEqual(self.store.data,before)
        result=self.store.organizer_apply({'token':plan['token']});self.assertEqual(len(result['individuals']),2)
        self.assertEqual(self.store.organizer_apply({'token':plan['token']}),result)

    def test_review_and_sets_conflict_and_stale_category_rejected(self):
        draft=self.draft('review',count=1);draft['draft']['sets']=[{'id':'set','saved':True,'name':'Set','members':['image-0']}]
        plan=self.store.organizer_preview(draft);self.assertTrue(plan['issues'])
        with self.assertRaisesRegex(ValueError,'Resolve'):self.store.organizer_import({'token':plan['token'],'id':'image-0'})
        draft['draft']['sets']=[];draft['draft']['individuals'][0]['options']={'destination':'main','categories':['gone']}
        with self.assertRaisesRegex(ValueError,'categories changed'):self.store.organizer_preview(draft)

    def test_main_and_sets_together_preserve_both(self):
        draft=self.draft(count=1);draft['draft']['sets']=[{'id':'set','saved':True,'name':'Set','members':['image-0']}]
        result=self.apply(draft);mid=result['individuals']['image-0']['id']
        self.assertTrue(self.store.media_item(mid)['in_all']);self.assertEqual(self.store.set_item(result['mapping']['set'])['media_ids'],[mid])

    def test_pending_review_not_bypassed_by_direct_import(self):
        draft=self.draft('review',count=1);out=self.apply(draft);mid=out['individuals']['image-0']['id']
        draft['draft']['individuals'][0]['options']['destination']='main'
        self.assertEqual(self.apply(draft)['individuals']['image-0']['destination'],'review');self.assertIsNone(self.store.media_item(mid));self.assertIsNotNone(self.store.rapid_item(mid))

    def test_purgatory_solo_and_cross_owner_validation(self):
        draft=self.draft('purgatory',count=1);out=self.apply(draft);item=self.store.media_item(out['individuals']['image-0']['id'])
        self.assertTrue(item['in_purgatory']);self.assertFalse(item['in_all'])
        draft['draft']['individuals'][0]['character_id']='wrong'
        with self.assertRaisesRegex(ValueError,'another character'):self.store.organizer_preview(draft)

    def test_changed_source_and_deleted_queue_rejected(self):
        draft=self.draft('review',count=1);plan=self.store.organizer_preview(draft)
        from pathlib import Path
        Path(draft['draft']['source_catalog']['image-0']['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):self.store.organizer_import({'token':plan['token'],'id':'image-0'})
        draft=self.draft('review',count=1);out=self.apply(draft);plan=self.store.organizer_preview(draft)
        self.store.resolve_rapid({'character_id':self.character['id'],'action':'discard','media_ids':[out['individuals']['image-0']['id']]})
        with self.assertRaisesRegex(ValueError,'incomplete or changed'):self.store.organizer_apply({'token':plan['token']})

    def test_wrong_library_and_duplicate_hash_choices_rejected(self):
        draft=self.draft(count=1);draft['draft']['individuals'][0]['library_instance']='unrelated-library'
        with self.assertRaisesRegex(ValueError,'another library'):self.store.organizer_preview(draft)
        draft['draft']['individuals'][0].pop('library_instance')
        draft['draft']['source_catalog']['alias']=dict(draft['draft']['source_catalog']['image-0'],id='alias')
        draft['draft']['individuals'].append({'id':'alias','options':{'destination':'review'}})
        with self.assertRaisesRegex(ValueError,'each image once'):self.store.organizer_preview(draft)
