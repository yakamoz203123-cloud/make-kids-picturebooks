import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:from prepare_font import prepare_font
except ImportError:prepare_font=None
from fontTools.ttLib import TTFont
from reportlab.pdfbase.ttfonts import TTFont as RLFont
def make_source(root):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    from fontTools.ttLib import TTCollection
    chars='小朋友造桥。123';order=['.notdef']+['u'+hex(ord(c))[2:] for c in chars]
    builder=FontBuilder(1000,isTTF=False);builder.setupGlyphOrder(order)
    builder.setupCharacterMap({ord(c):order[i+1] for i,c in enumerate(chars)})
    strings={}
    for name in order:
        pen=T2CharStringPen(1000,None);pen.moveTo((50,0));pen.lineTo((500,0));pen.lineTo((500,700));pen.lineTo((50,700));pen.closePath();strings[name]=pen.getCharString()
    builder.setupCFF('Fixture-Regular',{'FullName':'Fixture Regular','FamilyName':'Fixture','Weight':'Regular'},strings,{})
    builder.setupHorizontalMetrics({g:(1000,0) for g in order});builder.setupHorizontalHeader(ascent=800,descent=-200)
    builder.setupNameTable({'familyName':'Fixture','styleName':'Regular','psName':'Fixture-Regular','licenseDescription':'SIL Open Font License, Version 1.1','licenseInfoURL':'https://openfontlicense.org/'})
    builder.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=800,usWinDescent=200);builder.setupPost()
    collection=TTCollection();collection.fonts=[builder.font];path=root/'fixture.ttc';collection.save(path);return path

class FontTests(unittest.TestCase):
    def test_cff_collection_to_embeddable_ttf(self):
        self.assertIsNotNone(prepare_font,'字体准备接口尚未实现')
        with tempfile.TemporaryDirectory() as td:
            source=make_source(Path(td));p=Path(td)/'font.ttf';prepare_font(source,p,'小朋友造桥。123',face_index=0)
            f=TTFont(p)
            self.assertIn('glyf',f)
            self.assertTrue(all(ord(x) in f.getBestCmap() for x in '小朋友造桥。123'))
            self.assertEqual(f['name'].getDebugName(13),'SIL Open Font License, Version 1.1')
            f.close();RLFont('PreparedTest',str(p))
            with self.assertRaises(FileExistsError):prepare_font(source,p,'小朋友',face_index=0)
    def test_missing_source_or_missing_glyph(self):
        self.assertIsNotNone(prepare_font)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):prepare_font(Path(td)/'missing.ttf',Path(td)/'f.ttf','小朋友')
            with self.assertRaisesRegex(ValueError,'缺字'):prepare_font(make_source(Path(td)),Path(td)/'f.ttf','缺')
if __name__=='__main__':unittest.main()
