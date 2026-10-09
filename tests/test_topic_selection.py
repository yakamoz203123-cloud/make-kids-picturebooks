import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from project_state import next_action,validate_project
class TopicSelectionTests(unittest.TestCase):
 def setUp(self):
  self.project={'schema_version':1,'adaptation_mode':'selected_topics','source':{'path':'source/book.md','version':'v1','coverage':'partial','chapter_index':[{'chapter':1,'read':True,'suggested_books':['b-unfit']},{'chapter':2,'read':False}]},'characters_version':'v1','target_age_bands':['3-4'],'books':[], 'topic_selection':{'age_band':'3-4','status':'ready','topics':[{'id':'abstract','status':'deferred','book_ids':['b-unfit'],'reason':'依赖形式证明'},{'id':'flowers','status':'selected','book_ids':['b-fit'],'reason':'可见工序'}],'queue':['b-fit']}}
 def test_resume_follows_selected_queue_instead_of_chapters(self):
  self.assertEqual(next_action(self.project),{'book_id':'b-fit','stage':'assessed'})
 def test_finished_selection_does_not_expand_to_unread_chapters(self):
  self.project['topic_selection']['queue']=[]
  self.assertIsNone(next_action(self.project))
 def test_pending_selection_requests_age_specific_screening(self):
  self.project['topic_selection'].update(status='pending',topics=[],queue=[])
  self.assertEqual(next_action(self.project),{'stage':'select_topics','age_band':'3-4'})
 def test_queue_cannot_include_deferred_topic(self):
  self.project['topic_selection']['queue']=['b-unfit']
  self.assertTrue(validate_project(self.project))
 def test_selection_age_must_match_target(self):
  self.project['topic_selection']['age_band']='8-10'
  self.assertTrue(validate_project(self.project))
 def test_in_progress_unselected_book_is_not_automatically_continued(self):
  self.project['books']=[{'id':'b-unfit','age_band':'3-4','status':'text','source_version':'v1','characters_version':'v1','artifacts':{}}]
  self.assertEqual(next_action(self.project),{'book_id':'b-fit','stage':'assessed'})
 def test_invalid_mode_is_rejected(self):
  self.project['adaptation_mode']='all_content_automatically'
  self.assertTrue(validate_project(self.project))
 def test_legacy_project_without_mode_keeps_its_resume_behavior(self):
  del self.project['adaptation_mode'];del self.project['topic_selection']
  self.assertEqual(next_action(self.project),{'book_id':'b-unfit','stage':'assessed'})
if __name__=='__main__':unittest.main()
