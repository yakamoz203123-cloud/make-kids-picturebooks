import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / 'scripts'))
from project_state import validate_project, next_action
from render_book import _lines, render_book


class ReleaseGuardTests(unittest.TestCase):
    def setUp(self):
        self.project = {'schema_version': 1, 'source': {'path': 'chapter.txt', 'version': 'v1', 'coverage': 'partial'},
                        'characters_version': 'v1', 'target_age_bands': ['3-4'],
                        'books': [{'id': 'b01', 'age_band': '3-4', 'status': 'text', 'source_version': 'v1',
                                   'characters_version': 'v1', 'artifacts': {}}]}
        pdfmetrics.registerFont(TTFont('GuardTest', str(SKILL / 'assets/kidsbook-print.ttf')))

    def test_project_rejects_invalid_age_even_if_no_manifest_is_loaded(self):
        self.project['books'][0]['age_band'] = 'bad'
        self.assertTrue(validate_project(self.project))

    def test_completed_status_requires_artifact_records(self):
        self.project['books'][0]['status'] = 'digital_checked'
        self.assertTrue(validate_project(self.project))

    def test_files_missing_after_completion_return_revalidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.project['books'][0]['status'] = 'digital_checked'
            self.project['books'][0]['artifacts'] = {key: 'missing.json' for key in
                ('concept', 'story', 'storyboard', 'layout', 'page_manifest', 'reading_pdf', 'print_pdf', 'review', 'acceptance')}
            (Path(tmp) / 'chapter.txt').write_text('source',encoding='utf-8')
            try:
                result = next_action(self.project, base_dir=Path(tmp))
            except TypeError:
                result = None
            self.assertIsNotNone(result)
            self.assertEqual(result['stage'], 'revalidate')

    def test_automatic_wrap_never_starts_with_closing_punctuation(self):
        width = pdfmetrics.stringWidth('小朋友', 'GuardTest', 22)
        lines = _lines('小朋友，小朋友。', 'GuardTest', 22, width)
        self.assertEqual(''.join(lines), '小朋友，小朋友。')
        self.assertTrue(all(line[0] not in '，。”' for line in lines))
        self.assertTrue(all(pdfmetrics.stringWidth(line, 'GuardTest', 22) <= width + .01 for line in lines))

    def test_opening_quote_is_not_left_at_end_of_line(self):
        width = pdfmetrics.stringWidth('小朋友', 'GuardTest', 22)
        lines = _lines('我说“来吧”。', 'GuardTest', 22, width)
        self.assertTrue(all(not line.endswith('“') for line in lines))
        self.assertEqual(''.join(lines), '我说“来吧”。')

    def test_one_point_font_is_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = {'font_size': 1, 'pages': [{'number': 1, 'text': '小朋友', 'text_box_mm': [14, 20, 120, 40]}]}
            (root / 'layout.json').write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaises(ValueError):
                render_book(root / 'layout.json', root / 'reading.pdf')
            self.assertFalse((root / 'reading.pdf').exists())

    def test_story_text_ignores_boundary_pages_and_preserves_story_order(self):
        from accept_book import story_text_errors
        pages = [
            {'kind': 'cover', 'text': '小小探险家'},
            {'kind': 'story', 'text': '先穿过花园。'},
            {'kind': 'parents', 'text': '给家长的话'},
            {'kind': 'story', 'text': '再回到家。'},
            {'kind': 'blank', 'text': ''},
            {'kind': 'back', 'text': '明天见！'},
        ]
        self.assertEqual(story_text_errors(pages, '先穿过花园。再回到家。'), [])
        pages[1]['text'], pages[3]['text'] = pages[3]['text'], pages[1]['text']
        self.assertTrue(story_text_errors(pages, '先穿过花园。再回到家。'))


if __name__ == '__main__':
    unittest.main()
