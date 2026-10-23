import json
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


VERSION = "0.11.0-preview"
APPROVED_CORE_RECEIPT_SHA256 = "e3b22df86aa1989660895c39061690468dd6663955a576a7772001ea7a337659"
APPROVED_CORE_MANIFEST_SHA256 = "cbb4669d776e8fc1fcc2eb47ce798ead237885f599321f7366205dfd0747f30b"
APPROVED_CORE_REFERENCE_SHA256 = "fb16e77d104bc8fb328dab096c4bd83c04245c5310a18a4b6efee404e438af07"


class SkillPackageTests(unittest.TestCase):
    def make_skill(self, root: Path) -> Path:
        skill = root / "make-kids-picturebooks"
        (skill / "assets").mkdir(parents=True)
        (skill / "agents").mkdir()
        (skill / "SKILL.md").write_text("# test skill\n", encoding="utf-8")
        (skill / "assets" / "icon.svg").write_text("<svg/>", encoding="utf-8")
        (skill / "agents" / "openai.yaml").write_text("interface: {}\n", encoding="utf-8")
        (skill / "__pycache__").mkdir()
        (skill / "__pycache__" / "ignored.pyc").write_bytes(b"ignored")
        return skill

    def test_skill_zip_has_one_top_level_directory_and_manifest_hashes(self):
        from package_skill import package_skill

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = self.make_skill(root)
            output = root / "dist" / f"make-kids-picturebooks-v{VERSION}.zip"

            result = package_skill(skill, output, VERSION)

            self.assertEqual(result["version"], VERSION)
            self.assertTrue(output.is_file())
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                self.assertTrue(names)
                self.assertEqual({name.split("/", 1)[0] for name in names}, {skill.name})
                self.assertEqual(sum(name.endswith("/SKILL.md") for name in names), 1)
                self.assertFalse(any(name.startswith("/") or "/../" in f"/{name}" for name in names))
                self.assertNotIn(f"{skill.name}/__pycache__/ignored.pyc", names)
                manifest_name = f"{skill.name}/MANIFEST.json"
                manifest = json.loads(archive.read(manifest_name))
                self.assertEqual(manifest["version"], VERSION)
                listed = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
                self.assertEqual(set(listed), set(names) - {manifest_name})
                for path, digest in listed.items():
                    import hashlib

                    self.assertEqual(hashlib.sha256(archive.read(path)).hexdigest(), digest)

            with self.assertRaises(FileExistsError):
                package_skill(skill, output, VERSION)

    def test_skill_package_rejects_output_inside_skill_directory(self):
        from package_skill import package_skill

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = self.make_skill(root)
            with self.assertRaises(ValueError):
                package_skill(skill, skill / "release.zip", VERSION)

    def test_download_bundle_allows_documented_auxiliary_files(self):
        from package_skill import package_download_bundle

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = self.make_skill(root)
            install = root / "安装说明.txt"
            checksums = root / "文件校验清单.json"
            install.write_text("install", encoding="utf-8")
            checksums.write_text("{}", encoding="utf-8")
            output = root / "dist" / f"宝宝知识绘本_完整下载包-v{VERSION}.zip"

            package_download_bundle(skill, [install, checksums], output, VERSION)

            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn("安装说明.txt", names)
                self.assertIn("文件校验清单.json", names)
                self.assertIn(f"{skill.name}/SKILL.md", names)
                self.assertNotIn("__pycache__/ignored.pyc", names)

            with self.assertRaises(FileExistsError):
                package_download_bundle(skill, [install, checksums], output, VERSION)

    def test_skill_release_metadata_uses_one_preview_version(self):
        repository = Path(__file__).resolve().parents[1]
        readme = (repository / "README.md").read_text(encoding="utf-8")
        release = (repository / "RELEASE.md").read_text(encoding="utf-8")
        workflow = (repository / ".github" / "workflows" / "picturebook-skill.yml").read_text(encoding="utf-8")

        self.assertIn(f"v{VERSION}", readme)
        self.assertIn(f"make-kids-picturebooks-v{VERSION}.zip", readme)
        self.assertIn(f"v{VERSION}", release)
        self.assertIn(f"# make kids picturebooks {VERSION}", release)
        self.assertIn(f"make-kids-picturebooks-v{VERSION}.zip", release)
        self.assertIn(f"make-kids-picturebooks-v{VERSION}.zip", workflow)
        self.assertIn(f"--version {VERSION}", workflow)
        self.assertIn(f"m['version']=='{VERSION}'", workflow)
        for stale in ("0.9.1", "0.9.2", "0.10.0-preview"):
            self.assertNotIn(stale, readme)
            self.assertNotIn(stale, release)
            self.assertNotIn(stale, workflow)

    def test_repository_package_contains_layout_surface_without_user_assets(self):
        from package_skill import package_skill

        repository = Path(__file__).resolve().parents[1]
        skill = repository
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / f"make-kids-picturebooks-v{VERSION}.zip"
            package_skill(skill, output, VERSION)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                required = {
                    f"{skill.name}/scripts/layout_design.py",
                    f"{skill.name}/scripts/layout_styles.py",
                    f"{skill.name}/scripts/render_social.py",
                    f"{skill.name}/scripts/preflight_image_generation.py",
                    f"{skill.name}/assets/book-template.json",
                    f"{skill.name}/assets/education-goal-template.json",
                    f"{skill.name}/assets/page-manifest-template.json",
                    f"{skill.name}/references/education-goals.md",
                    f"{skill.name}/references/social-output.md",
                }
                self.assertTrue(required <= names)
                self.assertFalse(any("/source/" in name or "/exports/" in name for name in names))
                public_core_prefix = f"{skill.name}/assets/characters/core-v1.2/"
                character_paths = [
                    name for name in names if f"/assets/characters/core-v1.2/" in name
                ]
                self.assertTrue(character_paths)
                receipt_path = f"{public_core_prefix}manifest-receipt.json"
                receipt = json.loads(archive.read(receipt_path))
                canonical_receipt = json.dumps(
                    {key: value for key, value in receipt.items() if key != "receipt_sha256"},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                self.assertTrue(receipt["immutable"])
                self.assertEqual(receipt["receipt_sha256"], APPROVED_CORE_RECEIPT_SHA256)
                self.assertEqual(hashlib.sha256(canonical_receipt).hexdigest(), APPROVED_CORE_RECEIPT_SHA256)
                self.assertEqual(receipt["manifest_sha256"], APPROVED_CORE_MANIFEST_SHA256)
                self.assertEqual(receipt["reference_sha256"], APPROVED_CORE_REFERENCE_SHA256)
                approved_paths = {f"{public_core_prefix}{path}" for path in receipt["files"]} | {receipt_path}
                self.assertEqual(set(character_paths), approved_paths)
                core_manifest = json.loads(archive.read(f"{public_core_prefix}manifest.json"))
                self.assertEqual(core_manifest["bundle_id"], "core-characters-v1.2")
                self.assertEqual(core_manifest["version"], "v1.2")
                self.assertEqual(core_manifest["status"], "approved-reference")
                self.assertTrue(core_manifest["visual_reference"]["do_not_redesign"])
                self.assertIn("immutable", core_manifest["usage_contract"]["version_rule"])
                for relative, digest in receipt["files"].items():
                    self.assertEqual(hashlib.sha256(archive.read(f"{public_core_prefix}{relative}")).hexdigest(), digest)
                staged_paths = [
                    name for name in names if f"/assets/characters/core-v1.3/" in name
                ]
                self.assertTrue(staged_paths)
                manifest = json.loads(archive.read(f"{skill.name}/MANIFEST.json"))
                self.assertEqual(manifest["version"], VERSION)
                listed = {entry["path"] for entry in manifest["files"]}
                self.assertEqual(listed, names - {f"{skill.name}/MANIFEST.json"})

    def test_aesthetic_layout_fixture_is_multi_page_multi_style_and_social_ready(self):
        repository = Path(__file__).resolve().parents[1]
        fixture = repository / "tests" / "fixtures" / "aesthetic-layout"
        layout = json.loads((fixture / "layout.json").read_text(encoding="utf-8"))

        self.assertGreaterEqual(len(layout["pages"]), 4)
        self.assertGreaterEqual({page["layout_design"]["layout_mode"] for page in layout["pages"]}.__len__(), 2)
        self.assertTrue(any(any("\u4e00" <= char <= "\u9fff" for char in page["text"]) for page in layout["pages"]))
        for page in layout["pages"]:
            self.assertTrue((fixture / page["image"]).is_file())
            self.assertEqual(page["layout_design"]["social_layout"]["canvas"], {"width_px": 1080, "height_px": 1920})
        social_pages = sorted((fixture / "social").glob("page-*.png"))
        self.assertGreaterEqual(len(social_pages), 4)
        from PIL import Image

        for path in social_pages:
            with Image.open(path) as image:
                self.assertEqual(image.size, (1080, 1920))


if __name__ == "__main__":
    unittest.main()
