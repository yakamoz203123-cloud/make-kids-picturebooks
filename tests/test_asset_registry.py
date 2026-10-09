import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from asset_registry import collect_declared_assets


class AssetRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self._write("sources/reading.txt", "registered source")
        self._write("sources/private-not-declared.txt", "must not collect")
        self._write("characters/v1/hero.png", "character reference")
        self._write("artifacts/story.txt", "story")
        self._write("artifacts/concept.json", "{}")
        self._write("artifacts/layout.json", json.dumps({
            "font_path": "fonts/book.ttf",
            "font_license_path": "fonts/license.txt",
            "font_provenance_path": "fonts/provenance.json",
        }))
        self._write("artifacts/review.json", json.dumps({
            "reading_pages": [{"image_path": "artifacts/renders/reading-01.png"}],
            "print_sides": [{"image_path": "artifacts/renders/print-01.png"}],
        }))
        self._write("artifacts/renders/reading-01.png", "reading render")
        self._write("artifacts/renders/print-01.png", "print render")
        self._write("artifacts/fonts/book.ttf", "font")
        self._write("artifacts/fonts/license.txt", "license")
        self._write("artifacts/fonts/provenance.json", "provenance")
        self.project_path = self.root / "project.json"
        self.project = {
            "source": {"path": "sources/reading.txt"},
            "characters_path": "characters/v1",
        }
        self.book = {
            "artifacts": {
                "concept": "artifacts/concept.json",
                "story": "artifacts/story.txt",
                "layout": "artifacts/layout.json",
                "review": "artifacts/review.json",
            }
        }

    def tearDown(self):
        self.temp.cleanup()

    def _write(self, relative, contents):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def test_collects_explicit_source_but_not_unrelated_source_sibling(self):
        assets = collect_declared_assets(self.project_path, self.project, self.book)

        self.assertIn("sources/reading.txt", assets)
        self.assertNotIn("sources/private-not-declared.txt", assets)

    def test_collects_declared_artifacts_review_renders_and_font_evidence(self):
        assets = collect_declared_assets(self.project_path, self.project, self.book)

        self.assertTrue({
            "artifacts/concept.json",
            "artifacts/story.txt",
            "artifacts/layout.json",
            "artifacts/review.json",
            "artifacts/renders/reading-01.png",
            "artifacts/renders/print-01.png",
            "artifacts/fonts/book.ttf",
            "artifacts/fonts/license.txt",
            "artifacts/fonts/provenance.json",
            "characters/v1/hero.png",
        }.issubset(assets))

    def test_rejects_project_outside_declared_asset(self):
        self.book["artifacts"]["story"] = "../outside.txt"

        with self.assertRaises(ValueError):
            collect_declared_assets(self.project_path, self.project, self.book)

    def test_rejects_source_directory_as_character_reference_directory(self):
        self.project["characters_path"] = "sources"

        with self.assertRaisesRegex(ValueError, "角色参考目录"):
            collect_declared_assets(self.project_path, self.project, self.book)

    def test_rejects_missing_font_evidence(self):
        layout_path = self.root / "artifacts/layout.json"
        for field in ("font_path", "font_license_path", "font_provenance_path"):
            with self.subTest(field=field):
                layout = json.loads(layout_path.read_text(encoding="utf-8"))
                del layout[field]
                layout_path.write_text(json.dumps(layout), encoding="utf-8")

                with self.assertRaisesRegex(ValueError, "缺少"):
                    collect_declared_assets(self.project_path, self.project, self.book)

                layout_path.write_text(json.dumps({
                    "font_path": "fonts/book.ttf",
                    "font_license_path": "fonts/license.txt",
                    "font_provenance_path": "fonts/provenance.json",
                }), encoding="utf-8")

    def test_returns_posix_relative_paths_for_windows_separators(self):
        self.book["artifacts"]["story"] = "artifacts\\story.txt"

        assets = collect_declared_assets(self.project_path, self.project, self.book)

        self.assertIn("artifacts/story.txt", assets)
        self.assertTrue(all("\\" not in path for path in assets))


if __name__ == "__main__":
    unittest.main()
