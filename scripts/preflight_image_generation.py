"""Verify that a generated probe image is native to the selected social profile."""

import argparse
import json
from pathlib import Path

from PIL import Image

from layout_design import (
    DEFAULT_SOCIAL_PROFILE,
    get_social_profile,
    image_matches_aspect_ratio,
)


def preflight_image_generation(
    image_path: str | Path,
    profile: str = DEFAULT_SOCIAL_PROFILE,
) -> dict:
    """Return a passed probe record or raise a blocking validation error.

    The probe must be an actual image returned by the configured generator.
    This check intentionally does not resize, crop, pad, or otherwise repair it.
    """
    profile_config = get_social_profile(profile)
    if profile_config is None:
        raise ValueError(f"image_generation_blocked: 不支持的社媒profile: {profile}")

    probe_path = Path(image_path)
    if not probe_path.is_file():
        raise ValueError(f"image_generation_blocked: 预检源图不存在: {probe_path}")

    try:
        with Image.open(probe_path) as probe:
            probe.load()
            width, height = probe.size
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"image_generation_blocked: 预检源图无法读取: {probe_path}"
        ) from exc

    expected_aspect_ratio = profile_config["source_aspect_ratio"]
    result = {
        "status": "passed",
        "profile": profile,
        "expected_aspect_ratio": expected_aspect_ratio,
        "actual_size": [width, height],
        "probe_path": str(probe_path),
    }
    if not image_matches_aspect_ratio(width, height, expected_aspect_ratio):
        raise ValueError(
            "image_generation_blocked: "
            f"{profile}预检源图实际尺寸为{width}×{height}，"
            f"目标必须是原生{expected_aspect_ratio}；"
            "不能缩放、中心裁切或补白后继续排版"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_path", type=Path)
    parser.add_argument("--profile", default=DEFAULT_SOCIAL_PROFILE)
    args = parser.parse_args()
    try:
        result = preflight_image_generation(args.image_path, args.profile)
    except ValueError as exc:
        print(
            json.dumps(
                {"status": "blocked", "error": str(exc)},
                ensure_ascii=False,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
