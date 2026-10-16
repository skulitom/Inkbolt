"""External B10 deliveries retain native precision, source identity and real history."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from benchmark_driver import ExternalTrial,run_external_task,workspace_files,run_owned
from benchmark_photo import PROMPT,judge,judge_memory,MAX_PEAK_COMMIT_BYTES
from benchmark_baseline_photo import manifest,inspect_tiff
from benchmark_tasks import CHECKS,ENGINE_CHECKS
from benchmark_runtime import TaskFailure
from test_benchmark_driver import driver,fake_tools
from verify_process import MEMORY_SCOPE,MEMORY_METHOD,unavailable_memory


class ExternalPhotoTests(unittest.TestCase):
    def assert_photo(self,row):
        self.assertEqual(row['status'],'passed' if os.name=='nt' else 'failed',
                         dict(error=row['error'],checks=row['checks'],missing=row['missing_checks'],
                              synthetic_client_failures=getattr(self,'client_failures',[])))
        self.assertEqual({c['name'] for c in row['checks'] if c['status']=='fail'},
                         set() if os.name=='nt' else {'memory-budget'})
        self.assertFalse(row['model_trials']);self.assertIsNone(row['model_calls'])

    def test_external_model_relocated_capture_and_damaged_delivery_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configuration=driver('--photo-names','--custom-session-store');configuration['timeout_seconds']=90
            self.client_failures=[]
            def observed_client(*args,**kwargs):
                # Only this known credential-free synthetic fixture is captured.
                # The production harness still discards arbitrary client output.
                self.assertIn(str(ROOT/'tests/benchmark_fake_driver.py'),args[0])
                result=run_owned(*args,**kwargs)
                if result['status']!='passed':
                    self.client_failures.append(dict(status=result['status'],exit_code=result['exit_code'],
                        seconds=result['seconds'],output=result.get('output','')[-4000:]))
                return result
            with patch('benchmark_driver.run_owned',side_effect=observed_client):
                row=run_external_task(EXE,root/'live','B10',1,'model',configuration)
            self.assert_photo(row)
            self.assertEqual(row['judge_engine_commands'],9)
            self.assertIsNone(row['peak_commit_bytes']);self.assertFalse(row['memory_complete'])
            before=workspace_files(root/'live/workspace')
            self.assertFalse((root/'live/workspace/.inkbolt/sessions').exists())
            (root/'live').rename(root/'captured')  # Every old absolute resource root is now absent.
            imported=run_external_task(EXE,root/'import','B10',1,'model',configuration,import_source=root/'captured')
            self.assert_photo(imported)
            self.assertEqual(imported['checks'],row['checks'])
            self.assertEqual(imported['external_process_tree_memory'],row['external_process_tree_memory'])
            workspace=root/'import/workspace'
            self.assertFalse((workspace/'.inkbolt/sessions').exists())
            self.assertEqual(before,workspace_files(workspace))
            self.assertEqual(before,workspace_files(root/'captured/workspace'))
            self.assertEqual(json.loads((workspace/'editable.json').read_bytes())['id'],'original-studio')
            # Retain the actual independent judge responses. Damaged-delivery
            # controls deliberately provide these stale correct responses so
            # receipts/pictures cannot hide corrupt delivered files or state.
            responses={}
            for path in (root/'import/evidence').glob('*.request.json'):
                step=path.name.split('-',1)[1].removesuffix('.request.json')
                responses[step]=json.loads(path.with_name(path.name.replace('.request.json','.response.json')).read_bytes())['result']
            mutations={'patch':('edited.json','editable-exact-patch'),'undo':('undo-source.json','undo-editability'),
                       'review':('review.json','editable-exact-patch'),
                       'review-bytes':('review.json','editable-exact-patch'),
                       'review-manifest':('review.json','editable-exact-patch'),'import':('import-report.json','native-import'),
                       'receipt':('publication-report.json','edited-native-samples'),
                       'native':('edited.tiff','edited-native-samples'),'head':(None,'history-valid'),
                       'tile':(str(next((workspace/'.inkbolt/assets').glob('*.native-tile')).relative_to(workspace)),'immutable-tiles')}
            for fault,(filename,check) in mutations.items():
                with self.subTest(fault=fault):
                    case=ExternalTrial(EXE,root/('control-'+fault),'B10',1,'cli',CHECKS['B10'],arm='model')
                    self.addCleanup(case.close);case.judge_root=case.root
                    case.begin(PROMPT.read_text(encoding='utf-8'));case.root=workspace;case.sources=row['sources']
                    case.driver_evidence=imported['driver'];case.begin_judging()
                    def cached(step,command,**arguments):
                        result=copy.deepcopy(responses[step])
                        if fault=='head' and step=='judge-history':result['revision']=4
                        return result
                    case.call=cached
                    original=(workspace/filename).read_bytes() if filename else None
                    try:
                        if filename and filename.endswith('.json'):
                            value=json.loads(original)
                            if fault=='patch':
                                value['items'][0]['content']['grid']['base']['tiles'][0]='0'*64
                            elif fault=='undo':value['items'][0]['opacity']=.5
                            elif fault=='review':value['proposal']['base_state_sha256']='0'*64
                            elif fault=='review-bytes':
                                p=value['proposed_document']['items'][0]['content']['grid']['staged']['pending'][0]
                                raw=bytearray.fromhex(p['data_hex']);raw[-1]^=1;p['data_hex']=raw.hex()
                            elif fault=='review-manifest':
                                value['proposed_document']['items'][0]['content']['grid']['staged']['manifest']['sha256']='0'*64
                            elif fault=='receipt':value['edited']['sha256']='0'*64
                            else:value['source_changed']=True
                            (workspace/filename).write_text(json.dumps(value),encoding='utf-8')
                        elif filename:
                            changed=bytearray(original);changed[-8]^=1  # Includes an unrelated bottom-right sample.
                            (workspace/filename).write_bytes(changed)
                        judge(case)
                        self.assertEqual(next(c for c in case.checks if c['name']==check)['status'],'fail',case.checks)
                    finally:
                        if filename:(workspace/filename).write_bytes(original)

    def test_baseline_native_bytes_preview_and_manifest_without_engine_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configuration=driver();configuration['timeout_seconds']=90
            with patch('benchmark_baseline_photo.inspect_tiff') as inspection, \
                 patch('benchmark_driver.ExternalTrial.call',side_effect=AssertionError('Baseline launched Inkbolt')):
                row=run_external_task(None,root/'baseline','B10',1,'baseline',configuration,fake_tools())
            self.assert_photo(row);inspection.assert_called_once()
            checks={c['name']:c['status'] for c in row['checks']}
            for name in ENGINE_CHECKS['B10']:self.assertEqual(checks[name],'not_applicable')
            from benchmark_baseline_photo import judge_photo
            workspace=root/'baseline/workspace'
            original=(workspace/'edited.tiff').read_bytes()
            for fault in ('outside-sample','precision','preview','manifest'):
                with self.subTest(fault=fault):
                    case=ExternalTrial(None,root/('control-'+fault),'B10',1,'cli',CHECKS['B10'],arm='baseline')
                    case.judge_root=case.root;case.begin(PROMPT.read_text(encoding='utf-8'));case.root=workspace
                    case.driver_evidence=row['driver'];case.begin_judging()
                    saved={n:(workspace/n).read_bytes() for n in ('edited.tiff','preview.png','editable.json')}
                    try:
                        if fault in ('outside-sample','precision'):
                            data=bytearray(original)
                            offset=-8 if fault=='outside-sample' else len(data)-1920*1080*8+(766*1920+1150)*8
                            data[offset]^=1  # One low native bit, including inside the repaired patch.
                            (workspace/'edited.tiff').write_bytes(data)
                        elif fault=='preview':(workspace/'preview.png').write_bytes(b'not a PNG')
                        else:
                            value=manifest();value['transform'][4]=True
                            (workspace/'editable.json').write_text(json.dumps(value),encoding='utf-8')
                        with patch('benchmark_baseline_photo.inspect_tiff'):
                            judge_photo(case,fake_tools())
                        name='photo-preview' if fault=='preview' else 'edited-native-samples'
                        self.assertEqual(next(c for c in case.checks if c['name']==name)['status'],'fail')
                    finally:
                        for name,data in saved.items():(workspace/name).write_bytes(data)

    def test_budget_rejects_missing_and_over_limit_without_using_judge_memory(self):
        good=dict(available=True,scope=MEMORY_SCOPE,method=MEMORY_METHOD,reason=None,
                  peak_process_commit_bytes=MAX_PEAK_COMMIT_BYTES,peak_job_commit_bytes=MAX_PEAK_COMMIT_BYTES*2)
        for index,memory in enumerate((good,dict(good,peak_process_commit_bytes=MAX_PEAK_COMMIT_BYTES+1),
                                      unavailable_memory('not observed'))):
            with tempfile.TemporaryDirectory() as directory:
                case=ExternalTrial(None,Path(directory)/'budget','B10',1,'cli',CHECKS['B10'],arm='baseline')
                case.driver_evidence=dict(kind='synthetic',execution=dict(memory=memory));case.judge_root=case.root
                judge_memory(case)
                self.assertEqual(case.checks[0]['status'],'pass' if index==0 else 'fail')

    def test_pinned_tiff_inspection_rejects_failed_or_misreported_decoding(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            case=SimpleNamespace(root=Path(directory));good=dict(width=1920,height=1080,channels='rgba',depth='u16')
            with patch('benchmark_baseline_photo.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(good).encode())) as launch:
                inspect_tiff(case,fake_tools());self.assertEqual(launch.call_args.args[0][:2],[sys.executable,'-I'])
            for code,value in ((1,good),(0,{}),(0,dict(good,depth='u8'))):
                with patch('benchmark_baseline_photo.subprocess.run',return_value=SimpleNamespace(returncode=code,stdout=json.dumps(value).encode())):
                    with self.assertRaises(TaskFailure):inspect_tiff(case,fake_tools())


if __name__=='__main__':unittest.main()
