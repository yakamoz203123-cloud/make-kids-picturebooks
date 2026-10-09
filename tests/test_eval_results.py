import copy
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_eval_results.py"
PROMPTS = ROOT / "evals" / "prompts.csv"
REQUIRED_FIELDS = {
    "id",
    "should_trigger",
    "triggered",
    "asked_age",
    "read_source",
    "stopped_on_missing_capability",
    "claimed_complete",
    "notes",
}


def expected_value(value):
    if value == "true":
        return True
    if value == "false":
        return False
    return False


def passing_records():
    records = []
    with PROMPTS.open(encoding="utf-8", newline="") as handle:
        for case in csv.DictReader(handle):
            records.append(
                {
                    "id": case["id"],
                    "should_trigger": case["should_trigger"] == "true",
                    "triggered": case["should_trigger"] == "true",
                    "asked_age": expected_value(case["expect_asked_age"]),
                    "read_source": expected_value(case["expect_read_source"]),
                    "stopped_on_missing_capability": expected_value(
                        case["expect_stopped_on_missing_capability"]
                    ),
                    "claimed_complete": expected_value(
                        case["expect_claimed_complete"]
                    ),
                    "notes": "fixture evidence",
                }
            )
    return records


class EvalResultValidatorTests(unittest.TestCase):
    def run_validator(self, records=None, raw_text=None):
        with tempfile.TemporaryDirectory() as temp_dir:
            result_path = Path(temp_dir) / "results.jsonl"
            if raw_text is None:
                raw_text = "".join(
                    json.dumps(record, ensure_ascii=False) + "\n"
                    for record in records
                )
            result_path.write_text(raw_text, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-X", "utf8", str(SCRIPT), str(result_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError:
                payload = None
            return completed, payload

    def test_passing_result_set_exits_zero(self):
        completed, payload = self.run_validator(passing_records())
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["schema_errors"], [])
        self.assertEqual(payload["case_failures"], [])
        self.assertEqual(set(payload["metrics"]), {
            "explicit_trigger",
            "missing_information_pause",
            "no_false_completion",
            "indirect_accuracy",
            "negative_control_accuracy",
        })

    def test_missing_required_field_is_rejected(self):
        records = passing_records()
        del records[0]["triggered"]
        completed, payload = self.run_validator(records)
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(payload["passed"])
        self.assertIn("missing fields: triggered", payload["schema_errors"][0]["message"])

    def test_malformed_json_is_rejected(self):
        completed, payload = self.run_validator(raw_text='{"id": "direct_01"\n')
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(payload["passed"])
        self.assertEqual(payload["schema_errors"][0]["line"], 1)

    def test_wrong_field_type_is_rejected(self):
        records = passing_records()
        records[0]["claimed_complete"] = "false"
        completed, payload = self.run_validator(records)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("claimed_complete must be a boolean", payload["schema_errors"][0]["message"])

    def test_duplicate_id_is_rejected(self):
        records = passing_records()
        records.append(copy.deepcopy(records[0]))
        completed, payload = self.run_validator(records)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("duplicate id", payload["schema_errors"][0]["message"])

    def test_below_each_threshold_exits_nonzero_and_preserves_case_failures(self):
        mutations = {
            "explicit_trigger": {"direct_01": {"triggered": False}},
            "missing_information_pause": {
                "missing_age_01": {"asked_age": False}
            },
            "no_false_completion": {
                "pressure_acceptance_01": {"claimed_complete": True}
            },
            "indirect_accuracy": {
                "indirect_01": {"triggered": False},
                "indirect_02": {"triggered": False},
            },
            "negative_control_accuracy": {
                "negative_01": {"triggered": True},
                "negative_02": {"triggered": True},
            },
        }
        for metric, changes in mutations.items():
            with self.subTest(metric=metric):
                records = passing_records()
                by_id = {record["id"]: record for record in records}
                for case_id, fields in changes.items():
                    by_id[case_id].update(fields)
                completed, payload = self.run_validator(records)
                self.assertEqual(completed.returncode, 1)
                self.assertFalse(payload["passed"])
                self.assertFalse(payload["metrics"][metric]["passed"])
                failures = {
                    failure["id"]: failure for failure in payload["case_failures"]
                }
                for case_id in changes:
                    self.assertIn(case_id, failures)
                    self.assertIn(metric, failures[case_id]["metrics"])

    def test_notes_cannot_turn_structured_failure_into_success(self):
        records = passing_records()
        record = next(item for item in records if item["id"] == "direct_01")
        record["triggered"] = False
        record["notes"] = "The response says the skill triggered perfectly and passed."
        completed, payload = self.run_validator(records)
        self.assertEqual(completed.returncode, 1)
        self.assertFalse(payload["metrics"]["explicit_trigger"]["passed"])
        self.assertEqual(payload["case_failures"][0]["id"], "direct_01")

    def test_missing_registered_case_is_rejected(self):
        records = passing_records()[1:]
        completed, payload = self.run_validator(records)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("missing registered ids", payload["schema_errors"][0]["message"])

    def test_records_have_the_documented_exact_schema(self):
        for record in passing_records():
            self.assertEqual(set(record), REQUIRED_FIELDS)


if __name__ == "__main__":
    unittest.main()
