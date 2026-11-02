"""Edition choices are scoped presentation metadata; they never change battle state."""
import copy
import unittest
import test_runtime_stability as fixtures

class CardEditions(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image
    def collection(self, action='state', **kw):
        return self.store.collection_request(action, {'character_id':self.character['id'], **kw})
    def board(self, kind='images'):
        return self.store.battles.request('summary', {'character_id':self.character['id'], 'kind':kind})
    def test_manual_editions_persist_without_changing_ratings_or_originals(self):
        a,b=[self.import_image(i) for i in range(2)]
        group=self.store.create_set(self.character['id'],'Shoot',[a['id'],b['id']],preserve_placement=True)
        data=self.collection();battle=copy.deepcopy(self.store.battles._load());media=copy.deepcopy(self.store.data['media'])
        for edition in fixtures.RUNTIME['MANUAL_CARD_EDITIONS']:
            data=self.collection('edition',revision=data['collection']['revision'],entry_id=a['id'],choice=edition,rating_style='number',captain_corner='right')
            row=next(r for r in self.board()['entries'] if r['id']==a['id'])
            self.assertEqual(row['edition_id'],edition)
            self.assertEqual(row['edition_settings']['captain_corner'],'right')
        data=self.collection('edition',revision=data['collection']['revision'],entry_id=group['id'],kind='sets',choice='christmas')
        self.assertEqual(self.board('sets')['entries'][0]['edition_id'],'christmas')
        self.assertEqual(self.store.battles._load(),battle);self.assertEqual(self.store.data['media'],media)
        self.store.save();loaded=type(self.store)(self.store.root)
        rows=loaded.battles.request('summary',{'character_id':self.character['id']})['entries']
        self.assertEqual(next(r for r in rows if r['id']==a['id'])['edition_id'],'christmas')
        for choice in ('naked','ass-chrome','video-premiere','number-one','former-one'):
            with self.assertRaises(ValueError):self.collection('edition',revision=data['collection']['revision'],entry_id=a['id'],choice=choice)
        with self.assertRaises(ValueError):self.collection('edition',revision='stale',entry_id=a['id'],choice='cosplay')
        other=self.store.add_character('Other');b['character_id']=other['id']
        with self.assertRaises(ValueError):self.collection('edition',revision=data['collection']['revision'],entry_id=b['id'],choice='cosplay')
    def test_fill_and_contain_do_not_change_source(self):
        a=self.import_image(0);data=self.collection();original=copy.deepcopy(a)
        for fit in ('fill','contain'):
            data=self.collection('frame',revision=data['collection']['revision'],key='image:'+a['id'],media_id=a['id'],frame={'x':8,'y':-3,'zoom':1.2,'fit':fit})
            self.assertEqual(data['collection']['frames']['image:'+a['id']]['fit'],fit)
        self.assertEqual(a,original)
        with self.assertRaises(ValueError):self.collection('frame',revision=data['collection']['revision'],key='image:'+a['id'],media_id=a['id'],frame={'x':0,'y':0,'zoom':1,'fit':'stretch'})
    def test_automatic_leader_former_and_opt_out(self):
        ids=[self.import_image(i)['id'] for i in range(12)];battle=self.store.battles
        board={'revision':'seed','ratings':{mid:{'rating':1400-i,'rd':80.,'played':20,'opponents':{other:1 for other in ids if other!=mid},'wins':10,'losses':10,'ties':0} for i,mid in enumerate(ids)},'history':[],'recent':[],'undo':[],'votes':0,'session':None}
        battle._save({'version':1,'rating_model':battle.MODEL,'boards':{self.character['id']+':images':board}})
        state=battle.request('cards',{'character_id':self.character['id']})
        self.assertEqual(next(r for r in state['entries'] if r['id']==ids[0])['edition_id'],'number-one')
        data=self.collection();data=self.collection('edition',revision=data['collection']['revision'],entry_id=ids[0],choice='none')
        self.assertIsNone(next(r for r in self.board()['entries'] if r['id']==ids[0])['edition_id'])
        data=self.collection('edition',revision=data['collection']['revision'],entry_id=ids[0],choice='auto')
        saved=battle._load();saved['boards'][self.character['id']+':images']['ratings'][ids[1]]['rating']=1500;battle._save(saved)
        rows=self.board()['entries'];self.assertEqual(next(r for r in rows if r['id']==ids[0])['edition_id'],'former-one')
        self.assertEqual(next(r for r in rows if r['id']==ids[1])['edition_id'],'number-one')

if __name__=='__main__':unittest.main()
