"""Pass the final, read-only pre-delivery gate before releasing a pure-image package."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_pure_image_delivery import _project_root
from project_preflight import preflight_project


class DeliveryReleaseError(ValueError):
    """A delivery package is not eligible for the released state."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeliveryReleaseError(f"invalid delivery JSON: {path}") from exc
    if not isinstance(value, dict):
        raise DeliveryReleaseError(f"delivery JSON must be an object: {path}")
    return value


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def release_delivery(
    project: str | Path,
    book_id: str,
    delivery: str | Path,
    *,
    version: str | None = None,
) -> dict[str, Any]:
    """Transition one technically built package to ``released`` exactly once."""
    root = _project_root(project)
    delivery_path = Path(delivery).resolve()
    validation_path = delivery_path / "delivery-validation.json"
    receipt_path = delivery_path / "release-receipt.json"
    if not delivery_path.is_dir() or not validation_path.is_file():
        raise DeliveryReleaseError("DELIVERY_VALIDATION_MISSING")
    report = preflight_project(
        root,
        book_id,
        version=version,
        phase="pre_delivery",
        mode="strict",
        output=delivery_path,
    )
    if report.get("status") != "passed":
        blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
        detail = ";".join(str(item) for item in blockers[:12]) or "unknown blocker"
        raise DeliveryReleaseError(f"PRE_DELIVERY_GATE_BLOCKED:{detail}")

    validation = _read_json(validation_path)
    if validation.get("status") != "passed":
        raise DeliveryReleaseError("DELIVERY_VALIDATION_NOT_PASSED")
    if receipt_path.exists():
        receipt = _read_json(receipt_path)
        current_input = next(
            (
                item.get("value")
                for item in report.get("evidence", [])
                if isinstance(item, dict) and item.get("kind") == "delivery_input_fingerprint"
            ),
            None,
        )
        if (
            receipt.get("status") == "released"
            and receipt.get("input_fingerprint") == validation.get("input_fingerprint") == current_input
            and receipt.get("plan_fingerprint") == report.get("plan_fingerprint")
        ):
            return {
                "status": "reused",
                "output": str(delivery_path),
                "release_receipt": str(receipt_path),
            }
        raise DeliveryReleaseError("RELEASE_RECEIPT_STALE")

    receipt = {
        "schema_version": 1,
        "status": "released",
        "phase": "release",
        "preflight_status": report["status"],
        "project_root": report.get("project_root"),
        "book_key": report.get("book_key"),
        "version": report.get("version"),
        "book_id": validation.get("book_id"),
        "delivery": str(delivery_path),
        "plan_fingerprint": report.get("plan_fingerprint"),
        "input_fingerprint": validation.get("input_fingerprint"),
        "released_at": _now(),
        "human_review_boundary": "pre_delivery strict passed; human review evidence remains in project review.json",
    }
    _write_json_atomic(receipt_path, receipt)
    return {
        "status": "released",
        "output": str(delivery_path),
        "release_receipt": str(receipt_path),
        "plan_fingerprint": receipt["plan_fingerprint"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("book_id")
    parser.add_argument("delivery", type=Path)
    parser.add_argument("--version")
    args = parser.parse_args(argv)
    try:
        result = release_delivery(args.project, args.book_id, args.delivery, version=args.version)
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
