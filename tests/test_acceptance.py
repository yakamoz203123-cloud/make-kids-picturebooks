import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
class AcceptanceTests(unittest.TestCase):
 def test_hash_receipt_rejects_changed_file(self):
  from accept_book import verify_receipt
  import hashlib
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/'story.md').write_text('original')
   project={'source':{'version':'v1'},'characters_version':'v1'}
   book={'id':'b1','age_band':'3-4','source_version':'v1','characters_version':'v1','artifacts':{'acceptance':'receipt.json'}}
   receipt={'schema_version':1,'book_id':'b1','age_band':'3-4','source_version':'v1','characters_version':'v1','files':{'story.md':hashlib.sha256((root/'story.md').read_bytes()).hexdigest()}}
   (root/'receipt.json').write_text(json.dumps(receipt))
   self.assertEqual(verify_receipt(project,book,root),[])
   (root/'story.md').write_text('changed')
   self.assertTrue(verify_receipt(project,book,root))
 def test_missing_receipt_does_not_claim_completion(self):
  from accept_book import verify_receipt
  with tempfile.TemporaryDirectory() as td:
   self.assertTrue(verify_receipt({}, {'artifacts':{'acceptance':'missing.json'}},Path(td)))
 def test_quality_requires_explicit_pilot_choice(self):
  from accept_book import quality_errors
  self.assertTrue(quality_errors({'target_dpi':200}))
  self.assertTrue(quality_errors({'quality_profile':'home-pilot','target_dpi':200}))
  self.assertEqual(quality_errors({'quality_profile':'home-pilot','target_dpi':200,'quality_approval':'用户选择家庭试制200'}),[])
  self.assertEqual(quality_errors({'target_dpi':300}),[])
 def test_complete_book_requires_story_and_covers(self):
  from accept_book import structure_errors
  self.assertTrue(structure_errors([{'kind':'parents'}]*4))
  self.assertEqual(structure_errors([{'kind':'cover'},{'kind':'story'},{'kind':'parents'},{'kind':'back'}]),[])
 def test_receipt_detects_changed_source_path_without_version_bump(self):
  from accept_book import verify_receipt
  import hashlib
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/'source.txt').write_text('a');(root/'other.txt').write_text('b')
   project={'source':{'path':'source.txt','version':'v1'},'characters_version':'v1','characters_path':'characters/v1'}
   book={'id':'b1','age_band':'3-4','artifacts':{'acceptance':'receipt.json'}}
   receipt={'schema_version':1,'book_id':'b1','age_band':'3-4','source_version':'v1','characters_version':'v1','source_path':'source.txt','characters_path':'characters/v1','files':{'source.txt':hashlib.sha256((root/'source.txt').read_bytes()).hexdigest()}}
   (root/'receipt.json').write_text(json.dumps(receipt))
   self.assertEqual(verify_receipt(project,book,root),[])
   project['source']['path']='other.txt'
   self.assertTrue(verify_receipt(project,book,root))
if __name__=='__main__':unittest.main()
