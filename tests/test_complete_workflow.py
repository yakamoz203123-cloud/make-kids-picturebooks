import json,shutil,sys,tempfile,unittest
from pathlib import Path
from PIL import Image
SKILL=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SKILL/'scripts'))
from export_book import export_book
from accept_book import check_book,accept_book,read
from project_state import next_action
from package_project import package_project

class CompleteWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);r=self.root
        def write(p,data):(r/p).write_text(json.dumps(data,ensure_ascii=False) if not isinstance(data,str) else data)
        write('source.txt','source A');write('source-new.txt','source B')
        (r/'characters').mkdir();write('characters/ref.txt','original character reference')
        (r/'new-characters').mkdir();write('new-characters/ref.txt','different character reference')
        shutil.copy(SKILL/'assets/kidsbook-print.ttf',r/'font.ttf')
        shutil.copy(SKILL/'assets/font-license.txt',r/'font-license.txt')
        Image.new('RGB',(1600,2400),'white').save(r/'test-image.png')
        pages=[{'number':i,'kind':kind,'text':'小朋友。','image':'test-image.png','image_box_mm':[10,10,128,190],'text_box_mm':[14,120,120,76],'image_role':'background','text_area_reviewed':True} for i,kind in enumerate(('cover','story','story','back'),1)]
        write('layout.json',{'font_path':'font.ttf','font_license_path':'font-license.txt','pages':pages});write('concept.json',{'book_id':'b1','age_band':'5-7'})
        write('story.txt','小朋友。'*4);write('storyboard.json',{'pages':pages})
        write('manifest.json',{'schema_version':1,'book_id':'b1','age_band':'5-7','pages':[{'page':i,'text_version':'v1','characters_version':'v1','text_area':p['text_box_mm'],'current_prompt_path':'prompt.txt','current_image_path':'test-image.png','props':[],'knowledge_check':{'status':'passed','evidence':'synthetic test fixture'}} for i,p in enumerate(pages,1)]})
        write('prompt.txt','synthetic test only');export_book(r/'layout.json',r/'export')
        write('review.json',{'reading_pages':[{'page':i,'status':'passed','evidence':'synthetic test only','image_path':f'export/reading-pages/page-{i:02}.png'} for i in range(1,5)],'print_sides':[{'side':i,'status':'passed','evidence':'synthetic test only','image_path':f'export/print-pages/page-{i:02}.png'} for i in range(1,3)],'unresolved_digital_defects':[]})
        write('project.json',{'schema_version':1,'target_age_bands':['5-7'],'source':{'path':'source.txt','version':'v1','coverage':'synthetic'},'characters_version':'v1','characters_path':'characters','books':[{'id':'b1','age_band':'5-7','source_version':'v1','characters_version':'v1','status':'laid_out','artifacts':{'concept':'concept.json','story':'story.txt','storyboard':'storyboard.json','layout':'layout.json','page_manifest':'manifest.json','reading_pdf':'export/reading.pdf','print_pdf':'export/print.pdf','review':'review.json'}}]})

    def tearDown(self):self.temp.cleanup()
    def test_export_accept_resume_and_package(self):
        p=self.root/'project.json'
        report=check_book(p,'b1');self.assertEqual(report['errors'],[])
        self.assertIn('font-license.txt',report['files'])
        accept_book(p,'b1',self.root/'receipt.json')
        self.assertIsNone(next_action(read(p),self.root))
        self.assertGreater(package_project(p,'b1',self.root/'materials.zip')['files'],10)
        (self.root/'story.txt').write_text('changed')
        self.assertEqual(next_action(read(p),self.root)['stage'],'revalidate')
        with self.assertRaises(ValueError):package_project(p,'b1',self.root/'stale.zip')
    def test_existing_but_different_selected_image_is_rejected(self):
        Image.new('RGB',(1600,2400),'blue').save(self.root/'other.png')
        p=self.root/'manifest.json';data=read(p);data['pages'][0]['current_image_path']='other.png';p.write_text(json.dumps(data))
        self.assertTrue(any('选图不一致' in e for e in check_book(self.root/'project.json','b1')['errors']))
    def test_review_text_file_is_not_final_render(self):
        p=self.root/'review.json';data=read(p);data['reading_pages'][0]['image_path']='source.txt';p.write_text(json.dumps(data))
        self.assertTrue(any('审核渲染图' in e for e in check_book(self.root/'project.json','b1')['errors']))

if __name__=='__main__':unittest.main()
