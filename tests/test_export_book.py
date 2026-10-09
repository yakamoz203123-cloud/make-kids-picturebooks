import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
class ExportTests(unittest.TestCase):
 def test_export_renders_every_page_and_preserves_editable_text(self):
  from export_book import export_book
  from pypdf import PdfReader
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);layout=root/'layout.json'
   layout.write_text(json.dumps({'font_size':22,'pages':[{'number':i,'text':'小朋友。'} for i in range(1,5)]}))
   result=export_book(layout,root/'export')
   self.assertEqual(result['reading_pages'],4);self.assertEqual(result['print_sides'],2)
   self.assertEqual(len(list((root/'export/reading-pages').glob('*.png'))),4)
   self.assertIn('小朋友',PdfReader(root/'export/reading.pdf').pages[0].extract_text())
   with self.assertRaises(FileExistsError):export_book(layout,root/'export')
 def test_invalid_booklet_has_no_partial_export(self):
  from export_book import export_book
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);layout=root/'layout.json'
   layout.write_text(json.dumps({'pages':[{'number':1,'text':'小朋友。'}]}))
   with self.assertRaises(ValueError):export_book(layout,root/'export')
   self.assertFalse((root/'export').exists())
if __name__=='__main__':unittest.main()
