import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from content_gate import (  # noqa: E402
    build_knowledge_whitelist,
    configure_cli_encoding,
    validate_research_packet,
    validate_story_claims,
    validate_storyboard_science,
)


class _ReconfigurableStream:
    def __init__(self):
        self.calls = []

    def reconfigure(self, **kwargs):
        self.calls.append(kwargs)


class _PlainStream:
    pass


def write_packet(root: Path, *, packet_id="demo-3-4", age_band="3-4") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "research_packet.md").write_text(
        f"# Research Packet: 小种子\n\n- packet_id: {packet_id}\n- topic: 小种子\n- age_band: {age_band}\n",
        encoding="utf-8",
    )
    (root / "sources.json").write_text(
        json.dumps(
            {
                "packet_id": packet_id,
                "age_band": age_band,
                "sources": [
                    {
                        "source_id": "source-01",
                        "title": "示例来源",
                        "url": "https://example.com/source",
                        "supports_claim_ids": ["claim-fact"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "claims.json").write_text(
        json.dumps(
            {
                "packet_id": packet_id,
                "age_band": age_band,
                "claims": [
                    {
                        "claim_id": "claim-fact",
                        "statement": "种子吸水后会发生变化。",
                        "status": "fact",
                        "age_band": age_band,
                        "age_fit": "include",
                        "source_ids": ["source-01"],
                    },
                    {
                        "claim_id": "claim-inference",
                        "statement": "可以先让孩子观察变化。",
                        "status": "inference",
                        "age_band": age_band,
                        "age_fit": "borderline",
                        "source_ids": ["source-01"],
                    },
                    {
                        "claim_id": "claim-uncertain",
                        "statement": "一定三天发芽。",
                        "status": "uncertain",
                        "age_band": age_band,
                        "age_fit": "omit",
                        "source_ids": ["source-01"],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "child_concepts.json").write_text(
        json.dumps(
            {
                "packet_id": packet_id,
                "age_band": age_band,
                "concepts": [
                    {
                        "concept_id": "concept-01",
                        "label": "种子变化",
                        "age_band": age_band,
                        "linked_claim_ids": ["claim-fact"],
                        "suitability": {
                            "outcome": "include",
                            "adult_mediation_required": False,
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return root


class ResearchPacketGateTests(unittest.TestCase):
    def test_configure_cli_encoding_requests_utf8_when_stream_supports_it(self):
        stdout = _ReconfigurableStream()
        stderr = _ReconfigurableStream()
        with patch("content_gate.sys.stdout", stdout), patch("content_gate.sys.stderr", stderr):
            configure_cli_encoding()

        self.assertEqual(
            [{"encoding": "utf-8", "errors": "backslashreplace"}],
            stdout.calls,
        )
        self.assertEqual(
            [{"encoding": "utf-8", "errors": "backslashreplace"}],
            stderr.calls,
        )

    def test_configure_cli_encoding_ignores_stream_without_reconfigure(self):
        with patch("content_gate.sys.stdout", _PlainStream()), patch(
            "content_gate.sys.stderr", _PlainStream()
        ):
            configure_cli_encoding()

    def test_valid_packet_passes_and_is_traceable(self):
        with tempfile.TemporaryDirectory() as td:
            report = validate_research_packet(write_packet(Path(td) / "packet"))

        self.assertEqual("passed", report["status"])
        self.assertEqual("demo-3-4", report["metadata"]["packet_id"])
        self.assertEqual([], report["errors"])

    def test_missing_required_file_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            packet = write_packet(Path(td) / "packet")
            (packet / "claims.json").unlink()
            report = validate_research_packet(packet)

        self.assertEqual("blocked", report["status"])
        self.assertTrue(any("claims.json" in error for error in report["errors"]))

    def test_malformed_json_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            packet = write_packet(Path(td) / "packet")
            (packet / "claims.json").write_text("{not-json", encoding="utf-8")
            report = validate_research_packet(packet)

        self.assertEqual("blocked", report["status"])
        self.assertTrue(any("JSON" in error for error in report["errors"]))

    def test_packet_identity_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            packet = write_packet(Path(td) / "packet")
            claims = json.loads((packet / "claims.json").read_text(encoding="utf-8"))
            claims["packet_id"] = "other-packet"
            (packet / "claims.json").write_text(
                json.dumps(claims, ensure_ascii=False), encoding="utf-8"
            )
            report = validate_research_packet(packet)

        self.assertEqual("blocked", report["status"])
        self.assertTrue(any("packet_id" in error for error in report["errors"]))

    def test_age_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            packet = write_packet(Path(td) / "packet")
            concepts = json.loads(
                (packet / "child_concepts.json").read_text(encoding="utf-8")
            )
            concepts["age_band"] = "5-7"
            (packet / "child_concepts.json").write_text(
                json.dumps(concepts, ensure_ascii=False), encoding="utf-8"
            )
            report = validate_research_packet(packet)

        self.assertEqual("blocked", report["status"])
        self.assertTrue(any("age_band" in error for error in report["errors"]))

    def test_invalid_source_reference_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            packet = write_packet(Path(td) / "packet")
            claims = json.loads((packet / "claims.json").read_text(encoding="utf-8"))
            claims["claims"][0]["source_ids"] = ["source-missing"]
            (packet / "claims.json").write_text(
                json.dumps(claims, ensure_ascii=False), encoding="utf-8"
            )
            report = validate_research_packet(packet)

        self.assertEqual("blocked", report["status"])
        self.assertTrue(any("source-missing" in error for error in report["errors"]))

    def test_missing_claims_and_concepts_block(self):
        with tempfile.TemporaryDirectory() as td:
            packet = write_packet(Path(td) / "packet")
            claims = json.loads((packet / "claims.json").read_text(encoding="utf-8"))
            claims["claims"] = []
            (packet / "claims.json").write_text(
                json.dumps(claims, ensure_ascii=False), encoding="utf-8"
            )
            concepts = json.loads(
                (packet / "child_concepts.json").read_text(encoding="utf-8")
            )
            concepts["concepts"] = []
            (packet / "child_concepts.json").write_text(
                json.dumps(concepts, ensure_ascii=False), encoding="utf-8"
            )
            report = validate_research_packet(packet)

        self.assertEqual("blocked", report["status"])
        self.assertTrue(any("claims" in error for error in report["errors"]))
        self.assertTrue(any("concept" in error for error in report["errors"]))


class KnowledgeWhitelistTests(unittest.TestCase):
    def test_only_allowed_fact_enters_whitelist(self):
        with tempfile.TemporaryDirectory() as td:
            whitelist = build_knowledge_whitelist(write_packet(Path(td) / "packet"))

        self.assertEqual("passed", whitelist["status"])
        allowed_ids = {item["claim_id"] for item in whitelist["allowed_knowledge"]}
        self.assertEqual({"claim-fact"}, allowed_ids)
        self.assertIn("claim-inference", whitelist["restricted_knowledge"])
        self.assertIn("claim-uncertain", whitelist["blocked_knowledge"])


class StoryClaimTraceTests(unittest.TestCase):
    def _whitelist(self, td: str):
        return build_knowledge_whitelist(write_packet(Path(td) / "packet"))

    def test_allowed_scientific_sentence_passes(self):
        with tempfile.TemporaryDirectory() as td:
            whitelist = self._whitelist(td)
            report = validate_story_claims(
                "小熊说：种子吸水后会发生变化。",
                [
                    {
                        "sentence_id": "s1",
                        "text": "种子吸水后会发生变化。",
                        "kind": "scientific_claim",
                        "claim_ids": ["claim-fact"],
                        "claim_statement": "种子吸水后会发生变化。",
                    }
                ],
                whitelist,
            )

        self.assertEqual("passed", report["status"])
        self.assertEqual([], report["errors"])

    def test_unbound_scientific_sentence_fails(self):
        with tempfile.TemporaryDirectory() as td:
            report = validate_story_claims(
                "种子一定三天发芽。",
                [
                    {
                        "sentence_id": "s1",
                        "text": "种子一定三天发芽。",
                        "kind": "scientific_claim",
                        "claim_ids": [],
                    }
                ],
                self._whitelist(td),
            )

        self.assertEqual("blocked", report["status"])
        self.assertIn("unverified_scientific_claim", report["error_codes"])

    def test_uncertain_claim_cannot_be_used_as_fact(self):
        with tempfile.TemporaryDirectory() as td:
            report = validate_story_claims(
                "种子一定三天发芽。",
                [
                    {
                        "sentence_id": "s1",
                        "text": "种子一定三天发芽。",
                        "kind": "scientific_claim",
                        "claim_ids": ["claim-uncertain"],
                    }
                ],
                self._whitelist(td),
            )

        self.assertEqual("blocked", report["status"])
        self.assertIn("forbidden_claim_status", report["error_codes"])

    def test_inference_must_remain_inference(self):
        with tempfile.TemporaryDirectory() as td:
            report = validate_story_claims(
                "我们可以先观察种子。",
                [
                    {
                        "sentence_id": "s1",
                        "text": "我们可以先观察种子。",
                        "kind": "scientific_claim",
                        "claim_ids": ["claim-inference"],
                    }
                ],
                self._whitelist(td),
            )

        self.assertEqual("blocked", report["status"])
        self.assertIn("inference_promoted_to_fact", report["error_codes"])

    def test_wrong_claim_binding_fails(self):
        with tempfile.TemporaryDirectory() as td:
            report = validate_story_claims(
                "种子吸水后会发生变化。",
                [
                    {
                        "sentence_id": "s1",
                        "text": "种子吸水后会发生变化。",
                        "kind": "scientific_claim",
                        "claim_ids": ["claim-fact"],
                        "claim_statement": "这是另一条科学结论。",
                    }
                ],
                self._whitelist(td),
            )

        self.assertEqual("blocked", report["status"])
        self.assertIn("claim_binding_mismatch", report["error_codes"])

    def test_fictional_sentence_does_not_need_scientific_claim(self):
        with tempfile.TemporaryDirectory() as td:
            report = validate_story_claims(
                "小熊给种子唱了一首摇篮曲。",
                [
                    {
                        "sentence_id": "s1",
                        "text": "小熊给种子唱了一首摇篮曲。",
                        "kind": "fictional_story",
                        "claim_ids": [],
                    }
                ],
                self._whitelist(td),
            )

        self.assertEqual("passed", report["status"])

    def test_dialogue_marked_scientific_requires_trace(self):
        with tempfile.TemporaryDirectory() as td:
            report = validate_story_claims(
                "小猛说：洗手有用。",
                [
                    {
                        "sentence_id": "s1",
                        "text": "洗手有用。",
                        "kind": "dialogue",
                        "scientific": True,
                        "claim_ids": [],
                    }
                ],
                self._whitelist(td),
            )

        self.assertEqual("blocked", report["status"])
        self.assertIn("unverified_scientific_claim", report["error_codes"])


class StoryboardScienceTests(unittest.TestCase):
    def _whitelist(self, td: str):
        return build_knowledge_whitelist(write_packet(Path(td) / "packet"))

    def test_storyboard_science_checks_pass(self):
        with tempfile.TemporaryDirectory() as td:
            report = validate_storyboard_science(
                {
                    "pages": [
                        {
                            "page": 1,
                            "knowledge_claims": ["claim-fact"],
                            "science_visual_checks": [
                                {
                                    "claim_id": "claim-fact",
                                    "required_visual_evidence": "种子变大",
                                    "status": "pending",
                                }
                            ],
                        }
                    ],
                    "science_visual_consistency": {
                        "status": "pending",
                        "checks": ["前后状态连续"],
                    },
                },
                self._whitelist(td),
            )

        self.assertEqual("passed", report["status"])

    def test_storyboard_rejects_blocked_claim(self):
        with tempfile.TemporaryDirectory() as td:
            report = validate_storyboard_science(
                {
                    "pages": [
                        {
                            "page": 1,
                            "knowledge_claims": ["claim-uncertain"],
                            "science_visual_checks": [
                                {
                                    "claim_id": "claim-uncertain",
                                    "required_visual_evidence": "固定三天",
                                    "status": "pending",
                                }
                            ],
                        }
                    ],
                    "science_visual_consistency": {
                        "status": "pending",
                        "checks": ["不把未确认内容画成事实"],
                    },
                },
                self._whitelist(td),
            )

        self.assertEqual("blocked", report["status"])
        self.assertIn("forbidden_claim_status", report["error_codes"])


if __name__ == "__main__":
    unittest.main()
