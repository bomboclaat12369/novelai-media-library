"""Focused regression checks for keeper provenance and review transfers."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_bulk_preparation import FakeEncoder,create
from engine import Engine,sha256
from bulk.workbench import Workbench
import tempfile,unittest
from unittest.mock import patch

class OriginWorkflow(unittest.TestCase):
    def test_history_inventory_skips_grouping_and_keeps_unresolved_origins(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);incoming=root/'incoming';engine=Engine(root/'state')
            live=incoming/'Post 1'/'kept.png';create(live,(20,30,40))
            q=incoming/'_Duplicate_Review_Quarantine'/'batch'/'Post 2'/'old.png';create(q,(50,60,70))
            w=Workbench(engine)
            with patch.object(w,'recover_visual_aliases',return_value=0),patch.object(w,'encode',side_effect=AssertionError('No set analysis')):
                w.start({'roots':[str(incoming)],'limit':0},inventory_only=True);w.thread.join(20)
            self.assertNotIn('error',w.current);self.assertTrue(w.current['inventory_complete'])
            self.assertEqual(w.current['items'],{});self.assertEqual(w.current['proposals'],[])
            d=w.origin_audit(mode='all');self.assertEqual(d['total_files'],1)
            self.assertEqual(d['origins'][0]['original_path'],str(incoming/'Post 2'/'old.png'))
            self.assertEqual(d['origins'][0]['quarantine_path'],str(q))
            self.assertEqual(d['image']['w'],160)
            w.mark_origin({'job':w.current['id'],'target':d['image']['id'],'status':'discarded'})
            self.assertEqual(w.origin_audit()['total_files'],1)
            self.assertEqual(w.origin_audit()['counts']['discarded'],1)
            before=q.read_bytes();keeper=d['candidates'][0]['id']
            w.confirm_origin({'job':w.current['id'],'target':d['image']['id'],'keeper':keeper})
            self.assertEqual(q.read_bytes(),before);self.assertTrue(live.exists())
            self.assertEqual(len(w.current['source_catalog'][keeper]['origins']),2)
            w.undo_origin({'job':w.current['id']});self.assertEqual(w.origin_audit()['total_files'],1)

    def test_recorded_keeper_chain_undo_and_full_folder_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);incoming=root/'incoming';engine=Engine(root/'state')
            paths=[incoming/('Post '+str(i+1))/('A'+str(i)+'.png') for i in range(3)]
            for i,p in enumerate(paths):create(p,(40+i*50,20,40))
            engine.start([str(incoming)],[],'balanced');engine.thread.join(20)
            with engine.db() as db:
                rows=[dict(db.execute('SELECT * FROM files WHERE path=?',(str(p),)).fetchone()) for p in paths]
                engine._move_records(db,rows[0],rows[1])
                engine._move_records(db,rows[1],rows[2])
                moves=[dict(x) for x in db.execute('SELECT * FROM moves ORDER BY created')]
            self.assertEqual(moves[0]['keeper_sha'],rows[1]['sha'])
            w=Workbench(engine,lambda _:FakeEncoder())
            with patch.object(w,'recover_visual_aliases',return_value=0):
                w.start({'roots':[str(incoming)],'limit':200});w.thread.join(20)
            self.assertNotIn('error',w.current)
            self.assertEqual(w.current['inventory']['recorded_decision_links'],2)
            item=next(iter(w.current['items'].values()));self.assertEqual(len(item['sources']),3)
            # Undone links must not be reused, even when the kept image survives.
            with engine.db() as db:db.execute("UPDATE moves SET state='undone' WHERE id=?",(moves[0]['id'],))
            with patch.object(w,'recover_visual_aliases',return_value=0):
                w.start({'roots':[str(incoming)],'limit':200});w.thread.join(20)
            self.assertEqual(w.current['inventory']['recorded_decision_links'],1)
            self.assertEqual(w.current['inventory']['unlinked_quarantine'],1)
            audit=w.origin_audit();self.assertEqual(audit['total'],1)
            w.confirm_origin({'job':w.current['id'],'target':audit['image']['id'],'keeper':rows[2]['sha']})
            self.assertEqual(w.origin_audit()['total'],0)
            w.undo_origin({'job':w.current['id']});self.assertEqual(w.origin_audit()['total'],1)
            w.confirm_origin({'job':w.current['id'],'target':audit['image']['id'],'keeper':rows[2]['sha']})
            with patch.object(w,'recover_visual_aliases',return_value=0):
                w.start({'roots':[str(incoming)],'limit':200});w.thread.join(20)
            self.assertEqual(w.current['inventory']['unlinked_quarantine'],0)

    def test_targeted_queue_keeps_all_origins_and_resumes_without_padding(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);incoming=root/'incoming';engine=Engine(root/'state')
            for i in range(30):create(incoming/'Post 1'/('A'+str(i)+'.png'),(i,10,20))
            q1=incoming/'_Duplicate_Review_Quarantine'/'one'/'Post 2'/'missing.png'
            q2=incoming/'_Duplicate_Review_Quarantine'/'two'/'Post 3'/'missing-copy.png'
            q3=incoming/'_Duplicate_Review_Quarantine'/'three'/'Post 4'/'other.png'
            create(q1,(230,110,20));q2.parent.mkdir(parents=True);q2.write_bytes(q1.read_bytes());create(q3,(240,110,20))
            w=Workbench(engine,lambda _:FakeEncoder())
            with patch.object(w,'recover_visual_aliases',return_value=0):
                w.start({'roots':[str(incoming)],'limit':200});w.thread.join(20)
            d=w.origin_audit();self.assertEqual(d['total_files'],3);self.assertEqual(d['total'],2)
            self.assertEqual(d['candidates'],[])  # No fingerprints: never pad with random survivors.
            allrows=w.origin_audit(mode='all');self.assertEqual(allrows['candidate_count'],30)
            self.assertEqual(len(allrows['candidates']),24);self.assertEqual(len(w.origin_audit(mode='all',page=1)['candidates']),6)
            search=w.origin_audit(query='A29.png');self.assertEqual(search['candidate_count'],1)
            selected=w.origin_audit(offset=1)
            reopened=Workbench(engine,lambda _:FakeEncoder());self.assertEqual(reopened.origin_audit()['digest'],selected['digest'])
            reopened.mark_origin({'job':w.current['id'],'target':selected['image']['id'],'status':'deferred'})
            self.assertEqual(reopened.origin_audit()['total_files'],3)
            self.assertEqual(reopened.origin_audit(review_filter='deferred')['total'],1)
            self.assertIn(selected['digest'],reopened.export()['origin_review'])
            reopened.mark_origin({'job':w.current['id'],'target':selected['image']['id'],'status':'no_counterpart'})
            self.assertEqual(reopened.origin_audit()['counts']['no_counterpart'],selected['copy_count'])
            pair=reopened.origin_audit(target=sha256(q1));self.assertEqual(pair['copy_count'],2)
            self.assertEqual({o['post_id'] for o in pair['origins']},{'2','3'})
            keeper=search['candidates'][0]['id'];before=reopened.current['inventory']['unlinked_quarantine']
            # A changed second physical copy must fail without attaching any origins.
            old=q2.read_bytes();q2.write_bytes(b'changed')
            with self.assertRaises(ValueError):reopened.confirm_origin({'job':w.current['id'],'target':pair['image']['id'],'keeper':keeper})
            self.assertEqual(reopened.current['inventory']['unlinked_quarantine'],before)
            q2.write_bytes(old)
            from engine import stat_key
            for row in reopened.current['source_catalog'].values():
                if row['path']==str(q2):row['stamp']=stat_key(q2)
            reopened.confirm_origin({'job':w.current['id'],'target':pair['image']['id'],'keeper':keeper})
            survivor=reopened.current['source_catalog'][keeper]
            self.assertEqual({o['post_id'] for o in survivor['origins']},{'1','2','3'})
            self.assertEqual(reopened.origin_audit()['total_files'],1)
            reopened.undo_origin({'job':w.current['id']});self.assertEqual(reopened.origin_audit()['total_files'],3)

    def test_context_transfer_and_undo_preserve_unique_membership(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);incoming=root/'incoming'
            for n,c in [('A1',(30,40,50)),('A2',(40,50,60)),('B1',(150,20,30)),('B2',(160,30,40))]:create(incoming/'Post 42'/(n+'.png'),c)
            engine=Engine(root/'state');w=Workbench(engine,lambda _:FakeEncoder())
            w.start({'roots':[str(incoming)],'limit':200});w.thread.join(20)
            a,b=w.current['proposals'];b['review']='accepted'
            detail=w.neighbors(a['id']);self.assertEqual(detail['total'],2);self.assertTrue(detail['complete_inventory'])
            self.assertEqual(detail['related'][0]['id'],b['id'])
            job=w.current['id'];ids=b['members'][:]
            w.transfer({'job':job,'group':a['id'],'members':ids})
            self.assertEqual(len(a['members']),4);self.assertEqual(b['members'],[]);self.assertEqual(a['review'],'pending')
            w.undo_review({'job':job});a,b=w.current['proposals']
            self.assertEqual(len(a['members']),2);self.assertEqual(b['members'],ids);self.assertEqual(b['review'],'accepted')
            # An outside-pilot image remains visible but cannot be transferred.
            outside=w.current['items'].pop(ids[0]);b['members'].remove(ids[0])
            detail=w.neighbors(a['id']);row=next(i for i in detail['images'] if i['id']==ids[0])
            self.assertFalse(row['can_add']);self.assertIn('Outside pilot',row['status'])
            self.assertEqual(w.preview_path(ids[0]),Path(outside['path']))
            with self.assertRaises(ValueError):w.transfer({'job':job,'group':a['id'],'members':[ids[0]]})

if __name__=='__main__':unittest.main()
