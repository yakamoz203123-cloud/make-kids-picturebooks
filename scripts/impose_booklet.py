"""Impose sequential PDF pages on landscape A4 for folded booklets."""
import argparse,json,os,tempfile
from pathlib import Path
from pypdf import PdfReader,PdfWriter,Transformation
MM=72/25.4

def booklet_pairs(page_count: int) -> list[tuple[int,int]]:
    if isinstance(page_count,bool) or not isinstance(page_count,int) or page_count<4 or page_count%4:raise ValueError('总页数必须是正的4倍数')
    pairs=[]
    for sheet in range(page_count//4):
        pairs.extend([(page_count-2*sheet,1+2*sheet),(2+2*sheet,page_count-1-2*sheet)])
    return pairs

def impose_booklet(input_path: Path, output_path: Path) -> dict:
    input_path=Path(input_path);output_path=Path(output_path)
    if output_path.exists():raise FileExistsError(output_path)
    reader=PdfReader(input_path);pairs=booklet_pairs(len(reader.pages));writer=PdfWriter()
    paper_w,paper_h=297*MM,210*MM;slot_w=paper_w/2;white=5*MM
    for pair in pairs:
        target=writer.add_blank_page(width=paper_w,height=paper_h)
        for side,n in enumerate(pair):
            page=reader.pages[n-1]
            if page.rotation:page.transfer_rotation_to_content()
            w,h=float(page.mediabox.width),float(page.mediabox.height)
            if w<=0 or h<=0:raise ValueError(f'页{n}: 非法页面尺寸')
            scale=min((slot_w-2*white)/w,(paper_h-2*white)/h)
            x=side*slot_w+(slot_w-w*scale)/2;y=(paper_h-h*scale)/2
            transform=Transformation().translate(-float(page.mediabox.left),-float(page.mediabox.bottom)).scale(scale).translate(x,y)
            target.merge_transformed_page(page,transform,expand=False)
    output_path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(suffix='.pdf',dir=output_path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            writer.write(f);f.flush();os.fsync(f.fileno())
        os.link(tmp,output_path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return {'sheets':len(pairs)//2,'print_sides':len(pairs),'pairs':pairs,'paper_mm':[297,210],'output':str(output_path)}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    print(json.dumps(impose_booklet(a.input,a.output),ensure_ascii=False,indent=2))
