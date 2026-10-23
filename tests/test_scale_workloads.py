"""Fast reduced-extent workflow checks; only the fixed CLI suite proves scale."""
import copy
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_cli import EXE, ROOT
import synthetic_jpeg
import test_workload_gates as gate_tests

sys.path.insert(0,str(ROOT/'tools'))
import scale_oracles as oracle
import scale_workloads as scale
import workload_cases as measure
import workload_gates as gates


class ScaleWorkloadTests(unittest.TestCase):
    def test_complete_photo_workflow_preserves_samples_review_and_every_history_state(self):
        with tempfile.TemporaryDirectory() as directory:
            case=measure.Case(EXE,Path(directory)/'photo','photo-50mp',1)
            row=scale.run(case,dimensions=(512,384))
            self.assertTrue(row['success'],row)
            self.assertFalse(row['fixed_fixture'])
            self.assertEqual(row['dimensions'],[512,384])
            self.assertEqual(row['process_calls'],30)
            self.assertEqual(len(row['checks']),31)
            self.assertEqual([(c['step'],c['command']) for c in row['calls']],gates.SCALE_CONTRACTS['photo-50mp'][0])
            self.assertEqual([c['name'] for c in row['checks']],gates.SCALE_CONTRACTS['photo-50mp'][1])
            self.assertEqual((case.root/'edited.tiff').read_bytes(),(case.root/'restored.tiff').read_bytes())
            fixture=scale.Photo(512,384)
            with (case.root/'edited.tiff').open('r+b') as stream:
                tags=measure.tiff_tags(stream.read());at=tags[273][-1]+tags[279][-1]-1
                stream.seek(at);last=stream.read(1);stream.seek(at);stream.write(bytes([last[0]^1]))
            with self.assertRaises(AssertionError):
                oracle.check_tiff(case.root/'edited.tiff',512,384,lambda y:fixture.row(y,6))
            self.assertNotEqual(fixture.row(34,0),fixture.row(34,4))
            self.assertNotEqual(fixture.row(0,4),fixture.row(0,6))

    def test_page_and_rgba_delivery_check_geometry_alpha_and_every_pixel(self):
        with tempfile.TemporaryDirectory() as directory:
            for name,size in [('print-a2',(384,320)),('rgba8-8192',(256,256))]:
                with self.subTest(case=name):
                    case=measure.Case(EXE,Path(directory)/name,name,1)
                    row=scale.run(case,dimensions=size)
                    self.assertTrue(row['success'],row)
                    self.assertFalse(row['fixed_fixture'])
                    self.assertGreater(row['first_verified_png_engine_seconds'],0)
                    path=case.root/('preview.png' if name=='print-a2' else 'image.png')
                    with self.assertRaises(AssertionError):
                        oracle.check_png(path,*size,lambda y:bytes(size[0]*4))

    def test_original_jpeg_oracle_covers_baseline_progressive_edges_and_exact_alpha(self):
        with tempfile.TemporaryDirectory() as directory:
            for progressive in (False,True):
                case=measure.Case(EXE,Path(directory)/str(progressive),'jpeg-24mp',1)
                w,h=133,131
                source=case.source('original.jpg',synthetic_jpeg.jpeg(w,h,progressive=progressive))
                result=scale.call(case,'import','sample.import',source_path=source,id='jpeg',storage={},color_policy='assume_srgb',orientation='apply')
                def expected(y):
                    return bytes(v for x in range(w) for v in [*(synthetic_jpeg.value(x,y,c) for c in range(3)),255])
                self.assertEqual(oracle.check_native(case.root,result['document'],w,h,expected,depth='u8',tolerance=3),0)
                def wrong_alpha(y):
                    row=bytearray(expected(y));row[3]=254;return row
                with self.assertRaises(AssertionError):
                    oracle.check_native(case.root,result['document'],w,h,wrong_alpha,depth='u8',tolerance=3)
                wrong=copy.deepcopy(result['document']);wrong['items'][0]['content']['grid']['base']['sha256']='0'*64
                with self.assertRaises(AssertionError):oracle.check_native(case.root,wrong,w,h,expected,depth='u8',tolerance=3)

    def test_driver_failures_and_missing_memory_cannot_become_budget_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            case=measure.Case(EXE,Path(directory)/'jpeg','jpeg-24mp',1)
            failure=subprocess.CompletedProcess([],1,b'',b'pinned decoder unavailable')
            with patch.object(scale.subprocess,'run',return_value=failure):
                row=scale.run(case,dimensions=(16,16),jpeg_python=Path(sys.executable))
            self.assertFalse(row['success'])
            self.assertEqual(row['commit_budget']['status'],'unavailable')
            self.assertEqual((case.root/'jpeg-generator.stderr').read_bytes(),failure.stderr)
            self.assertEqual(row['checks'][0]['name'],'harness')
            self.assertEqual(scale.DIMENSIONS['photo-50mp'],(8192,6144))
            self.assertEqual(scale.MAX_PEAK_COMMIT_BYTES,512*1024*1024)

    def test_scale_gates_reject_reduced_missing_changed_and_unknown_memory_evidence(self):
        report=gate_tests.report();template=report['rows'][0]
        report.update(suite='scale-v2',selected_cases=list(gates.SCALE_CASES),rows=[],
            candidate_files={name:'3'*64 for name in gates.SCALE_HARNESS})
        for repetition in range(1,6):
            for name in gates.SCALE_CASES:
                row=copy.deepcopy(template);commands,checks=gates.SCALE_CONTRACTS[name]
                calls=[dict(copy.deepcopy(template['calls'][0]),step=step,command=command) for step,command in commands]
                row.update(case=name,repetition=repetition,calls=calls,process_calls=len(calls),
                    checks=[dict(name=c,status='pass') for c in checks],engine_seconds=sum(c['seconds'] for c in calls),
                    dimensions=gates.SCALE_DIMENSIONS[name],fixed_fixture=True,
                    commit_budget=dict(status='passed',maximum_bytes=512*1024*1024))
                if name=='jpeg-24mp':row['jpeg_tools']=dict(pillow_version='10.3.0',dimensions=[6000,4000],quality=93,subsampling=0,
                    python_sha256='4'*64,pillow_files_sha256='5'*64,source_rgb_sha256='6'*64)
                report['rows'].append(row)
        gate=gates.create(report,'7'*64,'Synthetic contract checks, not engine performance')
        self.assertEqual(gates.check(gate,report)['status'],'passed')
        for change in ('small','flag','missing','rss','ceiling','decoder','fixture','helper','oracle','call','failed'):
            with self.subTest(change=change):
                altered=copy.deepcopy(report);row=altered['rows'][0]
                if change=='small':row['dimensions']=[256,256]
                elif change=='flag':row['fixed_fixture']=False
                elif change=='missing':altered['rows'].pop()
                elif change=='rss':row['commit_budget']['status']='unavailable';row['peak_resident_bytes']=1
                elif change=='ceiling':row['commit_budget']['maximum_bytes']+=1
                elif change=='decoder':row['jpeg_tools']['pillow_version']='unknown'
                elif change=='fixture':row['jpeg_tools']['source_rgb_sha256']='8'*64
                elif change=='helper':altered['candidate_files']['tools/scale_oracles.py']='8'*64
                elif change=='oracle':row['checks'].pop()
                elif change=='call':row['calls'].pop()
                else:row['success']=False
                self.assertEqual(gates.check(gate,altered)['status'],'ineligible')
        self.assertEqual(gates.check(gate,gate_tests.report())['status'],'ineligible')
        metrics={name:dict(median_seconds=1,maximum_seconds=2,peak_commit_bytes=400*1024*1024) for name in gates.SCALE_CASES}
        self.assertTrue(all(v['peak_commit_bytes']==512*1024*1024 for v in gates.limits(metrics,gates.SCALE_CASES).values()))


if __name__=='__main__':unittest.main()
