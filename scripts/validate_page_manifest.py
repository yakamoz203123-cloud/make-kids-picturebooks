"""Validate production records, not the scientific truth of their contents."""
import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping

from asset_resolver import CORE_BUNDLE_ROOT, load_core_manifest
from continuity_contract import validate_continuity_invariants
from layout_design import validate_layout_design
from page_production import build_page_prompt, validate_page_spec
from project_paths import resolve_book_image_file


def _load_strict_asset_manifest(
    asset_manifest_path: str | Path | Mapping[str, Any] | None,
    asset_bundle_root: str | Path | None,
) -> tuple[Mapping[str, Any], Path | None]:
    """Load the approved asset manifest used by optional strict validation."""
    if isinstance(asset_manifest_path, Mapping):
        return asset_manifest_path, Path(asset_bundle_root).resolve() if asset_bundle_root else None
    if asset_manifest_path is None:
        return load_core_manifest(), Path(asset_bundle_root).resolve() if asset_bundle_root else CORE_BUNDLE_ROOT
    manifest_path = Path(asset_manifest_path).resolve()
    if manifest_path.is_dir():
        manifest_path = manifest_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, Mapping):
        raise ValueError("strict asset manifest must be an object")
    return manifest, Path(asset_bundle_root).resolve() if asset_bundle_root else manifest_path.parent


def _validate_strict_assets(
    data: Mapping[str, Any],
    errors: list[str],
    *,
    asset_manifest_path: str | Path | Mapping[str, Any] | None,
    asset_bundle_root: str | Path | None,
    style_bundle_root: str | Path | None,
) -> None:
    try:
        manifest, bundle_root = _load_strict_asset_manifest(asset_manifest_path, asset_bundle_root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"strict_assets: {exc}")
        return

    for number, page in enumerate(data.get("pages", []), 1):
        where = f"pages[{number}].strict_assets"
        if not isinstance(page, dict):
            continue
        spec_errors = validate_page_spec(page, mode="production")
        for message in spec_errors:
            errors.append(f"{where}: {message}")
        if spec_errors:
            continue
        try:
            # The prompt boundary performs the same resolver call used by
            # production and also checks any declared resolved/style hashes.
            build_page_prompt(
                page,
                manifest=manifest,
                bundle_root=bundle_root,
                style_bundle_root=style_bundle_root,
                mode="production",
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"{where}: {exc}")


