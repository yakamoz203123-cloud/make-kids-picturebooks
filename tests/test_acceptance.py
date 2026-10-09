import json,shutil,sys,tempfile,unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))

SKILL=Path(__file__).resolve().parents[1]

def complete_project(root):
 def write(path,data):
  (root/path).write_text(json.dumps(data,ensure_ascii=False) if not isinstance(data,str) else data,encoding='utf-8')
 write('source.txt','source A')
 (root/'characters').mkdir();write('characters/ref.txt','character reference')
 shutil.copy(SKILL/'assets/kidsbook-print.ttf',root/'font.ttf')
 shutil.copy(SKILL/'assets/font-license.txt',root/'font-license.txt')
 write('font-provenance.txt','synthetic font provenance')
 Image.new('RGB',(1600,2400),'white').save(root/'test-image.png')
 pages=[{'number':i,'kind':kind,'text':'小朋友。','image':'test-image.png','image_box_mm':[10,10,128,190],'text_box_mm':[14,120,120,76],'image_role':'background','text_area_reviewed':True} for i,kind in enumerate(('cover','story','story','back'),1)]
 write('layout.json',{'font_path':'font.ttf','font_license_path':'font-license.txt','font_provenance_path':'font-provenance.txt','pages':pages})
 write('concept.json',{'book_id':'b1','age_band':'5-7'});write('story.txt','小朋友。'*4);write('storyboard.json',{'pages':pages})
 write('manifest.json',{'schema_version':1,'book_id':'b1','age_band':'5-7','pages':[{'page':i,'text_version':'v1','characters_version':'v1','text_area':page['text_box_mm'],'current_prompt_path':'prompt.txt','current_image_path':'test-image.png','props':[],'knowledge_check':{'status':'passed','evidence':'synthetic test fixture'}} for i,page in enumerate(pages,1)]})
 write('prompt.txt','synthetic test only')
 from export_book import export_book
 export_book(root/'layout.json',root/'export')
 write('review.json',{'reading_pages':[{'page':i,'status':'passed','evidence':'synthetic test only','image_path':f'export/reading-pages/page-{i:02}.png'} for i in range(1,5)],'print_sides':[{'side':i,'status':'passed','evidence':'synthetic test only','image_path':f'export/print-pages/page-{i:02}.png'} for i in range(1,3)],'unresolved_digital_defects':[]})
 write('project.json',{'schema_version':1,'target_age_bands':['5-7'],'source':{'path':'source.txt','version':'v1','coverage':'synthetic'},'characters_version':'v1','characters_path':'characters','books':[{'id':'b1','age_band':'5-7','source_version':'v1','characters_version':'v1','status':'laid_out','artifacts':{'concept':'concept.json','story':'story.txt','storyboard':'storyboard.json','layout':'layout.json','page_manifest':'manifest.json','reading_pdf':'export/reading.pdf','print_pdf':'export/print.pdf','review':'review.json'}}]})
 return root/'project.json'

class AcceptanceTests(unittest.TestCase):
 def test_acceptance_requires_declared_font_license_and_provenance(self):
  from accept_book import check_book
  for field,label in (('font_license_path','字体许可证'),('font_provenance_path','字体来源证明')):
   with self.subTest(field=field),tempfile.TemporaryDirectory() as td:
    root=Path(td);project_path=complete_project(root);layout=json.loads((root/'layout.json').read_text(encoding='utf-8'))
    del layout[field];(root/'layout.json').write_text(json.dumps(layout,ensure_ascii=False),encoding='utf-8')
    self.assertIn(f'验收版面须保存项目内{label}路径',check_book(project_path,'b1')['errors'])
 def test_hash_receipt_rejects_changed_file(self):
  from accept_book import verify_receipt
  import hashlib
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/'story.md').write_text('original',encoding='utf-8')
   project={'source':{'version':'v1'},'characters_version':'v1'}
   book={'id':'b1','age_band':'3-4','source_version':'v1','characters_version':'v1','artifacts':{'acceptance':'receipt.json'}}
   receipt={'schema_version':1,'book_id':'b1','age_band':'3-4','source_version':'v1','characters_version':'v1','files':{'story.md':hashlib.sha256((root/'story.md').read_bytes()).hexdigest()}}
   (root/'receipt.json').write_text(json.dumps(receipt),encoding='utf-8')
   self.assertEqual(verify_receipt(project,book,root),[])
   (root/'story.md').write_text('changed',encoding='utf-8')
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
   root=Path(td);(root/'source.txt').write_text('a',encoding='utf-8');(root/'other.txt').write_text('b',encoding='utf-8')
   project={'source':{'path':'source.txt','version':'v1'},'characters_version':'v1','characters_path':'characters/v1'}
   book={'id':'b1','age_band':'3-4','artifacts':{'acceptance':'receipt.json'}}
   receipt={'schema_version':1,'book_id':'b1','age_band':'3-4','source_version':'v1','characters_version':'v1','source_path':'source.txt','characters_path':'characters/v1','files':{'source.txt':hashlib.sha256((root/'source.txt').read_bytes()).hexdigest()}}
   (root/'receipt.json').write_text(json.dumps(receipt),encoding='utf-8')
   self.assertEqual(verify_receipt(project,book,root),[])
   project['source']['path']='other.txt'
   self.assertTrue(verify_receipt(project,book,root))
if __name__=='__main__':unittest.main()
