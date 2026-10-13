"""Focused coverage for separate Set categories and standalone-only updates."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import test_runtime_stability as fixtures

class SetCategoryTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    post=fixtures.RuntimeStabilityTests.post

    def test_api_persistence_isolation_and_delete(self):
        owner=self.character['id']
        media_category=self.store.add_category(owner,'Outfits')
        status,category=self.post('/api/set-categories',{'character_id':owner,'name':'Outfits'})
        self.assertEqual(status,200)
        self.assertNotEqual(category['id'],media_category['id'])
        self.assertEqual(self.store.add_set_category(owner,'outfits')['id'],category['id'])
        status,item=self.post('/api/sets',{'character_id':owner,'name':'Set','media_ids':[],'categories':[category['id'],category['id']]})
        self.assertEqual(status,200);self.assertEqual(item['categories'],[category['id']])
        foreign=self.store.add_set_category(self.store.add_character('Other')['id'],'Foreign')
        for invalid in [[foreign['id']],[media_category['id']],'not a list',[{}]]:
            status,_=self.post('/api/sets/'+item['id'],{'name':'Must not save','categories':invalid})
            self.assertEqual(status,400);self.assertEqual(item['name'],'Set')
        self.store.update_set(item['id'],favorite=True)
        self.assertEqual(item['categories'],[category['id']])
        self.post('/api/set-categories/'+category['id'],{'name':'Clothing'})
        reloaded=fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertEqual(reloaded.character(owner)['set_categories'][0]['name'],'Clothing')
        self.assertEqual(reloaded.set_item(item['id'])['categories'],[category['id']])
        reloaded.edit_set_category(category['id'])
        self.assertEqual(reloaded.set_item(item['id'])['categories'],[])
        self.assertEqual(reloaded.character(owner)['categories'],[media_category])
        self.assertTrue(reloaded.set_item(item['id'])['favorite'])

    def test_clear_and_legacy_set(self):
        item=self.store.create_set(self.character['id'],'Legacy',[])
        item.pop('categories');self.store.save()
        cat=self.store.add_set_category(self.character['id'],'Tagged')
        self.store.update_set(item['id'],categories=[cat['id']])
        self.store.update_set(item['id'],categories=[])
        self.assertEqual(item['categories'],[])

class StandaloneUpdatesTests(unittest.TestCase):
    def test_only_html_downloaded_force_failure_and_cached_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            ui=fixtures.RUNTIME['StandaloneUI'](Path(directory))
            html=b'<html data-nai-media-payload-version="2.8.73">verified</html>'
            calls=[]
            def download(url,*args):
                calls.append(url)
                if 'manifest.json' in url:
                    return json.dumps({'standalone_url':ui.BASE+'payload/page.html','standalone_sha256':hashlib.sha256(html).hexdigest()}).encode()
                return html
            ui._download=download
            self.assertEqual(ui.document(force=True),html)
            self.assertEqual(len(calls),2)
            self.assertEqual(ui.document(),html);self.assertEqual(len(calls),2)
            def offline(*args):raise OSError('offline')
            ui._download=offline
            with self.assertRaises(OSError):ui.document(force=True)
            self.assertEqual(ui.document(),html)
            calls.clear();ui._download=download
            ui.document(force=True)
            self.assertEqual(len(calls),1,'same release needs only its manifest')
