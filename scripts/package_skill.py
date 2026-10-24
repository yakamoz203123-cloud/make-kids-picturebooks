"""Build non-overwriting distribution archives for the picturebook skill."""

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path

from asset_hashing import canonical_bytes

EXCLUDED_DIRS = {".git", ".superpowers", "__pycache__"}
PACKAGE_NAME = "make-kids-picturebooks"


def _package_name(root: Path) -> str:
    """Read the stable package identity from SKILL.md front matter."""
    lines = (root / "SKILL.md").read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return PACKAGE_NAME
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, separator, value = line.partition(":")
        if separator and key.strip() == "name":
            name = value.strip().strip("'\"")
            if name and Path(name).name == name and name not in {".", ".."}:
                return name
            raise ValueError("SKILL.md front matter 必须包含安全的 name")
    return PACKAGE_NAME


def _resolved_inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _skill_files(skill_dir: Path) -> list[tuple[str, Path]]:
    root = Path(skill_dir).resolve()
    if not root.is_dir():
        raise ValueError("技能目录不存在")
    skill_md = root / "SKILL.md"
    if not skill_md.is_file():
        raise ValueError("技能目录必须包含 SKILL.md")

    result: list[tuple[str, Path]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(root).parts
        # MANIFEST.json is generated from the exact archive inputs below.  A
        # checked-in release manifest must not be copied into the archive and
        # then duplicated by the generated manifest entry.
        if relative_parts == ("MANIFEST.json",):
            continue
        if any(part in EXCLUDED_DIRS for part in relative_parts) or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError(f"技能包不允许符号链接: {path}")
        if not _resolved_inside(root, path):
            raise ValueError(f"技能包文件越界: {path}")
        result.append((path.relative_to(root).as_posix(), path))
    return result


def _digest(path: Path) -> str:
    return hashlib.sha256(canonical_bytes(path)).hexdigest()


def _archive_value(path: Path) -> bytes | Path:
    normalized = canonical_bytes(path)
    return normalized if normalized != path.read_bytes() else path


def _publish_archive(output: Path, entries: list[tuple[str, bytes | Path]]) -> None:
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".skill-package-", suffix=".zip", dir=output.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, value in entries:
                if Path(name).is_absolute() or ".." in Path(name).parts:
                    raise ValueError(f"归档路径非法: {name}")
                if isinstance(value, Path):
                    archive.write(value, name)
                else:
                    archive.writestr(name, value)
        try:
            os.link(temporary, output)
        except FileExistsError:
            raise
        except OSError as exc:
            if output.exists():
                raise FileExistsError(output) from exc
            raise ValueError(f"无法原子发布归档: {output}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _manifest_bytes(version: str, package_type: str, files: list[dict[str, str]]) -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "package_type": package_type,
            "version": version,
            "files": files,
        },
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8") + b"\n"


def package_skill(skill_dir: Path, output: Path, version: str) -> dict:
    root = Path(skill_dir).resolve()
    output = Path(output).resolve()
    if _resolved_inside(root, output):
        raise ValueError("技能包输出不能位于技能目录内")

    files = _skill_files(root)
    top = _package_name(root)
    entries: list[tuple[str, bytes | Path]] = []
    manifest_files = []
    for relative, source in files:
        archive_path = f"{top}/{relative}"
        entries.append((archive_path, _archive_value(source)))
        manifest_files.append({"path": archive_path, "sha256": _digest(source)})
    manifest_path = f"{top}/MANIFEST.json"
    entries.append((manifest_path, _manifest_bytes(version, "skill", manifest_files)))
    _publish_archive(output, entries)
    return {"version": version, "package_type": "skill", "files": len(entries), "output": str(output)}


def package_download_bundle(skill_dir: Path, auxiliary_files: list[Path], output: Path, version: str) -> dict:
    root = Path(skill_dir).resolve()
    output = Path(output).resolve()
    if _resolved_inside(root, output):
        raise ValueError("下载包输出不能位于技能目录内")

    files = _skill_files(root)
    top = _package_name(root)
    entries: list[tuple[str, bytes | Path]] = []
    manifest_files = []
    for relative, source in files:
        archive_path = f"{top}/{relative}"
        entries.append((archive_path, _archive_value(source)))
        manifest_files.append({"path": archive_path, "sha256": _digest(source)})

    seen_aux: set[str] = set()
    for auxiliary in auxiliary_files:
        source = Path(auxiliary).resolve()
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"辅助发布文件不可用: {auxiliary}")
        name = source.name
        if not name or name in seen_aux or name in {entry[0] for entry in entries}:
            raise ValueError(f"辅助发布文件名冲突: {name}")
        seen_aux.add(name)
        entries.append((name, _archive_value(source)))
        manifest_files.append({"path": name, "sha256": _digest(source)})

    entries.append(("发布清单.json", _manifest_bytes(version, "download_bundle", manifest_files)))
    _publish_archive(output, entries)
    return {
        "version": version,
        "package_type": "download_bundle",
        "files": len(entries),
        "output": str(output),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--bundle", action="store_true")
    parser.add_argument("--aux", action="append", type=Path, default=[])
    args = parser.parse_args()
    if args.bundle:
        result = package_download_bundle(args.skill_dir, args.aux, args.output, args.version)
    else:
        if args.aux:
            parser.error("--aux 只能与 --bundle 一起使用")
        result = package_skill(args.skill_dir, args.output, args.version)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
