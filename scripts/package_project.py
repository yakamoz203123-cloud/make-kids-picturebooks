"""Package accepted current assets for private project continuation.

This is not a public-release privacy filter. User books and private source
metadata require separate permission before publishing anywhere.
"""
import argparse,json,os,tempfile,zipfile
from pathlib import Path
from accept_book import verify_receipt
from project_paths import normalize_relative_path,resolve_project_file

def package_project(project_path,book_id,output):
    project_path=Path(project_path).resolve();base=project_path.parent
    candidate=Path(output)
    if candidate.is_absolute():
        try:output_relative=candidate.resolve().relative_to(base)
        except ValueError as exc:raise ValueError('打包输出必须位于项目目录内') from exc
    else:output_relative=candidate
    output=resolve_project_file(base,normalize_relative_path(base,output_relative))
    if output.exists():raise FileExistsError(output)
    project=json.loads(project_path.read_text(encoding='utf-8'))
    book=next(b for b in project['books'] if b['id']==book_id)
    errors=verify_receipt(project,book,base)
    if errors:raise ValueError('; '.join(errors))
    receipt_path=normalize_relative_path(base,book['artifacts']['acceptance'])
    receipt=json.loads(resolve_project_file(base,receipt_path).read_text(encoding='utf-8'))
    paths={normalize_relative_path(base,path) for path in receipt['files']}|{project_path.relative_to(base).as_posix(),receipt_path}
    for path in paths:
        resolved=resolve_project_file(base,path)
        if not resolved.is_file():raise ValueError('打包文件缺失')
    output.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(suffix='.zip',dir=output.parent);os.close(fd)
    try:
        with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(paths):archive.write(resolve_project_file(base,path),path)
        os.link(tmp,output)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return {'files':len(paths),'output':str(output),'scope':'accepted-book-assets; private continuation'}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('project',type=Path);p.add_argument('book_id');p.add_argument('output',type=Path);a=p.parse_args()
    print(json.dumps(package_project(a.project,a.book_id,a.output),ensure_ascii=False))
