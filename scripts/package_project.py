"""Package accepted current assets for private project continuation.

This is not a public-release privacy filter. User books and private source
metadata require separate permission before publishing anywhere.
"""
import argparse,json,os,tempfile,zipfile
from pathlib import Path
from accept_book import verify_receipt

def package_project(project_path,book_id,output):
    project_path=Path(project_path).resolve();base=project_path.parent;output=Path(output).resolve()
    if output.exists():raise FileExistsError(output)
    project=json.loads(project_path.read_text(encoding='utf-8'))
    book=next(b for b in project['books'] if b['id']==book_id)
    errors=verify_receipt(project,book,base)
    if errors:raise ValueError('; '.join(errors))
    receipt_path=Path(book['artifacts']['acceptance']);receipt=json.loads((base/receipt_path).read_text(encoding='utf-8'))
    paths=set(receipt['files'])|{str(project_path.relative_to(base)),str(receipt_path)}
    for path in paths:
        resolved=(base/path).resolve()
        if not resolved.is_relative_to(base) or Path(path).is_absolute():raise ValueError('打包路径必须位于项目内')
    output.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(suffix='.zip',dir=output.parent);os.close(fd)
    try:
        with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(paths):archive.write(base/path,path)
        os.link(tmp,output)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return {'files':len(paths),'output':str(output),'scope':'accepted-book-assets; private continuation'}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('project',type=Path);p.add_argument('book_id');p.add_argument('output',type=Path);a=p.parse_args()
    print(json.dumps(package_project(a.project,a.book_id,a.output),ensure_ascii=False))
