"""Presentation export tests; no trusted runner or candidate imports."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('export_demo', ROOT / 'tools/export_demo.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ExportFailures(unittest.TestCase):
    def test_changed_report_rejected_before_other_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            path.write_text('{"classification":{"baseline":"PASS"}}')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                module.derive(path, path.parent / 'absent-contract.json', path.parent)

    def test_missing_report_cannot_generate_success(self):
        with self.assertRaises(FileNotFoundError):
            module.derive(Path('absent-report.json'), Path('absent-contract.json'), ROOT)

    def test_duplicate_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            module.strict_json('{"status":"PASS","status":"FAIL"}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Non-finite'):
            module.strict_json('{"review_minutes":NaN}')


if __name__ == '__main__':
    unittest.main()
