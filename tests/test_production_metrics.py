import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "production_metrics.py"


def load_module():
    if not SCRIPT_PATH.exists():
        raise AssertionError(f"missing production metrics script: {SCRIPT_PATH}")
    spec = importlib.util.spec_from_file_location("production_metrics_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.path.insert(0, str(SCRIPT_PATH.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPT_PATH.parent))
    return module


class ProductionMetricsTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_canonical_contract_uses_unknown_for_unobservable_empty_queue(self):
        result = self.module.summarize_production({"schema_version": 1, "jobs": []})

        for field in (
            "wall_clock_ms",
            "image_artifact_span_ms",
            "model_wait_ms",
            "image_generation_calls",
            "attempts",
            "failures",
            "retries",
            "rework_rounds",
            "cache_hits",
            "resume_events",
        ):
            self.assertEqual(result[field], "unknown", field)
        self.assertEqual(result["failure_rate"], "unknown")
        self.assertEqual(result["output_quality"], "pending")

    def test_explicit_generation_and_model_wait_records_are_not_claim_events(self):
        state = {
            "schema_version": 1,
            "jobs": [{"page": 1, "status": "completed", "attempts": 1}],
            "events": [
                {"event": "claimed", "page": 1, "at": "2026-10-16T04:00:00Z"},
                {
                    "event": "image_generation_call",
                    "page": 1,
                    "count": 2,
                    "at": "2026-10-16T04:00:01Z",
                },
                {
                    "event": "model_wait",
                    "page": 1,
                    "elapsed_ms": 450,
                    "at": "2026-10-16T04:00:02Z",
                },
            ],
        }

        result = self.module.summarize_production(state)

        self.assertEqual(result["image_generation_calls"], 2)
        self.assertEqual(result["model_wait_ms"], 450)
        self.assertEqual(result["attempts"], 1)

        claim_only = self.module.summarize_production(
            {
                "schema_version": 1,
                "jobs": [{"page": 1, "status": "completed", "attempts": 1}],
                "events": [{"event": "claimed", "page": 1}],
            }
        )
        self.assertEqual(claim_only["image_generation_calls"], "unknown")
        self.assertEqual(claim_only["model_wait_ms"], "unknown")

    def test_phase_events_supply_attempts_failures_and_image_elapsed(self):
        state = {
            "schema_version": 1,
            "jobs": [{"page": 1, "status": "completed", "attempts": 0}],
            "events": [],
        }
        phase_events = [
            {"event": "claimed", "page": 1, "attempt": 1, "at": "2026-10-16T04:00:00Z"},
            {"event": "failed", "page": 1, "retryable": True, "at": "2026-10-16T04:00:01Z"},
            {"event": "claimed", "page": 1, "attempt": 2, "at": "2026-10-16T04:00:02Z"},
            {"event": "image_artifact_completed", "page": 1, "elapsed_ms": 750, "at": "2026-10-16T04:00:03Z"},
        ]

        result = self.module.summarize_production(state, phase_events)

        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["failures"], 1)
        self.assertEqual(result["retries"], 1)
        self.assertEqual(result["failure_rate"], 0.5)
        self.assertEqual(result["image_artifact_span_ms"], 750)

    def test_duplicate_queue_and_phase_events_are_not_counted_twice(self):
        duplicate_claim = {"event": "claimed", "page": 1, "attempt": 1, "at": "2026-10-16T04:00:00Z"}
        duplicate_failure = {"event": "failed", "page": 1, "retryable": False, "at": "2026-10-16T04:00:01Z"}
        state = {
            "schema_version": 1,
            "jobs": [{"page": 1, "status": "failed", "attempts": 1}],
            "events": [duplicate_claim, duplicate_failure],
        }
        result = self.module.summarize_production(state, [duplicate_claim, duplicate_failure])

        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["failures"], 1)

    def test_explicit_zero_counts_are_preserved_for_observed_cached_job(self):
        result = self.module.summarize_production(
            {
                "schema_version": 1,
                "jobs": [
                    {
                        "page": 1,
                        "status": "cached",
                        "attempts": 0,
                        "errors": [],
                        "revision": 1,
                    }
                ],
            }
        )

        self.assertEqual(result["attempts"], 0)
        self.assertEqual(result["failures"], 0)
        self.assertEqual(result["retries"], 0)
        self.assertEqual(result["rework_rounds"], 0)
        self.assertEqual(result["cache_hits"], 1)

    def test_generation_status_is_separate_from_review_status(self):
        result = self.module.summarize_production(
            {
                "schema_version": 1,
                "jobs": [
                    {"page": 1, "status": "completed", "attempts": 1},
                    {"page": 2, "status": "cached", "attempts": 0},
                ],
            }
        )

        self.assertEqual(result["generation_status"], "generated")
        self.assertEqual(result["review_status"], "pending")
        self.assertEqual(result["terminal_success_count"], 2)
        self.assertEqual(result["next_gate"], "human_review")

    def test_cli_rejects_output_over_phase_events(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            queue_path = root / "queue.json"
            phase_path = root / "phase-events.json"
            queue_path.write_text(json.dumps({"schema_version": 1, "jobs": []}), encoding="utf-8")
            original_phase = json.dumps({"events": [{"event": "phase_started"}]})
            phase_path.write_text(original_phase, encoding="utf-8")

            exit_code = self.module.main(
                [str(queue_path), "--phase-events", str(phase_path), "--output", str(phase_path)]
            )

            self.assertEqual(exit_code, 2)
            self.assertEqual(phase_path.read_text(encoding="utf-8"), original_phase)

    def test_summarize_uses_queue_and_phase_events_without_double_counting(self):
        state = {
            "schema_version": 1,
            "queue_id": "queue-1",
            "created_at": "2026-10-16T00:00:00Z",
            "updated_at": "2026-10-16T00:00:20Z",
            "jobs": [
                {
                    "page": 1,
                    "status": "completed",
                    "attempts": 2,
                    "elapsed_ms": 1200,
                    "created_at": "2026-10-16T00:00:01Z",
                    "started_at": "2026-10-16T00:00:02Z",
                    "finished_at": "2026-10-16T00:00:05Z",
                    "revision": 1,
                },
                {"page": 2, "status": "cached", "attempts": 0, "elapsed_ms": None, "revision": 1},
                {"page": 3, "status": "failed", "attempts": 2, "elapsed_ms": None, "revision": 1},
            ],
            "events": [
                {"event": "claimed", "page": 1, "attempt": 1, "at": "2026-10-16T00:00:02Z"},
                {"event": "failed", "page": 1, "retryable": True, "at": "2026-10-16T00:00:03Z"},
                {"event": "claimed", "page": 1, "attempt": 2, "at": "2026-10-16T00:00:03Z"},
                {
                    "event": "completed",
                    "page": 1,
                    "elapsed_ms": 1200,
                    "at": "2026-10-16T00:00:05Z",
                },
                {"event": "page_reset", "page": 3, "at": "2026-10-16T00:00:10Z"},
                {"event": "claimed", "page": 3, "attempt": 1, "at": "2026-10-16T00:00:11Z"},
                {"event": "failed", "page": 3, "retryable": True, "at": "2026-10-16T00:00:12Z"},
                {"event": "claimed", "page": 3, "attempt": 2, "at": "2026-10-16T00:00:13Z"},
                {"event": "failed", "page": 3, "retryable": False, "at": "2026-10-16T00:00:14Z"},
            ],
        }
        phase_events = [
            {"event": "phase_started", "phase": "planning", "at": "2026-10-16T00:00:00Z"},
            {"event": "phase_finished", "phase": "export", "at": "2026-10-16T00:00:25Z"},
        ]

        result = self.module.summarize_production(state, phase_events)

        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["queue_id"], "queue-1")
        self.assertEqual(result["wall_clock_span_ms"], 25000)
        self.assertEqual(result["recorded_image_elapsed_ms"], 1200)
        self.assertEqual(result["attempts"], 4)
        self.assertEqual(result["failure_events"], 3)
        self.assertEqual(result["failure_rate"], 0.75)
        self.assertEqual(result["retry_count"], 2)
        self.assertEqual(result["cache_hits"], 1)
        self.assertEqual(result["page_rework_count"], 1)
        self.assertEqual(result["pages_completed"], 2)
        self.assertEqual(result["output_quality"], "pending")
        self.assertEqual(result["wall_clock_ms"], 25000)
        self.assertEqual(result["failures"], 3)
        self.assertEqual(result["retries"], 2)
        self.assertEqual(result["rework_rounds"], 1)

    def test_summarize_falls_back_to_schema_v1_jobs_when_events_are_absent(self):
        state = {
            "schema_version": 1,
            "queue_id": "queue-fallback",
            "created_at": "2026-10-16T01:00:00Z",
            "updated_at": "2026-10-16T01:00:01Z",
            "jobs": [
                {"page": 1, "status": "completed", "attempts": 2, "elapsed_ms": 100, "revision": 1},
                {"page": 2, "status": "cached", "attempts": 0, "elapsed_ms": None, "revision": 1},
                {
                    "page": 3,
                    "status": "failed",
                    "attempts": 1,
                    "elapsed_ms": None,
                    "revision": 3,
                    "errors": [{"message": "temporary"}],
                },
            ],
        }

        result = self.module.summarize_production(state)

        self.assertEqual(result["wall_clock_span_ms"], 1000)
        self.assertEqual(result["recorded_image_elapsed_ms"], 100)
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(result["failure_events"], 1)
        self.assertEqual(result["failure_rate"], 1 / 3)
        self.assertEqual(result["retry_count"], 1)
        self.assertEqual(result["cache_hits"], 1)
        self.assertEqual(result["page_rework_count"], 2)
        self.assertEqual(result["pages_completed"], 2)

    def test_recorded_elapsed_includes_keyed_completion_events_not_present_in_jobs(self):
        state = {
            "schema_version": 1,
            "queue_id": "queue-partial",
            "jobs": [
                {"page": 1, "status": "completed", "elapsed_ms": 100},
            ],
            "events": [
                {"event": "completed", "page": 1, "elapsed_ms": 100},
                {"event": "completed", "page": 2, "elapsed_ms": 250},
            ],
        }

        result = self.module.summarize_production(state)

        self.assertEqual(result["recorded_image_elapsed_ms"], 350)

    def test_recorded_elapsed_counts_previous_page_rework_without_double_counting_latest_job(self):
        state = {
            "schema_version": 1,
            "queue_id": "queue-rework",
            "jobs": [
                {"page": 1, "status": "completed", "attempts": 1, "elapsed_ms": 250, "revision": 2},
            ],
            "events": [
                {"event": "completed", "page": 1, "elapsed_ms": 100},
                {"event": "page_reset", "page": 1},
                {"event": "completed", "page": 1, "elapsed_ms": 250},
            ],
        }

        result = self.module.summarize_production(state)

        self.assertEqual(result["recorded_image_elapsed_ms"], 350)

    def test_output_quality_defaults_to_pending_and_requires_explicit_approval(self):
        state = {
            "schema_version": 1,
            "queue_id": "queue-quality",
            "jobs": [{"page": 1, "status": "completed", "output_path": "images/page-01.png"}],
        }

        self.assertEqual(self.module.summarize_production(state)["output_quality"], "pending")
        approved = self.module.summarize_production(
            state,
            [{"event": "quality_reviewed", "output_quality": "approved", "at": "2026-10-16T02:00:00Z"}],
        )
        self.assertEqual(approved["output_quality"], "approved")

    def test_phase_events_are_grouped_without_inventing_unknown_elapsed_time(self):
        state = {
            "schema_version": 1,
            "queue_id": "queue-phases",
            "jobs": [],
        }
        phases = [
            {
                "event_id": "phase-1",
                "phase": "image-postprocess",
                "task_id": "page-02",
                "start_at": "2026-10-16T02:00:00Z",
                "end_at": "2026-10-16T02:00:01Z",
                "elapsed_ms": 1000,
                "status": "passed",
                "error_count": 0,
                "retry_count": 0,
            },
            {
                "event_id": "phase-2",
                "phase": "user-approval",
                "task_id": "sample",
                "start_at": "2026-10-16T02:00:00Z",
                "end_at": None,
                "elapsed_ms": "unknown",
                "status": "running",
                "error_count": 0,
                "retry_count": 0,
            },
        ]

        result = self.module.summarize_production(state, phases)

        self.assertEqual(result["phase_timings"]["image-postprocess"]["elapsed_ms"], 1000)
        self.assertEqual(result["phase_timings"]["user-approval"]["elapsed_ms"], "unknown")
        self.assertEqual(result["phase_timings"]["user-approval"]["status"], "running")

    def test_invalid_schema_or_quality_is_rejected(self):
        with self.assertRaises(ValueError):
            self.module.summarize_production({"schema_version": 2, "jobs": []})
        with self.assertRaises(ValueError):
            self.module.summarize_production(
                {"schema_version": 1, "jobs": []},
                [{"event": "quality_reviewed", "output_quality": "guessed"}],
            )

    def test_atomic_writer_and_cli_read_without_mutating_queue(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            queue_path = root / "queue.json"
            output_path = root / "reports" / "metrics.json"
            phase_path = root / "phase-events.json"
            queue = {
                "schema_version": 1,
                "queue_id": "queue-cli",
                "created_at": "2026-10-16T03:00:00Z",
                "updated_at": "2026-10-16T03:00:02Z",
                "jobs": [{"page": 1, "status": "completed", "attempts": 1, "elapsed_ms": 50}],
                "events": [],
            }
            queue_path.write_text(json.dumps(queue), encoding="utf-8")
            phase_path.write_text(
                json.dumps({"events": [{"event": "quality_reviewed", "output_quality": "approved"}]}),
                encoding="utf-8",
            )
            before = queue_path.read_bytes()

            exit_code = self.module.main(
                [str(queue_path), "--phase-events", str(phase_path), "--output", str(output_path)]
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(queue_path.read_bytes(), before)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["output_quality"], "approved")
            self.assertFalse(list(output_path.parent.glob(".*.tmp")))

    def test_request_lifecycle_metrics_separate_unknowns_recovery_and_wrapper_time(self):
        state = {
            "schema_version": 1,
            "jobs": [],
            "request_lifecycle": [
                {
                    "request_id": "request-1",
                    "terminal_state": "pending_unknown",
                    "wrapper_elapsed_ms": 5000,
                    "model_wait_ms": "unknown",
                    "cost": "cost_unknown",
                    "local_timeout_observed": True,
                    "artifact_path": None,
                    "artifact_sha256": None,
                    "recovery_of_request_id": None,
                    "submission_observed": True,
                    "backend_task_id": "unknown",
                },
                {
                    "request_id": "request-2",
                    "terminal_state": "succeeded",
                    "wrapper_elapsed_ms": 700,
                    "model_wait_ms": "unknown",
                    "cost": "cost_unknown",
                    "local_timeout_observed": False,
                    "artifact_path": "images/page-01-r2.png",
                    "artifact_sha256": "a" * 64,
                    "recovery_of_request_id": "request-1",
                    "submission_observed": True,
                    "backend_task_id": "unknown",
                },
            ],
            "recovery_authorizations": [
                {"authorization_id": "auth-1", "used_calls": 1, "max_calls": 1}
            ],
        }

        result = self.module.summarize_production(state)

        lifecycle = result["request_lifecycle"]
        self.assertEqual(lifecycle["request_attempts"], 2)
        self.assertEqual(lifecycle["artifact_record_count"], 1)
        self.assertEqual(lifecycle["local_timeout_events"], 1)
        self.assertEqual(lifecycle["timed_out_count"], 0)
        self.assertEqual(lifecycle["pending_unknown_count"], 1)
        self.assertEqual(lifecycle["authorized_recovery_count"], 1)
        self.assertEqual(lifecycle["recovery_request_count"], 1)
        self.assertEqual(lifecycle["automatic_retry_count"], 0)
        self.assertEqual(lifecycle["known_wrapper_elapsed_ms"], 5700)
        self.assertEqual(lifecycle["unknown_model_wait_count"], 2)
        self.assertEqual(lifecycle["unknown_cost_count"], 2)
        self.assertEqual(lifecycle["backend_task_id_unknown_count"], 2)

    def test_request_lifecycle_metrics_include_observed_queue_stage_timings(self):
        result = self.module.summarize_production(
            {
                "schema_version": 1,
                "jobs": [],
                "request_lifecycle": [
                    {
                        "request_id": "request-1",
                        "terminal_state": "succeeded",
                        "wrapper_elapsed_ms": 700,
                        "model_wait_ms": "unknown",
                        "cost": "cost_unknown",
                        "submission_observed": True,
                        "backend_task_id": "task-1",
                        "stage_timings": {
                            "claim_to_submit_ms": 120,
                            "submit_to_complete_ms": 580,
                            "claim_to_complete_ms": 700,
                        },
                    }
                ],
            }
        )

        self.assertEqual(result["request_lifecycle"]["claim_to_submit_ms"], 120)
        self.assertEqual(result["request_lifecycle"]["submit_to_complete_ms"], 580)
        self.assertEqual(result["request_lifecycle"]["claim_to_complete_ms"], 700)

    def test_legacy_queue_without_lifecycle_keeps_lifecycle_metrics_unknown(self):
        result = self.module.summarize_production({"schema_version": 1, "jobs": []})

        self.assertEqual(result["request_lifecycle"]["request_attempts"], "unknown")
        self.assertEqual(result["request_lifecycle"]["unknown_model_wait_count"], "unknown")
        self.assertEqual(result["request_lifecycle"]["unknown_cost_count"], "unknown")


if __name__ == "__main__":
    unittest.main()
