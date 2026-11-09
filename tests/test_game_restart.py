"""Authenticated restart lifecycle, with isolated synthetic saves."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from game.server import build_server, serve, RESTART_EXIT_CODE


class RestartLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'game.sqlite3'
        self.server=build_server(0,save=self.path,restartable=True)
        self.exit_codes=[]
        self.thread=threading.Thread(target=lambda:self.exit_codes.append(serve(self.server)),daemon=True)
        self.thread.start()
        self.server.store.apply('new',{'selected':['demo-0','demo-1']},'restart-founders',0)

    def tearDown(self):
        if self.thread.is_alive():self.server.shutdown()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def request(self,path='/game/api/restart',data=None,token=None,origin=None):
        headers={'Content-Type':'application/json','X-Game-Token':self.server.token if token is None else token}
        if origin:headers['Origin']=origin
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        connection.request('POST',path,json.dumps(data or {}),headers)
        response=connection.getresponse();body=response.read();connection.close()
        return response.status,json.loads(body)

    def test_restart_preserves_pending_pack_and_releases_port(self):
        self.server.store.apply('pack',{'pack':'standard'},'pack-before-restart',1)
        before=self.server.store.read();old_token=self.server.token
        status,body=self.request()
        self.assertEqual(status,202,body)
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())
        self.assertEqual(self.exit_codes,[RESTART_EXIT_CODE])
        reopened=build_server(self.server.server_port,save=self.path,restartable=True)
        try:
            self.assertEqual(reopened.store.read(),before)
            self.assertNotEqual(reopened.token,old_token)
            self.assertTrue(reopened.store.backups())
        finally:reopened.server_close()

    def test_restart_requires_current_token_and_same_origin(self):
        before=self.server.store.read()
        self.assertEqual(self.request(token='wrong-token')[0],403)
        self.assertEqual(self.request(origin='https://example.invalid')[0],403)
        self.assertFalse(self.server.restarting)
        self.assertEqual(self.server.store.read(),before)

    def test_unmanaged_server_cannot_be_stopped_from_page(self):
        self.server.restartable=False
        self.assertEqual(self.request()[0],400)
        self.assertFalse(self.server.restarting)
        self.assertTrue(self.thread.is_alive())

    def test_backup_failure_leaves_server_and_save_running(self):
        before=self.server.store.read()
        with patch.object(self.server.store,'backup',side_effect=OSError('fixture backup failure')):
            self.assertEqual(self.request()[0],500)
        self.assertFalse(self.server.restarting)
        self.assertEqual(self.server.store.read(),before)
        self.assertTrue(self.thread.is_alive())

    def test_request_waiting_behind_restart_cannot_mutate_save(self):
        before=self.server.store.read()
        self.server.restarting=True
        status,_=self.request('/game/api/action',{'action':'start','body':{},'revision':1,'id':'queued-after-restart'})
        self.assertEqual(status,503)
        self.assertEqual(self.server.store.read(),before)


if __name__=='__main__':unittest.main()
