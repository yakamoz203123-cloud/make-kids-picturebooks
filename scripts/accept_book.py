"""Accept one complete book against its saved records and reviewed PDF pages.

File hashes detect later edits. They do not substitute for human visual or
scientific review; review records must already contain actual evidence.
"""
import argparse,hashlib,json,os,re,tempfile
from pathlib import Path
import pymupdf as fitz
from asset_registry import collect_declared_assets
from project_paths import normalize_relative_path,resolve_book_image_file,resolve_project_file
from validate_page_manifest import validate_page_manifest
from layout_design import get_social_profile,image_matches_aspect_ratio,validate_layout_design,validate_layout_review
from impose_booklet import booklet_pairs,MM
from validate_exports import allowed_empty_pages,minimum_print_text_size,validation_errors

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def normal(text):return re.sub(r'\s+','',text)

def structure_errors(pages):
    if not pages or pages[0].get('kind')!='cover' or pages[-1].get('kind')!='back' or not any(p.get('kind')=='story' for p in pages):
        return ['完整绘本需要封面、实际故事页及封底']
    return []

def story_text_errors(pages,story):
    cursor=0;errors=[]
    for number,page in enumerate(pages,1):
        if page.get('kind')!='story':continue
        text=normal(page.get('text',''))
        found=story.find(text,cursor)
        if found<0:errors.append(f'页{number}: 朗读稿缺少或乱序本页正文')
        else:cursor=found+len(text)
    return errors

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

def layout_design_errors(value,number,label):
    errors=[]
    if value is None:errors.append(f'页{number}: 旧项目缺少{label}，请迁移到layout-v1后再验收')
    for message in validate_layout_design(value,True):errors.append(f'页{number}: {label}: {message}')
    return errors

def layout_review_errors(value,number,label='reading_pages'):
    errors=[]
    prefix=f'{label} {number}' if label=='reading_pages' else f'{label}{number}'
    if value is None:errors.append(f'{prefix}: 缺少完整版式审核（layout_review）')
    for message in validate_layout_review(value,True):errors.append(f'{prefix}: {message}')
    return errors

EDUCATION_GOAL_FIELDS=(
    'core_knowledge',
    'target_age_band',
    'prior_experience',
    'visible_relationship',
    'knowledge_boundary',
    'reading_observation',
)
METRIC_FIELDS=(
    'wall_clock_ms',
    'image_artifact_span_ms',
    'model_wait_ms',
    'image_generation_calls',
    'attempts',
    'failures',
    'retries',
    'rework_rounds',
    'cache_hits',
    'resume_events',
    'output_quality',
)
EVIDENCE_DOMAINS=(
    'engineering_evidence',
    'content_evidence',
    'visual_evidence',
    'real_reading_evidence',
)

def education_goal_errors(value,age_band):
    errors=[]
    if not isinstance(value,dict):return ['education_goal必须是JSON对象']
    if value.get('schema_version')!=1:errors.append('education_goal.schema_version必须为1')
    for field in EDUCATION_GOAL_FIELDS:
        if not isinstance(value.get(field),str) or not value[field].strip():errors.append(f'education_goal缺少{field}')
    if value.get('target_age_band')!=age_band:errors.append('education_goal.target_age_band与绘本年龄段不一致')
    return errors

def metrics_errors(value):
    errors=[]
    if not isinstance(value,dict):return ['metrics必须是JSON对象']
    for field in METRIC_FIELDS:
        if field not in value:errors.append(f'metrics缺少{field}');continue
        item=value[field]
        if field=='output_quality':
            if item not in ('pending','approved'):errors.append('metrics.output_quality必须是pending或approved')
        elif item!='unknown' and (isinstance(item,bool) or not isinstance(item,(int,float)) or item<0):
            errors.append(f'metrics.{field}必须是非负数或unknown')
    return errors

def evidence_errors(review):
    errors=[]
    for field in EVIDENCE_DOMAINS:
        value=review.get(field)
        if not isinstance(value,dict):errors.append(f'{field}: 缺少证据记录');continue
        if value.get('status') not in ('passed','pending','failed'):errors.append(f'{field}: status必须是passed、pending或failed')
        if not isinstance(value.get('evidence'),str) or not value['evidence'].strip():errors.append(f'{field}: 缺少evidence')
        if value.get('status')=='failed':errors.append(f'{field}: 证据状态不能是failed')
        if field!='real_reading_evidence' and value.get('status')!='passed':errors.append(f'{field}: 数字验收需要passed')
    return errors

