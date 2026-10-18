"""Profile validation, independent MMR and persistence checks."""
import unittest
import test_runtime_stability as fixtures

class ProfileTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image
    post=fixtures.RuntimeStabilityTests.post

    def test_profile_persistence_validation_and_conflicts(self):
        images=[self.import_image(i) for i in range(7)]
        owner=self.character['id']
        def call(action,**extra):
            return self.post('/api/profile/'+action,{'character_id':owner,**extra})
        code,state=call('state');self.assertEqual(code,200)
        profile={'photos':[m['id'] for m in images[:5]],'measurements':{'height':{'value':'67.5','status':'confirmed'},'bust':{'value':'35','status':'estimated'},'bra':{'value':'34D (US)','status':'estimated'}},'notes':'Test notes'}
        code,saved=call('save',revision='',profile=profile);self.assertEqual(code,200,saved)
        self.assertEqual(saved['profile']['photos'],profile['photos'])
        self.assertEqual(saved['profile']['measurements']['height']['status'],'confirmed')
        restored=type(self.store)(self.store.root)
        self.assertEqual(restored.profile_request('state',{'character_id':owner}),saved)
        self.assertEqual(call('save',revision='',profile=profile)[0],400)
        revision=saved['profile']['revision']
        for value in ['NaN','inf','-1','0','abc']:
            bad={**profile,'measurements':{'height':{'value':value}}}
            self.assertEqual(call('save',revision=revision,profile=bad)[0],400)
        other=self.store.add_character('Other person');images[5]['character_id']=other['id'];images[6]['media_type']='video'
        for ids in [[images[5]['id']],[images[6]['id']],[images[0]['id']]*2,[m['id'] for m in images[:6]]]:
            self.assertEqual(call('save',revision=revision,profile={**profile,'photos':ids})[0],400)
        self.assertEqual(call('state')[1],saved)
        # Deleted images disappear from profile display; manual photos never affect rankings.
        self.store.data['media'].remove(images[0])
        current=call('state')[1]['profile'];self.assertNotIn(images[0]['id'],current['photos'])
        self.assertEqual(self.store.battles.request('state',{'character_id':owner})['votes'],0)

if __name__=='__main__':unittest.main()
