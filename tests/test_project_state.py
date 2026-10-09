import copy, json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    from project_state import validate_project, save_project, next_action
except ImportError:
    validate_project=save_project=next_action=None

class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.data={'schema_version':1,'source':{'path':'source/ch2.txt','version':'v1','coverage':'partial'},'characters_version':'v1','books':[{'id':'b1','status':'illustrated','source_version':'v1','characters_version':'v1','artifacts':{},'print_feedback':None}]}
    def test_valid_and_resume(self):
        self.assertIsNotNone(validate_project,'进度接口尚未实现')
        self.assertEqual(validate_project(self.data),[])
        self.assertEqual(next_action(self.data),{'book_id':'b1','stage':'laid_out'})
    def test_duplicate_ids(self):
        self.assertIsNotNone(validate_project)
        self.data['books'].append(copy.deepcopy(self.data['books'][0]))
        self.assertTrue(validate_project(self.data))
    def test_invalid_status_and_missing_source(self):
        self.assertIsNotNone(validate_project)
        self.data['books'][0]['status']='bogus'
        del self.data['source']
        self.assertGreaterEqual(len(validate_project(self.data)),2)
    def test_print_feedback_required(self):
        self.assertIsNotNone(validate_project)
        self.data['books'][0]['status']='print_checked'
        self.assertTrue(validate_project(self.data))
    def test_completed_book_skipped(self):
        self.assertIsNotNone(next_action)
        self.data['books'][0].update(status='digital_checked',age_band='3-4',artifacts={k:k+'.json' for k in ('concept','story','storyboard','layout','page_manifest','reading_pdf','print_pdf','review','acceptance')})
        self.assertIsNone(next_action(self.data))
    def test_revision_needs_revalidation(self):
        self.assertIsNotNone(next_action)
        self.data['characters_version']='v2'
        self.assertEqual(next_action(self.data),{'book_id':'b1','stage':'revalidate'})
    def test_invalid_save_preserves_existing(self):
        self.assertIsNotNone(save_project)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'project.json'
            save_project(p,self.data)
            original=p.read_bytes()
            self.data['books'][0]['status']='bogus'
            with self.assertRaises(ValueError): save_project(p,self.data)
            self.assertEqual(p.read_bytes(),original)
            self.assertEqual(json.loads(p.read_text())['books'][0]['status'],'illustrated')
    def test_malformed_input_returns_errors(self):
        self.assertIsNotNone(validate_project)
        for data in [None,[],{}, {'schema_version':1,'source':None,'books':[None]}]:
            self.assertTrue(validate_project(data))

if __name__=='__main__': unittest.main()