def contact_sheet_review_errors(value,track):
    errors=[]
    if not isinstance(value,dict):return ['contact_sheet_review: 缺少整书缩略图审核记录']
    if value.get('status')!='passed':errors.append('contact_sheet_review: status必须是passed')
    if not isinstance(value.get('evidence'),str) or not value['evidence'].strip():errors.append('contact_sheet_review: 缺少evidence')
    if not isinstance(value.get('reviewer'),str) or not value['reviewer'].strip():errors.append('contact_sheet_review: 缺少reviewer')
    if not isinstance(value.get('reviewed_at'),str) or not value['reviewed_at'].strip():errors.append('contact_sheet_review: 缺少reviewed_at')
    image_path=value.get('image_path')
    if not isinstance(image_path,(str,Path)) or not str(image_path).strip():return errors+['contact_sheet_review: 缺少图片路径']
    try:path=track(image_path)
    except (OSError,ValueError,TypeError) as exc:return errors+[f'contact_sheet_review: 图片不可用: {exc}']
    from PIL import Image
    try:
        with Image.open(path) as image:image.verify()
        with Image.open(path) as image:image.load()
    except (OSError,ValueError) as exc:errors.append(f'contact_sheet_review: 图片不可读取: {exc}')
    return errors

def social_render_errors(record,number,design,source_image,track):
    errors=[]
    label=f'社媒页{number}'
    if not isinstance(record,dict):return [f'{label}: 缺少社媒渲染记录']
    errors.extend(layout_review_errors(record.get('layout_review'),number,'社媒页'))
    social=design.get('social_layout') if isinstance(design,dict) else None
    if not isinstance(social,dict):return [f'{label}: 缺少social_layout，无法验证社媒输出']
    profile=social.get('profile')
    profile_config=get_social_profile(profile)
    if record.get('page')!=number:errors.append(f'{label}: 页码不连续')
    if record.get('status') not in ('rendered','passed'):errors.append(f'{label}: 渲染状态必须是rendered或passed')
    if profile_config is None:
        errors.append(f'{label}: profile必须是受支持的社媒profile')
    else:
        canvas=profile_config['canvas']
        source_aspect_ratio=profile_config['source_aspect_ratio']
        if record.get('canvas')!=canvas:errors.append(f'{label}: canvas必须是{canvas["width_px"]}×{canvas["height_px"]}')
        if record.get('source_aspect_ratio')!=source_aspect_ratio:errors.append(f'{label}: 源图比例必须是{source_aspect_ratio}')
    if record.get('profile')!=profile:errors.append(f'{label}: profile与layout.json不一致')
    for field in ('subject_safe_area','text_safe_area'):
        if record.get(field)!=social.get(field):errors.append(f'{label}: {field}与layout.json不一致')
    if source_image is None or not source_image.is_file():
        errors.append(f'{label}: 源图文件不可用')
    else:
        from PIL import Image
        try:
            with Image.open(source_image) as image:
                if profile_config is not None and not image_matches_aspect_ratio(image.width,image.height,profile_config['source_aspect_ratio']):errors.append(f'{label}: 源图必须是{profile_config["source_aspect_ratio"]}，禁止用印刷页中心裁切冒充')
        except (OSError,ValueError) as exc:errors.append(f'{label}: 源图不可读取: {exc}')
    output_value=record.get('output_path')
    if not isinstance(output_value,(str,Path)) or not str(output_value).strip():
        errors.append(f'{label}: 缺少渲染文件路径');return errors
    try:output=track(output_value)
    except (OSError,ValueError,TypeError) as exc:
        errors.append(f'{label}: 渲染文件不可用: {exc}');return errors
    from PIL import Image
    try:
        with Image.open(output) as image:
            if profile_config is not None and image.size!=(profile_config['canvas']['width_px'],profile_config['canvas']['height_px']):errors.append(f'{label}: 渲染文件必须是{profile_config["canvas"]["width_px"]}×{profile_config["canvas"]["height_px"]}')
    except (OSError,ValueError) as exc:errors.append(f'{label}: 渲染文件不可读取: {exc}')
    return errors

