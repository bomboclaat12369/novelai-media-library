import copy, tempfile, unittest
from unittest.mock import patch
from test_organizer import fixture
from test_organizer_evidence import add_large_post
from organizer import Organizer, title_case_label


class NavigationTests(unittest.TestCase):
    def test_latest_selected_source_anchor_and_page_use_actual_sort_order(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp);add_large_post(bulk,ids);org.bound=None;org.bind()
            latest='dump-image-0950';prior='dump-image-0005'
            before=copy.deepcopy(bulk.current)
            related=org.related({'ids':[ids[2],prior,latest]})
            posts={p['id']:p for p in related['posts']}
            self.assertEqual(posts['post:dump']['anchor_id'],latest)
            self.assertEqual(posts['post:1']['anchor_id'],ids[2])
            for order in ('original','filename','similar'):
                with patch('organizer.load_image',side_effect=AssertionError('No new analysis')):
                    page=org.page('post','post:dump',order=order,focus_id=latest)
                self.assertEqual(page['offset'],page['ids'].index(latest)//60*60)
                self.assertEqual(page['focus_id'],latest)
                self.assertIn(latest,[i['id'] for i in page['images']])
                self.assertEqual(org.state()['view']['offset'],page['offset'])
            self.assertEqual(bulk.current,before)
            org.mutate('post_evidence',{'job':'fixture-job','revision':0,'id':'post:dump','ignored':True})
            self.assertNotIn('post:dump',[p['id'] for p in org.related({'ids':[latest]})['posts']])
            org.mutate('post_evidence',{'job':'fixture-job','revision':1,'id':'post:dump','ignored':False})
            self.assertEqual(org.related({'ids':[latest]})['posts'][0]['anchor_id'],latest)

    def test_invalid_anchor_does_not_change_post_membership_or_resurrect_parked_images(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            page=org.page('post','post:1',focus_id=ids[7])
            self.assertIsNone(page['focus_id']);self.assertNotIn(ids[7],page['ids'])
            org.mutate('unsort',{'job':'fixture-job','revision':0,'post':'post:1','ids':[ids[2]]})
            page=org.page('post','post:1',focus_id=ids[2])
            self.assertIsNone(page['focus_id']);self.assertNotIn(ids[2],page['ids'])

    def test_names_and_colors_match_library_rules_and_undo(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            org.mutate('save',{'job':'fixture-job','revision':0,'name':'blue and white outfit','ids':[ids[2]],'colors':['black with gold','blue','Blue']})
            group=next(g for g in org.sets().values() if not g.get('library_id'))
            self.assertEqual(group['name'],'Blue and White Outfit');self.assertEqual(group['colors'],['Black with Gold','Blue'])
            target=group['id']
            org.mutate('set_details',{'job':'fixture-job','revision':1,'target':target,'colors':['light blue or green']})
            reopened=Organizer(engine,bulk);reopened.bind()
            self.assertEqual(reopened.sets()[target]['colors'],['Light Blue or Green'])
            reopened.mutate('undo',{'job':'fixture-job','revision':2})
            self.assertEqual(reopened.sets()[target]['colors'],group['colors'])
            self.assertEqual(reopened.export()['sets'][-1]['name'],group['name'])
            self.assertEqual(title_case_label('the girl with a pearl earring'),'The Girl with a Pearl Earring')

if __name__=='__main__':unittest.main()
