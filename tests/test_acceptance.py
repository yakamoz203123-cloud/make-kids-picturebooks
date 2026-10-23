import copy,json,shutil,sys,tempfile,unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))

SKILL=Path(__file__).resolve().parents[1]

def social_layout():
 return {'profile':'social-vertical-9x16','canvas':{'width_px':1080,'height_px':1920},'subject_safe_area':[0.08,0.10,0.84,0.62],'text_safe_area':[0.08,0.76,0.84,0.14],'avoid_regions':['top-ui','bottom-ui'],'source_aspect_ratio':'9:16','status':'passed'}

def layout_design(page):
 return {'layout_style_version':'layout-v1','layout_mode':'scene-integrated','text_anchor':'top-left','text_treatment':'natural-space','text_align':'left','max_lines':4,'focal_point':f'第{page}页孩子手中的纸飞机','text_safe_area':'左上方浅色墙面','avoid_covering':['孩子的脸部','纸飞机'],'page_rhythm':'action','palette_token':'warm-paper','status':'passed','social_layout':social_layout()}

def layout_review(page):
 return {'status':'passed','evidence':f'第{page}页正文位于左上方浅色墙面，未遮挡孩子的脸部和纸飞机。','text_image_relationship':'integrated','contrast':'passed','focal_point_clear':True,'occlusion':'none','rhythm_reason':f'第{page}页沿用左上文字与右下主体的动作节奏。'}

def social_layout_review(page):
 return {'status':'passed','evidence':f'社媒第{page}页文字位于左上方浅色安全区，未遮挡孩子脸部、纸飞机和动作焦点。','text_image_relationship':'integrated','contrast':'passed','focal_point_clear':True,'occlusion':'none','rhythm_reason':f'社媒第{page}页保持左上文字与右下主体的视觉节奏。'}