def validate_page_manifest(
    data: dict,
    base_dir: Path,
    require_images: bool = False,
    strict_assets: bool = False,
    asset_manifest_path: str | Path | Mapping[str, Any] | None = None,
    asset_bundle_root: str | Path | None = None,
    style_bundle_root: str | Path | None = None,
) -> list[str]:
    errors = []
    project_root = Path(base_dir).resolve()
    def error(where, message):
        errors.append(f'{where}: {message}')
    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())
    def finite_number(value):
        if type(value) not in (int, float):
            return False
        try:
            return math.isfinite(value)
        except OverflowError:
            return False
    def file_record(value, where, required, *, image=False):
        if value is None and not required:
            return
        if not nonempty(value):
            error(where, 'expected a nonempty path')
            return
        try:
            candidate = (
                resolve_book_image_file(project_root, value)
                if image
                else (project_root / Path(value)).resolve()
            )
            containment_root = (
                project_root.parent
                if image and project_root.name.lower() == 'content'
                else project_root
            )
            candidate.relative_to(containment_root)
        except (OSError, ValueError):
            error(where, f'selected file must stay inside project: {value}')
            return
        if not candidate.is_file():
            error(where, f'selected file does not exist: {value}')
    if not isinstance(data, dict):
        return ['manifest: expected an object']
    if type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        error('schema_version', 'expected 1')
    if not nonempty(data.get('book_id')):
        error('book_id', 'expected a nonempty string')
    if data.get('age_band') not in ('3-4', '5-7', '8-10', '5-6'):
        error('age_band', 'select 3-4, 5-7 or 8-10; legacy 5-6 is also accepted')
    pages = data.get('pages')
    if not isinstance(pages, list) or not pages:
        error('pages', 'expected a nonempty list')
        return errors
    for number, page in enumerate(pages, 1):
        where = f'pages[{number}]'
        if not isinstance(page, dict):
            error(where, 'expected an object')
            continue
        if type(page.get('page')) is not int or page['page'] != number:
            error(where + '.page', 'must be consecutive in list order starting at 1')
        for field in ('text_version', 'characters_version'):
            if not nonempty(page.get(field)):
                error(where + '.' + field, 'expected a nonempty string')
        file_record(page.get('character_reference_path'), where + '.character_reference_path', require_images)
        reference_assets = page.get('character_reference_assets')
        if reference_assets is not None:
            if not isinstance(reference_assets, list):
                error(where + '.character_reference_assets', 'expected a list')
            else:
                for index, reference in enumerate(reference_assets):
                    reference_where = f'{where}.character_reference_assets[{index}]'
                    if not isinstance(reference, dict):
                        error(reference_where, 'expected an object')
                        continue
                    if not nonempty(reference.get('asset_id')):
                        error(reference_where + '.asset_id', 'expected a nonempty string')
                    file_record(reference.get('path'), reference_where + '.path', require_images)
                    if 'sha256' in reference and (not nonempty(reference.get('sha256')) or len(reference['sha256']) != 64):
                        error(reference_where + '.sha256', 'expected a SHA-256 string')
        file_record(page.get('current_prompt_path'), where + '.current_prompt_path', True)
        if 'current_image_path' not in page:
            error(where + '.current_image_path', 'required; may be null while planning')
        else:
            file_record(
                page['current_image_path'],
                where + '.current_image_path',
                require_images,
                image=True,
            )
        continuity = validate_continuity_invariants(page, project_root=project_root)
        for item in continuity["blocks"]:
            error(where + '.continuity_invariants', f'{item["code"]}: {item["message"]}')
        area = page.get('text_area')
        if not isinstance(area, list) or len(area) != 4 or not all(finite_number(n) for n in area):
            error(where + '.text_area', 'expected four finite coordinates in mm')
        elif area[0] < 0 or area[1] < 0 or area[2] <= 0 or area[3] <= 0:
            error(where + '.text_area', 'origin must be nonnegative and dimensions positive')
        for message in validate_layout_design(page.get('layout_design'), require_images):
            error(where + '.layout_design', message)
        props = page.get('props')
        if not isinstance(props, list):
            error(where + '.props', 'expected a list (empty for pages without props)')
        else:
            ids = set()
            for index, prop in enumerate(props):
                pw = f'{where}.props[{index}]'
                if not isinstance(prop, dict):
                    error(pw, 'expected an object')
                    continue
                pid = prop.get('id')
                if not nonempty(pid):
                    error(pw + '.id', 'expected a nonempty string')
                elif pid in ids:
                    error(pw + '.id', 'duplicate prop id on page')
                else:
                    ids.add(pid)
                if type(prop.get('count')) is not int or prop['count'] < 0:
                    error(pw + '.count', 'expected a nonnegative integer')
                for field in ('location', 'state', 'change'):
                    if not nonempty(prop.get(field)):
                        error(pw + '.' + field, 'expected a nonempty string')
        check = page.get('knowledge_check')
        if not isinstance(check, dict):
            error(where + '.knowledge_check', 'expected an object')
        else:
            if check.get('status') not in ('pending', 'passed', 'failed'):
                error(where + '.knowledge_check.status', 'expected pending, passed or failed')
            if not isinstance(check.get('evidence'), str):
                error(where + '.knowledge_check.evidence', 'expected a string')
            if require_images and (check.get('status') != 'passed' or not nonempty(check.get('evidence'))):
                error(where + '.knowledge_check', 'completion requires passed status and actual evidence')
        for field in ('previous_page_state', 'current_page_entry', 'next_page_hook'):
            record_where = where + '.' + field
            if field not in page:
                if require_images:
                    error(record_where, 'completion requires an object')
                continue
            record = page[field]
            if not isinstance(record, dict):
                error(record_where, 'expected an object')
                continue
            if set(record) != {'state_id', 'summary'}:
                error(record_where, 'expected exactly the required fields')
            for key in ('state_id', 'summary'):
                if not nonempty(record.get(key)):
                    error(record_where + '.' + key, 'expected a nonempty string')
        for field in ('text_image_match', 'continuity_review'):
            review_where = where + '.' + field
            if field not in page:
                if require_images:
                    error(review_where, 'completion requires an object')
                continue
            review = page[field]
            if not isinstance(review, dict):
                error(review_where, 'expected an object')
                continue
            if set(review) != {'status', 'evidence'}:
                error(review_where, 'expected exactly the required fields')
            if review.get('status') not in ('pending', 'passed', 'failed'):
                error(review_where + '.status', 'expected pending, passed or failed')
            if not isinstance(review.get('evidence'), str):
                error(review_where + '.evidence', 'expected a string')
            if require_images and (review.get('status') != 'passed' or not nonempty(review.get('evidence'))):
                error(review_where, 'completion requires passed status and actual evidence')
        if number > 1:
            previous_hook = pages[number - 2].get('next_page_hook')
            current_entry = page.get('current_page_entry')
            if (isinstance(previous_hook, dict) and isinstance(current_entry, dict)
                    and nonempty(previous_hook.get('state_id'))
                    and nonempty(current_entry.get('state_id'))
                    and previous_hook['state_id'] != current_entry['state_id']):
                error(f'pages[{number - 1}].next_page_hook.state_id',
                      f'must equal pages[{number}].current_page_entry.state_id')
    if require_images:
        first = pages[0].get('previous_page_state')
        if isinstance(first, dict) and nonempty(first.get('state_id')) and first['state_id'] != 'story_start':
            error('pages[1].previous_page_state.state_id', 'completion requires story_start')
        last = pages[-1].get('next_page_hook')
        if isinstance(last, dict) and nonempty(last.get('state_id')) and last['state_id'] != 'story_end':
            error(f'pages[{len(pages)}].next_page_hook.state_id', 'completion requires story_end')
    if strict_assets and isinstance(data, dict):
        _validate_strict_assets(
            data,
            errors,
            asset_manifest_path=asset_manifest_path,
            asset_bundle_root=asset_bundle_root,
            style_bundle_root=style_bundle_root,
        )
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--require-images', action='store_true')
    parser.add_argument('--strict-assets', action='store_true', help='validate asset-bound page records without changing legacy mode')
    parser.add_argument('--asset-manifest', type=Path, help='asset manifest JSON or its bundle directory')
    parser.add_argument('--asset-bundle-root', type=Path, help='approved asset bundle root used for reference checks')
    parser.add_argument('--style-bundle-root', type=Path, help='approved non-default style bundle root used for explicit style checks')
    args = parser.parse_args()
    try:
        data = json.loads(args.manifest.read_text(encoding='utf-8'))
        errors = validate_page_manifest(
            data,
            args.manifest.resolve().parent,
            args.require_images,
            args.strict_assets,
            args.asset_manifest,
            args.asset_bundle_root,
            args.style_bundle_root,
        )
    except (OSError, ValueError) as exc:
        errors = [str(exc)]
    for message in errors:
        print(message)
    if not errors:
        print('Manifest records valid; scientific and visual review remain separate.')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
