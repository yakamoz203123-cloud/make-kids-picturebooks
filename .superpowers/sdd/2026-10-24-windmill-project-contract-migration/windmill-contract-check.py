from __future__ import annotations

import json
from pathlib import Path


PROJECT = Path(r"D:\宝宝绘本制作\projects\windmill-3-4-v1")
BOOK = PROJECT / "books" / "b01" / "v1"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    project = read_json(PROJECT / "project.json")
    manifest = read_json(BOOK / "content" / "page-manifest.json")
    assert project.get("project_profile") == "production-ready", "project_profile is not explicit"
    assert manifest.get("research_packet_path") == "../../../research"
    assert manifest.get("knowledge_whitelist_path") == "../review/knowledge-whitelist.json"
    assert manifest.get("story_claim_trace_path") == "../review/story-claim-trace.json"
    consistency = manifest.get("science_visual_consistency")
    assert isinstance(consistency, dict), "science_visual_consistency is missing"
    assert consistency.get("status") in {"pending", "passed"}
    assert consistency.get("checks"), "science_visual_consistency.checks is empty"
    print("windmill project contract: passed")


if __name__ == "__main__":
    main()
