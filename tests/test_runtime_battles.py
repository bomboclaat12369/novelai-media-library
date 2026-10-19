"""Focused battle voting, isolation, persistence and undo checks."""
import unittest
import test_runtime_stability as fixtures

class BattleTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image
    post=fixtures.RuntimeStabilityTests.post

    def call(self,action,kind='images',**extra):
        status,data=self.post('/api/battles/'+action,{'character_id':self.character['id'],'kind':kind,**extra})
        self.assertEqual(status,200,data)
        return data

    def test_main_only_same_character_and_separate_set_board(self):
        images=[self.import_image(i) for i in range(8)]
        images[2]['in_all']=False;images[3]['in_review']=True;images[4]['in_purgatory']=True
        images[5]['media_type']='video'
        other=self.store.add_character('Other person');images[6]['character_id']=other['id']
        a=self.store.create_set(self.character['id'],'First',[images[0]['id'],images[2]['id']],preserve_placement=True)
        b=self.store.create_set(self.character['id'],'Second',[images[1]['id'],images[7]['id']],preserve_placement=True)
        state=self.call('state')
        self.assertEqual({e['id'] for e in state['entries']},{images[i]['id'] for i in (0,1,7)})
        sets=self.call('state','sets');self.assertEqual({e['id'] for e in sets['entries']},{a['id'],b['id']})
        self.assertIn(images[2]['id'],next(e for e in sets['entries'] if e['id']==a['id'])['images'])
        status,_=self.post('/api/battles/start',{'character_id':self.character['id'],'kind':'sets','minimum':5,'limit':10})
        self.assertNotEqual(status,200)
        sets=self.call('start','sets',minimum=2,limit=10,similar=True)
        sets=self.call('vote','sets',revision=sets['revision'],pair_id=sets['session']['pair']['id'],outcome='left')
        self.assertEqual(sets['votes'],1);self.assertEqual(self.call('state')['votes'],0)

    def test_vote_resume_duplicate_rejection_winner_skip_and_undo(self):
        for i in range(4):self.import_image(i)
        state=self.call('start',mode='winner',limit=10)
        pair=state['session']['pair'];old=state['revision']
        state=self.call('vote',revision=old,pair_id=pair['id'],outcome='left')
        self.assertEqual(state['votes'],1)
        self.assertIn(pair['left'],(state['session']['pair']['left'],state['session']['pair']['right']))
        by_id={e['id']:e for e in state['entries']}
        self.assertGreater(by_id[pair['left']]['rating'],1300)
        self.assertAlmostEqual(by_id[pair['left']]['rating']+by_id[pair['right']]['rating'],2400)
        status,_=self.post('/api/battles/vote',{'character_id':self.character['id'],'kind':'images','revision':old,'pair_id':pair['id'],'outcome':'right'})
        self.assertNotEqual(status,200)
        reloaded=fixtures.RUNTIME['LibraryStore'](self.store.root)
        resumed=reloaded.battles.request('state',{'character_id':self.character['id'],'kind':'images'})
        self.assertEqual(resumed['session'],state['session']);self.assertEqual(resumed['entries'],state['entries'])
        skipped=self.call('vote',revision=state['revision'],pair_id=state['session']['pair']['id'],outcome='skip')
        self.assertEqual(skipped['votes'],1);self.assertEqual(skipped['session']['done'],1)
        restored=self.call('undo',revision=skipped['revision'])
        self.assertEqual(restored['session']['pair'],pair);self.assertEqual(restored['votes'],0)
        self.assertTrue(all(e['played']==0 and e['rating']==1200 for e in restored['entries']))

    def test_round_completion_ties_and_eligibility_change(self):
        images=[self.import_image(i) for i in range(2)]
        state=self.call('start',limit=10)
        for i in range(10):state=self.call('vote',revision=state['revision'],pair_id=state['session']['pair']['id'],outcome='tie')
        self.assertIsNone(state['session']['pair']);self.assertEqual(state['session']['done'],10)
        self.assertTrue(all(e['rating']==1200 and e['ties']==10 and e['provisional'] for e in state['entries']))
        state=self.call('undo',revision=state['revision']);self.assertEqual(state['session']['done'],9)
        images[0]['in_all']=False
        status,_=self.post('/api/battles/vote',{'character_id':self.character['id'],'kind':'images','revision':state['revision'],'pair_id':state['session']['pair']['id'],'outcome':'left'})
        self.assertNotEqual(status,200);self.assertEqual(self.call('state')['votes'],9)

if __name__=='__main__':unittest.main()
