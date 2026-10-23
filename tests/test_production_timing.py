import json
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
try:
    from production_timing import PhaseRecorder, summarize_phase_events
finally:
    sys.path.remove(str(SCRIPTS_DIR))


def test_phase_recorder_persists_required_fields_and_groups_elapsed_time(tmp_path: Path) -> None:
    path = tmp_path / "phase-events.json"
    recorder = PhaseRecorder(path)
    event_id = recorder.start("image-postprocess", task_id="page-02")
    recorder.finish(event_id, status="passed")
    recorder.record(
        "user-approval",
        task_id="sample-page",
        start_at="2026-10-19T00:00:00+00:00",
        end_at="2026-10-19T00:00:02+00:00",
        elapsed_ms=2000,
        status="passed",
    )

    saved = json.loads(path.read_text(encoding="utf-8"))
    event = saved["events"][0]
    assert event["phase"] == "image-postprocess"
    assert event["task_id"] == "page-02"
    assert event["status"] == "passed"
    assert isinstance(event["start_at"], str)
    assert isinstance(event["end_at"], str)
    assert isinstance(event["elapsed_ms"], int)
    assert event["error_count"] == 0
    assert event["retry_count"] == 0
    summary = summarize_phase_events(saved["events"])
    assert summary["user-approval"]["elapsed_ms"] == 2000
    assert summary["user-approval"]["task_count"] == 1


def test_unfinished_phase_is_unknown_and_does_not_invent_elapsed_time(tmp_path: Path) -> None:
    recorder = PhaseRecorder(tmp_path / "phase-events.json")
    recorder.start("user-approval", task_id="story-gate")

    summary = summarize_phase_events(recorder.events)

    assert summary["user-approval"]["elapsed_ms"] == "unknown"
    assert summary["user-approval"]["status"] == "running"
