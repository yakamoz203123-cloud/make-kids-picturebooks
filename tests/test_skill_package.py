import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


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
            output = root / "dist" / "make-kids-picturebooks-v0.9.1.zip"

            result = package_skill(skill, output, "0.9.1")

            self.assertEqual(result["version"], "0.9.1")
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
                self.assertEqual(manifest["version"], "0.9.1")
                listed = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
                self.assertEqual(set(listed), set(names) - {manifest_name})
                for path, digest in listed.items():
                    import hashlib

                    self.assertEqual(hashlib.sha256(archive.read(path)).hexdigest(), digest)

            with self.assertRaises(FileExistsError):
                package_skill(skill, output, "0.9.1")

    def test_skill_package_rejects_output_inside_skill_directory(self):
        from package_skill import package_skill

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = self.make_skill(root)
            with self.assertRaises(ValueError):
                package_skill(skill, skill / "release.zip", "0.9.1")

    def test_download_bundle_allows_documented_auxiliary_files(self):
        from package_skill import package_download_bundle

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = self.make_skill(root)
            install = root / "安装说明.txt"
            checksums = root / "文件校验清单.json"
            install.write_text("install", encoding="utf-8")
            checksums.write_text("{}", encoding="utf-8")
            output = root / "dist" / "宝宝知识绘本_完整下载包-v0.9.1.zip"

            package_download_bundle(skill, [install, checksums], output, "0.9.1")

            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn("安装说明.txt", names)
                self.assertIn("文件校验清单.json", names)
                self.assertIn(f"{skill.name}/SKILL.md", names)
                self.assertNotIn("__pycache__/ignored.pyc", names)

            with self.assertRaises(FileExistsError):
                package_download_bundle(skill, [install, checksums], output, "0.9.1")


if __name__ == "__main__":
    unittest.main()
