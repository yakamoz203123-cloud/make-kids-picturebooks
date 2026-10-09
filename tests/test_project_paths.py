import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from project_paths import (
    normalize_relative_path,
    require_project_file,
    resolve_project_file,
)


class ProjectPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "绘本 项目"
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_normalize_relative_path_converts_windows_separators_to_posix(self):
        self.assertEqual(
            normalize_relative_path(self.root, "export\\reading.pdf"),
            "export/reading.pdf",
        )

    def test_unicode_and_space_containing_path_resolves_within_project(self):
        expected = self.root / "资料 空间" / "第 1 册.txt"
        expected.parent.mkdir()
        expected.write_text("内容", encoding="utf-8")

        self.assertEqual(
            resolve_project_file(self.root, "资料 空间/第 1 册.txt"),
            expected.resolve(),
        )
        self.assertEqual(
            require_project_file(self.root, "资料 空间/第 1 册.txt", "来源"),
            expected.resolve(),
        )

    def test_absolute_paths_are_rejected(self):
        with self.assertRaises(ValueError):
            normalize_relative_path(self.root, self.root / "export" / "reading.pdf")

    def test_parent_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_project_file(self.root, "../outside.txt")

    def test_resolved_file_cannot_escape_project_root(self):
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("private", encoding="utf-8")
        link = self.root / "linked-outside.txt"
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")

        with self.assertRaises(ValueError):
            resolve_project_file(self.root, "linked-outside.txt")

    def test_require_project_file_rejects_missing_file_with_label(self):
        with self.assertRaisesRegex(ValueError, "来源"):
            require_project_file(self.root, "missing.txt", "来源")

    def test_rejects_unsupported_path_value_types(self):
        for value in (None, 42, object()):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(TypeError):
                    normalize_relative_path(self.root, value)


if __name__ == "__main__":
    unittest.main()
