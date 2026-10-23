import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from render_contact_sheet import discover_page_images, render_contact_sheet


class ContactSheetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pages = self.root / "reading-pages"
        self.pages.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write_page(self, number, color=(240, 220, 180), suffix=".png"):
        path = self.pages / f"page-{number:02d}{suffix}"
        Image.new("RGB", (630, 893), color).save(path)
        return path

    def test_discover_page_images_sorts_by_numeric_page_number(self):
        for number in range(1, 11):
            self.write_page(number)

        discovered = discover_page_images(self.pages)

        self.assertEqual(list(range(1, 11)), [item.page_number for item in discovered])
        self.assertEqual(
            [f"page-{number:02d}.png" for number in range(1, 11)],
            [item.path.name for item in discovered],
        )

    def test_render_contact_sheet_uses_deterministic_three_column_grid_and_labels(self):
        for number in range(1, 6):
            self.write_page(number, color=(number * 20, 120, 180))
        output = self.root / "reviews" / "contact-sheet.png"

        result = render_contact_sheet(self.pages, output)

        self.assertEqual(output, result)
        with Image.open(output) as rendered:
            self.assertEqual((1040, 1050), rendered.size)
            # The first tile's label strip must contain ink, not just the
            # background, proving that page labels are rendered separately.
            label_strip = rendered.crop((24, 24 + 453, 24 + 320, 24 + 453 + 40))
            background = Image.new("RGB", label_strip.size, "white")
            self.assertIsNotNone(ImageChops.difference(label_strip, background).getbbox())

    def test_render_contact_sheet_rejects_missing_page_numbers(self):
        self.write_page(1)
        self.write_page(3)

        with self.assertRaisesRegex(ValueError, "缺少页面.*2"):
            render_contact_sheet(self.pages, self.root / "contact-sheet.png")

    def test_render_contact_sheet_rejects_corrupt_image(self):
        self.write_page(1)
        (self.pages / "page-02.png").write_bytes(b"not an image")

        with self.assertRaisesRegex(ValueError, "无法读取图像.*page-02.png"):
            render_contact_sheet(self.pages, self.root / "contact-sheet.png")

    def test_render_contact_sheet_rejects_non_image_input(self):
        self.write_page(1)
        (self.pages / "notes.txt").write_text("not a page", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "非图像输入.*notes.txt"):
            render_contact_sheet(self.pages, self.root / "contact-sheet.png")

    def test_render_contact_sheet_accepts_jpeg_pages(self):
        self.write_page(1, suffix=".jpeg")
        output = render_contact_sheet(self.pages, self.root / "contact-sheet.jpg")

        with Image.open(output) as rendered:
            self.assertEqual((1040, 541), rendered.size)

    def test_cli_renders_requested_grid(self):
        for number in range(1, 4):
            self.write_page(number)
        output = self.root / "contact-sheet.png"
        script = ROOT / "scripts" / "render_contact_sheet.py"

        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                str(self.pages),
                str(output),
                "--columns",
                "2",
                "--thumb-width",
                "100",
                "--thumb-height",
                "140",
                "--label-height",
                "20",
                "--margin",
                "10",
                "--gap",
                "5",
            ],
            text=True,
            capture_output=True,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        with Image.open(output) as rendered:
            self.assertEqual((225, 345), rendered.size)


if __name__ == "__main__":
    unittest.main()
