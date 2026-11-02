import copy,json,tempfile,unittest
from test_organizer import fixture
from organizer import Organizer
from bulk.workbench import Workbench
class OrganizerColors(unittest.TestCase):
    def test_backfill_all_scopes_and_future_save_without_changing_progress(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp);state=copy.deepcopy(org.state());catalog=copy.deepcopy(bulk.current)
            original={'id':'saved','name':'White Bikini 3','colors':['Custom'],'members':[ids[3]],'created':123,'updated':456}
            with org.db() as db:
                for scope in (org.scope,'other-girl'):db.execute('INSERT INTO sets VALUES (?,?,?)',(scope,'saved',json.dumps(original)))
            reopened=Organizer(engine,bulk);reopened.bind()
            with reopened.db() as db:
                records=[json.loads(raw) for raw, in db.execute('SELECT data FROM sets WHERE id="saved"')]
            self.assertEqual(len(records),2)
            for record in records:self.assertEqual(record,{**original,'colors':['Custom','White']})
            self.assertEqual(reopened.state(),state);self.assertEqual(bulk.current,catalog)
            reopened.mutate('save',{'job':'fixture-job','revision':state.get('revision',0),'ids':[ids[4]],'name':'Red Blue Outfit'})
            group=next(g for g in reopened.sets().values() if g['name']=='Red Blue Outfit');self.assertEqual(group['colors'],['Red','Blue'])
    def test_accepted_bulk_drafts_backfill_without_reordering_jobs(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            group={'id':'draft','name':'Pink Dress','colors':['Custom'],'review':'accepted','members':ids[2:4],'original_members':ids[2:4],'reviewed_at':123}
            job={**copy.deepcopy(bulk.current),'proposals':[group]}
            with bulk.db() as db:
                db.execute('UPDATE jobs SET data=?,updated=? WHERE id=?',(json.dumps(job),456,job['id']))
            loaded=Workbench(engine)
            self.assertEqual(loaded.current['proposals'][0],{**group,'colors':['Custom','Pink']})
            with loaded.db() as db:self.assertEqual(db.execute('SELECT updated FROM jobs WHERE id=?',(job['id'],)).fetchone()[0],456)
            loaded.current['proposals'][0]['name']='Purple Dress';loaded.persist()
            self.assertEqual(loaded.current['proposals'][0]['colors'],['Custom','Pink','Purple'])
if __name__=='__main__':unittest.main()
