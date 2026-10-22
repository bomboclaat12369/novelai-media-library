"""Card metadata, direct challenges and title eligibility stay separate from MMR."""
import copy
import unittest
import test_runtime_stability as fixtures
class CardFeatures(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image
    def call(self,action,kind='images',**kw):
        return self.store.battles.request(action,{'character_id':self.character['id'],'kind':kind,**kw})
    def collection(self,action='state',**kw):
        return self.store.collection_request(action,{'character_id':self.character['id'],**kw})
    def test_arrival_baseline_eligibility_seen_and_persistence(self):
        a=self.import_image(0);state=self.call('cards');self.assertEqual(state['new_count'],0)
        b=self.import_image(1);b['in_all']=False;b['in_review']=True
        self.assertEqual(self.call('cards')['new_count'],0)
        b['in_review']=False;b['in_all']=True
        state=self.call('cards');self.assertEqual(state['new_count'],1)
        row=next(r for r in state['entries'] if r['id']==b['id']);token=row['arrival']['token']
        state=self.call('seen',revision=state['revision'],tokens={b['id']:'stale'});self.assertEqual(state['new_count'],1)
        state=self.call('seen',revision=state['revision'],tokens={b['id']:token});self.assertEqual(state['new_count'],0);self.assertEqual(state['unfinished_count'],2)
        self.assertEqual(state['votes'],0);self.assertTrue(all(r['rating']==1200 for r in state['entries']))
        self.store.save();loaded=type(self.store)(self.store.root)
        self.assertEqual(loaded.battles.request('state',{'character_id':self.character['id']})['new_count'],0)
        b['in_purgatory']=True;self.call('cards');b['in_purgatory']=False
        state=self.call('cards');self.assertEqual(state['new_count'],1)
        self.assertNotEqual(token,next(r for r in state['entries'] if r['id']==b['id'])['arrival']['token'])
    def test_captain_independent_cover_and_main_only_title(self):
        a,b,c=[self.import_image(i) for i in range(3)];c['in_all']=False
        group=self.store.create_set(self.character['id'],'Team',[a['id'],b['id'],c['id']],preserve_placement=True)
        group['cover_media_id']=a['id'];data=self.collection();before=copy.deepcopy(self.store.battles._load())
        self.collection('captain',revision=data['collection']['revision'],set_id=group['id'],media_id=b['id'])
        self.assertEqual(group['cover_media_id'],a['id']);self.assertEqual(self.store.battles._load(),before)
        br=next(r for r in self.call('summary')['entries'] if r['id']==b['id'])
        self.assertEqual([t['id'] for t in br['titles']],['team_captain'])
        self.assertEqual(self.call('summary','sets')['entries'][0]['captain_id'],b['id'])
        self.assertEqual(self.call('summary','sets')['entries'][0]['titles'],[])
        data=self.collection();self.collection('title',revision=data['collection']['revision'],media_id=b['id'],choice='none')
        self.assertEqual(next(r for r in self.call('summary')['entries'] if r['id']==b['id'])['title_choice'],'none')
        data=self.collection();self.collection('captain',revision=data['collection']['revision'],set_id=group['id'],media_id=c['id'])
        self.assertFalse(any(r['titles'] for r in self.call('summary')['entries']))
        with self.assertRaises(ValueError):self.collection('title',revision=self.collection()['collection']['revision'],media_id=c['id'],choice='team_captain')
        other=self.store.add_character('Other');c['character_id']=other['id']
        with self.assertRaises(ValueError):self.collection('captain',revision=self.collection()['collection']['revision'],set_id=group['id'],media_id=c['id'])
    def test_recorded_former_leader_and_undo(self):
        images=[self.import_image(i) for i in range(12)];ids=[m['id'] for m in images];battle=self.store.battles
        board={'revision':'seed','ratings':{ident:{'rating':1400-i*1.,'rd':80.,'played':20,'opponents':{other:1 for other in ids if other!=ident},'wins':10,'losses':10,'ties':0} for i,ident in enumerate(ids)},'history':[],'recent':[],'undo':[],'votes':0,'session':None}
        battle._save({'version':1,'rating_model':battle.MODEL,'boards':{self.character['id']+':images':board}})
        state=self.call('cards');self.assertFalse(any(r['titles'] for r in state['entries']))
        state=self.call('challenge',revision=state['revision'],entry_id=ids[0],opponent_id=ids[1]);pair=state['session']['pair']
        state=self.call('vote',revision=state['revision'],pair_id=pair['id'],outcome='right')
        old=next(r for r in state['entries'] if r['id']==ids[0]);self.assertIn('former_number_one',[t['id'] for t in old['titles']])
        state=self.call('undo',revision=state['revision']);self.assertFalse(any(r['titles'] for r in state['entries']));self.assertEqual(state['votes'],0)
        flagged=copy.deepcopy(board);flagged['cards']={'started_at':'x','eligible':ids,'arrivals':{},'leaders':{},'best':{}}
        entries=battle._entries(self.character['id'],'images');entries[ids[0]]['flagged_for_removal']=True
        battle._sync_cards(flagged,entries);self.assertEqual(flagged['cards']['leaders'],{})
        provisional=copy.deepcopy(board);provisional['cards']={'started_at':'x','eligible':ids,'arrivals':{},'leaders':{},'best':{}}
        for score in provisional['ratings'].values():score['played']=1
        battle._sync_cards(provisional,battle._entries(self.character['id'],'images'));self.assertEqual(provisional['cards']['leaders'],{})
    def test_challenge_preserves_mode_atomic_vote_and_scope(self):
        a,b,c,d=[self.import_image(i) for i in range(4)];state=self.call('start',mode='winner',limit=10)
        state=self.call('challenge',revision=state['revision'],entry_id=a['id'],opponent_id=b['id']);pair=state['session']['pair']
        old=state['revision'];state=self.call('vote',revision=old,pair_id=pair['id'],outcome='left')
        self.assertEqual(state['votes'],1);self.assertEqual(state['session']['mode'],'winner');self.assertEqual(state['session']['done'],0)
        with self.assertRaises(ValueError):self.call('vote',revision=old,pair_id=pair['id'],outcome='left')
        self.assertEqual(self.call('state')['votes'],1)
        for x,y in [(a['id'],a['id']),(a['id'],'missing')]:
            with self.assertRaises(ValueError):self.call('challenge',revision=state['revision'],entry_id=x,opponent_id=y)
        c['in_review']=True
        with self.assertRaises(ValueError):self.call('challenge',revision=state['revision'],entry_id=a['id'],opponent_id=c['id'])
        before=copy.deepcopy(self.store.battles._load());save=self.store.battles._save;self.store.battles._save=lambda data:(_ for _ in ()).throw(OSError('disk full'))
        try:
            with self.assertRaises(OSError):self.call('challenge',revision=state['revision'],entry_id=a['id'],opponent_id=d['id'])
            self.assertEqual(self.store.battles._load(),before)
        finally:self.store.battles._save=save
if __name__=='__main__':unittest.main()
