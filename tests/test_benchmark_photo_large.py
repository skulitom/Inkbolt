"""Bounded large-photo lifecycle probes and strict separation from original B10."""
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_cli import EXE,ROOT
sys.path.insert(0,str(ROOT/'tools'))
import benchmark_photo_large as photo
import benchmark_photo_large_fixture as fixture
from benchmark_runtime import Trial,TaskFailure
from benchmark_tasks import CHECKS
from benchmark_photo import MAX_PEAK_COMMIT_BYTES,check_memory
from benchmark_driver import contract,migration
from benchmark_comparison import compare,load_report
from test_benchmark_comparison import suite,save
from test_benchmark_driver import driver

SMALL=(257,193,dict(x=124,y=124,width=20,height=16))


class LargePhotoTests(unittest.TestCase):
    def test_complete_cli_and_mcp_native_history_with_bounded_file_judging(self):
        with tempfile.TemporaryDirectory() as directory:
            hashes=[]
            for transport in ('cli','mcp'):
                case=Trial(EXE,Path(directory)/transport,'B10',1,transport,CHECKS['B10'])
                case.photo_test_profile=SMALL;case.benchmark_variant=fixture.VARIANT
                case.judge_root=Path(directory)/(transport+'-judge');case.judge_root.mkdir()
                try:photo.photograph(case)
                finally:case.close()
                row=case.finish()
                self.assertEqual(row['status'],'passed' if os.name=='nt' else 'failed',row)
                self.assertEqual({c['name'] for c in row['checks'] if c['status']=='fail'},
                                 set() if os.name=='nt' else {'memory-budget'})
                self.assertEqual(set(c['name'] for c in row['checks']),set(CHECKS['B10'])|{'source-preservation'})
                self.assertEqual((row['engine_commands'],row['judge_engine_commands']),(14,9))
                self.assertEqual(len([c for c in row['calls'] if 'judge_workspace' in c]),2)
                self.assertTrue((case.judge_root/'native-publication/judge-edited.tiff').is_file())
                self.assertFalse((case.root/'judge-edited.tiff').exists())
                self.assertEqual(row['benchmark_variant'],fixture.VARIANT)
                self.assertFalse(json.loads((case.root/'fixture-profile.json').read_text())['fixed_fixture'])
                self.assertFalse(row['model_trials'])
                self.assertGreater(row['first_verified_preview_seconds'],0)
                hashes.append(row['sources']['original.tiff'])
                with fixture.Rows(case.root/'original.tiff',*SMALL) as rows:
                    self.assertEqual(struct.unpack('<4H',rows.row(0)[:8]),(29582,28462,27342,65535))
                    start=SMALL[2]['x']*8
                    self.assertEqual(struct.unpack('<4H',rows.row(124)[start:start+8]),(61003,4007,54011,65535))
                    self.assertNotEqual(rows.row(124),rows.row(124,True))
                with self.assertRaisesRegex(TaskFailure,'Reduced'):
                    photo.contract_fields(case)
            self.assertEqual(*hashes)

    def test_independent_file_oracle_rejects_one_low_bit_outside_the_repair(self):
        from scale_oracles import write_tiff,check_tiff
        with tempfile.TemporaryDirectory() as directory:
            case=Trial(EXE,Path(directory)/'trial','B10',1,'cli',CHECKS['B10']);case.photo_test_profile=SMALL
            photo.fixture(case)
            with fixture.Rows(case.root/'original.tiff',*SMALL) as rows:
                path=case.root/'edited.tiff';write_tiff(path,*SMALL[:2],lambda y:rows.row(y,True))
                check_tiff(path,*SMALL[:2],lambda y:rows.row(y,True))
                with path.open('r+b') as stream:
                    stream.seek(-8,2);value=stream.read(1);stream.seek(-1,1);stream.write(bytes([value[0]^1]))
                with self.assertRaisesRegex(AssertionError,'TIFF sample mismatch'):
                    check_tiff(path,*SMALL[:2],lambda y:rows.row(y,True))

    def test_fixed_profiles_and_memory_budgets_do_not_replace_original_b10(self):
        import benchmark_photo
        self.assertEqual((benchmark_photo.WIDTH,benchmark_photo.HEIGHT,MAX_PEAK_COMMIT_BYTES),(1920,1080,256*1024**2))
        self.assertEqual((fixture.WIDTH,fixture.HEIGHT,fixture.MAX_PEAK_COMMIT_BYTES),(8192,6144,512*1024**2))
        observation=[dict(available=True,peak_commit_bytes=300*1024**2)]
        with self.assertRaises(TaskFailure):check_memory(observation)
        check_memory(observation,fixture.MAX_PEAK_COMMIT_BYTES)
        with self.assertRaises(TaskFailure):check_memory([dict(available=False)],fixture.MAX_PEAK_COMMIT_BYTES)
        self.assertIs(migration('B10',fixture.VARIANT)[0],photo)
        with self.assertRaises(TaskFailure):migration('B01',fixture.VARIANT)
        with self.assertRaises(TaskFailure):migration('B10','unknown')

    def test_capture_contract_and_comparison_cannot_mix_variants(self):
        def large(row,contract,usage):
            contract['benchmark_variant']=fixture.VARIANT;row['benchmark_variant']=fixture.VARIANT
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            model=suite(root/'model','model',tasks=('B10',),edit=large)
            value=json.loads(model.read_text());value['benchmark_variant']=fixture.VARIANT
            value['provenance']['benchmark_variant']=fixture.VARIANT;save(model,value)
            baseline=suite(root/'baseline','baseline',tasks=('B10',))
            result=compare(load_report(model,'model'),load_report(baseline,'baseline'))
            self.assertIn('Different benchmark_variant',result['global_issues'])
            self.assertFalse(next(t for t in result['tasks'] if t['task']=='B10')['comparable'])
            self.assertFalse(result['actual_model_benchmark_complete']);self.assertFalse(result['decision_ready'])
            value['provenance'].pop('benchmark_variant');save(model,value)
            with self.assertRaisesRegex(ValueError,'variant provenance'):load_report(model,'model')
            case=SimpleNamespace(task='B10',repetition=1,arm='model',prompt_sha256='a'*64,sources={},
                                 executable=EXE,benchmark_variant=fixture.VARIANT)
            self.assertEqual(contract(case,driver(),None)['benchmark_variant'],fixture.VARIANT)


if __name__=='__main__':unittest.main()
