"""Validate and atomically persist resumable picturebook project state."""
import argparse
import json
import os
import re
import tempfile
from pathlib import Path

from project_paths import normalize_relative_path

STATES = ('assessed','planned','text','illustrated','laid_out','digital_checked','print_checked')
AGES = ('3-4','5-7','8-10','5-6')
REQUIRED_ARTIFACTS = ('concept','story','storyboard','layout','page_manifest','reading_pdf','print_pdf','review','acceptance')
ADAPTATION_MODES = ('selected_topics','chapter_order','single_book')
LEGACY_PAGE_STATUS = re.compile(r'^page\d+_[A-Za-z0-9_]+$')

def _is_legacy_page_status(status: object) -> bool:
    """Recognize historical page-production states without treating them as release states."""
    return isinstance(status, str) and LEGACY_PAGE_STATUS.fullmatch(status) is not None

def _book_source_version(data: dict, book: dict) -> object:
    source = data.get('source')
    return book.get('source_version') or (source.get('version') if isinstance(source, dict) else None)

def _book_characters_version(data: dict, book: dict) -> object:
    return book.get('characters_version') or data.get('characters_version')

def validate_selection(data: dict) -> list[str]:
    errors=[]
    selection=data.get('topic_selection')
    if not isinstance(selection,dict):return ['适龄筛选模式需要 topic_selection']
    if selection.get('status') not in ('pending','ready'):errors.append('非法选题筛选状态')
    age=selection.get('age_band');targets=data.get('target_age_bands',[])
    if age is not None and age not in AGES:errors.append('非法选题年龄段')
    if selection.get('status')=='ready' and age not in AGES:errors.append('筛选完成需保存年龄段')
    if age is not None and isinstance(targets,list) and targets!=[age]:errors.append('选题年龄必须与本次单一目标年龄一致')
    topics=selection.get('topics');queue=selection.get('queue')
    if not isinstance(topics,list):return errors+['topics 必须是数组']
    selected=set();seen=set()
    for topic in topics:
        if not isinstance(topic,dict):errors.append('主题必须是对象');continue
        tid=topic.get('id')
        if not isinstance(tid,str) or not tid.strip():errors.append('主题缺少编号')
        elif tid in seen:errors.append('主题编号重复')
        else:seen.add(tid)
        if topic.get('status') not in ('candidate','selected','deferred','skipped'):errors.append('非法主题状态')
        ids=topic.get('book_ids',[])
        if not isinstance(ids,list) or any(not isinstance(bid,str) or not bid.strip() for bid in ids):errors.append('主题册编号必须是非空字符串数组');continue
        if topic.get('status')=='selected':selected.update(ids)
        if selection.get('status')=='ready' and not topic.get('reason'):errors.append('筛选完成需保存主题取舍理由')
    if not isinstance(queue,list) or any(not isinstance(bid,str) or not bid.strip() for bid in queue):return errors+['选题队列必须是非空字符串编号数组，可为空数组']
    if len(set(queue))!=len(queue):errors.append('选题队列编号重复')
    if not set(queue)<=selected:errors.append('选题队列含未选中、暂缓或跳过的主题册')
    return errors

