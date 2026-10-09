"""Native CPU identity remains observed when optional environment variables are absent."""
import os
import sys
import unittest
from unittest.mock import patch
from test_cli import ROOT

sys.path.insert(0,str(ROOT/'tools'))
import measurement_host as host


class MeasurementHostTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','Windows native measurement backend')
    def test_actual_native_architecture_and_cpu_model_do_not_require_env_vars(self):
        with patch.dict(os.environ,{},clear=True):
            result=host.identity()
        self.assertTrue(result['hardware_available'],result)
        self.assertIn(result['machine'],('x86','ARM','IA64','AMD64','ARM64'))
        self.assertTrue(result['processor'].strip())
        self.assertGreater(result['logical_cpus'],0)
        self.assertIn(result['pointer_bits'],(32,64))
        self.assertEqual(result,host.identity())

    @unittest.skipUnless(os.name=='nt','Windows native measurement backend')
    def test_failed_identity_read_is_explicit_unavailable_data(self):
        with patch.object(host,'windows_hardware',side_effect=OSError('unavailable registry')):
            result=host.identity()
        self.assertFalse(result['hardware_available'])
        self.assertIsNone(result['machine']);self.assertIsNone(result['processor'])
        self.assertIn('unavailable registry',result['hardware_error'])


if __name__=='__main__':unittest.main()
