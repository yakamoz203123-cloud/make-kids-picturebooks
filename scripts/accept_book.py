"""Accept one complete book against its saved records and reviewed PDF pages.

File hashes detect later edits. They do not substitute for human visual or
scientific review; review records must already contain actual evidence.
"""
import argparse,hashlib,json,re
from pathlib import Path
import fitz
from asset_registry import collect_declared_assets
from project_paths import normalize_relative_path,resolve_project_file
from validate_page_manifest import validate_page_manifest
from impose_booklet import booklet_pairs,MM

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def normal(text):return re.sub(r'\s+','',text)

def structure_errors(pages):
    if not pages or pages[0].get('kind')!='cover' or pages[-1].get('kind')!='back' or not any(p.get('kind')=='story' for p in pages):
        return ['完整绘本需要封面、实际故事页及封底']
    return []

def reviewed_image_errors(doc,index,path):
    from PIL import Image
    try:
        expected=doc[index].get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False,colorspace=fitz.csRGB)
        with Image.open(path) as image:
            actual=image.convert('RGB')
            if actual.size!=(expected.width,expected.height) or actual.tobytes()!=expected.samples:
                return ['审核渲染图不是当前PDF页面；用export_book.py重新渲染并审核']
        return []
    except (OSError,ValueError,IndexError) as exc:return [f'审核渲染图不可用: {exc}']

def quality_errors(layout):
    profile=layout.get('quality_profile','print')
    if profile not in ('print','home-pilot'):return ['未知打印质量档位']
    minimum=300 if profile=='print' else 200
    dpi=layout.get('target_dpi',300)
    errors=[]
    if not isinstance(dpi,(float,int)) or dpi<minimum:errors.append(f'{profile}: 分辨率门槛至少{minimum}')
    if profile=='home-pilot' and not str(layout.get('quality_approval','')).strip():errors.append('家庭试制档位需要明确选择记录')
    return errors

def verify_receipt(project,book,base):
    try:
        base=Path(base).resolve()
        receipt=read(resolve_project_file(base,book['artifacts']['acceptance']))
        errors=[]
        expected={'book_id':book['id'],'age_band':book['age_band'],'source_version':project['source']['version'],'characters_version':project['characters_version'],'source_path':project['source'].get('path'),'characters_path':project.get('characters_path'),'active_version':book.get('active_version')}
        if receipt.get('schema_version')!=1:errors.append('非法验收记录版本')
        for key,value in expected.items():
            if key in ('source_path','characters_path') and value is not None:
                value=normalize_relative_path(base,value)
                receipt_value=receipt.get(key)
                if receipt_value is not None:receipt_value=normalize_relative_path(base,receipt_value)
            else:receipt_value=receipt.get(key)
            if receipt_value!=value:errors.append(f'验收身份已变更: {key}')
        files=receipt.get('files')
        if not isinstance(files,dict) or not files:return errors+['验收未记录文件摘要']
        canonical_files=set()
        for path,digest in files.items():
            canonical=normalize_relative_path(base,path)
            canonical_files.add(canonical)
            p=resolve_project_file(base,path)
            if not p.is_file() or sha(p)!=digest:errors.append(f'验收文件缺失或已修改: {path}')
        # Every declared artifact, except the receipt, must be covered.
        for key,path in book['artifacts'].items():
            if key!='acceptance' and normalize_relative_path(base,path) not in canonical_files:errors.append(f'成果不在验收记录中: {key}')
        return errors
    except (OSError,ValueError,KeyError,TypeError) as exc:return [f'验收记录不可用: {exc}']

