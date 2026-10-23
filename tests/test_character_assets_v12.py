import json
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
ASSET_DIR = SKILL_DIR / "assets" / "characters" / "core-v1.2"
MANIFEST_PATH = ASSET_DIR / "manifest.json"


class CharacterAssetV12Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.assets = cls.manifest["assets"]

    def test_bundle_identity_and_visual_reference(self):
        self.assertEqual(self.manifest["bundle_id"], "core-characters-v1.2")
        self.assertEqual(self.manifest["version"], "v1.2")
        reference = ASSET_DIR / self.manifest["visual_reference"]["path"]
        self.assertTrue(reference.is_file())
        self.assertEqual(self.manifest["visual_reference"]["reference_image"],
                         "reference/core-character-assets-v1.2.png")

    def test_visual_reference_decodes_as_a_large_raster_image(self):
        from PIL import Image

        reference = ASSET_DIR / "reference" / "core-character-assets-v1.2.png"
        with Image.open(reference) as image:
            self.assertGreaterEqual(image.width, 1000)
            self.assertGreaterEqual(image.height, 800)
            image.verify()

    def test_required_characters_and_outfit_ids(self):
        self.assertEqual(
            {c["character_id"] for c in self.manifest["characters"]},
            {"xiaoxiong", "xiaomeng", "mother"},
        )
        outfits = {a["asset_id"] for a in self.assets if a["asset_type"] == "outfit"}
        self.assertEqual({f"G-{i:02d}" for i in range(1, 9)} | {f"B-{i:02d}" for i in range(1, 9)} | {f"M-{i:02d}" for i in range(1, 7)}, outfits)

    def test_required_asset_fields_are_present(self):
        required = {
            "asset_id", "character_id", "asset_type", "description", "usage",
            "compatible_characters", "reference_image", "version",
        }
        for asset in self.assets:
            with self.subTest(asset_id=asset.get("asset_id")):
                self.assertTrue(required <= set(asset))
                self.assertEqual(asset["version"], "v1.2")
                self.assertTrue(asset["reference_image"])

    def test_id_families_and_defaults_are_consistent(self):
        expressions = [a for a in self.assets if a["asset_type"] == "expression"]
        poses = [a for a in self.assets if a["asset_type"] == "pose"]
        angles = [a for a in self.assets if a["asset_type"] == "angle"]
        self.assertEqual(len([a for a in expressions if a["character_id"] == "xiaoxiong"]), 12)
        self.assertEqual(len([a for a in expressions if a["character_id"] == "xiaomeng"]), 12)
        self.assertEqual(len([a for a in expressions if a["character_id"] == "mother"]), 8)
        self.assertEqual(len([a for a in poses if a["character_id"] == "xiaoxiong"]), 12)
        self.assertEqual(len([a for a in poses if a["character_id"] == "xiaomeng"]), 12)
        self.assertEqual(len([a for a in poses if a["character_id"] == "mother"]), 10)
        self.assertEqual(len(angles), 8)
        defaults = {a["asset_id"] for a in self.assets if a.get("is_default")}
        self.assertEqual(defaults, {"G-01", "B-01", "M-01"})

    def test_interaction_assets_are_versioned_and_compatible(self):
        interactions = [a for a in self.assets if a["asset_type"] == "interaction"]
        self.assertGreaterEqual(len(interactions), 14)
        for asset in interactions:
            self.assertIn("xiaoxiong", asset["compatible_characters"] + [asset["character_id"]])
            self.assertEqual(asset["version"], "v1.2")

    def test_skill_and_readme_route_to_the_bundle(self):
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        readme = (ASSET_DIR / "README.md").read_text(encoding="utf-8")
        for text in (skill, readme):
            self.assertIn("core-characters-v1.2", text)
            self.assertIn("80% 固定资产", text)
            self.assertIn("20% 页面变化", text)


if __name__ == "__main__":
    unittest.main()
