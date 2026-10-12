"""Platform capabilities describe actual admission, including explicit refusals."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from advertised_limits import capabilities
from test_cli import EXE
import platform_support


class PlatformSupportTests(unittest.TestCase):
    def test_local_receipts_are_advertised_and_unavailable_jobs_fail_without_writes(self):
        cap = capabilities()
        self.assertTrue(cap['durable_publication']['supported_here'])
        expected = 'Windows_local_file_identity_and_SQLite_rollback_FULL' if os.name == 'nt' else 'Unix_device_inode_and_SQLite_rollback_FULL'
        self.assertEqual(cap['durable_publication']['backend'], expected)
        if cap['jobs']['supported_here']:
            self.assertTrue(cap['job_process']['supported_here'])
            return
        self.assertFalse(cap['job_process']['supported_here'])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = [('job.start', dict(document=dict(schema_version=2, id='small', kind='raster', width=2, height=2, color_space='srgb'), output=dict(output_root=str(root), file_name='result.png', format='png'))),
                        ('job.status', {}), ('job.result', {}), ('job.cancel', {}), ('job.resume', {}), ('job.wait', dict(wait_ms=0)), ('job.list', {})]
            for command, extra in commands:
                request = dict(command=command, job_root=str(root/'jobs'), **extra)
                if command != 'job.list':
                    request['request_id'] = 'job'
                result = subprocess.run([str(EXE)], input=json.dumps(request).encode(), capture_output=True, timeout=10)
                self.assertEqual((result.returncode, result.stderr), (1, b''))
                self.assertEqual(json.loads(result.stdout)['error']['code'], 'UNSUPPORTED_PLATFORM')
                self.assertEqual(list(root.iterdir()), [])

    def test_gate_uses_engine_truth_and_rejects_missing_or_invalid_support(self):
        for value in (False, True, 'false'):
            with patch.object(platform_support, 'capabilities', return_value={'jobs': {'supported_here': value}}):
                if value is False:
                    with self.assertRaises(unittest.SkipTest): platform_support.require_capability(self, 'jobs')
                elif value is True:
                    platform_support.require_capability(self, 'jobs')
                else:
                    with self.assertRaises(AssertionError): platform_support.require_capability(self, 'jobs')
        with patch.object(platform_support, 'capabilities', return_value={}):
            with self.assertRaises(KeyError): platform_support.require_capability(self, 'jobs')
