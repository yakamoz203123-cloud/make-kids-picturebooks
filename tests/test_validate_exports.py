import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


MM = 72 / 25.4


def write_pdf(path, pages, width, height, size=22):
    document = fitz.open()
    for text in pages:
        page = document.new_page(width=width, height=height)
        page.insert_text((36, 54), text, fontsize=size)
    document.save(path)
    document.close()


def write_booklet(path, texts, size=18, overrides=None):
    overrides = overrides or {}
    document = fitz.open()
    for left, right in ((4, 1), (2, 3)):
        page = document.new_page(width=297 * MM, height=210 * MM)
        for side, page_number in enumerate((left, right)):
            text = overrides.get(page_number, texts[page_number - 1])
            if text:
                page.insert_text(
                    (side * page.rect.width / 2 + 36, 54),
                    text,
                    fontsize=size,
                )
    document.save(path)
    document.close()


def write_valid_exports(root, print_size=18):
    reading = root / 'reading.pdf'
    printing = root / 'print.pdf'
    texts = ['page-one', 'page-two', 'page-three', 'page-four']
    write_pdf(reading, texts, 148 * MM, 210 * MM)
    write_booklet(printing, texts, print_size)
    return reading, printing, texts


class ValidateExportTests(unittest.TestCase):
    def validate(self, reading, printing, texts, **kwargs):
        from validate_exports import validate_exports
        try:
            return validate_exports(reading, printing, texts, **kwargs)
        except TypeError as exc:
            if 'allow_empty_pages' in kwargs:
                self.fail(f'validate_exports must accept explicit empty-page intent: {exc}')
            raise

    def test_rejects_zero_byte_reading_pdf(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reading, printing, texts = write_valid_exports(root)
            reading.write_bytes(b'')
            with self.assertRaisesRegex(ValueError, 'reading PDF is empty'):
                self.validate(reading, printing, texts)

    def test_rejects_malformed_print_pdf(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reading, printing, texts = write_valid_exports(root)
            printing.write_bytes(b'not a PDF')
            with self.assertRaisesRegex(ValueError, 'print PDF is unreadable'):
                self.validate(reading, printing, texts)

    def test_rejects_reading_pdf_missing_expected_page_text(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reading, printing, texts = write_valid_exports(root)
            write_pdf(reading, ['page-one', 'page-two', 'page-three', 'wrong-text'], 148 * MM, 210 * MM)
            with self.assertRaisesRegex(ValueError, 'reading page 4: expected text is not extractable'):
                self.validate(reading, printing, texts)

    def test_rejects_empty_or_whitespace_expected_page_text(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reading, printing, _ = write_valid_exports(root)
            with self.assertRaisesRegex(ValueError, 'expected page text must be non-empty'):
                self.validate(reading, printing, ['', '  ', '\t', '\n'])

    def test_accepts_explicitly_authorized_empty_page_and_booklet_half(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reading = root / 'reading.pdf'
            printing = root / 'print.pdf'
            texts = ['cover-text', '', 'story-text', 'back-text']
            write_pdf(reading, texts, 148 * MM, 210 * MM)
            write_booklet(printing, texts)

            report = self.validate(reading, printing, texts, allow_empty_pages={2})

            self.assertEqual(report['reading_pages'], 4)
            self.assertEqual(report['print_sides'], 2)

    def test_rejects_extractable_text_on_authorized_empty_reading_page(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reading = root / 'reading.pdf'
            printing = root / 'print.pdf'
            texts = ['cover-text', '', 'story-text', 'back-text']
            write_pdf(
                reading,
                ['cover-text', 'accidental-text', 'story-text', 'back-text'],
                148 * MM,
                210 * MM,
            )
            write_booklet(printing, texts)

            with self.assertRaisesRegex(
                ValueError,
                'reading page 2: authorized empty page contains extractable text',
            ):
                self.validate(reading, printing, texts, allow_empty_pages={2})

    def test_rejects_extractable_text_on_authorized_empty_booklet_half(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reading = root / 'reading.pdf'
            printing = root / 'print.pdf'
            texts = ['cover-text', '', 'story-text', 'back-text']
            write_pdf(reading, texts, 148 * MM, 210 * MM)
            write_booklet(printing, texts, overrides={2: 'accidental-text'})

            with self.assertRaisesRegex(
                ValueError,
                'print page 2 half 1: authorized empty page 2 contains extractable text',
            ):
                self.validate(reading, printing, texts, allow_empty_pages={2})

    def test_rejects_all_textless_book_even_when_every_page_is_authorized(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reading = root / 'reading.pdf'
            printing = root / 'print.pdf'
            texts = ['', '', '', '']
            write_pdf(reading, texts, 148 * MM, 210 * MM)
            write_booklet(printing, texts)

            with self.assertRaisesRegex(
                ValueError,
                'book must contain at least one content-bearing page with non-empty text',
            ):
                self.validate(reading, printing, texts, allow_empty_pages={1, 2, 3, 4})

    def test_rejects_reading_and_booklet_pages_without_extractable_text(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reading = root / 'reading.pdf'
            printing = root / 'print.pdf'
            write_pdf(reading, ['', '', '', ''], 148 * MM, 210 * MM)
            document = fitz.open()
            for _ in range(2):
                document.new_page(width=297 * MM, height=210 * MM)
            document.save(printing)
            document.close()
            with self.assertRaisesRegex(ValueError, 'reading page 1: no extractable text'):
                self.validate(reading, printing, ['page-one', 'page-two', 'page-three', 'page-four'])

    def test_rejects_wrong_page_count_and_page_dimensions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reading, printing, texts = write_valid_exports(root)
            write_pdf(reading, texts[:3], 150 * MM, 210 * MM)
            with self.assertRaisesRegex(ValueError, 'reading PDF page count: expected 4, got 3'):
                self.validate(reading, printing, texts)
            write_pdf(reading, texts, 150 * MM, 210 * MM)
            with self.assertRaisesRegex(ValueError, 'reading page 1: expected A5 dimensions'):
                self.validate(reading, printing, texts, page_mm=(150, 210))

    def test_rejects_non_a5_page_configuration_even_when_pdfs_are_a5(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reading, printing, texts = write_valid_exports(root)
            with self.assertRaisesRegex(ValueError, 'reading page dimensions must be fixed A5'):
                self.validate(reading, printing, texts, page_mm=(150, 210))

    def test_rejects_malformed_minimum_print_text_size_configuration(self):
        from validate_exports import minimum_print_text_size

        with self.assertRaisesRegex(ValueError, 'minimum_print_text_size_pt must be a finite number'):
            minimum_print_text_size({'minimum_print_text_size_pt': '18'})

    def test_rejects_final_print_text_smaller_than_default_threshold(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reading, printing, texts = write_valid_exports(root, print_size=17)
            with self.assertRaisesRegex(ValueError, 'print page 1: text size 17.0 pt is below 18.0 pt'):
                self.validate(reading, printing, texts)

    def test_uses_default_threshold_when_configured_threshold_is_lower(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reading, printing, texts = write_valid_exports(root, print_size=17)
            with self.assertRaisesRegex(ValueError, 'below 18.0 pt'):
                self.validate(reading, printing, texts, minimum_print_text_size_pt=12)

    def test_valid_exports_preserve_text_on_each_booklet_half(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reading, printing, texts = write_valid_exports(root)
            report = self.validate(reading, printing, texts)
            self.assertEqual(report['reading_pages'], 4)
            self.assertEqual(report['print_sides'], 2)
            document = fitz.open(printing)
            self.assertIn(texts[3], document[0].get_text(clip=fitz.Rect(0, 0, document[0].rect.width / 2, document[0].rect.height)))
            self.assertIn(texts[0], document[0].get_text(clip=fitz.Rect(document[0].rect.width / 2, 0, document[0].rect.width, document[0].rect.height)))
            document.close()


if __name__ == '__main__':
    unittest.main()
