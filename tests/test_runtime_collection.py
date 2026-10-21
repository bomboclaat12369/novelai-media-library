"""Card edits/progress must persist without changing ratings or profile data."""
import copy
import unittest
import test_runtime_stability as fixtures

class CollectionTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image
    post=fixtures.RuntimeStabilityTests.post

    def call(self,action='state',**kw):
        code,result=self.post('/api/collection/'+action,{'character_id':self.character['id'],**kw})
        return code,result

    def test_empty_and_invalid_edits(self):
        code,data=self.call();self.assertEqual(code,200,data)
        self.assertIsNone(data['completion']);self.assertEqual(data['xp'],0)
        rev=data['collection']['revision'];attrs=data['collection']['attributes']
        for invalid in [[],attrs[:3],attrs+[attrs[0]],[{**a,'value':100} for a in attrs],[{**a,'weight':float('nan')} for a in attrs],[{**a,'value':True} for a in attrs]]:
            self.assertEqual(self.call('save',revision=rev,attributes=invalid)[0],400)
        self.assertEqual(self.call('save',revision=rev,finish='platinum')[0],400)
        self.assertEqual(self.call('frame',revision=rev,media_id='other',key='image:other',frame={'x':0,'y':0,'zoom':1})[0],400)
        self.assertEqual(self.call()[1]['collection'],data['collection'])

    def test_attributes_frames_and_old_profile_saves_do_not_change_mmr(self):
        m=self.import_image(1);code,data=self.call();self.assertEqual(code,200)
        before=copy.deepcopy(self.store.battles.data)
        attrs=[{'label':label,'value':score,'weight':weight} for label,score,weight in [('Face',95,2),('Breasts',89,1),('Butt',91,1),('Style',90,1)]]
        code,saved=self.call('save',revision=data['collection']['revision'],attributes=attrs);self.assertEqual(code,200,saved)
        self.assertEqual(self.call('save',revision=data['collection']['revision'],attributes=attrs)[0],400)
        rev=saved['collection']['revision']
        for frame in [{'x':51,'y':0,'zoom':1},{'x':0,'y':float('nan'),'zoom':1},{'x':0,'y':0,'zoom':0}]:
            self.assertEqual(self.call('frame',revision=rev,media_id=m['id'],key='image:'+m['id'],frame=frame)[0],400)
        code,saved=self.call('frame',revision=rev,media_id=m['id'],key='image:'+m['id'],frame={'x':10,'y':-5,'zoom':1.5});self.assertEqual(code,200,saved)
        code,profile=self.post('/api/profile/save',{'character_id':self.character['id'],'revision':'','profile':{'photos':[m['id']],'measurements':{},'notes':'old client'}});self.assertEqual(code,200)
        restored=type(self.store)(self.store.root).collection_request('state',{'character_id':self.character['id']})
        self.assertEqual(restored['collection']['attributes'],attrs)
        self.assertEqual(restored['collection']['frames']['image:'+m['id']]['x'],10)
        self.assertEqual(self.store.battles.data,before)
        self.assertNotIn('crop',m)

    def test_progress_organization_source_changes_and_permanent_milestones(self):
        a,b,c=[self.import_image(i) for i in range(3)]
        self.store.create_set(self.character['id'],'Set',[a['id']],preserve_placement=True)
        c['in_review']=True
        _,data=self.call();tracks={t['id']:t for t in data['tracks']}
        self.assertEqual(tracks['organization']['done'],1);self.assertEqual(tracks['organization']['total'],2)
        self.assertEqual(tracks['sets-placement']['total'],1)
        self.assertEqual(data['unorganized'],[b['id']]);self.assertEqual(data['stats']['review'],1)
        _,saved=self.call('review',revision=data['collection']['revision'],media_id=b['id'],reviewed=True)
        self.assertEqual(saved['unorganized'],[]);xp=saved['xp']
        self.assertEqual(self.call()[1]['xp'],xp)
        b['sha256']='new-source'
        _,changed=self.call();self.assertEqual(changed['unorganized'],[b['id']]);self.assertEqual(changed['xp'],xp)
        self.assertEqual(self.call('review',revision=changed['collection']['revision'],media_id='missing',reviewed=True)[0],400)
        other=self.store.add_character('Other');b['character_id']=other['id']
        self.assertEqual(self.call('frame',revision=changed['collection']['revision'],media_id=b['id'],key='image:'+b['id'],frame={'x':0,'y':0,'zoom':1})[0],400)

    def test_failed_save_rolls_back_collection(self):
        _,data=self.call();previous=copy.deepcopy(self.character['collection'])
        original=self.store.save
        self.store.save=lambda:(_ for _ in ()).throw(OSError('disk full'))
        try:
            with self.assertRaises(OSError):self.store.collection_request('save',{'character_id':self.character['id'],'revision':data['collection']['revision'],'attributes':data['collection']['attributes']})
            self.assertEqual(self.character['collection'],previous)
        finally:self.store.save=original

if __name__=='__main__':unittest.main()