def check_book(project_path,book_id):
    project_path=Path(project_path).resolve();base=project_path.parent
    project=read(project_path)
    book=next((b for b in project['books'] if b['id']==book_id),None)
    if not book:raise ValueError('找不到册编号')
    artifacts=book['artifacts'];errors=[];files=set()
    def canonical(path):
        return path.resolve().relative_to(base).as_posix()
    def track_resolved(path):
        p=Path(path).resolve()
        if not p.is_file():raise ValueError(f'文件缺失: {p}')
        try:relative=canonical(p)
        except ValueError:raise ValueError(f'验收资产必须位于项目内: {p}')
        files.add(relative);return p
    def track(path,parent=base):return track_resolved(resolve_project_file(parent,path))
    def artifact(key):return track(artifacts[key])
    try:
        for key in ('concept','story','storyboard','layout','page_manifest','reading_pdf','print_pdf','review'):artifact(key)
        source_path=track(project['source']['path'])
        if not project.get('characters_path'):errors.append('缺少角色参考目录')
        else:
            chars=resolve_project_file(base,project['characters_path'])
            refs=[p for p in chars.rglob('*') if p.is_file()]
            if not refs:errors.append('角色参考文件缺失')
            for p in refs:track_resolved(p)
        concept=read(artifact('concept'));layout_path=artifact('layout');layout=read(layout_path)
        manifest_path=artifact('page_manifest');manifest=read(manifest_path)
        storyboard=read(artifact('storyboard'));storyboard=storyboard.get('pages',[]) if isinstance(storyboard,dict) else storyboard
        review=read(artifact('review'))
        errors.extend(quality_errors(layout))
        if book.get('age_band') not in ('3-4','5-7','8-10','5-6'):errors.append('缺少有效年龄选择')
        if concept.get('age_band')!=book.get('age_band') or manifest.get('age_band')!=book.get('age_band'):errors.append('年龄记录不一致')
        if manifest.get('book_id')!=book_id or concept.get('book_id')!=book_id:errors.append('册编号不一致')
        if book.get('source_version')!=project['source']['version'] or book.get('characters_version')!=project['characters_version']:errors.append('项目版本已变化')
        errors.extend(validate_page_manifest(manifest,manifest_path.parent,True))
        pages=layout['pages'];n=len(pages);pairs=booklet_pairs(n)
        errors.extend(structure_errors(pages))
        story=normal(artifact('story').read_text(encoding='utf-8'))
        if len(storyboard)!=n or len(manifest['pages'])!=n:errors.append('分镜、清单与版面页数不一致')
        for i,page in enumerate(pages):
            number=i+1
            if page.get('number')!=number:errors.append(f'页{number}: 页码不连续')
            if page.get('font_size',layout.get('font_size',22))<22:errors.append(f'页{number}: 字号过小')
            if i>=len(storyboard) or i>=len(manifest['pages']):continue
            saved=manifest['pages'][i];board=storyboard[i]
            if page.get('text')!=board.get('text'):errors.append(f'页{number}: 正文与分镜不一致')
            if normal(page.get('text','')) not in story:errors.append(f'页{number}: 朗读稿缺少本页正文')
            if saved.get('text_area')!=page.get('text_box_mm'):errors.append(f'页{number}: 文字区域不一致')
            if saved.get('characters_version')!=book['characters_version']:errors.append(f'页{number}: 角色版本不一致')
            track(saved['current_prompt_path'],manifest_path.parent)
            selected=track(saved['current_image_path'],manifest_path.parent)
            kind=page.get('kind')
            if kind not in ('cover','story','parents','back','blank'):errors.append(f'页{number}: 缺少有效页面类型')
            if kind in ('cover','story','back') and not page.get('image'):errors.append(f'页{number}: 缺少实际插画')
            if kind=='story' and (page.get('image_role')!='background' or page.get('text_area_reviewed') is not True):errors.append(f'页{number}: 未确认画面中文字区域')
            if page.get('image'):
                actual=track(page['image'],layout_path.parent)
                if selected!=actual:errors.append(f'页{number}: 清单选图与排版选图不一致')
                from PIL import Image
                with Image.open(actual) as img:pw,ph=img.size
                box=page['image_box_mm'];effective=max(pw/(box[2]/25.4),ph/(box[3]/25.4))
                if effective+0.01<layout.get('target_dpi',300):errors.append(f'页{number}: 原生分辨率不足')
        font=Path(layout.get('font_path',''))
        if not layout.get('font_path'):errors.append('验收版面须保存项目内字体路径')
        else:track(font,layout_path.parent)
        if layout.get('font_license_path'):track(layout['font_license_path'],layout_path.parent)
        if layout.get('font_provenance_path'):track(layout['font_provenance_path'],layout_path.parent)
        def reviewed(field,count,index):
            records=review.get(field,[])
            if not isinstance(records,list) or len(records)!=count:errors.append(f'{field}: 未逐页记录审核');return
            for k,record in enumerate(records,1):
                if record.get(index)!=k or record.get('status')!='passed' or not record.get('evidence'):errors.append(f'{field} {k}: 缺少通过证据')
                if record.get('image_path'):track(record['image_path'])
                else:errors.append(f'{field} {k}: 缺少审核渲染图')
        reviewed('reading_pages',n,'page');reviewed('print_sides',len(pairs),'side')
        if review.get('unresolved_digital_defects'):errors.append('仍有未解决数字缺陷')
        reading=fitz.open(artifact('reading_pdf'));printing=fitz.open(artifact('print_pdf'))
        if len(reading)!=n or len(printing)!=len(pairs):errors.append('最终PDF页数不符')
        dims=layout.get('page_mm',[148,210])
        for i,page in enumerate(reading):
            if i>=n:break
            if normal(page.get_text())!=normal(pages[i]['text']):errors.append(f'阅读页{i+1}: 可提取正文不一致')
            if abs(page.rect.width-dims[0]*MM)>.05 or abs(page.rect.height-dims[1]*MM)>.05:errors.append(f'阅读页{i+1}: 尺寸不一致')
            used={s['font'] for b in page.get_text('dict')['blocks'] if b.get('type')==0 for l in b['lines'] for s in l['spans'] if s['text'].strip()}
            sizes=[s['size'] for b in page.get_text('dict')['blocks'] if b.get('type')==0 for l in b['lines'] for s in l['spans'] if s['text'].strip()]
            if any(size<21.99 for size in sizes):errors.append(f'阅读页{i+1}: 实际字号小于22磅')
            embedded={f[3].split('+')[-1] for f in page.get_fonts() if reading.extract_font(f[0])[3]}
            if not used<=embedded:errors.append(f'阅读页{i+1}: 实际使用字体未嵌入')
            records=review.get('reading_pages',[])
            if i<len(records) and records[i].get('image_path'):
                errors.extend(f'阅读页{i+1}: {e}' for e in reviewed_image_errors(reading,i,track(records[i]['image_path'])))
        for i,page in enumerate(printing):
            if i>=len(pairs):break
            if abs(page.rect.width-297*MM)>.05 or abs(page.rect.height-210*MM)>.05:errors.append(f'打印面{i+1}: 非横向A4')
            left,right=pairs[i]
            # Compare each half separately; PDF extraction order is not guaranteed.
            for side,num in enumerate((left,right)):
                rect=fitz.Rect(side*page.rect.width/2,0,(side+1)*page.rect.width/2,page.rect.height)
                if normal(page.get_text(clip=rect))!=normal(pages[num-1]['text']):errors.append(f'打印面{i+1}: 配对页{num}正文不符')
            records=review.get('print_sides',[])
            if i<len(records) and records[i].get('image_path'):
                errors.extend(f'打印面{i+1}: {e}' for e in reviewed_image_errors(printing,i,track(records[i]['image_path'])))
        reading.close();printing.close()
        files.update(collect_declared_assets(project_path,project,book))
    except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:errors.append(str(exc))
    return {'errors':errors,'files':{path:sha(resolve_project_file(base,path)) for path in sorted(files)},'book_id':book_id,'age_band':book.get('age_band'),'source_version':project['source']['version'],'characters_version':project['characters_version'],'source_path':normalize_relative_path(base,project['source'].get('path')),'characters_path':normalize_relative_path(base,project['characters_path']) if project.get('characters_path') else None,'active_version':book.get('active_version'),'schema_version':1}

def accept_book(project_path,book_id,receipt_path):
    from project_state import save_project
    path=Path(project_path).resolve();report=check_book(path,book_id)
    if report['errors']:raise ValueError('; '.join(report['errors']))
    destination=Path(receipt_path).resolve()
    if destination.exists():raise FileExistsError(destination)
    relative=destination.relative_to(path.parent).as_posix();destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    data=read(path);book=next(b for b in data['books'] if b['id']==book_id)
    book['artifacts']['acceptance']=relative;book['status']='digital_checked'
    try:save_project(path,data)
    except Exception:destination.unlink();raise
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('project',type=Path);p.add_argument('book_id');p.add_argument('--accept',type=Path);a=p.parse_args()
    result=accept_book(a.project,a.book_id,a.accept) if a.accept else check_book(a.project,a.book_id)
    print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(bool(result['errors']))
