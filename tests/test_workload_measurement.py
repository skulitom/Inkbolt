"""Measurement integrity, actual native history and OS lifetime-memory evidence."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE, ROOT
sys.path.insert(0, str(ROOT / 'tools'))
import workload_cases as measure


class WorkloadMeasurementTests(unittest.TestCase):
    def test_native_precision_edit_history_and_undo_use_actual_cli_and_independent_tiff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'native'
            case = measure.Case(EXE, root, 'native-control', 1)
            row = measure.run_case(case)
            self.assertTrue(row['success'], row)
            self.assertEqual(row['process_calls'], 9)
            self.assertEqual(row['blocked_steps'], 0)
            self.assertEqual(len(row['fixture_sources']), 1)
            self.assertTrue(all(c['status'] == 'pass' for c in row['checks']))
            self.assertIsNone(row['first_verified_png_engine_seconds'])
            self.assertEqual((root/'initial.tiff').read_bytes(), (root/'historical.tiff').read_bytes())
            self.assertEqual((root/'initial.tiff').read_bytes(), (root/'restored.tiff').read_bytes())
            self.assertNotEqual((root/'initial.tiff').read_bytes(), (root/'edited.tiff').read_bytes())
            self.assertEqual(row['adapter'],'native-tiled-v1')
            self.assertLess(row['response_bytes'],128*128*8)
            imported=json.loads((root/'00-import.response.json').read_bytes())['result']['document']
            self.assertEqual(imported['items'][0]['content']['type'],'stored_samples')
            self.assertGreater(row['engine_seconds'], 0)
            if os.name == 'nt':
                self.assertTrue(row['memory_complete'])
                self.assertGreater(row['peak_commit_bytes'], 0)

    def test_legacy_adapter_preserves_original_calls_and_native_oracle(self):
        with tempfile.TemporaryDirectory() as directory:
            case=measure.Case(EXE,Path(directory)/'legacy','native-control',1,adapter='legacy-v1')
            row=measure.run_case(case)
            self.assertTrue(row['success'],row)
            imported=json.loads((case.root/'00-import.response.json').read_bytes())['result']['document']
            self.assertEqual(imported['items'][0]['content']['type'],'samples')
            self.assertGreater(row['response_bytes'],128*128*8)
            for call in case.root.glob('*.request.json'):
                payload=json.loads(call.read_bytes())
                self.assertNotIn('storage',payload)
                self.assertNotIn('render_options',payload.get('output',{}))

    def test_oracle_mismatch_and_source_change_cannot_be_success(self):
        with tempfile.TemporaryDirectory() as directory:
            case = measure.Case(EXE, Path(directory)/'scene', 'social-square', 1)
            source = Path(case.source('original.bin', b'original'))
            doc = measure.document('small', 'vector', 2, 2, items=[measure.rectangle('r', 0, 0, 2, 2)])
            case.publish('wrong-oracle', doc, 'png', lambda p: measure.check_png(p, 2, 2, bytes(16)))
            source.write_bytes(b'changed')
            row = case.finish()
            self.assertFalse(row['success'])
            self.assertIsNone(row['first_verified_png_engine_seconds'])
            self.assertEqual([c['name'] for c in row['checks'] if c['status'] == 'fail'],
                             ['wrong-oracle', 'source-preservation'])

    def test_engine_failure_is_retained_and_dependent_steps_are_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            case = measure.Case(EXE, Path(directory)/'failed', 'native-screen', 1)
            result = case.call('missing', 'sample.import', source_path=str(case.root/'absent.png'), id='absent')
            self.assertIsNone(result)
            case.call('dependent', 'session.create', available=result is not None)
            row = case.finish()
            self.assertFalse(row['success'])
            self.assertEqual(row['process_calls'], 1)
            self.assertEqual(row['blocked_steps'], 1)
            self.assertEqual(row['calls'][0]['status'], 'engine_failure')
            self.assertTrue(row['calls'][0]['error']['code'])
            self.assertEqual(json.loads((case.root/'00-missing.response.json').read_bytes())['ok'], False)

    def test_invalid_envelopes_and_driver_errors_are_failures_not_engine_success(self):
        metrics = dict(exit_code=0, seconds=.1, timed_out=False, memory=dict(available=False))
        responses = [b'invalid-json', b'{"ok":true}', b'{"ok":false}',
                     b'{"ok":1,"result":{}}', b'{"ok":false,"error":{"code":"X"}}']
        with tempfile.TemporaryDirectory() as directory:
            for index, response in enumerate(responses):
                case = measure.Case(EXE, Path(directory)/str(index), 'native-control', index)
                with patch.object(measure, 'run_process', return_value=(metrics, response, b'')):
                    self.assertIsNone(case.call('broken', 'capabilities'))
                self.assertEqual(case.calls[0]['status'], 'harness_failure')
                self.assertFalse(case.finish()['success'])
            case = measure.Case(EXE, Path(directory)/'bug', 'native-control', 1)
            with patch.object(measure, '_run_case', side_effect=KeyError('missing-field')):
                row = measure.run_case(case)
            self.assertFalse(row['success'])
            self.assertEqual(row['checks'][0]['name'], 'harness')

    def test_aggregation_keeps_fast_failures_out_of_successful_latency(self):
        success = dict(case='native-screen', success=True, engine_seconds=5,
                       peak_commit_bytes=1000, response_bytes=100)
        failure = dict(success, success=False, engine_seconds=.01, peak_commit_bytes=10)
        result = measure.aggregate([success, failure])[0]
        self.assertEqual(result['successful'], 1)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(result['success_rate'], .5)
        self.assertEqual(result['successful_engine_seconds']['min'], 5)
        self.assertEqual(result['successful_peak_commit_bytes']['min'], 1000)
        self.assertIsNone(measure.aggregate([failure])[0]['successful_engine_seconds'])

    @unittest.skipUnless(os.name == 'nt', 'Verified Windows measurement backend')
    def test_memory_high_water_survives_free_and_process_exit(self):
        script = "import sys; a=bytearray(32*1024*1024); a[::4096]=bytes(len(a[::4096])); del a; sys.stdout.write('ok')"
        base, _, _ = measure.run_process([sys.executable, '-c', 'pass'], b'', 10)
        full, stdout, stderr = measure.run_process([sys.executable, '-c', script], b'', 10)
        self.assertEqual((full['exit_code'], stdout, stderr), (0, b'ok', b''))
        self.assertTrue(base['memory']['available']); self.assertTrue(full['memory']['available'])
        for key in ['peak_working_set_bytes', 'peak_commit_bytes']:
            self.assertGreater(full['memory'][key], base['memory'][key] + 24*1024*1024)

    def test_owned_timeout_is_reaped_and_reported(self):
        result, _, _ = measure.run_process([sys.executable, '-c', 'import time; time.sleep(30)'], b'', .2)
        self.assertTrue(result['timed_out'])
        self.assertNotEqual(result['exit_code'], 0)
        self.assertLess(result['seconds'], 10)

    def test_measurement_artifacts_never_replace_existing_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'report.json'
            measure.save_json(path, {'original': True})
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                measure.save_json(path, {'original': False})
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(FileExistsError):
                measure.Case(EXE, Path(directory), 'native-control', 1)


if __name__ == '__main__':
    unittest.main()
