import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts/validate_page_manifest.py'


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.exists(), 'missing manifest validator')
        spec = importlib.util.spec_from_file_location('page_manifest', MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.validate = module.validate_page_manifest
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        (self.base / 'prompt.md').write_text('scene', encoding='utf-8')
        self.data = {'schema_version': 1, 'book_id': 'b01', 'age_band': '3-4', 'pages': [
            {'page': 1, 'text_version': 'v1', 'current_prompt_path': 'prompt.md',
             'current_image_path': None, 'characters_version': 'test-v1',
             'text_area': [10, 110, 120, 80],
             'props': [{'id': 'blocks', 'count': 3, 'location': 'floor',
                        'state': 'loose', 'change': 'introduced'}],
             'knowledge_check': {'status': 'pending', 'evidence': ''}}]}

    def test_planning_without_image(self):
        self.assertEqual([], self.validate(self.data, self.base))

    def test_completion_needs_image(self):
        self.assertTrue(self.validate(self.data, self.base, True))

    def complete(self):
        (self.base / 'new.png').write_bytes(b'asset')
        self.data['pages'][0]['current_image_path'] = 'new.png'
        self.data['pages'][0]['knowledge_check'] = {'status': 'passed', 'evidence': 'viewed page 1; exactly 3 blocks'}

    def test_selected_new_asset_only(self):
        self.complete()
        (self.base / 'old.png').write_bytes(b'old')
        (self.base / 'page01-backup.png').write_bytes(b'backup')
        self.assertEqual([], self.validate(self.data, self.base, True))

    def test_no_fallback_when_selected_missing(self):
        self.complete()
        (self.base / 'new.png').unlink()
        (self.base / 'old.png').write_bytes(b'old')
        self.assertTrue(self.validate(self.data, self.base, True))

    def test_knowledge_must_pass_and_have_evidence(self):
        self.complete()
        for check in ({'status': 'pending', 'evidence': 'todo'}, {'status': 'failed', 'evidence': 'wrong'}, {'status': 'passed', 'evidence': ''}):
            with self.subTest(check=check):
                self.data['pages'][0]['knowledge_check'] = check
                self.assertTrue(self.validate(self.data, self.base, True))

    def test_duplicate_or_gap_page(self):
        for number in (1, 3):
            data = copy.deepcopy(self.data)
            data['pages'].append(copy.deepcopy(data['pages'][0]))
            data['pages'][1]['page'] = number
            self.assertTrue(self.validate(data, self.base))

    def test_invalid_age(self):
        for age in ('3-6', None, '', ['3-4', '5-7']):
            with self.subTest(age=age):
                self.data['age_band'] = age
                self.assertTrue(self.validate(self.data, self.base))

    def test_selected_age_bands_in_planning_and_completion(self):
        planning = copy.deepcopy(self.data)
        for age in ('3-4', '5-7', '8-10'):
            with self.subTest(age=age):
                self.data = copy.deepcopy(planning)
                self.data['age_band'] = age
                self.assertEqual([], self.validate(self.data, self.base))
                self.complete()
                self.assertEqual([], self.validate(self.data, self.base, True))

    def test_legacy_age_band_remains_readable(self):
        self.data['age_band'] = '5-6'
        self.assertEqual([], self.validate(self.data, self.base))
        self.complete()
        self.assertEqual([], self.validate(self.data, self.base, True))

    def test_bad_types_and_counts(self):
        for value in (-1, True, 1.5, '3'):
            data = copy.deepcopy(self.data)
            data['pages'][0]['props'][0]['count'] = value
            self.assertTrue(self.validate(data, self.base))
        for data in (None, [], {'schema_version': True}, {'pages': 'pages'}):
            self.assertTrue(self.validate(data, self.base))

    def test_duplicate_prop_and_missing_record(self):
        data = copy.deepcopy(self.data)
        data['pages'][0]['props'].append(copy.deepcopy(data['pages'][0]['props'][0]))
        self.assertTrue(self.validate(data, self.base))
        for key in ('text_version', 'characters_version', 'text_area', 'current_prompt_path', 'knowledge_check'):
            data = copy.deepcopy(self.data)
            del data['pages'][0][key]
            self.assertTrue(self.validate(data, self.base))

    def test_out_of_range_coordinate_returns_error(self):
        self.data['pages'][0]['text_area'][0] = 10 ** 400
        self.assertTrue(self.validate(self.data, self.base))


if __name__ == '__main__':
    unittest.main()
