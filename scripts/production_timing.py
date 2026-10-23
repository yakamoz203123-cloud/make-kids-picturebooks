"""Small, explicit phase timing records for picturebook production.

The recorder never infers missing time.  An unfinished or cross-process phase
keeps ``elapsed_ms=\"unknown\"`` until its caller supplies a measured value.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = 1
UNKNOWN = "unknown"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _write_atomic(path: Path, value: Mapping[str, Any]) -> None:
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
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    events = data.get("events") if isinstance(data, dict) else None
    if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
        raise ValueError(f"invalid phase event document: {path}")
    return list(events)


class PhaseRecorder:
    """Persist phase events with both wall timestamps and measured durations."""

    def __init__(self, path: str | Path, *, load_existing: bool = True) -> None:
        self.path = Path(path)
        self.events: list[dict[str, Any]] = _read_events(self.path) if load_existing else []
        self._monotonic_starts: dict[str, float] = {}

    def _save(self) -> None:
        _write_atomic(self.path, {"schema_version": SCHEMA_VERSION, "events": self.events})

    def start(self, phase: str, *, task_id: str | None = None) -> str:
        phase = str(phase).strip()
        if not phase:
            raise ValueError("phase must be non-empty")
        event_id = f"phase-{uuid.uuid4().hex}"
        self.events.append(
            {
                "event_id": event_id,
                "phase": phase,
                "task_id": task_id,
                "start_at": _now(),
                "end_at": None,
                "elapsed_ms": UNKNOWN,
                "status": "running",
                "error_count": 0,
                "retry_count": 0,
            }
        )
        self._monotonic_starts[event_id] = time.perf_counter()
        self._save()
        return event_id

    def finish(
        self,
        event_id: str,
        *,
        status: str,
        error_count: int = 0,
        retry_count: int = 0,
        elapsed_ms: int | None = None,
    ) -> dict[str, Any]:
        event = next((item for item in self.events if item.get("event_id") == event_id), None)
        if event is None:
            raise ValueError(f"unknown phase event: {event_id}")
        if event.get("end_at") is not None:
            raise ValueError(f"phase event is already finished: {event_id}")
        if type(error_count) is not int or error_count < 0:
            raise ValueError("error_count must be a non-negative integer")
        if type(retry_count) is not int or retry_count < 0:
            raise ValueError("retry_count must be a non-negative integer")
        if elapsed_ms is None and event_id in self._monotonic_starts:
            elapsed_ms = max(0, round((time.perf_counter() - self._monotonic_starts[event_id]) * 1000))
        if elapsed_ms is not None and (type(elapsed_ms) is not int or elapsed_ms < 0):
            raise ValueError("elapsed_ms must be a non-negative integer or None")
        event.update(
            {
                "end_at": _now(),
                "elapsed_ms": elapsed_ms if elapsed_ms is not None else UNKNOWN,
                "status": str(status).strip() or "unknown",
                "error_count": error_count,
                "retry_count": retry_count,
            }
        )
        self._monotonic_starts.pop(event_id, None)
        self._save()
        return dict(event)

    def record(
        self,
        phase: str,
        *,
        task_id: str | None = None,
        start_at: str,
        end_at: str | None,
        elapsed_ms: int | str = UNKNOWN,
        status: str,
        error_count: int = 0,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        if elapsed_ms != UNKNOWN and (type(elapsed_ms) is not int or elapsed_ms < 0):
            raise ValueError("elapsed_ms must be a non-negative integer or 'unknown'")
        if type(error_count) is not int or error_count < 0:
            raise ValueError("error_count must be a non-negative integer")
        if type(retry_count) is not int or retry_count < 0:
            raise ValueError("retry_count must be a non-negative integer")
        event = {
            "event_id": f"phase-{uuid.uuid4().hex}",
            "phase": str(phase).strip(),
            "task_id": task_id,
            "start_at": start_at,
            "end_at": end_at,
            "elapsed_ms": elapsed_ms,
            "status": str(status).strip() or "unknown",
            "error_count": error_count,
            "retry_count": retry_count,
        }
        if not event["phase"]:
            raise ValueError("phase must be non-empty")
        self.events.append(event)
        self._save()
        return dict(event)


def summarize_phase_events(events: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group unique phase events without treating unknown time as zero."""
    by_phase: dict[str, list[Mapping[str, Any]]] = {}
    seen: set[str] = set()
    for event in events:
        event_id = str(event.get("event_id", ""))
        if event_id and event_id in seen:
            continue
        if event_id:
            seen.add(event_id)
        phase = str(event.get("phase", "")).strip()
        if phase:
            by_phase.setdefault(phase, []).append(event)

    result: dict[str, dict[str, Any]] = {}
    for phase, phase_events in by_phase.items():
        observed = [event["elapsed_ms"] for event in phase_events if type(event.get("elapsed_ms")) is int]
        statuses = {str(event.get("status", "unknown")) for event in phase_events}
        if "failed" in statuses:
            status = "failed"
        elif "running" in statuses:
            status = "running"
        elif statuses and statuses <= {"passed", "skipped"}:
            status = "passed"
        else:
            status = "unknown"
        result[phase] = {
            "elapsed_ms": sum(observed) if observed else UNKNOWN,
            "status": status,
            "task_count": len({event.get("task_id") for event in phase_events if event.get("task_id")}),
            "event_count": len(phase_events),
            "error_count": sum(int(event.get("error_count", 0)) for event in phase_events),
            "retry_count": sum(int(event.get("retry_count", 0)) for event in phase_events),
        }
    return result
