import json,shutil,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
SKILL=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SKILL/'scripts'))
from export_book import export_book
from accept_book import check_book,accept_book,read
from project_state import next_action
from package_project import package_project

class CompleteWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'绘本项目';self.root.mkdir();r=self.root
        def write(p,data):(r/p).write_text(json.dumps(data,ensure_ascii=False) if not isinstance(data,str) else data,encoding='utf-8')
        write('source.txt','source A');write('source-new.txt','source B')
        (r/'characters').mkdir();write('characters/ref.txt','original character reference')
        (r/'new-characters').mkdir();write('new-characters/ref.txt','different character reference')
        shutil.copy(SKILL/'assets/kidsbook-print.ttf',r/'font.ttf')
        shutil.copy(SKILL/'assets/font-license.txt',r/'font-license.txt')
        write('font-provenance.txt','synthetic font provenance')
        Image.new('RGB',(1600,2400),'white').save(r/'test-image.png')
        pages=[{'number':i,'kind':kind,'text':'小朋友。','image':'test-image.png','image_box_mm':[10,10,128,190],'text_box_mm':[14,120,120,76],'image_role':'background','text_area_reviewed':True} for i,kind in enumerate(('cover','story','story','back'),1)]
        write('layout.json',{'font_path':'font.ttf','font_license_path':'font-license.txt','font_provenance_path':'font-provenance.txt','pages':pages});write('concept.json',{'book_id':'b1','age_band':'5-7'})
        write('story.txt','小朋友。'*4);write('storyboard.json',{'pages':pages})
        write('manifest.json',{'schema_version':1,'book_id':'b1','age_band':'5-7','pages':[{'page':i,'text_version':'v1','characters_version':'v1','text_area':p['text_box_mm'],'current_prompt_path':'prompt.txt','current_image_path':'test-image.png','props':[],'knowledge_check':{'status':'passed','evidence':'synthetic test fixture'}} for i,p in enumerate(pages,1)]})
        write('prompt.txt','synthetic test only');export_book(r/'layout.json',r/'export')
        write('review.json',{'reading_pages':[{'page':i,'status':'passed','evidence':'synthetic test only','image_path':f'export/reading-pages/page-{i:02}.png'} for i in range(1,5)],'print_sides':[{'side':i,'status':'passed','evidence':'synthetic test only','image_path':f'export/print-pages/page-{i:02}.png'} for i in range(1,3)],'unresolved_digital_defects':[]})
        write('project.json',{'schema_version':1,'target_age_bands':['5-7'],'source':{'path':'source.txt','version':'v1','coverage':'synthetic'},'characters_version':'v1','characters_path':'characters','books':[{'id':'b1','age_band':'5-7','source_version':'v1','characters_version':'v1','status':'laid_out','artifacts':{'concept':'concept.json','story':'story.txt','storyboard':'storyboard.json','layout':'layout.json','page_manifest':'manifest.json','reading_pdf':'export/reading.pdf','print_pdf':'export/print.pdf','review':'review.json'}}]})

    def tearDown(self):self.temp.cleanup()
    def test_unicode_project_path_uses_utf8_fixture(self):
        report=check_book(self.root/'project.json','b1')
        self.assertEqual(report['errors'],[])
        self.assertIn('story.txt',report['files'])
    def test_export_accept_resume_and_package(self):
        p=self.root/'project.json'
        project=read(p)
        project['books'][0]['artifacts']['reading_pdf']='export\\reading.pdf'
        project['books'][0]['artifacts']['print_pdf']='export\\print.pdf'
        p.write_text(json.dumps(project),encoding='utf-8')
        review=read(self.root/'review.json')
        review['reading_pages'][0]['image_path']='export\\reading-pages\\page-01.png'
        (self.root/'review.json').write_text(json.dumps(review),encoding='utf-8')
        report=check_book(p,'b1');self.assertEqual(report['errors'],[])
        self.assertIn('font-license.txt',report['files'])
        receipt_path=self.root/'receipts'/'receipt.json'
        accept_book(p,'b1',receipt_path)
        receipt=read(receipt_path)
        self.assertTrue(all('\\' not in path for path in receipt['files']))
        self.assertIn('export/reading.pdf',receipt['files'])
        saved=read(p)
        self.assertTrue(all('\\' not in path for path in saved['books'][0]['artifacts'].values()))
        self.assertIsNone(next_action(read(p),self.root))
        output_zip=self.root/'materials.zip'
        self.assertGreater(package_project(p,'b1',output_zip)['files'],10)
        with zipfile.ZipFile(output_zip) as archive:
            self.assertEqual(set(archive.namelist()),set(receipt['files'])|{'project.json','receipts/receipt.json'})
            self.assertTrue(all('\\' not in path for path in archive.namelist()))
        with self.assertRaises(FileExistsError):package_project(p,'b1',output_zip)
        (self.root/'story.txt').write_text('changed',encoding='utf-8')
        self.assertEqual(next_action(read(p),self.root)['stage'],'revalidate')
        with self.assertRaises(ValueError):package_project(p,'b1',self.root/'stale.zip')
    def test_existing_but_different_selected_image_is_rejected(self):
        Image.new('RGB',(1600,2400),'blue').save(self.root/'other.png')
        p=self.root/'manifest.json';data=read(p);data['pages'][0]['current_image_path']='other.png';p.write_text(json.dumps(data),encoding='utf-8')
        self.assertTrue(any('选图不一致' in e for e in check_book(self.root/'project.json','b1')['errors']))
    def test_accept_does_not_overwrite_receipt_created_during_publish(self):
        project_path=self.root/'project.json';receipt_path=self.root/'receipt.json'
        receipt_path.write_text('already published',encoding='utf-8')
        with patch('accept_book.Path.exists',return_value=False):
            with self.assertRaises(FileExistsError):accept_book(project_path,'b1',receipt_path)
        self.assertEqual(receipt_path.read_text(encoding='utf-8'),'already published')
        self.assertNotIn('acceptance',read(project_path)['books'][0]['artifacts'])
    def test_review_text_file_is_not_final_render(self):
        p=self.root/'review.json';data=read(p);data['reading_pages'][0]['image_path']='source.txt';p.write_text(json.dumps(data),encoding='utf-8')
        self.assertTrue(any('审核渲染图' in e for e in check_book(self.root/'project.json','b1')['errors']))
    def test_story_manuscript_ignores_cover_and_back_but_rejects_reversed_story_pages(self):
        def set_pages(story_texts,export_dir):
            layout=read(self.root/'layout.json')
            layout['pages'][0]['text']='小小探险家'
            layout['pages'][1]['text'],layout['pages'][2]['text']=story_texts
            layout['pages'][3]['text']='明天见！'
            (self.root/'layout.json').write_text(json.dumps(layout,ensure_ascii=False),encoding='utf-8')
            (self.root/'storyboard.json').write_text(json.dumps({'pages':layout['pages']},ensure_ascii=False),encoding='utf-8')
            (self.root/'story.txt').write_text('先穿过花园。再回到家。',encoding='utf-8')
            export_book(self.root/'layout.json',self.root/export_dir)
            review=read(self.root/'review.json')
            for i,record in enumerate(review['reading_pages'],1):record['image_path']=f'{export_dir}/reading-pages/page-{i:02}.png'
            for i,record in enumerate(review['print_sides'],1):record['image_path']=f'{export_dir}/print-pages/page-{i:02}.png'
            (self.root/'review.json').write_text(json.dumps(review,ensure_ascii=False),encoding='utf-8')
            project=read(self.root/'project.json');artifacts=project['books'][0]['artifacts']
            artifacts['reading_pdf']=f'{export_dir}/reading.pdf';artifacts['print_pdf']=f'{export_dir}/print.pdf'
            (self.root/'project.json').write_text(json.dumps(project,ensure_ascii=False),encoding='utf-8')
        set_pages(('先穿过花园。','再回到家。'),'boundary-pages')
        self.assertEqual(check_book(self.root/'project.json','b1')['errors'],[])
        set_pages(('再回到家。','先穿过花园。'),'reversed-story-pages')
        self.assertIn('页3: 朗读稿缺少或乱序本页正文',check_book(self.root/'project.json','b1')['errors'])

if __name__=='__main__':unittest.main()
