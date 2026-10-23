import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from preflight_image_generation import preflight_image_generation


class ImageGenerationPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_accepts_native_xiaohongshu_probe(self):
        probe = self.root / "probe-3x4.png"
        Image.new("RGB", (768, 1024), "white").save(probe)

        result = preflight_image_generation(probe)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["profile"], "xiaohongshu-feed-3x4")
        self.assertEqual(result["actual_size"], [768, 1024])
        self.assertEqual(result["expected_aspect_ratio"], "3:4")

    def test_blocks_fixed_landscape_generator_output(self):
        probe = self.root / "probe-landscape.png"
        Image.new("RGB", (1280, 720), "white").save(probe)

        with self.assertRaisesRegex(
            ValueError,
            "image_generation_blocked.*1280×720.*不能缩放、中心裁切或补白",
        ):
            preflight_image_generation(probe)

    def test_supports_explicit_legacy_9x16_probe(self):
        probe = self.root / "probe-9x16.png"
        Image.new("RGB", (900, 1600), "white").save(probe)

        result = preflight_image_generation(probe, "social-vertical-9x16")

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["profile"], "social-vertical-9x16")
        self.assertEqual(result["expected_aspect_ratio"], "9:16")


if __name__ == "__main__":
    unittest.main()
