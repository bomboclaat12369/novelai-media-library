"""Only the storage and preloading paths changed in the viewer release."""
import copy
import unittest
from unittest.mock import patch
import test_runtime_stability as fixtures

class ViewerReleaseTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image

    def test_clear_holding_keeps_set_and_does_not_promote_and_can_undo(self):
        image=self.import_image(1)
        group=self.store.create_set(self.character['id'],'Set',[image['id']],preserve_placement=True)
        for holding in ('review','purgatory'):
            getattr(self.store,'set_'+holding)(image['id'],True)
            before=copy.deepcopy(image)
            result=self.store.clear_holding(image['id'])
            self.assertFalse(result['in_all']);self.assertFalse(result['in_review']);self.assertFalse(result['in_purgatory'])
            self.assertIn(image['id'],group['media_ids'])
            self.store.undo_last(self.store.undo_history()['entries'][0]['id'])
            self.assertEqual(image,before)

    def test_category_dates_track_additions_without_resetting_existing_dates(self):
        image=self.import_image(2);cat=self.store.add_category(self.character['id'],'Dress')
        with patch.dict(fixtures.RUNTIME['LibraryStore']._change_media.__globals__,now_iso=lambda:'2026-10-20T01:00:00Z'):
            self.store.set_categories(image['id'],[cat['id']],True)
        self.assertEqual(image['category_added_at'][cat['id']],'2026-10-20T01:00:00Z')
        with patch.dict(fixtures.RUNTIME['LibraryStore']._change_media.__globals__,now_iso=lambda:'2026-10-21T01:00:00Z'):
            self.store.set_categories(image['id'],[cat['id']],True)
            self.assertEqual(image['category_added_at'][cat['id']],'2026-10-20T01:00:00Z')
            self.store.set_categories(image['id'],[],True);self.store.set_categories(image['id'],[cat['id']],True)
            self.assertEqual(image['category_added_at'][cat['id']],'2026-10-21T01:00:00Z')

    def test_forecast_does_not_refit_history_or_change_saved_ratings(self):
        for i in range(8):self.import_image(i)
        battle=self.store.battles;body={'character_id':self.character['id']}
        state=battle.request('start',body);before=battle.path.read_bytes()
        with patch.object(battle,'_fit_history',side_effect=AssertionError('Preloading must not fit history')):
            after=battle.request('state',body)
        self.assertEqual(state['entries'],after['entries']);self.assertEqual(before,battle.path.read_bytes())
        with patch.object(battle,'_fit_history',wraps=battle._fit_history) as fit:
            battle.request('vote',{**body,'revision':state['revision'],'pair_id':state['session']['pair']['id'],'outcome':'left'})
            self.assertEqual(fit.call_count,1)

if __name__=='__main__':unittest.main()
