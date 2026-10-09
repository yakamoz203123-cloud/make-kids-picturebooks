import sys,tempfile,unittest
from pathlib import Path
import fitz
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
class RenderEvidenceTests(unittest.TestCase):
 def test_final_page_image_is_required(self):
  from accept_book import reviewed_image_errors
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);doc=fitz.open();page=doc.new_page(width=200,height=300);page.insert_text((20,30),'Actual page',fontsize=22)
   page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(root/'correct.png')
   self.assertEqual(reviewed_image_errors(doc,0,root/'correct.png'),[])
   (root/'not-image.txt').write_text('reviewed')
   self.assertTrue(reviewed_image_errors(doc,0,root/'not-image.txt'))
   Image.new('RGB',(300,450),'white').save(root/'wrong.png')
   self.assertTrue(reviewed_image_errors(doc,0,root/'wrong.png'))
   doc.close()
if __name__=='__main__':unittest.main()
