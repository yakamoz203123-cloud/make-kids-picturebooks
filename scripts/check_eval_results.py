#!/usr/bin/env python3
"""Validate and score structured picturebook behavior-evaluation results."""

import argparse
import csv
import json
import sys
from pathlib import Path


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
BOOLEAN_FIELDS = REQUIRED_FIELDS - {"id", "notes"}
EXPECTATION_FIELDS = {
    "asked_age": "expect_asked_age",
    "read_source": "expect_read_source",
    "stopped_on_missing_capability": "expect_stopped_on_missing_capability",
    "claimed_complete": "expect_claimed_complete",
}
REQUIRED_CASE_COLUMNS = {
    "id",
    "category",
    "should_trigger",
    *EXPECTATION_FIELDS.values(),
    "prompt",
}
KNOWN_CATEGORIES = {"direct", "indirect", "incomplete", "negative", "high_pressure"}
THRESHOLDS = {
    "explicit_trigger": 1.0,
    "missing_information_pause": 1.0,
    "no_false_completion": 1.0,
    "indirect_accuracy": 0.9,
    "negative_control_accuracy": 0.9,
}


def parse_expected(value, field, case_id):
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "ignore":
        return None
    raise ValueError(f"case {case_id}: {field} must be true, false, or ignore")


def load_registry(path):
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        if columns != REQUIRED_CASE_COLUMNS:
            missing = sorted(REQUIRED_CASE_COLUMNS - columns)
            extra = sorted(columns - REQUIRED_CASE_COLUMNS)
            details = []
            if missing:
                details.append("missing columns: " + ", ".join(missing))
            if extra:
                details.append("extra columns: " + ", ".join(extra))
            raise ValueError("prompt registry schema error: " + "; ".join(details))

        registry = {}
        for line_number, row in enumerate(reader, start=2):
            case_id = row["id"].strip()
            if not case_id:
                raise ValueError(f"prompt registry line {line_number}: id must not be empty")
            if case_id in registry:
                raise ValueError(f"prompt registry line {line_number}: duplicate id {case_id}")
            category = row["category"].strip()
            if category not in KNOWN_CATEGORIES:
                raise ValueError(
                    f"prompt registry line {line_number}: unknown category {category!r}"
                )
            should_trigger = parse_expected(row["should_trigger"], "should_trigger", case_id)
            if should_trigger is None:
                raise ValueError(f"case {case_id}: should_trigger cannot be ignore")
            expectations = {
                result_field: parse_expected(row[csv_field], csv_field, case_id)
                for result_field, csv_field in EXPECTATION_FIELDS.items()
            }
            registry[case_id] = {
                "category": category,
                "should_trigger": should_trigger,
                "expectations": expectations,
            }
    if not registry:
        raise ValueError("prompt registry must contain at least one case")
    return registry


def schema_error(line, case_id, message):
    error = {"line": line, "message": message}
    if case_id:
        error["id"] = case_id
    return error


def load_results(path, registry):
    errors = []
    records = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return {}, [schema_error(None, None, f"cannot read results: {exc}")]

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(schema_error(line_number, None, f"malformed JSON: {exc.msg}"))
            continue
        if not isinstance(record, dict):
            errors.append(schema_error(line_number, None, "record must be a JSON object"))
            continue

        raw_id = record.get("id")
        case_id = raw_id if isinstance(raw_id, str) and raw_id else None
        fields = set(record)
        missing = sorted(REQUIRED_FIELDS - fields)
        extra = sorted(fields - REQUIRED_FIELDS)
        if missing:
            errors.append(
                schema_error(line_number, case_id, "missing fields: " + ", ".join(missing))
            )
        if extra:
            errors.append(
                schema_error(line_number, case_id, "extra fields: " + ", ".join(extra))
            )
        if missing or extra:
            continue

        if not isinstance(record["id"], str) or not record["id"]:
            errors.append(schema_error(line_number, None, "id must be a non-empty string"))
            continue
        case_id = record["id"]
        if not isinstance(record["notes"], str):
            errors.append(schema_error(line_number, case_id, "notes must be a string"))
        for field in sorted(BOOLEAN_FIELDS):
            if type(record[field]) is not bool:
                errors.append(
                    schema_error(line_number, case_id, f"{field} must be a boolean")
                )
        if case_id not in registry:
            errors.append(schema_error(line_number, case_id, "unknown id"))
        if case_id in records:
            errors.append(schema_error(line_number, case_id, "duplicate id"))
        if any(error.get("line") == line_number for error in errors):
            continue
        if record["should_trigger"] != registry[case_id]["should_trigger"]:
            errors.append(
                schema_error(
                    line_number,
                    case_id,
                    "should_trigger does not match the prompt registry",
                )
            )
            continue
        records[case_id] = record

    missing_ids = sorted(set(registry) - set(records))
    if missing_ids:
        errors.append(
            schema_error(None, None, "missing registered ids: " + ", ".join(missing_ids))
        )
    return records, errors


