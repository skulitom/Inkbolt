"""Independent B19 recovery oracles; Unix keeps job verification unsupported."""
import json
from contextlib import closing
from pathlib import Path
import sys
import tempfile
import unittest

from test_cli import EXE,ROOT
from platform_support import require_capability
sys.path.insert(0,str(ROOT/'tools'))
from benchmark_recovery import fixture,solve,judge,durable_inputs,judge_retained,PROMPT
from benchmark_recovery_runtime import RecoveryTrial
from benchmark_tasks import CHECKS
from benchmark_runtime import Trial
from test_images_cli import png


class RecoveryFixtureTests(unittest.TestCase):
    def test_original_texture_identity_is_platform_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            case=Trial(EXE,Path(directory)/'fixture','B19',1,'cli',CHECKS['B19']);fixture(case)
            self.assertEqual(case.sources,{'original.png':'c85754243823a9cd10679d0c8220d45aade52b8149a2a491f752316b776a77f6'})
            self.assertEqual(case.calls,[])


class RecoveryJudgeTests(unittest.TestCase):
    def setUp(self):require_capability(self,'jobs')

    def prepare(self,root):
        case=RecoveryTrial(EXE,root,'B19',1,'cli',CHECKS['B19']);self.addCleanup(case.close)
        fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));solve(case);case.results.clear();case.begin_judging()
        return case

    def test_judge_reopens_durable_state_without_solver_cache_and_preserves_files(self):
        with tempfile.TemporaryDirectory() as directory,closing(self.prepare(Path(directory)/'retained')) as case:
            names=['original.png','preview.png','recovered.png','editable.json','attempts.json','recovery-observations.json']
            before={name:(case.root/name).read_bytes() for name in names};identity=(case.root/'recovered.png').stat().st_ino
            judge(case);row=case.finish()
            self.assertEqual(row['status'],'passed',{k:row[k] for k in ('status','error','checks','missing_checks')})
            self.assertIsNone(row['first_verified_preview_seconds']);self.assertTrue(row['judge_separated'])
            self.assertEqual(before,{name:(case.root/name).read_bytes() for name in names})
            self.assertEqual(identity,(case.root/'recovered.png').stat().st_ino)

    def test_wrong_attempts_pixels_artwork_and_fault_observations_fail(self):
        with tempfile.TemporaryDirectory() as directory,closing(self.prepare(Path(directory)/'negative')) as case:
            # Reuse the same freshly observed durable state while testing only
            # mutations to retained client artifacts. Real DB changes below
            # and the transport test rerun every engine oracle.
            durable=durable_inputs(case)
            names=['attempts.json','editable.json','preview.png','recovered.png','recovery-observations.json']
            good={name:(case.root/name).read_bytes() for name in names}
            faults={'cancel':'active-cancellation','inspection':'interrupted-unpublished','receipt':'single-publication-no-overwrite',
                'current':'revision-resource-pinning','review-pixels':'review-pixels','output-pixels':'recovered-pixels',
                'boundary':'active-cancellation','process':'interrupted-unpublished','checkpoint':'interrupted-unpublished','physical':'single-publication-no-overwrite',
                'partial':'no-partial-final'}
            for fault,expected in faults.items():
                with self.subTest(fault=fault):
                    for name,raw in good.items():(case.root/name).write_bytes(raw)
                    case.checks.clear()
                    if fault in ('cancel','inspection','receipt'):
                        value=json.loads(good['attempts.json'])
                        if fault=='cancel':value['cancelled']['attempt']=2
                        elif fault=='inspection':value['interrupted-wait']['state']='running'
                        else:value['result-replay']['sha256']='0'*64
                        (case.root/'attempts.json').write_text(json.dumps(value),encoding='utf-8')
                    elif fault=='current':
                        value=json.loads(good['editable.json']);value['items'][0]['opacity']=.5
                        (case.root/'editable.json').write_text(json.dumps(value),encoding='utf-8')
                    elif fault in ('review-pixels','output-pixels'):
                        (case.root/('preview.png' if fault=='review-pixels' else 'recovered.png')).write_bytes(png(1,1,bytes(4)))
                    else:
                        value=json.loads(good['recovery-observations.json']);events=value['events']
                        if fault=='boundary':next(e for e in events if e['kind']=='fault-boundary' and e['request_id']=='cancel')['outputs_absent']=False
                        elif fault=='process':next(e for e in events if e['kind']=='interrupted-tree-exited')['runner']['created']+=1
                        elif fault=='checkpoint':next(e for e in events if e['kind']=='output-checkpoint' and e['label']=='after-inspection')['snapshot']['jobs']['recover']['phase']='running'
                        elif fault=='physical':next(e for e in events if e['kind']=='output-checkpoint' and e['label']=='after-replays')['outputs']['recovered.png']['identity'][0]+=1
                        else:next(e for e in events if e['kind']=='output-observed')['bytes']-=1
                        (case.root/'recovery-observations.json').write_text(json.dumps(value),encoding='utf-8')
                    judge_retained(case,**durable)
                    self.assertIn(expected,[c['name'] for c in case.checks if c['status']=='fail'],case.checks)

    def test_extra_real_revision_is_not_hidden_by_correct_delivery(self):
        with tempfile.TemporaryDirectory() as directory,closing(self.prepare(Path(directory)/'extra')) as case:
            case.call('extra','session.apply',session_id='work',request_id='extra',expected_revision=1,
                action=dict(type='edit',operations=[dict(op='transform',id='badge',matrix=[1,0,0,1,1,0],space='world')]),response_mode='compact')
            judge(case)
            self.assertIn('history-valid',[c['name'] for c in case.checks if c['status']=='fail'])
            self.assertIn('revision-resource-pinning',[c['name'] for c in case.checks if c['status']=='fail'])


if __name__=='__main__':unittest.main()
