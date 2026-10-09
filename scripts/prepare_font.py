"""Prepare an embeddable TrueType subset, including CFF collection sources."""
import argparse,json
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools import subset
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen

def prepare_font(source: Path, output: Path, text: str, face_index: int=0) -> dict:
    source=Path(source);output=Path(output)
    if output.exists():raise FileExistsError(output)
    if not source.is_file():raise ValueError('字体来源不存在')
    font=TTFont(source,fontNumber=face_index)
    try:
        cmap=font.getBestCmap() or {};codes={ord(x) for x in text if x not in '\n\r\t'}
        missing=codes-set(cmap)
        if missing:raise ValueError('字体缺字: '+''.join(chr(x) for x in sorted(missing)))
        fs=font['OS/2'].fsType if 'OS/2' in font else 0
        if fs & (0x2|0x100|0x200):raise ValueError('字体不允许本次嵌入或子集处理')
        opts=subset.Options();opts.name_IDs=['*'];opts.name_legacy=True;opts.name_languages=['*'];opts.layout_features=[]
        worker=subset.Subsetter(options=opts);worker.populate(unicodes=codes);worker.subset(font)
        output.parent.mkdir(parents=True,exist_ok=True)
        if 'glyf' in font:
            with output.open('xb') as f:font.save(f)
        elif 'CFF ' in font:
            units=font['head'].unitsPerEm;order=font.getGlyphOrder();glyph_set=font.getGlyphSet();glyphs={}
            for name in order:
                pen=TTGlyphPen(glyph_set);convert=Cu2QuPen(pen,max_err=units/1000,reverse_direction=True)
                glyph_set[name].draw(convert);glyphs[name]=pen.glyph()
            builder=FontBuilder(units,isTTF=True);builder.setupGlyphOrder(order);builder.setupCharacterMap(font.getBestCmap())
            builder.setupGlyf(glyphs);builder.setupHorizontalMetrics(dict(font['hmtx'].metrics))
            builder.setupHorizontalHeader(ascent=font['hhea'].ascent,descent=font['hhea'].descent)
            family='KidsBook Print';builder.setupNameTable({'familyName':family,'styleName':'Regular','uniqueFontIdentifier':family+' Regular','fullName':family+' Regular','psName':'KidsBookPrint-Regular','version':'Version 1.0','copyright':font['name'].getDebugName(0) or '', 'licenseDescription':font['name'].getDebugName(13) or '', 'licenseInfoURL':font['name'].getDebugName(14) or ''})
            os2=font['OS/2'];builder.setupOS2(sTypoAscender=os2.sTypoAscender,sTypoDescender=os2.sTypoDescender,usWinAscent=os2.usWinAscent,usWinDescent=os2.usWinDescent,fsType=fs)
            builder.setupPost();builder.setupMaxp()
            with output.open('xb') as f:builder.font.save(f)
        else:raise ValueError('不支持的字体轮廓')
        return {'output':str(output),'characters':len(codes),'face_index':face_index}
    finally:font.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('text_file',type=Path);p.add_argument('output',type=Path);p.add_argument('--face-index',type=int,default=0);a=p.parse_args()
    print(json.dumps(prepare_font(a.source,a.output,a.text_file.read_text(encoding='utf-8'),a.face_index),ensure_ascii=False))
