import json,sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from PIL import Image
from pypdf import PdfReader
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:from render_book import render_book
except ImportError:render_book=None
FONT=str(Path(__file__).resolve().parents[1]/'assets/kidsbook-print.ttf')
class RenderTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name)
        Image.new('RGB',(2000,2000),'white').save(self.root/'art.png')
        self.data={'font_path':FONT,'page_mm':[148,210],'font_size':22,'target_dpi':300,'safe_margin_mm':10,'pages':[{'number':i,'text':'A bridge for us.','image':'art.png','image_box_mm':[14,70,120,120],'text_box_mm':[14,20,120,40]} for i in range(1,9)]}
    def tearDown(self):self.t.cleanup()
    def render(self):
        p=self.root/'layout.json';p.write_text(json.dumps(self.data),encoding='utf-8');return render_book(p,self.root/'out.pdf')
    def test_valid_pdf_with_embedded_font(self):
        self.assertIsNotNone(render_book,'排版尚未实现')
        result=self.render();reader=PdfReader(self.root/'out.pdf')
        self.assertEqual(result['pages'],8)
        self.assertAlmostEqual(float(reader.pages[0].mediabox.width),148*72/25.4,places=3)
        fonts=reader.pages[0]['/Resources']['/Font']
        self.assertTrue(any(f.get_object().get('/FontDescriptor',{}).get('/FontFile2') for f in fonts.values()))
    def test_bundled_chinese_font(self):
        self.assertIsNotNone(render_book)
        del self.data['font_path']
        self.data['pages'][0]['text']='小朋友造桥。'
        result=self.render()
        self.assertTrue(result['font_embedded'])
        self.assertIn('小朋友',PdfReader(self.root/'out.pdf').pages[0].extract_text())
    def test_crlf_and_tabs_are_normalized(self):
        self.assertIsNotNone(render_book)
        del self.data['font_path']
        self.data['pages'][0]['text']='小朋友\r\n造桥。\t'
        self.render()
        text=PdfReader(self.root/'out.pdf').pages[0].extract_text()
        self.assertNotIn('\x00',text)
        self.assertIn('造桥',text)
    def test_font_extents_fit_safe_text_box(self):
        self.assertIsNotNone(render_book)
        del self.data['font_path']
        self.data['pages'][0]['text']='小朋友'
        self.data['pages'][0]['image']=None
        self.data['pages'][0]['text_box_mm']=[14,10,120,22*25.4/72]
        self.render()
        positions=[]
        PdfReader(self.root/'out.pdf').pages[0].extract_text(visitor_text=lambda text,cm,tm,font,size: positions.append(tm[5]) if text.strip() else None)
        from fontTools.ttLib import TTFont
        from fontTools.pens.boundsPen import BoundsPen
        font=TTFont(Path(__file__).resolve().parents[1]/'assets/kidsbook-print.ttf')
        glyphs=font.getGlyphSet();bottoms=[]
        for ch in '小朋友':
            pen=BoundsPen(glyphs);glyphs[font.getBestCmap()[ord(ch)]].draw(pen);bottoms.append(pen.bounds[1])
        ink_bottom=min(positions)+min(bottoms)/font['head'].unitsPerEm*22
        font.close()
        self.assertGreaterEqual(ink_bottom,10*72/25.4,'实际墨迹必须在安全边内')
    def test_interrupted_final_publish_does_not_leave_corrupt_pdf(self):
        self.assertIsNotNone(render_book)
        real_open=Path.open;dest=self.root/'out.pdf'
        class BrokenWrite:
            def __enter__(self):
                self.file=real_open(dest,'xb');return self
            def write(self,data):
                self.file.write(data[:20]);raise OSError('simulated disk failure')
            def __exit__(self,*args):self.file.close()
        def intercepted(path,mode='r',*args,**kwargs):
            if path==dest and mode=='xb':return BrokenWrite()
            return real_open(path,mode,*args,**kwargs)
        failed=False
        with patch.object(Path,'open',intercepted):
            try:self.render()
            except OSError:failed=True
        if failed:
            self.assertFalse(dest.exists(),'写入中断不能留下损坏成品')
            self.render()
        self.assertEqual(len(PdfReader(dest).pages),8)
    def test_missing_font_and_missing_glyph(self):
        self.assertIsNotNone(render_book)
        self.data['font_path']='missing.ttf'
        with self.assertRaises(ValueError):self.render()
        self.data['font_path']=FONT;self.data['pages'][0]['text']='\U0010ffff'
        with self.assertRaisesRegex(ValueError,'缺字'):self.render()
    def test_missing_image(self):
        self.assertIsNotNone(render_book)
        self.data['pages'][0]['image']='missing.png'
        with self.assertRaises(ValueError):self.render()
    def test_text_overflow(self):
        self.assertIsNotNone(render_book)
        self.data['pages'][0]['text']='A long story. '*300
        with self.assertRaisesRegex(ValueError,'溢出'):self.render()
    def test_low_resolution(self):
        self.assertIsNotNone(render_book)
        Image.new('RGB',(100,100),'white').save(self.root/'art.png')
        with self.assertRaisesRegex(ValueError,'分辨率'):self.render()
    def test_boxes_overlap_or_outside(self):
        self.assertIsNotNone(render_book)
        self.data['pages'][0]['text_box_mm']=[14,90,120,40]
        with self.assertRaises(ValueError):self.render()
        self.data['pages'][0]['text_box_mm']=[0,0,120,40]
        with self.assertRaises(ValueError):self.render()
    def test_reviewed_background_accepts_text_and_keeps_it_extractable(self):
        p=self.data['pages'][0]
        p.update(image_role='background',image_box_mm=[10,10,128,190],text_box_mm=[14,120,120,70],text_area_reviewed=True)
        self.render()
        self.assertIn('A bridge for us.',PdfReader(self.root/'out.pdf').pages[0].extract_text())
    def test_page_font_size_supports_cover_hierarchy(self):
        p=self.data['pages'][0]
        p.update(text='Title',font_size=32,text_box_mm=[14,20,120,45])
        self.render()
        sizes=[]
        PdfReader(self.root/'out.pdf').pages[0].extract_text(visitor_text=lambda text,cm,tm,font,size: sizes.append(size) if text.strip() else None)
        self.assertEqual(sizes,[32])
    def test_background_requires_actual_text_area_review(self):
        p=self.data['pages'][0]
        p.update(image_role='background',image_box_mm=[10,10,128,190],text_box_mm=[14,120,120,70])
        with self.assertRaisesRegex(ValueError,'留白区域'):self.render()
    def test_unknown_image_role_is_rejected(self):
        self.data['pages'][0]['image_role']='anything'
        with self.assertRaisesRegex(ValueError,'图像角色'):self.render()
    def test_layout_mode_requires_layout_design_for_export(self):
        self.data['pages'][0]['layout_mode']='soft-card'
        with self.assertRaisesRegex(ValueError,'layout_design'):
            self.render()
    def test_no_partial_output_or_overwrite(self):
        self.assertIsNotNone(render_book)
        self.data['pages'][-1]['image']='missing.png'
        with self.assertRaises(ValueError):self.render()
        self.assertFalse((self.root/'out.pdf').exists())
        self.data['pages'][-1]['image']='art.png';self.render()
        with self.assertRaises(FileExistsError):self.render()
if __name__=='__main__':unittest.main()
