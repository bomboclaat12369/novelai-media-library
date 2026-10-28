import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_history_verify import fixture
from bulk.workbench import Workbench
from bulk.history_verify import top_suggestion
import same_photo


class AcceptSuggestionsTests(unittest.TestCase):
    def test_top_choice_ignores_confidence_and_margin_but_respects_separations(self):
        catalog={'a':{'id':'a','sha':'sha-a'},'b':{'id':'b','sha':'sha-b'},'q':{'id':'q','sha':'sha-q','quarantine_only':True}}
        a={'id':'a','score':40};b={'id':'b','score':40}
        self.assertEqual(top_suggestion([b,a],catalog,'target',set()),[a])
        self.assertEqual(top_suggestion([a,b],catalog,'target',{('sha-a','target')}),[b])
        self.assertEqual(top_suggestion([{'id':'missing','score':100},{'id':'q','score':100}],catalog,'target',set()),[])

    def test_no_verification_or_cache_changes_complete_provenance_and_batch_undo(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,work,keeper,target,duplicate,bad,none=fixture(temp)
            cat=work.current['source_catalog'];work.current['history_matches'][cat[bad]['sha']][0]['score']=98
            before=copy.deepcopy(cat);files={p['path']:Path(p['path']).read_bytes() for p in cat.values()}
            with work.db() as db:
                for ident in (target,bad):db.execute('INSERT INTO aliases VALUES (?,?,?,?)',(cat[ident]['sha'],cat[keeper]['sha'],same_photo.VERSION,0))
                aliases=list(db.execute('SELECT * FROM aliases'))
            with patch('same_photo.prepare',side_effect=AssertionError('No decode')),patch('same_photo.verify',side_effect=AssertionError('No verifier')),patch('bulk.history_confidence.prepare',side_effect=AssertionError('No high-confidence checks')),patch.object(work,'inventory',side_effect=AssertionError('No rescan')):
                work.verify_history({'job':work.current['id'],'policy':'accept_suggestions'});work.thread.join(30)
            self.assertEqual(work.current['phase'],'Saved suggestions accepted')
            self.assertEqual(work.current['inventory']['unlinked_quarantine'],1)
            self.assertEqual(work.current['history_verification']['without_candidate'],1)
            self.assertEqual(len(cat[keeper]['origins']),4)
            self.assertTrue(all(x['proof']=='user-accepted top saved suggestion' for x in cat[keeper]['copies']))
            reopened=Workbench(engine);self.assertEqual(reopened.origin_audit()['auto_policy'],'accept_suggestions')
            reopened.undo_origin({'job':reopened.current['id']})
            self.assertEqual(reopened.current['source_catalog'],before)
            self.assertEqual(files,{p:Path(p).read_bytes() for p in files})
            with work.db() as db:self.assertEqual(aliases,list(db.execute('SELECT * FROM aliases')))

    def test_deferred_entries_and_changed_files_stay_unlinked(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,work,keeper,target,duplicate,bad,none=fixture(temp)
            cat=work.current['source_catalog'];work.current['history_matches'][cat[bad]['sha']][0]['score']=98
            with work.db() as db:db.execute('INSERT INTO origin_review VALUES (?,?,?)',(cat[target]['sha'],'deferred',1))
            Path(cat[bad]['path']).write_bytes(b'changed')
            work.verify_history({'job':work.current['id'],'policy':'accept_suggestions'});work.thread.join(30)
            self.assertEqual(work.current['inventory']['unlinked_quarantine'],4)
            self.assertEqual(work.origin_audit(review_filter='deferred')['total'],1)
            self.assertTrue(work.current['issues'])

    def test_stopping_resuming_and_undo_preserve_previous_connections(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,work,keeper,target,duplicate,bad,none=fixture(temp)
            cat=work.current['source_catalog'];work.current['history_matches'][cat[bad]['sha']][0]['score']=98
            work.current['origin_undo']={'prior_manual_marker':True}
            before=copy.deepcopy(work.current);persist=work.persist
            def stop_after_link():
                persist()
                if work.current.get('origin_undo',{}).get('policy')=='accept_suggestions':work.cancel.set()
            with patch.object(work,'persist',side_effect=stop_after_link):
                work.verify_history({'job':work.current['id'],'policy':'accept_suggestions'});work.thread.join(30)
            self.assertIn('paused',work.current['phase'])
            work=Workbench(engine)
            work.verify_history({'job':work.current['id'],'policy':'accept_suggestions'});work.thread.join(30)
            self.assertEqual(work.current['inventory']['unlinked_quarantine'],1)
            work.undo_origin({'job':work.current['id']})
            self.assertEqual(work.current['source_catalog'],before['source_catalog'])
            self.assertEqual(work.current['origin_undo'],before['origin_undo'])

if __name__=='__main__':unittest.main()
