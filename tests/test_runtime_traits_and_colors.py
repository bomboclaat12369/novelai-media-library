import copy,unittest
import test_runtime_stability as fixtures

class TraitsAndColors(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image
    def call(self,**kw):
        data=self.store.collection_request('state',{'character_id':self.character['id']})
        return self.store.collection_request('edition',{'character_id':self.character['id'],'revision':data['collection']['revision'],**kw})
    def rows(self):return self.store.battles.request('summary',{'character_id':self.character['id']})['entries']
    def test_owned_traits_separate_from_display_and_migrate_existing_choice(self):
        a,b=[self.import_image(i) for i in range(2)];owner=self.character['id'];self.rows()
        data=self.store.collection_request('state',{'character_id':owner});self.character['collection']['editions'][a['id']]={'choice':'christmas'}
        self.assertEqual(next(r for r in self.rows() if r['id']==a['id'])['owned_editions'],['christmas'])
        before=copy.deepcopy(self.store.battles._load())
        self.call(entry_ids=[a['id'],b['id']],add_traits=['hall-of-fame','former-one'])
        rows={r['id']:r for r in self.rows()};self.assertEqual(rows[a['id']]['edition_id'],'christmas');self.assertIsNone(rows[b['id']]['edition_id'])
        self.call(entry_id=a['id'],choice='hall-of-fame');self.call(entry_id=a['id'],choice='none')
        self.assertEqual(set(next(r for r in self.rows() if r['id']==a['id'])['owned_editions']),{'christmas','hall-of-fame','former-one'})
        with self.assertRaises(ValueError):self.call(entry_id=b['id'],choice='christmas')
        self.call(entry_id=a['id'],remove_traits=['christmas'])
        self.assertNotIn('christmas',next(r for r in self.rows() if r['id']==a['id'])['owned_editions'])
        snapshot=copy.deepcopy(self.character['collection']['editions'])
        with self.assertRaises(ValueError):self.call(entry_ids=[a['id'],'missing'],add_traits=['birthday'])
        self.assertEqual(snapshot,self.character['collection']['editions']);self.assertEqual(before,self.store.battles._load())
        self.store.save();loaded=type(self.store)(self.store.root);self.assertEqual(loaded.character(owner)['collection']['editions'],snapshot)
    def test_captain_automatic_and_profile_colors(self):
        a=self.import_image(0);g=self.store.create_set(self.character['id'],'White Bikini',[a['id']],preserve_placement=True);owner=self.character['id']
        data=self.store.collection_request('state',{'character_id':owner});self.store.collection_request('captain',{'character_id':owner,'revision':data['collection']['revision'],'set_id':g['id'],'media_id':a['id']})
        self.call(entry_id=a['id'],show_captain=False)
        self.assertTrue(self.rows()[0]['edition_settings']['show_captain'])
        state=self.store.profile_request('state',{'character_id':owner});saved=self.store.profile_request('save',{'character_id':owner,'revision':state['profile']['revision'],'profile':{'photos':[],'measurements':{},'eye_color':'Hazel','hair_color':'Dark blonde'}})
        loaded=type(self.store)(self.store.root);self.assertEqual(loaded.profile_request('state',{'character_id':owner})['profile']['eye_color'],'Hazel')
        self.assertEqual(saved['profile']['hair_color'],'Dark blonde')
    def test_set_color_backfill_create_and_rename_preserve_metadata(self):
        a=self.import_image(0);g=self.store.create_set(self.character['id'],'White Bikini 2',[a['id']],preserve_placement=True,colors=['Custom'])
        self.assertEqual(g['colors'],['Custom','White']);g['colors']=['Custom'];g['created_at']='old';g['updated_at']='old2';self.store.save()
        loaded=type(self.store)(self.store.root);restored=loaded.set_item(g['id']);self.assertEqual(restored['colors'],['Custom','White']);self.assertEqual(restored['created_at'],'old');self.assertEqual(restored['updated_at'],'old2');self.assertEqual(restored['media_ids'],[a['id']])
        changed=loaded.update_set(g['id'],name='Red and blue Bikini');self.assertTrue({'Red','Blue','White','Custom'}<=set(changed['colors']))
        self.assertEqual(fixtures.RUNTIME['set_name_colors']('Blackberry in the greenhouse'),[])

if __name__=='__main__':unittest.main()
