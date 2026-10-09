"""An isolated miniature suite proves worker/count failures cannot become success."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class VerificationRunnerTests(unittest.TestCase):
    def test_parallel_runner_requires_every_worker_and_exact_discovery_count(self):
        runner=Path(__file__).resolve().parents[1]/'tools/verify.py'
        script='''import importlib.util,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location("fixture_verify",sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.ROOT=Path(sys.argv[2]);module.python_checks(2)
'''
        for body,success in [('self.assertEqual(2+3,5)',True),('self.fail("seeded fixture failure")',False),
                             ('print("Ran 999 tests in 0.0s")',False)]:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'tests').mkdir()
                (root/'tests/test_original_a.py').write_text('import unittest\nclass A(unittest.TestCase):\n def test_one(self): self.assertTrue(True)\n',encoding='utf-8')
                (root/'tests/test_original_b.py').write_text(f'import unittest\nclass B(unittest.TestCase):\n def test_two(self): {body}\n',encoding='utf-8')
                result=subprocess.run([sys.executable,'-c',script,str(runner),str(root)],capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode==0,success,result.stdout+result.stderr)
                if success:self.assertIn('All 2 Python tests passed across 2 isolated modules.',result.stdout)
                else:self.assertIn('Python verification failed',result.stderr)


if __name__=='__main__':unittest.main()