def complete_project(root, blank_page=None):
 def write(path,data):
  (root/path).write_text(json.dumps(data,ensure_ascii=False) if not isinstance(data,str) else data,encoding='utf-8')
 write('source.txt','source A')
 (root/'characters').mkdir();write('characters/ref.txt','character reference')
 shutil.copy(SKILL/'assets/kidsbook-print.ttf',root/'font.ttf')
 shutil.copy(SKILL/'assets/font-license.txt',root/'font-license.txt')
 write('font-provenance.txt','synthetic font provenance')
 Image.new('RGB',(1800,3200),'white').save(root/'test-image.png')
 Image.new('RGB',(600,800),'white').save(root/'contact-sheet.png')
 write('education-goal.json',{'schema_version':1,'core_knowledge':'纸飞机会沿着飞行方向前进。','target_age_band':'5-7','prior_experience':'孩子见过纸飞机或玩过投掷游戏。','visible_relationship':'手臂用力和纸飞机飞行方向可以在画面中对应起来。','knowledge_boundary':'不把一次飞行距离说成固定规律。','reading_observation':'共读后请孩子指出纸飞机从哪里飞向哪里。'})
 write('metrics.json',{'wall_clock_ms':120000,'image_artifact_span_ms':60000,'model_wait_ms':'unknown','image_generation_calls':4,'attempts':4,'failures':0,'retries':0,'rework_rounds':0,'cache_hits':0,'resume_events':'unknown','output_quality':'pending'})
 pages=[]
 for i,kind in enumerate(('cover','story','story','back'),1):
  if i==blank_page:kind='blank'
  pages.append({'number':i,'kind':kind,'text':'' if i==blank_page else '小朋友。','image':'test-image.png','image_box_mm':[10,10,128,190],'text_box_mm':[14,120,120,76],'image_role':'background','text_area_reviewed':True,'layout_design':layout_design(i)})
 write('layout.json',{'font_path':'font.ttf','font_license_path':'font-license.txt','font_provenance_path':'font-provenance.txt','pages':pages})
 write('concept.json',{'book_id':'b1','age_band':'5-7'});write('story.txt',''.join(page['text'] for page in pages if page['kind']=='story'));write('storyboard.json',{'pages':pages})
 manifest_pages=[]
 for i,page in enumerate(pages,1):
  manifest_pages.append({'page':i,'text':page['text'],'text_version':'v1','characters_version':'v1','character_reference_path':'characters/ref.txt','text_area':page['text_box_mm'],'layout_design':copy.deepcopy(page['layout_design']),'current_prompt_path':'prompt.txt','current_image_path':'test-image.png','props':[],'knowledge_check':{'status':'passed','evidence':'页面知识检查：纸飞机动作与正文一致。'},'previous_page_state':{'state_id':'story_start' if i==1 else f'page-{i-1:02d}-hook','summary':f'第{i}页承接上一页的动作状态。'},'current_page_entry':{'state_id':'page-01-entry' if i==1 else f'page-{i-1:02d}-hook','summary':f'第{i}页从纸飞机仍在孩子手中开始。'},'next_page_hook':{'state_id':'story_end' if i==len(pages) else f'page-{i:02d}-hook','summary':f'第{i}页把视线引向下一页的纸飞机轨迹。'},'text_image_match':{'status':'passed','evidence':f'第{i}页正文描述纸飞机动作，画面主体与动作方向一致。'},'continuity_review':{'status':'passed','evidence':f'第{i}页角色服装和纸飞机状态与相邻页连续。'}})
 write('manifest.json',{'schema_version':1,'book_id':'b1','age_band':'5-7','pages':manifest_pages})
 write('prompt.txt','synthetic test only')
 from export_book import export_book
 export_book(root/'layout.json',root/'export')
 (root/'social').mkdir()
 for i in range(1,5):Image.new('RGB',(1080,1920),'white').save(root/f'social/page-{i:02}.png')
 write('review.json',{'reading_pages':[{'page':i,'status':'passed','evidence':f'第{i}页已查看当前PDF渲染图。','image_path':f'export/reading-pages/page-{i:02}.png','layout_review':layout_review(i)} for i in range(1,5)],'print_sides':[{'side':i,'status':'passed','evidence':f'第{i}个打印面已核对配对、方向和边距。','image_path':f'export/print-pages/page-{i:02}.png'} for i in range(1,3)],'social_pages':[{'page':i,'status':'rendered','output_path':f'social/page-{i:02}.png','profile':'social-vertical-9x16','canvas':{'width_px':1080,'height_px':1920},'source_aspect_ratio':'9:16','subject_safe_area':[0.08,0.10,0.84,0.62],'text_safe_area':[0.08,0.76,0.84,0.14],'layout_review':social_layout_review(i)} for i in range(1,5)],'engineering_evidence':{'status':'passed','evidence':'已运行导出、PDF、字体和文件结构检查。'},'content_evidence':{'status':'passed','evidence':'已核对来源、教育目标卡、年龄段和故事顺序。'},'visual_evidence':{'status':'passed','evidence':'已完成逐页版式与社媒视觉检查。'},'real_reading_evidence':{'status':'pending','evidence':'尚未完成家庭试打和实际共读。'},'contact_sheet_review':{'status':'passed','evidence':'已查看整书缩略图总览，页间角色和色彩没有明显跳变。','image_path':'contact-sheet.png','reviewer':'synthetic reviewer','reviewed_at':'2026-10-16T00:00:00Z'},'unresolved_digital_defects':[]})
 write('project.json',{'schema_version':1,'target_age_bands':['5-7'],'source':{'path':'source.txt','version':'v1','coverage':'synthetic'},'characters_version':'v1','characters_path':'characters','books':[{'id':'b1','age_band':'5-7','source_version':'v1','characters_version':'v1','status':'laid_out','artifacts':{'concept':'concept.json','education_goal':'education-goal.json','story':'story.txt','storyboard':'storyboard.json','layout':'layout.json','page_manifest':'manifest.json','reading_pdf':'export/reading.pdf','print_pdf':'export/print.pdf','review':'review.json','metrics':'metrics.json'}}]})
 return root/'project.json'

