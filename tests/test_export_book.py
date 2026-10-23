import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
class ExportTests(unittest.TestCase):
 def test_export_renders_every_page_and_preserves_editable_text(self):
  from export_book import export_book
  from pypdf import PdfReader
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);layout=root/'layout.json'
   layout.write_text(json.dumps({'font_size':22,'pages':[{'number':i,'text':'小朋友。'} for i in range(1,5)]}),encoding='utf-8')
   result=export_book(layout,root/'export')
   self.assertEqual(result['reading_pages'],4);self.assertEqual(result['print_sides'],2)
   self.assertEqual(len(list((root/'export/reading-pages').glob('*.png'))),4)
   self.assertIn('小朋友',PdfReader(root/'export/reading.pdf').pages[0].extract_text())
   with self.assertRaises(FileExistsError):export_book(layout,root/'export')
 def test_invalid_booklet_has_no_partial_export(self):
  from export_book import export_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);layout=root/'layout.json'
   layout.write_text(json.dumps({'pages':[{'number':1,'text':'小朋友。'}]}),encoding='utf-8')
   with self.assertRaises(ValueError):export_book(layout,root/'export')
   self.assertFalse((root/'export').exists())
 def test_export_accepts_explicit_blank_and_wordless_pages(self):
  from export_book import export_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);layout=root/'layout.json'
   pages=[
    {'number':1,'kind':'cover','text':'封面'},
    {'number':2,'kind':'story','wordless':True,'text':''},
    {'number':3,'kind':'blank','text':''},
    {'number':4,'kind':'back','text':'再见'},
   ]
   layout.write_text(json.dumps({'font_size':22,'pages':pages},ensure_ascii=False),encoding='utf-8')
   try:
    result=export_book(layout,root/'export')
   except (TypeError,ValueError) as exc:
    self.fail(f'explicit blank and wordless pages should export: {exc}')
   self.assertEqual(result['reading_pages'],4)
   self.assertEqual(result['print_sides'],2)
 def test_export_rejects_unmarked_empty_content_page_without_publishing(self):
  from export_book import export_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);layout=root/'layout.json'
   pages=[
    {'number':1,'kind':'cover','text':'封面'},
    {'number':2,'kind':'story','text':''},
    {'number':3,'kind':'story','text':'故事'},
    {'number':4,'kind':'back','text':'再见'},
   ]
   layout.write_text(json.dumps({'font_size':22,'pages':pages},ensure_ascii=False),encoding='utf-8')
   with self.assertRaisesRegex(ValueError,'expected page text must be non-empty for page 2'):
    export_book(layout,root/'export')
   self.assertFalse((root/'export').exists())
 def test_export_rejects_wordless_marker_on_non_story_page(self):
  from export_book import export_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);layout=root/'layout.json'
   pages=[
    {'number':1,'kind':'cover','wordless':True,'text':''},
    {'number':2,'kind':'story','text':'故事'},
    {'number':3,'kind':'story','text':'继续'},
    {'number':4,'kind':'back','text':'再见'},
   ]
   layout.write_text(json.dumps({'font_size':22,'pages':pages},ensure_ascii=False),encoding='utf-8')
   with self.assertRaisesRegex(ValueError,'expected page text must be non-empty for page 1'):
    export_book(layout,root/'export')
   self.assertFalse((root/'export').exists())
if __name__=='__main__':unittest.main()
