import copy,io,json,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import test_individual_imports as fixtures

class ManualImportHTTPTests(unittest.TestCase):
    setUp=fixtures.IndividualHTTPTests.setUp
    tearDown=fixtures.IndividualHTTPTests.tearDown
    request=fixtures.IndividualHTTPTests.request
    def image(self,color='red'):
        buffer=io.BytesIO();Image.new('RGB',(90,120),color).save(buffer,format='PNG')
        return self.store.import_bytes(buffer.getvalue(),color+'.png',self.owner['id'],[],{'kind':'local'},'image/png')[0]
    def body(self,**extra):
        state=self.request('state');return {'job':state['job'],'revision':state['state']['revision'],'character_id':self.owner['id'],**extra}

    def test_manual_search_attach_live_set_and_image_without_rescan(self):
        image=self.image();group=self.store.create_set(self.owner['id'],'Manual White',[image['id']]);self.store.update_set(group['id'],in_purgatory=True)
        with patch.object(self.engine,'start',side_effect=AssertionError('No rescan')):
            result=self.request('manual-search',self.body(kind='sets',query='white',placement='purgatory'))
            self.assertEqual(result['rows'][0]['id'],group['id'])
            added=self.request('attach-library',self.body(set_id=group['id'],library_instance=result['library_instance']))
            self.assertEqual(added['ids'],[image['sha256']]);saved=self.request('state')['sets'];self.assertTrue(next(g for g in saved if g['library_id']==group['id'])['in_purgatory'])
            original=self.request('library-image?owner='+self.owner['id']+'&id='+image['id'],raw=True);self.assertEqual(original,(self.store.root/image['stored_rel']).read_bytes())
            thumb=self.request('library-image?owner='+self.owner['id']+'&id='+image['id']+'&size=600',raw=True);self.assertEqual(Image.open(io.BytesIO(thumb)).format,'JPEG')
        self.assertEqual(len(self.store.data['media']),1)

    def test_duplicate_keep_over_http_with_restart_and_stale_guards(self):
        image=self.image();source=self.ids[3];org=self.server.organizer
        self.request('queue_individuals',self.body(ids=[source],options={'destination':'main'},character_id=self.owner['id']))
        result=self.request('manual-search',self.body(kind='images'));choice=self.request('duplicate-choice',self.body(id=source,action='keep',target=image['id'],target_sha=image['sha256'],library_instance=result['library_instance']))['choice']
        self.assertEqual(choice['target'],image['id']);before=self.request('state')['state']['revision']
        from organizer import Organizer
        reopened=Organizer(self.engine,self.server.bulk);self.assertEqual(reopened.state()['revision'] if reopened.bound else reopened.summary()['state']['revision'],before)
        plan=self.request('transfer-preview',self.body(include_sets=False));self.assertFalse(plan['imports']);self.assertTrue(plan['duplicates'])
        applied=self.request('transfer-apply',self.body(token=plan['token']));self.assertEqual(applied['individuals'][source]['id'],image['id']);self.assertEqual(len(self.store.data['media']),1)
        history=org.export()['tracking']['events'];self.assertTrue(any('duplicate_choices' in json.dumps(e) for e in history))
        with self.assertRaisesRegex(ValueError,'changed'):org.duplicate_choice({**self.body(id=source,action='replace',target=image['id'],target_sha='bad',library_instance=result['library_instance'])})

    def test_local_search_category_purgatory_and_session_filter(self):
        org=self.server.organizer;state=org.summary();target=next(g['id'] for g in state['sets'] if g['members'])
        org.mutate('set_details',self.body(target=target,in_purgatory=True))
        result=self.request('manual-search',self.body(source='inventory',kind='sets',placement='purgatory'));self.assertEqual(result['rows'][0]['id'],target)
        prefs=org.session_preferences({'setFilter':'purgatory'});self.assertEqual(prefs['setFilter'],'purgatory')
        ids=self.request('manual-search',self.body(source='inventory',kind='images',placement='unassigned'));self.assertTrue(ids['rows'])

    def test_scan_candidates_are_from_saved_engine_pairs_without_new_analysis(self):
        image=self.image();source=self.ids[3];org=self.server.organizer;org.bind();digest=org.catalog[source]['sha']
        with self.engine.db() as db:
            db.execute('INSERT INTO files(id,path,sha,moved) VALUES (1001,?,?,0)',('/incoming',digest));db.execute('INSERT INTO files(id,path,sha,moved) VALUES (1002,?,?,0)',('/library',image['sha256']));db.execute("INSERT INTO pairs(a,b,kind,score,key) VALUES (1001,1002,'visual',.99,'manual-test')")
        with patch.object(self.engine,'start',side_effect=AssertionError('No scan')):
            result=self.request('manual-search',self.body(kind='images',duplicate_source=source));self.assertEqual([r['id'] for r in result['rows']],[image['id']])
        with self.engine.db() as db:db.execute("UPDATE pairs SET decision='different' WHERE key='manual-test'")
        result=self.request('manual-search',self.body(kind='images',duplicate_source=source));self.assertEqual(result['rows'],[])