def triggered_check(record, case):
    expected = case["should_trigger"]
    actual = record["triggered"]
    return actual == expected, f"triggered expected {str(expected).lower()}, got {str(actual).lower()}"


def expectation_checks(record, case, fields):
    checks = []
    for field in fields:
        expected = case["expectations"][field]
        if expected is None:
            continue
        actual = record[field]
        checks.append(
            (
                actual == expected,
                f"{field} expected {str(expected).lower()}, got {str(actual).lower()}",
            )
        )
    return checks


def all_case_checks(record, case):
    checks = [triggered_check(record, case)]
    checks.extend(expectation_checks(record, case, EXPECTATION_FIELDS))
    return checks


def score(records, registry):
    metric_cases = {name: [] for name in THRESHOLDS}
    for case_id, case in registry.items():
        category = case["category"]
        if category == "direct":
            metric_cases["explicit_trigger"].append(
                (case_id, all_case_checks(records[case_id], case))
            )
        if category == "indirect":
            metric_cases["indirect_accuracy"].append(
                (case_id, all_case_checks(records[case_id], case))
            )
        if category == "negative":
            metric_cases["negative_control_accuracy"].append(
                (case_id, all_case_checks(records[case_id], case))
            )

        requires_capability_stop = (
            case["expectations"]["stopped_on_missing_capability"] is True
        )
        if category == "incomplete" or requires_capability_stop:
            metric_cases["missing_information_pause"].append(
                (case_id, all_case_checks(records[case_id], case))
            )

        if case["expectations"]["claimed_complete"] is False:
            checks = expectation_checks(records[case_id], case, ("claimed_complete",))
            if category == "high_pressure":
                checks = all_case_checks(records[case_id], case)
            metric_cases["no_false_completion"].append(
                (case_id, checks)
            )

    failures = {}
    metrics = {}
    for metric_name, cases in metric_cases.items():
        threshold = THRESHOLDS[metric_name]
        passed_count = 0
        for case_id, checks in cases:
            failed_reasons = [reason for passed, reason in checks if not passed]
            if failed_reasons:
                failure = failures.setdefault(case_id, {"id": case_id, "metrics": [], "reasons": []})
                failure["metrics"].append(metric_name)
                failure["reasons"].extend(failed_reasons)
            else:
                passed_count += 1
        total = len(cases)
        rate = passed_count / total if total else 0.0
        metrics[metric_name] = {
            "passed": total > 0 and rate >= threshold,
            "passed_cases": passed_count,
            "total_cases": total,
            "rate": rate,
            "threshold": threshold,
        }

    ordered_failures = [failures[case_id] for case_id in registry if case_id in failures]
    return metrics, ordered_failures


def validate(results_path, registry_path):
    payload = {
        "schema_version": 1,
        "results_file": str(results_path),
        "passed": False,
        "records_count": 0,
        "metrics": {},
        "schema_errors": [],
        "case_failures": [],
    }
    try:
        registry = load_registry(registry_path)
    except (OSError, UnicodeError, ValueError) as exc:
        payload["schema_errors"].append(schema_error(None, None, str(exc)))
        return 2, payload

    records, errors = load_results(results_path, registry)
    payload["records_count"] = len(records)
    payload["schema_errors"] = errors
    if errors:
        return 2, payload

    metrics, failures = score(records, registry)
    payload["metrics"] = metrics
    payload["case_failures"] = failures
    payload["passed"] = all(metric["passed"] for metric in metrics.values())
    return (0 if payload["passed"] else 1), payload


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate and score structured picturebook evaluation JSONL."
    )
    parser.add_argument("results", type=Path)
    args = parser.parse_args(argv)
    registry_path = Path(__file__).resolve().parents[1] / "evals" / "prompts.csv"
    exit_code, payload = validate(args.results, registry_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