def social_profile_errors(pages,social_records):
    errors=[];profiles=[]
    for number,page in enumerate(pages,1):
        design=page.get('layout_design') if isinstance(page,dict) else None
        social=design.get('social_layout') if isinstance(design,dict) else None
        profile=social.get('profile') if isinstance(social,dict) else None
        if not isinstance(profile,str) or not profile.strip():
            errors.append(f'页{number}: social_layout.profile必须是非空值')
        else:profiles.append(profile)
    if isinstance(social_records,list):
        for number,record in enumerate(social_records,1):
            profile=record.get('profile') if isinstance(record,dict) else None
            if not isinstance(profile,str) or not profile.strip():
                errors.append(f'社媒页{number}: profile必须是非空值')
            else:profiles.append(profile)
    if profiles and len(set(profiles))!=1:
        errors.append('本次check_book的全部layout pages和social_pages必须绑定同一个非空profile')
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
    def track_image(path,parent=base):return track_resolved(resolve_book_image_file(parent,path))
    def artifact(key):return track(artifacts[key])
    try:
        approved_characters_dir = None
        for key in ('concept','education_goal','story','storyboard','layout','page_manifest','reading_pdf','print_pdf','review','metrics'):artifact(key)
        source_path=track(project['source']['path'])
        if not project.get('characters_path'):errors.append('缺少角色参考目录')
        else:
            chars=resolve_project_file(base,project['characters_path'])
            approved_characters_dir=chars.resolve()
            refs=[p for p in chars.rglob('*') if p.is_file()]
            if not refs:errors.append('角色参考文件缺失')
            for p in refs:track_resolved(p)
        concept=read(artifact('concept'));layout_path=artifact('layout');layout=read(layout_path)
        manifest_path=artifact('page_manifest');manifest=read(manifest_path)
        storyboard=read(artifact('storyboard'));storyboard=storyboard.get('pages',[]) if isinstance(storyboard,dict) else storyboard
        review=read(artifact('review'))
        errors.extend(education_goal_errors(read(artifact('education_goal')),book.get('age_band')))
        errors.extend(metrics_errors(read(artifact('metrics'))))
        errors.extend(evidence_errors(review))
        errors.extend(contact_sheet_review_errors(review.get('contact_sheet_review'),track))
        for field,label in (('font_path','字体'),('font_license_path','字体许可证'),('font_provenance_path','字体来源证明')):
            value=layout.get(field)
            if not isinstance(value,(str,Path)) or not str(value).strip():errors.append(f'验收版面须保存项目内{label}路径')
            else:track(value,layout_path.parent)
        errors.extend(quality_errors(layout))
        if book.get('age_band') not in ('3-4','5-7','8-10','5-6'):errors.append('缺少有效年龄选择')
        if concept.get('age_band')!=book.get('age_band') or manifest.get('age_band')!=book.get('age_band'):errors.append('年龄记录不一致')
        if manifest.get('book_id')!=book_id or concept.get('book_id')!=book_id:errors.append('册编号不一致')
        if book.get('source_version')!=project['source']['version'] or book.get('characters_version')!=project['characters_version']:errors.append('项目版本已变化')
        errors.extend(validate_page_manifest(manifest,manifest_path.parent,True))
        pages=layout.get('pages');n=len(pages) if isinstance(pages,list) else 0;pairs=booklet_pairs(n)
        if not isinstance(pages,list) or not pages:errors.append('layout.json缺少可验收的pages数组');pages=[]
        errors.extend(structure_errors(pages))
        story=normal(artifact('story').read_text(encoding='utf-8'))
        errors.extend(story_text_errors(pages,story))
        if len(storyboard)!=n or len(manifest['pages'])!=n:errors.append('分镜、清单与版面页数不一致')
        source_images={}
        for i,page in enumerate(pages):
            number=i+1
            if page.get('number')!=number:errors.append(f'页{number}: 页码不连续')
            if page.get('font_size',layout.get('font_size',22))<22:errors.append(f'页{number}: 字号过小')
            if i>=len(storyboard) or i>=len(manifest['pages']):continue
            saved=manifest['pages'][i];board=storyboard[i]
            if page.get('text')!=board.get('text'):errors.append(f'页{number}: 正文与分镜不一致')
            if saved.get('text_area')!=page.get('text_box_mm'):errors.append(f'页{number}: 文字区域不一致')
            if saved.get('text')!=page.get('text'):errors.append(f'页{number}: 清单正文与layout.json不一致')
            if page.get('layout_design')!=saved.get('layout_design'):errors.append(f'页{number}: 清单与layout.json版式不一致')
            errors.extend(layout_design_errors(page.get('layout_design'),number,'layout_design'))
            errors.extend(layout_design_errors(saved.get('layout_design'),number,'清单layout_design'))
            if saved.get('characters_version')!=book['characters_version']:errors.append(f'页{number}: 角色版本不一致')
            track(saved['current_prompt_path'],manifest_path.parent)
            selected=track_image(saved['current_image_path'],manifest_path.parent)
            reference_value=saved.get('character_reference_path')
            if isinstance(reference_value,(str,Path)) and str(reference_value).strip():
                try:
                    reference=resolve_project_file(manifest_path.parent,reference_value)
                except (OSError,ValueError) as exc:
                    errors.append(f'页{number}: 角色参考路径不可用: {exc}')
                else:
                    if not reference.is_file():
                        errors.append(f'页{number}: 角色参考文件缺失: {reference_value}')
                    elif approved_characters_dir is not None:
                        try:
                            reference.relative_to(approved_characters_dir)
                        except ValueError:
                            errors.append(f'页{number}: 角色参考不在当前批准目录 {project.get("characters_path")}')
                        else:
                            track_resolved(reference)
            kind=page.get('kind')
            if kind not in ('cover','story','parents','back','blank'):errors.append(f'页{number}: 缺少有效页面类型')
            if kind in ('cover','story','back') and not page.get('image'):errors.append(f'页{number}: 缺少实际插画')
            if kind=='story' and (page.get('image_role')!='background' or page.get('text_area_reviewed') is not True):errors.append(f'页{number}: 未确认画面中文字区域')
            if page.get('image'):
                actual=track(page['image'],layout_path.parent)
                source_images[number]=actual
                if selected!=actual:errors.append(f'页{number}: 清单选图与排版选图不一致')
                from PIL import Image
                with Image.open(actual) as img:pw,ph=img.size
                box=page['image_box_mm'];effective=max(pw/(box[2]/25.4),ph/(box[3]/25.4))
                if effective+0.01<layout.get('target_dpi',300):errors.append(f'页{number}: 原生分辨率不足')
        def reviewed(field,count,index):
            records=review.get(field,[])
            if not isinstance(records,list) or len(records)!=count:errors.append(f'{field}: 未逐页记录审核');return
            for k,record in enumerate(records,1):
                if record.get(index)!=k or record.get('status')!='passed' or not record.get('evidence'):errors.append(f'{field} {k}: 缺少通过证据')
                if record.get('image_path'):track(record['image_path'])
                else:errors.append(f'{field} {k}: 缺少审核渲染图')
        reviewed('reading_pages',n,'page');reviewed('print_sides',len(pairs),'side')
        reading_records=review.get('reading_pages',[])
        if isinstance(reading_records,list):
            for number,record in enumerate(reading_records,1):errors.extend(layout_review_errors(record.get('layout_review') if isinstance(record,dict) else None,number))
        social_records=review.get('social_pages')
        if not isinstance(social_records,list) or len(social_records)!=n:
            errors.append('社媒输出未逐页记录渲染结果')
        else:
            for number in range(1,n+1):
                record=next((item for item in social_records if isinstance(item,dict) and item.get('page')==number),None)
                page=pages[number-1]
                errors.extend(social_render_errors(record,number,page.get('layout_design'),source_images.get(number),track))
        errors.extend(social_profile_errors(pages,social_records))
        if review.get('unresolved_digital_defects'):errors.append('仍有未解决数字缺陷')
        dims=layout.get('page_mm',[148,210])
        reading_path=artifact('reading_pdf');printing_path=artifact('print_pdf')
        errors.extend(validation_errors(reading_path,printing_path,[page.get('text','') for page in pages],dims,minimum_print_text_size(layout),allowed_empty_pages(layout)))
        reading=fitz.open(reading_path);printing=fitz.open(printing_path)
        if len(reading)!=n or len(printing)!=len(pairs):errors.append('最终PDF页数不符')
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
    fd,tmp=tempfile.mkstemp(prefix='.receipt-',dir=destination.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.link(tmp,destination)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    data=read(path);book=next(b for b in data['books'] if b['id']==book_id)
    book['artifacts']['acceptance']=relative;book['status']='digital_checked'
    try:save_project(path,data)
    except Exception:destination.unlink();raise
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('project',type=Path);p.add_argument('book_id');p.add_argument('--accept',type=Path);a=p.parse_args()
    result=accept_book(a.project,a.book_id,a.accept) if a.accept else check_book(a.project,a.book_id)
    print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(bool(result['errors']))