def validate_project(data: dict) -> list[str]:
    if not isinstance(data, dict): return ['项目必须是对象']
    errors=[]
    mode=data.get('adaptation_mode')
    if mode is not None and mode not in ADAPTATION_MODES:errors.append('非法改编模式')
    if mode=='selected_topics':errors.extend(validate_selection(data))
    targets=data.get('target_age_bands',[])
    if not isinstance(targets,list) or any(age not in AGES for age in targets):errors.append('非法目标年龄段')
    if data.get('schema_version') != 1: errors.append('schema_version 必须为1')
    source=data.get('source')
    if not isinstance(source,dict) or not all(source.get(k) for k in ('path','version','coverage')):
        errors.append('缺少来源路径、版本或覆盖范围')
    if not data.get('characters_version'): errors.append('缺少角色版本')
    books=data.get('books')
    if not isinstance(books,list): return errors+['books 必须是数组']
    seen=set()
    for i,book in enumerate(books):
        if not isinstance(book,dict): errors.append(f'册{i}: 必须是对象'); continue
        bid=book.get('id')
        if not isinstance(bid,str) or not bid.strip(): errors.append(f'册{i}: 缺少编号')
        elif bid in seen: errors.append(f'册{i}: 编号重复 {bid}')
        else: seen.add(bid)
        status = book.get('status')
        if status not in STATES and not _is_legacy_page_status(status): errors.append(f'册{i}: 非法状态')
        if not _book_source_version(data, book) or not _book_characters_version(data, book): errors.append(f'册{i}: 缺少来源或角色版本')
        artifacts = book.get('artifacts')
        if artifacts is not None and not isinstance(artifacts, dict): errors.append(f'册{i}: artifacts 必须是对象')
        if 'age_band' in book and book['age_band'] not in AGES: errors.append(f'册{i}: 非法年龄段')
        if mode=='selected_topics' and isinstance(data.get('topic_selection'),dict):
            selection=data['topic_selection'];queue=selection.get('queue',[])
            if isinstance(queue,list) and bid in queue and book.get('age_band')!=selection.get('age_band'):errors.append(f'册{i}: 本次队列册的年龄不一致')
        if status in ('digital_checked','print_checked'):
            if book.get('age_band') not in AGES:errors.append(f'册{i}: 完成册需要年龄段')
            artifacts=book.get('artifacts')
            if not isinstance(artifacts,dict) or any(not isinstance(artifacts.get(k),str) or not artifacts[k].strip() for k in REQUIRED_ARTIFACTS):
                errors.append(f'册{i}: 完成册缺少验收成果路径')
        if status=='print_checked':
            feedback=book.get('print_feedback')
            if not isinstance(feedback,dict) or feedback.get('passed') is not True or not feedback.get('note'):
                errors.append(f'册{i}: 试打通过需要用户实际反馈')
    return errors

def _normalize_project_paths(path: Path, data: dict) -> None:
    root = Path(path).resolve().parent
    source = data.get('source')
    if isinstance(source, dict) and source.get('path'):
        source['path'] = normalize_relative_path(root, source['path'])
    if data.get('characters_path'):
        data['characters_path'] = normalize_relative_path(root, data['characters_path'])
    for book in data.get('books', []):
        if not isinstance(book, dict) or not isinstance(book.get('artifacts'), dict):
            continue
        for key, value in book['artifacts'].items():
            book['artifacts'][key] = normalize_relative_path(root, value)

def save_project(path: Path, data: dict) -> None:
    path=Path(path)
    _normalize_project_paths(path, data)
    errors=validate_project(data)
    if errors: raise ValueError('; '.join(errors))
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.project-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False,indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)

def next_action(data: dict, base_dir: Path | None = None) -> dict | None:
    errors=validate_project(data)
    if errors: raise ValueError('; '.join(errors))
    selected=data.get('adaptation_mode')=='selected_topics'
    if selected:
        selection=data['topic_selection']
        if selection['status']=='pending':
            age=selection.get('age_band')
            if age is None:
                targets=data.get('target_age_bands',[])
                age=targets[0] if len(targets)==1 else None
            return {'stage':'select_topics','age_band':age} if age else {'stage':'select_age'}
        by_id={book['id']:book for book in data['books']}
        books=[by_id.get(bid,{'id':bid}) for bid in selection['queue']]
    else:books=data['books']
    for book in books:
        if 'status' not in book:return {'book_id':book['id'],'stage':'assessed'}
        if base_dir is not None and book['status'] in ('digital_checked','print_checked'):
            from accept_book import verify_receipt
            if verify_receipt(data,book,Path(base_dir)):
                return {'book_id':book['id'],'stage':'revalidate'}
        if _book_source_version(data, book)!=data['source']['version'] or _book_characters_version(data, book)!=data['characters_version'] or book.get('stale'):
            return {'book_id':book['id'],'stage':'revalidate'}
        if _is_legacy_page_status(book['status']):
            return {'book_id':book['id'],'stage':'resume_page_production','status':book['status']}
        idx=STATES.index(book['status'])
        if idx<STATES.index('digital_checked'):
            return {'book_id':book['id'],'stage':STATES[idx+1]}
    if selected:return None
    existing={b['id'] for b in data['books']}
    for chapter in data['source'].get('chapter_index',[]):
        for bid in chapter.get('suggested_books',[]):
            if bid not in existing:return {'book_id':bid,'stage':'assessed'}
        if chapter.get('read') is False:return {'chapter':chapter.get('chapter'),'stage':'read_source'}
    return None

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project',type=Path)
    args=parser.parse_args()
    data=json.loads(args.project.read_text(encoding='utf-8'))
    errors=validate_project(data)
    print(json.dumps({'errors':errors,'next_action':None if errors else next_action(data,args.project.resolve().parent)},ensure_ascii=False,indent=2))
    raise SystemExit(1 if errors else 0)
