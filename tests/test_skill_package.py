import json
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


VERSION = "0.11.0-preview"
PACKAGE_NAME = "make-kids-picturebooks"
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
                self.assertEqual({name.split("/", 1)[0] for name in names}, {PACKAGE_NAME})
                self.assertEqual(sum(name.endswith("/SKILL.md") for name in names), 1)
                self.assertFalse(any(name.startswith("/") or "/../" in f"/{name}" for name in names))
                self.assertNotIn(f"{PACKAGE_NAME}/__pycache__/ignored.pyc", names)
                manifest_name = f"{PACKAGE_NAME}/MANIFEST.json"
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
                self.assertIn(f"{PACKAGE_NAME}/SKILL.md", names)
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
                    f"{PACKAGE_NAME}/scripts/layout_design.py",
                    f"{PACKAGE_NAME}/scripts/preflight_image_generation.py",
                    f"{PACKAGE_NAME}/assets/book-template.json",
                    f"{PACKAGE_NAME}/assets/education-goal-template.json",
                    f"{PACKAGE_NAME}/assets/page-manifest-template.json",
                    f"{PACKAGE_NAME}/references/education-goals.md",
                }
                self.assertTrue(required <= names)
                for optional in (
                    "scripts/layout_styles.py",
                    "scripts/render_social.py",
                    "scripts/render_social_book.py",
                    "references/social-output.md",
                    "references/printing.md",
                ):
                    self.assertNotIn(f"{PACKAGE_NAME}/{optional}", names)
                self.assertFalse(any("/source/" in name or "/exports/" in name for name in names))
                public_core_prefix = f"{PACKAGE_NAME}/assets/characters/core-v1.2/"
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
                self.assertFalse(staged_paths)
                manifest = json.loads(archive.read(f"{PACKAGE_NAME}/MANIFEST.json"))
                self.assertEqual(manifest["version"], VERSION)
                listed = {entry["path"] for entry in manifest["files"]}
                self.assertEqual(listed, names - {f"{PACKAGE_NAME}/MANIFEST.json"})

    def test_runtime_package_excludes_development_and_compatibility_material(self):
        from package_skill import package_skill

        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / f"make-kids-picturebooks-v{VERSION}.zip"
            package_skill(repository, output, VERSION)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())

            forbidden_prefixes = (
                f"{PACKAGE_NAME}/.github/",
                f"{PACKAGE_NAME}/tests/",
                f"{PACKAGE_NAME}/evals/",
                f"{PACKAGE_NAME}/docs/",
                f"{PACKAGE_NAME}/.pytest_cache/",
            )
            self.assertFalse(
                any(name.startswith(prefix) for name in names for prefix in forbidden_prefixes)
            )
            for filename in (
                "README.md",
                "RELEASE.md",
                "ASSET_CONTRACT_HARDENING_REPORT.md",
                "WORKFLOW_GATE_HARDENING_REPORT.md",
                "UNIFIED_WORKFLOW_ENTRY_REPORT.md",
                "scripts/check_eval_results.py",
            ):
                self.assertNotIn(f"{PACKAGE_NAME}/{filename}", names)

            required = {
                f"{PACKAGE_NAME}/SKILL.md",
                f"{PACKAGE_NAME}/agents/openai.yaml",
                f"{PACKAGE_NAME}/scripts/workflow.py",
                f"{PACKAGE_NAME}/references/production-workflow.md",
                f"{PACKAGE_NAME}/assets/education-goal-template.json",
            }
            self.assertTrue(required <= names)

    def test_runtime_package_excludes_project_artifacts(self):
        from package_skill import package_skill

        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / f"make-kids-picturebooks-v{VERSION}.zip"
            package_skill(repository, output, VERSION)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())

            self.assertFalse(
                any(name.startswith(f"{PACKAGE_NAME}/projects/") for name in names)
            )

    def test_runtime_package_excludes_optional_asset_modules(self):
        from package_skill import package_skill

        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / f"make-kids-picturebooks-v{VERSION}.zip"
            package_skill(repository, output, VERSION)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())

        optional_prefixes = (
            f"{PACKAGE_NAME}/assets/characters/core-v1.3/",
            f"{PACKAGE_NAME}/assets/style-06-v0.1/",
        )
        self.assertFalse(
            any(name.startswith(prefix) for name in names for prefix in optional_prefixes)
        )
        for filename in (
            "assets/kidsbook-print.ttf",
            "assets/font-license.txt",
            "assets/font-provenance.json",
        ):
            self.assertNotIn(f"{PACKAGE_NAME}/{filename}", names)

        required_default_assets = {
            f"{PACKAGE_NAME}/assets/characters/core-v1.2/manifest.json",
            f"{PACKAGE_NAME}/assets/characters/core-v1.2/manifest-receipt.json",
            f"{PACKAGE_NAME}/assets/style-registry.json",
        }
        self.assertTrue(required_default_assets <= names)

    def test_complete_download_bundle_keeps_optional_modules_without_projects(self):
        from package_skill import package_download_bundle

        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / f"make-kids-picturebooks-complete-v{VERSION}.zip"
            package_download_bundle(repository, [], output, VERSION)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())

        self.assertIn(
            f"{PACKAGE_NAME}/assets/characters/core-v1.3/manifest.json",
            names,
        )
        self.assertIn(f"{PACKAGE_NAME}/assets/style-06-v0.1/manifest.json", names)
        self.assertIn(f"{PACKAGE_NAME}/assets/kidsbook-print.ttf", names)
        self.assertIn(f"{PACKAGE_NAME}/scripts/render_social_book.py", names)
        self.assertIn(f"{PACKAGE_NAME}/scripts/render_book.py", names)
        self.assertIn(f"{PACKAGE_NAME}/scripts/diagnose_project_paths.py", names)
        self.assertIn(f"{PACKAGE_NAME}/references/social-output.md", names)
        self.assertIn(f"{PACKAGE_NAME}/references/printing.md", names)
        self.assertIn(f"{PACKAGE_NAME}/requirements.txt", names)
        self.assertFalse(any(name.startswith(f"{PACKAGE_NAME}/projects/") for name in names))

    def test_runtime_package_excludes_optional_code_and_dependency_modules(self):
        from package_skill import package_skill

        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / f"make-kids-picturebooks-v{VERSION}.zip"
            package_skill(repository, output, VERSION)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())

        for optional in (
            "scripts/accept_book.py",
            "scripts/accept_social_book.py",
            "scripts/diagnose_project_paths.py",
            "scripts/export_book.py",
            "scripts/impose_booklet.py",
            "scripts/incremental_archive.py",
            "scripts/layout_styles.py",
            "scripts/migrate_social_only_layout.py",
            "scripts/package_project.py",
            "scripts/package_skill.py",
            "scripts/prepare_font.py",
            "scripts/production_metrics.py",
            "scripts/project_state.py",
            "scripts/render_book.py",
            "scripts/render_social.py",
            "scripts/render_social_book.py",
            "scripts/validate_exports.py",
            "references/printing.md",
            "references/social-output.md",
            "requirements.txt",
            "requirements-optional.txt",
        ):
            self.assertNotIn(f"{PACKAGE_NAME}/{optional}", names)
        self.assertIn(f"{PACKAGE_NAME}/requirements-core.txt", names)

    def test_full_dependency_manifest_composes_core_and_optional_requirements(self):
        repository = Path(__file__).resolve().parents[1]
        requirements = (repository / "requirements.txt").read_text(encoding="utf-8")

        self.assertIn("-r requirements-core.txt", requirements)
        self.assertIn("-r requirements-optional.txt", requirements)

    def test_checked_in_manifest_matches_generated_runtime_manifest(self):
        from package_skill import package_skill

        repository = Path(__file__).resolve().parents[1]
        checked_in = json.loads((repository / "MANIFEST.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / f"make-kids-picturebooks-v{VERSION}.zip"
            package_skill(repository, output, VERSION)
            with zipfile.ZipFile(output) as archive:
                generated = json.loads(
                    archive.read(f"{PACKAGE_NAME}/MANIFEST.json")
                )

        self.assertEqual(checked_in, generated)

    def test_checked_in_manifest_has_no_removed_runtime_paths(self):
        repository = Path(__file__).resolve().parents[1]
        manifest = json.loads((repository / "MANIFEST.json").read_text(encoding="utf-8"))
        paths = {entry["path"] for entry in manifest["files"]}

        for prefix in (
            f"{PACKAGE_NAME}/.github/",
            f"{PACKAGE_NAME}/tests/",
            f"{PACKAGE_NAME}/evals/",
            f"{PACKAGE_NAME}/docs/",
            f"{PACKAGE_NAME}/.pytest_cache/",
        ):
            self.assertFalse(any(path.startswith(prefix) for path in paths))
        for filename in (
            "README.md",
            "RELEASE.md",
            "ASSET_CONTRACT_HARDENING_REPORT.md",
            "WORKFLOW_GATE_HARDENING_REPORT.md",
            "UNIFIED_WORKFLOW_ENTRY_REPORT.md",
            "scripts/check_eval_results.py",
            "references/adaptation.md",
            "references/age-bands.md",
            "references/art-direction.md",
            "references/topic-selection.md",
        ):
            self.assertNotIn(f"{PACKAGE_NAME}/{filename}", paths)

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
