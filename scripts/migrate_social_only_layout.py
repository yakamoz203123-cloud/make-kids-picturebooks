"""Migrate an existing layout record to the current Xiaohongshu-only contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROFILE = "xiaohongshu-feed-3x4"
CANVAS = {"width_px": 1080, "height_px": 1440}
DEFAULT_TEXT_SAFE_AREA = [0.56, 0.06, 0.38, 0.34]


def migrate_layout(source_path, destination_path):
    source_path = Path(source_path)
    destination_path = Path(destination_path)
    if destination_path.exists():
        raise FileExistsError(destination_path)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("pages"), list):
        raise ValueError("版面文件必须包含pages数组")

    data["output_mode"] = "social-only"
    for page in data["pages"]:
        if not isinstance(page, dict) or not isinstance(page.get("layout_design"), dict):
            raise ValueError("每页必须包含layout_design")
        design = page["layout_design"]
        design["layout_mode"] = "scene-integrated"
        design["text_treatment"] = "natural-space"
        social = design.setdefault("social_layout", {})
        social["profile"] = PROFILE
        social["canvas"] = dict(CANVAS)
        social["composition_mode"] = "portrait-full-bleed"
        social["text_placement"] = "in-scene"
        social["source_aspect_ratio"] = "3:4"
        social.setdefault("text_safe_area", list(DEFAULT_TEXT_SAFE_AREA))
        if social["text_safe_area"] == [0.08, 0.76, 0.84, 0.14]:
            social["text_safe_area"] = list(DEFAULT_TEXT_SAFE_AREA)
        social.setdefault("subject_safe_area", [0.04, 0.45, 0.92, 0.5])
        social.setdefault("avoid_regions", ["top-ui", "bottom-ui"])
        social["status"] = "passed"
        page.setdefault("social_font_size", 36)

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destination_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_layout", type=Path)
    parser.add_argument("destination_layout", type=Path)
    args = parser.parse_args(argv)
    print(migrate_layout(args.source_layout, args.destination_layout))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
