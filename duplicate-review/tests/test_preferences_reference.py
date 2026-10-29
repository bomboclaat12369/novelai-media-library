import json, tempfile, unittest
from unittest.mock import patch
from pathlib import Path
from test_organizer import fixture
from engine import Engine
from organizer import Organizer
from bulk.workbench import Workbench

class PreferencesReferenceTests(unittest.TestCase):
    def test_current_choices_persist_separately_and_stale_requests_cannot_revert(self):
        with tempfile.TemporaryDirectory() as temp:
            engine=Engine(Path(temp)/'state')
            config={'incoming':['last scan'],'reference':[], 'mode':'balanced','library_character':'old'}
            with engine.db() as db: db.execute("INSERT OR REPLACE INTO settings VALUES ('config',?)",(json.dumps(config),))
            prefs=dict(edited_at=100,incoming_text='new folder\nsecond folder',reference_text='',history_roots='',library_character='new',library_id='lib',library_label='New')
            with patch.object(engine,'start',side_effect=AssertionError('No scan')):
                self.assertEqual(engine.ui_preferences(prefs),prefs)
                blank=dict(prefs,edited_at=101,incoming_text='',library_character='')
                engine.ui_preferences(blank)
                self.assertEqual(engine.ui_preferences(prefs),blank)
                reopened=Engine(Path(temp)/'state')
                self.assertEqual(reopened.ui_preferences(),blank)
                self.assertEqual(reopened.config(),config)
                with self.assertRaises(ValueError):engine.ui_preferences(dict(blank,edited_at='bad'))

    def test_pin_controls_evidence_without_changing_selection_or_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            body={'job':'fixture-job','ids':ids[6:11],'target':'library:existing','suggestion_reference':ids[2]}
            org.mutate('draft',body)
            with patch.object(org,'scores',wraps=org.scores) as scores:
                result=org.related(body)
                scores.assert_called_once_with([ids[2]])
            self.assertEqual({p['id'] for p in result['posts']},{'post:1'})
            self.assertEqual({i['id'] for i in result['images']},set(ids[3:6]))
            self.assertTrue(result['reference']['analyzed'])
            self.assertEqual(org.state()['selection'],ids[6:11])
            self.assertEqual(org.state()['target'],'library:existing')
            reopened=Organizer(engine,Workbench(engine))
            self.assertEqual(reopened.summary()['reference_image']['id'],ids[2])
            normal=org.related(dict(body,suggestion_reference=''))
            self.assertNotEqual(result['context'],normal['context'])
            self.assertIn('post:2',{p['id'] for p in normal['posts']})
            org.mutate('draft',dict(body,suggestion_reference=''))
            self.assertIsNone(org.summary()['reference_image'])

    def test_unanalyzed_pin_does_not_fall_back_to_selected_vectors(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            with bulk.db() as db:db.execute('DELETE FROM vectors WHERE sha=?',(ids[2],))
            org.load_vectors()
            result=org.related({'ids':ids[6:11],'suggestion_reference':ids[2]})
            self.assertFalse(result['reference']['analyzed'])
            self.assertNotIn(ids[11],{i['id'] for i in result['images']})
            self.assertEqual({p['id'] for p in result['posts']},{'post:1'})

if __name__=='__main__':unittest.main()