class AcceptanceTests(unittest.TestCase):
 def test_acceptance_allows_xiaohongshu_social_profile(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root)
   Image.new('RGB',(1800,2400),'white').save(root/'test-image.png')
   layout=read_json(root/'layout.json');manifest=read_json(root/'manifest.json');review=read_json(root/'review.json')
   for page in layout['pages']:
    page['layout_design']['social_layout'].update({'profile':'xiaohongshu-feed-3x4','canvas':{'width_px':1080,'height_px':1440},'subject_safe_area':[0.50,0.20,0.42,0.54],'text_safe_area':[0.08,0.12,0.38,0.24],'composition_mode':'portrait-full-bleed','text_placement':'in-scene','source_aspect_ratio':'3:4'})
   for page in manifest['pages']:
    page['layout_design']['social_layout'].update({'profile':'xiaohongshu-feed-3x4','canvas':{'width_px':1080,'height_px':1440},'subject_safe_area':[0.50,0.20,0.42,0.54],'text_safe_area':[0.08,0.12,0.38,0.24],'composition_mode':'portrait-full-bleed','text_placement':'in-scene','source_aspect_ratio':'3:4'})
   for record in review['social_pages']:
    record.update({'profile':'xiaohongshu-feed-3x4','canvas':{'width_px':1080,'height_px':1440},'subject_safe_area':[0.50,0.20,0.42,0.54],'text_safe_area':[0.08,0.12,0.38,0.24],'source_aspect_ratio':'3:4'})
   for path in sorted((root/'social').glob('page-*.png')):
    Image.new('RGB',(1080,1440),'white').save(path)
   write_json(root/'layout.json',layout);write_json(root/'manifest.json',manifest);write_json(root/'review.json',review)
   self.assertEqual(check_book(project_path,'b1')['errors'],[])

 def test_acceptance_rejects_missing_layout_design(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root);layout=read_json(root/'layout.json');del layout['pages'][0]['layout_design'];write_json(root/'layout.json',layout)
   errors=check_book(project_path,'b1')['errors']
   self.assertTrue(any('页1' in error and 'layout_design' in error for error in errors),errors)
 def test_acceptance_rejects_manifest_layout_mismatch(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root);manifest=read_json(root/'manifest.json');manifest['pages'][0]['layout_design']['palette_token']='cool-sky';write_json(root/'manifest.json',manifest)
   errors=check_book(project_path,'b1')['errors']
   self.assertTrue(any('页1' in error and '版式不一致' in error for error in errors),errors)
 def test_acceptance_rejects_missing_layout_review(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root);review=read_json(root/'review.json');del review['reading_pages'][0]['layout_review'];write_json(root/'review.json',review)
   errors=check_book(project_path,'b1')['errors']
   self.assertTrue(any('reading_pages 1' in error and '版式审核' in error for error in errors),errors)
 def test_acceptance_rejects_generic_layout_review_evidence(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root);review=read_json(root/'review.json');review['reading_pages'][0]['layout_review']['evidence']='已检查';write_json(root/'review.json',review)
   errors=check_book(project_path,'b1')['errors']
   self.assertTrue(any('layout_review.evidence' in error for error in errors),errors)
 def test_acceptance_rejects_missing_social_layout(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root);layout=read_json(root/'layout.json');del layout['pages'][0]['layout_design']['social_layout'];write_json(root/'layout.json',layout)
   errors=check_book(project_path,'b1')['errors']
   self.assertTrue(any('页1' in error and 'social_layout' in error for error in errors),errors)
 def test_acceptance_rejects_social_render_profile_mismatch(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root);review=read_json(root/'review.json');review['social_pages'][0]['profile']='print';write_json(root/'review.json',review)
   errors=check_book(project_path,'b1')['errors']
   self.assertTrue(any('社媒' in error and 'profile' in error for error in errors),errors)
 def test_acceptance_rejects_mixed_social_profiles_across_book(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root);layout=read_json(root/'layout.json');manifest=read_json(root/'manifest.json');review=read_json(root/'review.json')
   Image.new('RGB',(1800,2400),'white').save(root/'test-image-xhs.png');Image.new('RGB',(1080,1440),'white').save(root/'social/page-02-xhs.png')
   xhs={'profile':'xiaohongshu-feed-3x4','canvas':{'width_px':1080,'height_px':1440},'source_aspect_ratio':'3:4'}
   for document,key in ((layout,'image'),(manifest,'current_image_path')):
    document['pages'][1]['layout_design']['social_layout'].update(xhs)
    document['pages'][1][key]='test-image-xhs.png'
   review['social_pages'][1].update(xhs);review['social_pages'][1]['output_path']='social/page-02-xhs.png'
   write_json(root/'layout.json',layout);write_json(root/'manifest.json',manifest);write_json(root/'review.json',review)
   errors=check_book(project_path,'b1')['errors']
   self.assertTrue(any('profile' in error and '同一个' in error for error in errors),errors)
 def test_acceptance_rejects_empty_social_profile(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root);layout=read_json(root/'layout.json');manifest=read_json(root/'manifest.json');review=read_json(root/'review.json')
   for document in (layout,manifest):
    for page in document['pages']:page['layout_design']['social_layout']['profile']=''
   for record in review['social_pages']:record['profile']=''
   write_json(root/'layout.json',layout);write_json(root/'manifest.json',manifest);write_json(root/'review.json',review)
   errors=check_book(project_path,'b1')['errors']
   self.assertTrue(any('profile' in error and '非空' in error for error in errors),errors)
 def test_acceptance_rejects_missing_social_layout_review(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root);review=read_json(root/'review.json');del review['social_pages'][0]['layout_review'];write_json(root/'review.json',review)
   errors=check_book(project_path,'b1')['errors']
   self.assertTrue(any('社媒页1' in error and 'layout_review' in error for error in errors),errors)
 def test_acceptance_rejects_generic_social_layout_review_evidence(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root);review=read_json(root/'review.json');review['social_pages'][0]['layout_review']['evidence']='已检查';write_json(root/'review.json',review)
   errors=check_book(project_path,'b1')['errors']
   self.assertTrue(any('社媒页1' in error and 'layout_review.evidence' in error for error in errors),errors)
 def test_acceptance_rejects_failed_social_layout_review(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root);review=read_json(root/'review.json');review['social_pages'][0]['layout_review']['status']='failed';write_json(root/'review.json',review)
   errors=check_book(project_path,'b1')['errors']
   self.assertTrue(any('社媒页1' in error and 'status' in error for error in errors),errors)
 def test_acceptance_rejects_missing_social_render_file(self):
   from accept_book import check_book
   with tempfile.TemporaryDirectory() as td:
    root=Path(td);project_path=complete_project(root);review=read_json(root/'review.json');review['social_pages'][0]['output_path']='social/missing.png';write_json(root/'review.json',review)
    errors=check_book(project_path,'b1')['errors']
    self.assertTrue(any('社媒' in error and '文件' in error for error in errors),errors)
 def test_acceptance_rejects_missing_education_goal_artifact(self):
   from accept_book import check_book
   with tempfile.TemporaryDirectory() as td:
    root=Path(td);project_path=complete_project(root);project=read_json(project_path);del project['books'][0]['artifacts']['education_goal'];write_json(project_path,project)
    errors=check_book(project_path,'b1')['errors']
    self.assertTrue(any('education_goal' in error for error in errors),errors)
 def test_acceptance_rejects_invalid_education_goal(self):
   from accept_book import check_book
   with tempfile.TemporaryDirectory() as td:
    root=Path(td);project_path=complete_project(root);goal=read_json(root/'education-goal.json');goal['schema_version']=2;goal['target_age_band']='3-4';goal['core_knowledge']='';write_json(root/'education-goal.json',goal)
    errors=check_book(project_path,'b1')['errors']
    self.assertTrue(any('education_goal' in error for error in errors),errors)
    self.assertTrue(any('target_age_band' in error for error in errors),errors)
 def test_acceptance_rejects_missing_review_evidence_domain(self):
   from accept_book import check_book
   with tempfile.TemporaryDirectory() as td:
    root=Path(td);project_path=complete_project(root);review=read_json(root/'review.json');del review['visual_evidence'];write_json(root/'review.json',review)
    errors=check_book(project_path,'b1')['errors']
    self.assertTrue(any('visual_evidence' in error for error in errors),errors)
 def test_acceptance_rejects_failed_real_reading_evidence(self):
   from accept_book import check_book
   with tempfile.TemporaryDirectory() as td:
    root=Path(td);project_path=complete_project(root);review=read_json(root/'review.json');review['real_reading_evidence']['status']='failed';write_json(root/'review.json',review)
    errors=check_book(project_path,'b1')['errors']
    self.assertTrue(any('real_reading_evidence' in error for error in errors),errors)
 def test_acceptance_rejects_missing_contact_sheet_review(self):
   from accept_book import check_book
   with tempfile.TemporaryDirectory() as td:
    root=Path(td);project_path=complete_project(root);review=read_json(root/'review.json');del review['contact_sheet_review'];write_json(root/'review.json',review)
    errors=check_book(project_path,'b1')['errors']
    self.assertTrue(any('contact_sheet_review' in error for error in errors),errors)
 def test_acceptance_rejects_non_image_contact_sheet(self):
   from accept_book import check_book
   with tempfile.TemporaryDirectory() as td:
    root=Path(td);project_path=complete_project(root);(root/'not-an-image.txt').write_text('not an image',encoding='utf-8');review=read_json(root/'review.json');review['contact_sheet_review']['image_path']='not-an-image.txt';write_json(root/'review.json',review)
    errors=check_book(project_path,'b1')['errors']
    self.assertTrue(any('contact_sheet_review' in error and '图片' in error for error in errors),errors)
 def test_acceptance_rejects_missing_metrics_artifact(self):
   from accept_book import check_book
   with tempfile.TemporaryDirectory() as td:
    root=Path(td);project_path=complete_project(root);project=read_json(project_path);del project['books'][0]['artifacts']['metrics'];write_json(project_path,project)
    errors=check_book(project_path,'b1')['errors']
    self.assertTrue(any('metrics' in error for error in errors),errors)
 def test_acceptance_rejects_incomplete_metrics(self):
   from accept_book import check_book
   with tempfile.TemporaryDirectory() as td:
    root=Path(td);project_path=complete_project(root);metrics=read_json(root/'metrics.json');del metrics['resume_events'];metrics['output_quality']='approved-later';write_json(root/'metrics.json',metrics)
    errors=check_book(project_path,'b1')['errors']
    self.assertTrue(any('metrics' in error for error in errors),errors)
 def test_planning_fixture_remains_readable_but_not_digitally_complete(self):
  from accept_book import check_book
  from validate_page_manifest import validate_page_manifest
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root);manifest=read_json(root/'manifest.json')
   for page in manifest['pages']:page.pop('layout_design',None)
   self.assertEqual(validate_page_manifest(manifest,root,False),[])
   write_json(root/'manifest.json',manifest);layout=read_json(root/'layout.json')
   for page in layout['pages']:page.pop('layout_design',None)
   write_json(root/'layout.json',layout)
   errors=check_book(project_path,'b1')['errors']
   self.assertTrue(any('迁移' in error and 'layout_design' in error for error in errors),errors)

 def test_acceptance_allows_an_explicit_blank_page(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)
   try:project_path=complete_project(root,blank_page=3)
   except (TypeError,ValueError) as exc:self.fail(f'explicit blank page should export: {exc}')
   self.assertEqual(check_book(project_path,'b1')['errors'],[])
 def test_acceptance_requires_each_page_character_reference(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root);manifest=read_json(root/'manifest.json')
   del manifest['pages'][0]['character_reference_path'];write_json(root/'manifest.json',manifest)
   errors=check_book(project_path,'b1')['errors']
   self.assertTrue(any('pages[1].character_reference_path' in error for error in errors),errors)
 def test_acceptance_rejects_missing_character_reference_file(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root);manifest=read_json(root/'manifest.json')
   manifest['pages'][0]['character_reference_path']='characters/missing.txt';write_json(root/'manifest.json',manifest)
   errors=check_book(project_path,'b1')['errors']
   self.assertTrue(any('pages[1].character_reference_path' in error for error in errors),errors)
 def test_acceptance_rejects_stale_character_reference_directory(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root)
   (root/'characters-v0').mkdir();(root/'characters-v0/ref.txt').write_text('stale reference',encoding='utf-8')
   manifest=read_json(root/'manifest.json');manifest['pages'][0]['character_reference_path']='characters-v0/ref.txt';write_json(root/'manifest.json',manifest)
   errors=check_book(project_path,'b1')['errors']
   self.assertIn('页1: 角色参考不在当前批准目录 characters',errors)
 def test_acceptance_rejects_out_of_project_character_reference(self):
  from accept_book import check_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root)
   outside=root.parent/f'{root.name}-outside-reference.txt';outside.write_text('outside reference',encoding='utf-8')
   self.addCleanup(outside.unlink,missing_ok=True)
   manifest=read_json(root/'manifest.json');manifest['pages'][0]['character_reference_path']=str(outside);write_json(root/'manifest.json',manifest)
   errors=check_book(project_path,'b1')['errors']
   self.assertTrue(any('pages[1].character_reference_path' in error and 'project' in error for error in errors),errors)
 def test_acceptance_rejects_final_print_text_below_minimum(self):
  from accept_book import check_book
  import pymupdf as fitz
  from impose_booklet import MM
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);project_path=complete_project(root)
   font=root/'font.ttf';texts=['小朋友。']*4;printing=root/'export/print.pdf';document=fitz.open()
   for left,right in ((4,1),(2,3)):
    page=document.new_page(width=297*MM,height=210*MM)
    page.insert_font(fontname='kidsbook',fontfile=str(font))
    page.insert_text((36,54),texts[left-1],fontsize=17,fontname='kidsbook')
    page.insert_text((page.rect.width/2+36,54),texts[right-1],fontsize=17,fontname='kidsbook')
   document.save(printing);document.close()
   self.assertIn('print page 1: text size 17.0 pt is below 18.0 pt',check_book(project_path,'b1')['errors'])
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

def read_json(path):return json.loads(path.read_text(encoding='utf-8'))
def write_json(path,data):path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
if __name__=='__main__':unittest.main()
