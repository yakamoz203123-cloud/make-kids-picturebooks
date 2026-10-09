import sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from pypdf import PdfReader,PdfWriter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try: from impose_booklet import booklet_pairs,impose_booklet
except ImportError: booklet_pairs=impose_booklet=None
class BookletTests(unittest.TestCase):
    def test_eight_page_order(self):
        self.assertIsNotNone(booklet_pairs,'拼版尚未实现')
        self.assertEqual(booklet_pairs(8),[(8,1),(2,7),(6,3),(4,5)])
    def test_sixteen_pages_once(self):
        self.assertIsNotNone(booklet_pairs)
        self.assertEqual(sorted(x for pair in booklet_pairs(16) for x in pair),list(range(1,17)))
    def test_bad_counts(self):
        self.assertIsNotNone(booklet_pairs)
        for n in [0,3,6,-4,4.5,True]:
            with self.assertRaises(ValueError): booklet_pairs(n)
    def test_midwrite_failure_is_retryable(self):
        self.assertIsNotNone(impose_booklet)
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'r.pdf';dest=Path(td)/'p.pdf';w=PdfWriter()
            for _ in range(4):w.add_blank_page(width=400,height=600)
            w.write(src)
            def interrupted(writer,stream):
                stream.write(b'%PDF-1.3\npartial');raise OSError('simulated write failure')
            with patch.object(PdfWriter,'write',interrupted):
                with self.assertRaises(OSError):impose_booklet(src,dest)
            self.assertFalse(dest.exists(),'失败不应留下最终文件')
            impose_booklet(src,dest)
            self.assertEqual(len(PdfReader(dest).pages),2)
    def test_pdf_dimensions_and_no_overwrite(self):
        self.assertIsNotNone(impose_booklet)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'r.pdf';q=Path(td)/'p.pdf';w=PdfWriter()
            for _ in range(8):w.add_blank_page(width=148*72/25.4,height=210*72/25.4)
            w.write(p)
            result=impose_booklet(p,q);r=PdfReader(q)
            self.assertEqual(len(r.pages),4);self.assertEqual(result['sheets'],2)
            self.assertAlmostEqual(float(r.pages[0].mediabox.width),297*72/25.4,places=3)
            with self.assertRaises(FileExistsError):impose_booklet(p,q)
if __name__=='__main__':unittest.main()
