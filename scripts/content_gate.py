"""Research-packet, knowledge-whitelist, and story-claim gates.

The gate is deliberately deterministic. It validates the handoff from the
research Skill; it does not perform web search, fact-check prose semantically,
or generate images. A story author must provide a small sentence trace so that
scientific assertions can be checked against the approved knowledge set.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_FILES = (
    "research_packet.md",
    "sources.json",
    "claims.json",
    "child_concepts.json",
)
CLAIM_STATUSES = {"fact", "inference", "uncertain", "pending_confirmation", "omit"}
AGE_FITS = {"include", "borderline", "omit"}
CONCEPT_OUTCOMES = {"include", "borderline", "omit"}
TRACE_KINDS = {"scientific_claim", "observation", "inference", "dialogue", "fictional_story"}


def configure_cli_encoding() -> None:
    """Make human-readable JSON safe for Windows consoles using a legacy code page."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            # A host may expose a stream that advertises reconfigure but does
            # not allow changing it. The JSON file/output contract must still
            # remain usable by the caller.
            continue


def _error(code: str, message: str) -> str:
    return f"[{code}] {message}"


def _empty_report(packet_dir: Path) -> dict[str, Any]:
    return {
        "status": "blocked",
        "packet_dir": str(packet_dir),
        "metadata": {},
        "counts": {},
        "errors": [],
        "warnings": [],
        "error_codes": [],
    }


def _add_error(report: dict[str, Any], code: str, message: str) -> None:
    report["errors"].append(_error(code, message))
    if code not in report["error_codes"]:
        report["error_codes"].append(code)


def _read_text(path: Path, report: dict[str, Any]) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        _add_error(report, "unreadable_file", f"无法读取 {path.name}: {exc}")
        return None
    if "\x00" in text:
        _add_error(report, "corrupt_file", f"{path.name} 含有 NUL 字节，疑似损坏")
        return None
    if not text.strip():
        _add_error(report, "empty_file", f"{path.name} 为空")
        return None
    return text


def _read_json(path: Path, report: dict[str, Any]) -> dict[str, Any] | None:
    text = _read_text(path, report)
    if text is None:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        _add_error(report, "malformed_json", f"{path.name} 不是有效 JSON: {exc.msg}")
        return None
    if not isinstance(value, dict):
        _add_error(report, "invalid_json_shape", f"{path.name} 顶层必须是对象")
        return None
    return value


