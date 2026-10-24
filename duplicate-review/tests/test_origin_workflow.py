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
