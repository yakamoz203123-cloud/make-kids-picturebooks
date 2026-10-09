"""Render validated separate-text picturebook pages; refuse silent defects."""
import argparse,hashlib,json,math,os,tempfile
from pathlib import Path
from PIL import Image
from fontTools.ttLib import TTFont as FontInfo
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
MM=72/25.4

def _box(value,label,width,height,margin):
    if not isinstance(value,list) or len(value)!=4:raise ValueError(f'{label}: 需要四个毫米数值')
    if any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in value):raise ValueError(f'{label}: 非法数值')
    x,y,w,h=value
    if w<=0 or h<=0 or x<margin or y<margin or x+w>width-margin+0.001 or y+h>height-margin+0.001:raise ValueError(f'{label}: 超出安全边界')
    return tuple(v*MM for v in value)

def _lines(text,font,size,width):
    opening=set('（【《〈「『“‘(')
    closing=set('，。！？；：、）】》〉」』”’,.!?;:)')
    lines=[]
    for paragraph in text.split('\n'):
        if not paragraph:
            lines.append('');continue
        while paragraph:
            end=0
            while end<len(paragraph) and pdfmetrics.stringWidth(paragraph[:end+1],font,size)<=width:
                end+=1
            if not end:raise ValueError('单个字宽度超过文字框')
            if end<len(paragraph):
                while end and (paragraph[end] in closing or paragraph[end-1] in opening):
                    end-=1
                if not end:raise ValueError('文字框过窄，无法遵守中文标点断行规则')
            lines.append(paragraph[:end]);paragraph=paragraph[end:]
    return lines

def render_book(manifest_path: Path, output_path: Path) -> dict:
    manifest_path=Path(manifest_path);output_path=Path(output_path)
    if output_path.exists():raise FileExistsError(output_path)
    data=json.loads(manifest_path.read_text(encoding='utf-8'));base=manifest_path.parent
    if not isinstance(data,dict):raise ValueError('版面数据必须是对象')
    dims=data.get('page_mm',[148,210])
    if not isinstance(dims,list) or len(dims)!=2 or any(not isinstance(x,(int,float)) or not math.isfinite(x) or x<=0 for x in dims):raise ValueError('非法页面尺寸')
    width,height=dims;size=data.get('font_size',22);margin=data.get('safe_margin_mm',10);dpi=data.get('target_dpi',300)
    if any(not isinstance(x,(int,float)) or not math.isfinite(x) or x<=0 for x in (size,margin,dpi)):raise ValueError('字号、边距、分辨率必须是正数')
    if size<22:raise ValueError('正文最小字号为22磅')
    font_value=data.get('font_path')
    font_path=Path(font_value) if font_value else Path(__file__).resolve().parents[1]/'assets/kidsbook-print.ttf'
    font_path=font_path if font_path.is_absolute() else base/font_path
    if not font_path.is_file():raise ValueError('字体路径不可用')
    try:
        info=FontInfo(font_path);cmap=info.getBestCmap() or {};fs=info['OS/2'].fsType if 'OS/2' in info else 0;info.close()
        if fs & 0x2 or fs & 0x200 or fs & 0x100:raise ValueError('字体不允许当前嵌入或子集方式')
        font='Book-'+hashlib.sha256(font_path.read_bytes()).hexdigest()[:16]
        pdfmetrics.registerFont(TTFont(font,str(font_path)))
    except Exception as e:raise ValueError(f'字体无法嵌入: {e}') from e
    pages=data.get('pages')
    if not isinstance(pages,list) or not pages:raise ValueError('没有页面')
    prepared=[];image_checks=[]
    for n,page in enumerate(pages,1):
        if not isinstance(page,dict) or page.get('number')!=n:raise ValueError(f'页{n}: 页码必须连续')
        page_size=page.get('font_size',size)
        if not isinstance(page_size,(int,float)) or not math.isfinite(page_size) or page_size<=0:raise ValueError(f'页{n}: 非法字号')
        if page_size<22:raise ValueError(f'页{n}: 最小字号为22磅')
        text=page.get('text','')
        if not isinstance(text,str):raise ValueError(f'页{n}: 正文必须是字符串')
        text=text.replace('\r\n','\n').replace('\r','\n').expandtabs(4)
        missing=sorted({ch for ch in text if ch not in '\n\r\t' and ord(ch) not in cmap})
        if missing:raise ValueError(f'页{n}: 字体缺字 {"".join(missing)}')
        text_box=_box(page.get('text_box_mm',[14,20,120,40]),f'页{n}文字框',width,height,margin)
        lines=_lines(text,font,page_size,text_box[2]) if text else []
        ascent,descent=pdfmetrics.getAscentDescent(font,page_size)
        leading=max(page_size*1.35,ascent-descent)
        if lines and (len(lines)-1)*leading+ascent-descent>text_box[3]:raise ValueError(f'页{n}: 文字溢出，请改分镜或扩展文字框')
        image_path=None;draw_box=None
        role=page.get('image_role','inset')
        if role not in ('inset','background'):raise ValueError(f'页{n}: 非法图像角色')
        if page.get('image'):
            image_path=Path(page['image']);image_path=image_path if image_path.is_absolute() else base/image_path
            if not image_path.is_file():raise ValueError(f'页{n}: 图像缺失')
            image_box=_box(page.get('image_box_mm',[14,70,120,120]),f'页{n}图像框',width,height,margin)
            tx,ty,tw,th=text_box;ix,iy,iw,ih=image_box
            if text and tx<ix+iw and tx+tw>ix and ty<iy+ih and ty+th>iy:
                if role!='background':raise ValueError(f'页{n}: 图文框重叠')
                if page.get('text_area_reviewed') is not True:raise ValueError(f'页{n}: 必须实际查看并确认文字留白区域')
            with Image.open(image_path) as img:pw,ph=img.size;img.verify()
            scale=min(iw/pw,ih/ph);dw,dh=pw*scale,ph*scale
            effective=min(pw/(dw/72),ph/(dh/72))
            if effective+0.01<dpi:raise ValueError(f'页{n}: 有效分辨率{effective:.1f}低于{dpi}')
            draw_box=(ix+(iw-dw)/2,iy+(ih-dh)/2,dw,dh)
            image_checks.append({'page':n,'effective_dpi':round(effective,1)})
        prepared.append((lines,text_box,image_path,draw_box,ascent,leading,page_size))
    output_path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(suffix='.pdf',dir=output_path.parent);os.close(fd)
    try:
        c=canvas.Canvas(tmp,pagesize=(width*MM,height*MM));c.setTitle(data.get('title','宝宝知识绘本'))
        for lines,box,img,draw_box,ascent,leading,page_size in prepared:
            if img:c.drawImage(ImageReader(str(img)),*draw_box,mask='auto')
            c.setFont(font,page_size);x,y,w,h=box
            for idx,line in enumerate(lines):c.drawString(x,y+h-ascent-idx*leading,line)
            c.showPage()
        c.save()
        # Publish exclusively, preserving any existing output from another run.
        os.link(tmp,output_path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return {'pages':len(pages),'page_mm':dims,'font_embedded':True,'image_checks':image_checks,'output':str(output_path)}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    print(json.dumps(render_book(a.manifest,a.output),ensure_ascii=False,indent=2))
