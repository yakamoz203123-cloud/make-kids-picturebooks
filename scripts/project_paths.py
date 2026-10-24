"""Project-local path validation and canonicalization helpers."""

from pathlib import Path, PurePosixPath, PureWindowsPath


def _project_root(base: Path) -> Path:
    return Path(base).resolve()


def normalize_relative_path(base: Path, value: str | Path) -> str:
    """Return a project-relative path in POSIX form, rejecting escapes."""
    if not isinstance(value, (str, Path)):
        raise TypeError("项目路径必须是字符串或 Path")
    raw = str(value)
    candidate = raw.replace("\\", "/")
    if not candidate:
        raise ValueError("项目内路径不能为空")
    if PurePosixPath(candidate).is_absolute() or PureWindowsPath(raw).is_absolute():
        raise ValueError(f"项目路径必须是相对路径: {value}")
    if ".." in PurePosixPath(candidate).parts:
        raise ValueError(f"项目路径不得包含父目录穿越: {value}")

    root = _project_root(base)
    resolved = (root / Path(candidate)).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"项目路径必须位于项目目录内: {value}") from exc


def resolve_project_file(base: Path, value: str | Path) -> Path:
    """Resolve a project-local path and reject targets outside the project root."""
    root = _project_root(base)
    relative = normalize_relative_path(root, value)
    resolved = (root / Path(relative)).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"项目路径必须位于项目目录内: {value}") from exc
    return resolved


def require_project_file(base: Path, value: str | Path, label: str) -> Path:
    """Resolve an existing regular project file, naming it in failures."""
    resolved = resolve_project_file(base, value)
    if not resolved.is_file():
        raise ValueError(f"{label}文件缺失: {value}")
    return resolved


def resolve_book_image_file(base: Path, value: str | Path) -> Path:
    """Resolve a page image with the book-level image root as canonical.

    Content-layout projects historically stored source images below
    ``content/images``.  New production output belongs below the book-level
    ``images`` directory.  Prefer the canonical location when both exist, but
    keep the historical fallback so old delivery-only projects remain usable.
    """
    if not isinstance(value, (str, Path)):
        raise TypeError("图片路径必须是字符串或 Path")
    raw = str(value)
    normalized = normalize_relative_path(Path(base), raw)
    base_root = _project_root(Path(base))
    book_root = base_root.parent if base_root.name.lower() == "content" else base_root
    content_root = book_root / "content"
    roots = [book_root]
    if content_root != book_root:
        roots.append(content_root)
    for root in roots:
        candidate = (root / Path(normalized)).resolve()
        try:
            candidate.relative_to(book_root)
        except ValueError as exc:
            raise ValueError(f"图片路径必须位于书籍目录内: {value}") from exc
        if candidate.is_file():
            return candidate
    return (book_root / Path(normalized)).resolve()
