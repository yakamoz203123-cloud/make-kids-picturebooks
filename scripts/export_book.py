"""Export reading/print PDFs and every review render into a new directory."""
import argparse,json,os,shutil,tempfile
from pathlib import Path
from io import BytesIO
import pymupdf as fitz
from PIL import Image
from render_book import render_book
from impose_booklet import impose_booklet,booklet_pairs
from accept_book import quality_errors
from validate_exports import allowed_empty_pages,minimum_print_text_size,validate_exports

def compress_images(source,dest):
    doc=fitz.open(source);seen=set();count=0
    for page in doc:
        for item in page.get_images(full=True):
            xref=item[0]
            if xref in seen or item[1]:continue
            seen.add(xref)
            raw=doc.extract_image(xref)
            with Image.open(BytesIO(raw['image'])) as image:
                if image.mode not in ('RGB','L'):continue
                if image.width*image.height<100000:continue
                stream=BytesIO();image.save(stream,'JPEG',quality=95,optimize=True)
                if len(stream.getvalue())>=len(raw['image']):continue
                page.replace_image(xref,stream=stream.getvalue());count+=1
    doc.save(dest,garbage=4,deflate=True);doc.close();return count

def export_book(layout_path,output_dir):
    layout_path=Path(layout_path).resolve();output_dir=Path(output_dir).resolve()
    if output_dir.exists():raise FileExistsError(output_dir)
    layout=json.loads(layout_path.read_text(encoding='utf-8'))
    errors=quality_errors(layout)
    if errors:raise ValueError('; '.join(errors))
    booklet_pairs(len(layout.get('pages',[])))
    output_dir.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.export-',dir=output_dir.parent))
    try:
        result=render_book(layout_path,stage/'uncompressed.pdf')
        count=compress_images(stage/'uncompressed.pdf',stage/'reading.pdf')
        (stage/'uncompressed.pdf').unlink()
        imposed=impose_booklet(stage/'reading.pdf',stage/'print.pdf')
        validation=validate_exports(stage/'reading.pdf',stage/'print.pdf',[page.get('text','') for page in layout['pages']],layout.get('page_mm',[148,210]),minimum_print_text_size(layout),allowed_empty_pages(layout))
        for name in ('reading','print'):
            folder=stage/(name+'-pages');folder.mkdir()
            doc=fitz.open(stage/(name+'.pdf'))
            for i,page in enumerate(doc,1):page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(folder/f'page-{i:02}.png')
            doc.close()
        minimum_sizes={}
        for name in ('reading','print'):
            doc=fitz.open(stage/(name+'.pdf'));sizes=[span['size'] for page in doc for block in page.get_text('dict')['blocks'] if block.get('type')==0 for line in block['lines'] for span in line['spans'] if span['text'].strip()];doc.close()
            minimum_sizes[name]=round(min(sizes),2) if sizes else None
        report={'minimum_text_size_pt':minimum_sizes,'minimum_print_text_size_pt':minimum_print_text_size(layout),'reading_pages':validation['reading_pages'],'print_sides':validation['print_sides'],'sheets':imposed['sheets'],'pairs':imposed['pairs'],'image_checks':result['image_checks'],'compressed_images':count,'review_status':'pending','note':'已导出逐页渲染图；仍须实际查看并保存知识与视觉审核记录。'}
        (stage/'export-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        # Create destination exclusively; publish only after all exports succeed.
        output_dir.mkdir()
        try:
            for child in stage.iterdir():os.replace(child,output_dir/child.name)
        except Exception:
            shutil.rmtree(output_dir);raise
        return report
    finally:shutil.rmtree(stage,ignore_errors=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('layout',type=Path);p.add_argument('output_dir',type=Path);a=p.parse_args()
    print(json.dumps(export_book(a.layout,a.output_dir),ensure_ascii=False,indent=2))