def _markdown_metadata(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key in ("packet_id", "topic", "age_band"):
        match = re.search(rf"(?m)^-\s*{re.escape(key)}\s*:\s*(.+?)\s*$", text)
        if match:
            result[key] = match.group(1).strip()
    return result


def _unique_ids(items: list[Any], key: str, label: str, report: dict[str, Any]) -> set[str]:
    identifiers: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            _add_error(report, "invalid_record", f"{label}[{index}] 必须是对象")
            continue
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            _add_error(report, "missing_identifier", f"{label}[{index}] 缺少 {key}")
            continue
        if value in identifiers:
            _add_error(report, "duplicate_identifier", f"{label} 重复 {key}: {value}")
        identifiers.add(value)
    return identifiers


def validate_research_packet(packet_dir: str | Path) -> dict[str, Any]:
    """Validate the four-file Research handoff without modifying it."""

    packet_path = Path(packet_dir)
    report = _empty_report(packet_path)
    if not packet_path.is_dir():
        _add_error(report, "missing_packet_dir", f"研究包目录不存在: {packet_path}")
        return report

    missing = [name for name in REQUIRED_FILES if not (packet_path / name).is_file()]
    for name in missing:
        _add_error(report, "missing_required_file", f"缺少研究包文件: {name}")
    if missing:
        return report

    packet_text = _read_text(packet_path / "research_packet.md", report)
    sources_doc = _read_json(packet_path / "sources.json", report)
    claims_doc = _read_json(packet_path / "claims.json", report)
    concepts_doc = _read_json(packet_path / "child_concepts.json", report)
    if packet_text is None or sources_doc is None or claims_doc is None or concepts_doc is None:
        return report

    md_meta = _markdown_metadata(packet_text)
    for key in ("packet_id", "topic", "age_band"):
        if not md_meta.get(key):
            _add_error(report, "missing_packet_metadata", f"research_packet.md 缺少 {key}")

    docs = {
        "sources": sources_doc,
        "claims": claims_doc,
        "child_concepts": concepts_doc,
    }
    packet_ids = {md_meta.get("packet_id")}
    age_bands = {md_meta.get("age_band")}
    for label, document in docs.items():
        if not isinstance(document.get("packet_id"), str):
            _add_error(report, "missing_packet_id", f"{label}.json 缺少 packet_id")
        else:
            packet_ids.add(document["packet_id"])
        if not isinstance(document.get("age_band"), str):
            _add_error(report, "missing_age_band", f"{label}.json 缺少 age_band")
        else:
            age_bands.add(document["age_band"])
        if document.get("topic") is not None:
            if not isinstance(document.get("topic"), str):
                _add_error(report, "invalid_topic", f"{label}.json 的 topic 必须是字符串")
            elif md_meta.get("topic") and document["topic"] != md_meta["topic"]:
                _add_error(report, "topic_mismatch", f"{label}.json 的 topic 与 research_packet.md 不一致")

    packet_ids.discard(None)
    age_bands.discard(None)
    if len(packet_ids) != 1:
        _add_error(report, "packet_identity_mismatch", f"四文件 packet_id 不一致: {sorted(packet_ids)}")
    if len(age_bands) != 1:
        _add_error(report, "age_band_mismatch", f"四文件 age_band 不一致: {sorted(age_bands)}")

    sources = sources_doc.get("sources")
    claims = claims_doc.get("claims")
    concepts = concepts_doc.get("concepts")
    if not isinstance(sources, list) or not sources:
        _add_error(report, "missing_sources", "sources.json 必须包含非空 sources 列表")
        sources = []
    if not isinstance(claims, list) or not claims:
        _add_error(report, "missing_claims", "claims.json 必须包含非空 claims 列表")
        claims = []
    if not isinstance(concepts, list) or not concepts:
        _add_error(report, "missing_concepts", "child_concepts.json 必须包含非空 concepts 列表")
        concepts = []

    source_ids = _unique_ids(sources, "source_id", "sources", report)
    claim_ids = _unique_ids(claims, "claim_id", "claims", report)
    concept_ids = _unique_ids(concepts, "concept_id", "concepts", report)
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            continue
        for claim_id in source.get("supports_claim_ids", []) or []:
            if claim_id not in claim_ids:
                _add_error(report, "unknown_claim_reference", f"sources[{index}] 引用了不存在的 claim_id: {claim_id}")

    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        claim_id = claim.get("claim_id", f"claims[{index}]")
        for field in ("statement", "status", "age_band", "age_fit", "source_ids"):
            if field not in claim:
                _add_error(report, "incomplete_claim", f"{claim_id} 缺少 {field}")
        if claim.get("status") not in CLAIM_STATUSES:
            _add_error(report, "invalid_claim_status", f"{claim_id} 的 status 不受支持: {claim.get('status')}")
        if claim.get("age_fit") not in AGE_FITS:
            _add_error(report, "invalid_age_fit", f"{claim_id} 的 age_fit 不受支持: {claim.get('age_fit')}")
        if len(age_bands) == 1 and claim.get("age_band") not in age_bands:
            _add_error(report, "claim_age_mismatch", f"{claim_id} 的 age_band 与研究包不一致")
        if not isinstance(claim.get("source_ids"), list) or not claim.get("source_ids"):
            _add_error(report, "claim_without_source", f"{claim_id} 必须有 source_ids")
        else:
            for source_id in claim["source_ids"]:
                if source_id not in source_ids:
                    _add_error(report, "unknown_source_reference", f"{claim_id} 引用了不存在的 source_id: {source_id}")
        for evidence in claim.get("evidence_locations", []) or []:
            if isinstance(evidence, dict) and evidence.get("source_id") not in source_ids:
                _add_error(report, "unknown_source_reference", f"{claim_id} 的 evidence_locations 引用了不存在来源")

    expected_age_band = next(iter(age_bands), None)
    for index, concept in enumerate(concepts):
        if not isinstance(concept, dict):
            continue
        concept_id = concept.get("concept_id", f"concepts[{index}]")
        if concept.get("age_band") != expected_age_band:
            _add_error(report, "concept_age_mismatch", f"{concept_id} 的 age_band 与研究包不一致")
        suitability = concept.get("suitability")
        if not isinstance(suitability, dict) or suitability.get("outcome") not in CONCEPT_OUTCOMES:
            _add_error(report, "invalid_concept_suitability", f"{concept_id} 缺少有效 suitability.outcome")
        for claim_id in concept.get("linked_claim_ids", []) or []:
            if claim_id not in claim_ids:
                _add_error(report, "unknown_claim_reference", f"{concept_id} 引用了不存在的 claim_id: {claim_id}")

    report["metadata"] = {
        "packet_id": next(iter(packet_ids), md_meta.get("packet_id")),
        "topic": md_meta.get("topic"),
        "age_band": next(iter(age_bands), md_meta.get("age_band")),
    }
    report["counts"] = {
        "sources": len(sources),
        "claims": len(claims),
        "concepts": len(concepts),
    }
    report["source_ids"] = sorted(source_ids)
    report["claim_ids"] = sorted(claim_ids)
    report["concept_ids"] = sorted(concept_ids)
    report["documents"] = docs
    if not report["errors"]:
        report["status"] = "passed"
    return report


def _public_validation(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in report.items()
        if key != "documents"
    }


def build_knowledge_whitelist(
    packet_dir: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build the only knowledge set that story production may use."""

    validation = validate_research_packet(packet_dir)
    result: dict[str, Any] = {
        "schema_version": 1,
        "status": validation["status"],
        "metadata": validation.get("metadata", {}),
        "validation": _public_validation(validation),
        "allowed_knowledge": [],
        "restricted_knowledge": [],
        "blocked_knowledge": [],
        "claims": {},
    }
    if validation["status"] != "passed":
        if output_path:
            _write_json(Path(output_path), result)
        return result

    docs = validation["documents"]
    source_map = {item["source_id"]: item for item in docs["sources"]["sources"]}
    concepts = docs["child_concepts"]["concepts"]
    claims = docs["claims"]["claims"]
    linked_by_claim: dict[str, list[dict[str, Any]]] = {}
    for concept in concepts:
        for claim_id in concept.get("linked_claim_ids", []) or []:
            linked_by_claim.setdefault(claim_id, []).append(concept)

    for claim in claims:
        claim_id = claim["claim_id"]
        linked = linked_by_claim.get(claim_id, [])
        eligible_concepts = [
            concept
            for concept in linked
            if isinstance(concept.get("suitability"), dict)
            and concept["suitability"].get("outcome") in {"include", "borderline"}
        ]
        item = {
            "claim_id": claim_id,
            "statement": claim["statement"],
            "status": claim["status"],
            "age_fit": claim["age_fit"],
            "source_ids": list(claim["source_ids"]),
            "source_titles": [source_map[sid].get("title", sid) for sid in claim["source_ids"]],
            "concept_ids": [concept["concept_id"] for concept in linked],
            "limits": claim.get("limits", ""),
        }
        result["claims"][claim_id] = item
        if claim["status"] == "fact" and claim["age_fit"] == "include":
            if any(c["suitability"].get("outcome") == "include" for c in eligible_concepts):
                item["usage_mode"] = "child_fact"
                result["allowed_knowledge"].append(item)
            elif any(c["suitability"].get("outcome") == "borderline" for c in eligible_concepts):
                item["usage_mode"] = "adult_mediated"
                result["allowed_knowledge"].append(item)
            else:
                result["blocked_knowledge"].append(claim_id)
        elif claim["status"] == "fact" and claim["age_fit"] == "borderline":
            if any(c["suitability"].get("outcome") == "include" for c in eligible_concepts):
                item["usage_mode"] = "child_fact"
                result["allowed_knowledge"].append(item)
            elif any(
                c["suitability"].get("outcome") == "borderline"
                and c["suitability"].get("adult_mediation_required")
                for c in eligible_concepts
            ):
                item["usage_mode"] = "adult_mediated"
                result["allowed_knowledge"].append(item)
            else:
                result["blocked_knowledge"].append(claim_id)
        elif claim["status"] == "inference":
            result["restricted_knowledge"].append(claim_id)
        else:
            result["blocked_knowledge"].append(claim_id)

    if output_path:
        _write_json(Path(output_path), result)
    return result


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def validate_story_claims(
    story_text: str,
    trace: list[dict[str, Any]],
    whitelist: dict[str, Any],
) -> dict[str, Any]:
    """Validate explicit sentence classifications against a whitelist."""

    result: dict[str, Any] = {
        "status": "passed",
        "errors": [],
        "warnings": [],
        "error_codes": [],
        "sentence_count": len(trace) if isinstance(trace, list) else 0,
    }
    def fail(code: str, message: str) -> None:
        result["errors"].append(_error(code, message))
        if code not in result["error_codes"]:
            result["error_codes"].append(code)

    if not isinstance(story_text, str) or not story_text.strip():
        fail("empty_story", "story_text 不能为空")
    if not isinstance(trace, list) or not trace:
        fail("missing_story_trace", "故事必须提供逐句 scientific/story trace")
        result["status"] = "blocked"
        return result
    claim_index = whitelist.get("claims", {}) if isinstance(whitelist, dict) else {}
    allowed = {
        item["claim_id"]: item
        for item in whitelist.get("allowed_knowledge", [])
        if isinstance(item, dict) and item.get("claim_id")
    }
    seen_ids: set[str] = set()
    story_normalized = _normalize(story_text)
    for index, entry in enumerate(trace):
        if not isinstance(entry, dict):
            fail("invalid_story_trace", f"trace[{index}] 必须是对象")
            continue
        sentence_id = entry.get("sentence_id", f"trace[{index}]")
        if sentence_id in seen_ids:
            fail("duplicate_sentence_id", f"重复 sentence_id: {sentence_id}")
        seen_ids.add(sentence_id)
        text = entry.get("text")
        kind = entry.get("kind")
        claim_ids = entry.get("claim_ids", [])
        if not isinstance(text, str) or not text.strip():
            fail("invalid_story_trace", f"{sentence_id} 缺少 text")
            continue
        if _normalize(text) not in story_normalized:
            fail("trace_text_not_in_story", f"{sentence_id} 的 text 不在 story_text 中")
        if kind not in TRACE_KINDS:
            fail("invalid_story_kind", f"{sentence_id} 的 kind 不受支持: {kind}")
            continue
        if not isinstance(claim_ids, list):
            fail("invalid_story_trace", f"{sentence_id}.claim_ids 必须是列表")
            claim_ids = []

        scientific = kind in {"scientific_claim", "observation"} or (
            kind == "dialogue" and entry.get("scientific") is True
        )
        if scientific and not claim_ids:
            fail("unverified_scientific_claim", f"{sentence_id} 是科学断言但没有 claim_ids")
        if kind == "inference" and not claim_ids:
            fail("unverified_inference", f"{sentence_id} 是推论但没有 claim_ids")
        if kind == "fictional_story" and claim_ids:
            fail("fiction_claim_binding", f"{sentence_id} 的纯文学句不应绑定科学 claim")

        for claim_id in claim_ids:
            claim = claim_index.get(claim_id)
            if not claim:
                fail("unknown_claim", f"{sentence_id} 引用了不存在的 claim_id: {claim_id}")
                continue
            if entry.get("claim_statement") is not None and entry["claim_statement"] != claim.get("statement"):
                fail("claim_binding_mismatch", f"{sentence_id} 的 claim_statement 与 {claim_id} 不一致")
            status = claim.get("status")
            if kind == "inference":
                if status != "inference":
                    fail("inference_binding_mismatch", f"{sentence_id} 必须绑定 inference claim: {claim_id}")
                continue
            if scientific:
                if status == "inference":
                    fail("inference_promoted_to_fact", f"{sentence_id} 把 inference {claim_id} 当成科学事实")
                elif status in {"uncertain", "pending_confirmation", "omit"}:
                    fail("forbidden_claim_status", f"{sentence_id} 使用了禁止状态 {status}: {claim_id}")
                elif claim_id not in allowed:
                    fail("claim_not_in_whitelist", f"{sentence_id} 的 claim 不在 allowed_knowledge: {claim_id}")
                elif allowed[claim_id].get("usage_mode") == "adult_mediated" and entry.get("adult_mediation") is not True:
                    fail("adult_mediation_required", f"{sentence_id} 使用 {claim_id} 时必须标记 adult_mediation=true")

    if result["errors"]:
        result["status"] = "blocked"
    return result


def validate_storyboard_science(
    storyboard: dict[str, Any],
    whitelist: dict[str, Any],
) -> dict[str, Any]:
    """Check page-level claim IDs and storyboard science visual contracts."""

    result: dict[str, Any] = {
        "status": "passed",
        "errors": [],
        "warnings": [],
        "error_codes": [],
        "page_count": 0,
    }

    def fail(code: str, message: str) -> None:
        result["errors"].append(_error(code, message))
        if code not in result["error_codes"]:
            result["error_codes"].append(code)

    if not isinstance(storyboard, dict):
        fail("invalid_storyboard", "storyboard 必须是对象")
        result["status"] = "blocked"
        return result
    pages = storyboard.get("pages")
    if not isinstance(pages, list) or not pages:
        fail("missing_storyboard_pages", "storyboard.pages 必须是非空列表")
        pages = []
    consistency = storyboard.get("science_visual_consistency")
    if not isinstance(consistency, dict):
        fail("missing_storyboard_science_review", "缺少 science_visual_consistency")
    else:
        if consistency.get("status") not in {"pending", "passed", "failed"}:
            fail("invalid_storyboard_science_review", "science_visual_consistency.status 无效")
        if not isinstance(consistency.get("checks"), list) or not consistency.get("checks"):
            fail("missing_storyboard_science_review", "science_visual_consistency.checks 不能为空")

    claim_index = whitelist.get("claims", {}) if isinstance(whitelist, dict) else {}
    allowed_ids = {
        item.get("claim_id")
        for item in whitelist.get("allowed_knowledge", [])
        if isinstance(item, dict)
    }
    result["page_count"] = len(pages)
    for index, page in enumerate(pages):
        if not isinstance(page, dict):
            fail("invalid_storyboard_page", f"pages[{index}] 必须是对象")
            continue
        page_number = page.get("page", index + 1)
        claim_ids = page.get("knowledge_claims", [])
        checks = page.get("science_visual_checks", [])
        if not isinstance(claim_ids, list):
            fail("invalid_page_claims", f"第 {page_number} 页 knowledge_claims 必须是列表")
            claim_ids = []
        if not isinstance(checks, list):
            fail("invalid_page_visual_checks", f"第 {page_number} 页 science_visual_checks 必须是列表")
            checks = []
        check_claim_ids = set()
        for check_index, check in enumerate(checks):
            if not isinstance(check, dict):
                fail("invalid_page_visual_check", f"第 {page_number} 页 science_visual_checks[{check_index}] 必须是对象")
                continue
            check_id = check.get("claim_id")
            if check_id is not None:
                check_claim_ids.add(check_id)
            if not isinstance(check.get("required_visual_evidence"), str) or not check["required_visual_evidence"].strip():
                fail("missing_visual_evidence", f"第 {page_number} 页缺少 required_visual_evidence")
            if check.get("status") not in {"pending", "passed", "failed"}:
                fail("invalid_page_visual_check", f"第 {page_number} 页 science_visual_checks.status 无效")
            if check_id is not None and check_id not in claim_ids:
                fail("visual_check_claim_mismatch", f"第 {page_number} 页视觉检查引用的 claim 不在 knowledge_claims: {check_id}")
        for claim_id in claim_ids:
            claim = claim_index.get(claim_id)
            if not claim:
                fail("unknown_claim", f"第 {page_number} 页引用不存在的 claim_id: {claim_id}")
                continue
            if claim.get("status") in {"uncertain", "pending_confirmation", "omit"}:
                fail("forbidden_claim_status", f"第 {page_number} 页使用了禁止状态 {claim.get('status')}: {claim_id}")
            elif claim.get("status") != "inference" and claim_id not in allowed_ids:
                fail("claim_not_in_whitelist", f"第 {page_number} 页 claim 不在 allowed_knowledge: {claim_id}")
            if claim_id not in check_claim_ids:
                fail("missing_visual_check_for_claim", f"第 {page_number} 页缺少 {claim_id} 的 science_visual_check")

    if result["errors"]:
        result["status"] = "blocked"
    return result


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate-packet")
    check.add_argument("packet_dir", type=Path)
    whitelist = sub.add_parser("build-whitelist")
    whitelist.add_argument("packet_dir", type=Path)
    whitelist.add_argument("output", type=Path)
    story = sub.add_parser("validate-story")
    story.add_argument("story", type=Path)
    story.add_argument("trace", type=Path)
    story.add_argument("whitelist", type=Path)
    storyboard = sub.add_parser("validate-storyboard")
    storyboard.add_argument("storyboard", type=Path)
    storyboard.add_argument("whitelist", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_cli_encoding()
    args = _parser().parse_args(argv)
    if args.command == "validate-packet":
        result = validate_research_packet(args.packet_dir)
    elif args.command == "build-whitelist":
        result = build_knowledge_whitelist(args.packet_dir, args.output)
    elif args.command == "validate-story":
        story_text = args.story.read_text(encoding="utf-8")
        trace = json.loads(args.trace.read_text(encoding="utf-8"))
        whitelist = json.loads(args.whitelist.read_text(encoding="utf-8"))
        result = validate_story_claims(story_text, trace, whitelist)
    else:
        storyboard = json.loads(args.storyboard.read_text(encoding="utf-8"))
        whitelist = json.loads(args.whitelist.read_text(encoding="utf-8"))
        result = validate_storyboard_science(storyboard, whitelist)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
