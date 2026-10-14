"""B20 independent decoding and optional exact-tool durable integration checks."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from test_cli import EXE,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from benchmark_handoff import HandoffTrial,fixture,solve,judge,PROMPT,original_frames,consumer_rgba,check_decoded
from benchmark_handoff_judge import durable_inputs,judge_retained
from benchmark_runtime import Trial,TaskFailure
from benchmark_tasks import CHECKS
from workload_cases import sha
from test_images_cli import png


class HandoffOracleTests(unittest.TestCase):
    def test_fixture_is_original_and_stable_without_starting_a_consumer(self):
        with tempfile.TemporaryDirectory() as directory:
            case=Trial(EXE,Path(directory)/'fixture','B20',1,'cli',CHECKS['B20']);fixture(case)
            self.assertEqual(case.sources,{'original.rgba':'102a9605bfd43710c16e26d327b37b1e3da44c25b34ab83b0d2617b351cbaf68'})
            self.assertEqual(case.calls,[])

    def test_decoder_rejects_pixels_audio_timing_and_stream_changes(self):
        frames=[consumer_rgba(original_frames()[0])]
        good=dict(rgba=b''.join(frames),pcm=bytes(1920*4),times=dict(frames=[dict(best_effort_timestamp_time='0')]),
            streams=[dict(codec_type='video',width=32,height=16,avg_frame_rate='25/1',codec_name='ffv1'),
                dict(codec_type='audio',codec_name='pcm_s16le',sample_rate='48000',channels=2)])
        check_decoded(good,frames)
        for fault in ('pixels','sound','clock','rate','codec','channels'):
            value=copy.deepcopy(good)
            if fault=='pixels':value['rgba']=bytes([value['rgba'][0]^1])+value['rgba'][1:]
            elif fault=='sound':value['pcm']=b'\x01'+value['pcm'][1:]
            elif fault=='clock':value['times']['frames'][0]['best_effort_timestamp_time']='0.002'
            elif fault=='rate':value['streams'][0]['avg_frame_rate']='24/1'
            elif fault=='codec':value['streams'][0]['codec_name']='other'
            else:value['streams'][1]['channels']=1
            with self.subTest(fault=fault),self.assertRaises(TaskFailure):check_decoded(value,frames)


@unittest.skipUnless(os.name=='nt' and os.environ.get('INKBOLT_B20_TEST_TOOLS'),
    'Requires explicit INKBOLT_B20_TEST_TOOLS and Windows consumer-tree accounting; run the documented real-tool gate')
class HandoffDurableTests(unittest.TestCase):
    def prepare(self,root):
        tools=json.loads(Path(os.environ['INKBOLT_B20_TEST_TOOLS']).read_text(encoding='utf-8'))
        case=HandoffTrial(EXE,root,'B20',1,'cli',CHECKS['B20'],consumer_tools=tools);self.addCleanup(case.close)
        fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));solve(case);case.begin_judging()
        self.assertEqual(case.checks,[]);case.results.clear();case.consumer.records.clear()
        return case

    def files(self,case):
        # Enumerate only produced artifact types, so documentation edits do not
        # invalidate this test through an accidental whole-repository wildcard.
        paths=[*case.root.rglob('*.json'),*case.root.rglob('*.png'),*case.root.rglob('*.rgba'),
            *case.root.rglob('*.mkv'),*case.root.rglob('*.sqlite3')]
        return {p.relative_to(case.root).as_posix():sha(p.read_bytes()) for p in paths if p.is_file() and
            'consumer' not in p.relative_to(case.root).parts}

    def test_judge_reopens_both_histories_without_solver_cache_or_mutating_deliveries(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'good');before=self.files(case)
            judge(case);row=case.finish()
            self.assertEqual(row['status'],'passed',row['checks'])
            self.assertTrue(row['judge_separated']);self.assertIsNone(row['first_verified_preview_seconds'])
            self.assertEqual((row['engine_commands'],row['judge_engine_commands'],row['total_engine_commands']),(15,11,36))
            self.assertEqual((row['consumer']['commands'],row['consumer']['judge_engine_commands']),(21,9))
            self.assertEqual(len(row['consumer']['judges']),20)
            after=self.files(case);self.assertEqual(before,{k:after[k] for k in before});case.close()

    def test_changed_retained_artifacts_and_observations_cannot_supply_a_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'negative');durable=durable_inputs(case)
            names=['after.json','review.json','preview.png','delivery-1-handoff.json','before-relink.json',
                'timeline-after.json','consumer-attempts.json','handoff-observations.json']
            originals={name:(case.root/name).read_bytes() for name in names}
            faults={'source':'reviewed-source-only','review':'reviewed-source-only','preview':'revised-preview',
                'predecessor':'pinned-successor','implicit':'no-implicit-relink','unrelated':'explicit-consumer-revision',
                'stale':'consumer-undo-retry','retry':'consumer-undo-retry','movie':'revised-timeline',
                'delivery':'immutable-deliveries','process':'consumer-processes','observation':'no-implicit-relink'}
            for fault,expected in faults.items():
                with self.subTest(fault=fault):
                    for name,raw in originals.items():(case.root/name).write_bytes(raw)
                    case.checks.clear();values=copy.deepcopy(durable)
                    if fault=='movie':
                        raw=values['movies']['revised']['rgba'];values['movies']['revised']['rgba']=bytes([raw[0]^1])+raw[1:]
                    elif fault=='preview':(case.root/'preview.png').write_bytes(png(1,1,bytes(4)))
                    else:
                        name={'source':'after.json','review':'review.json','predecessor':'delivery-1-handoff.json',
                            'implicit':'before-relink.json','unrelated':'timeline-after.json','stale':'consumer-attempts.json',
                            'retry':'consumer-attempts.json','delivery':'handoff-observations.json','process':'handoff-observations.json',
                            'observation':'handoff-observations.json'}[fault]
                        value=json.loads(originals[name])
                        if fault=='source':value['items'][1]['opacity']=.5
                        elif fault=='review':value['predicted_receipt']['revision']=2
                        elif fault=='predecessor':value['manifest']['previous']['sha256']='0'*64
                        elif fault in ('implicit','unrelated'):value['tracks']['tracks'][0]['clips'][1]['id']='changed'
                        elif fault=='stale':value['stale']['code']='OTHER'
                        elif fault=='retry':value['retry']['revision']=3
                        elif fault=='delivery':value['delivery_files']['delivery-0/compiled.mkv']='0'*64
                        elif fault=='process':value['consumer']['calls'][0]['active_processes']=1
                        else:value['records']['before-relink']['response']['result']['revision']=2
                        (case.root/name).write_text(json.dumps(value),encoding='utf-8')
                        if fault=='source':
                            values['final']=case.call('reopen-changed-source','document.validate',
                                document=dict(file_path=name,sha256=sha((case.root/name).read_bytes())))
                    judge_retained(case,**values)
                    self.assertIn(expected,[row['name'] for row in case.checks if row['status']=='fail'],case.checks)
            case.close()

    def test_equivalent_sources_and_reviews_keep_strict_revision_and_history_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'equivalent');durable=durable_inputs(case)
            sources={'before.json':'before','after.json':'final','historical-source.json':'historical'}
            for name,field in sources.items():
                path=case.root/name;original=path.read_bytes()
                for fault in ('none','missing-revision','different-revision','resolution','artwork','timing'):
                    with self.subTest(name=name,fault=fault):
                        value=json.loads(original);del value['resolution_ppi']
                        if fault=='missing-revision':del value['revision']
                        elif fault=='different-revision':value['revision']+=1
                        elif fault=='resolution':value['resolution_ppi']=72
                        elif fault=='artwork':value['items'][1]['opacity']=.5
                        elif fault=='timing':value['variants']['sequence']['frames'][0]['delay']['numerator']=4
                        path.write_text(json.dumps(value),encoding='utf-8');values=copy.deepcopy(durable)
                        values[field]=case.call('reopen-'+field+'-'+fault,'document.validate',
                            document=dict(file_path=name,sha256=sha(path.read_bytes())))
                        case.checks.clear();judge_retained(case,**values)
                        failures=[row['name'] for row in case.checks if row['status']=='fail']
                        if fault=='none':self.assertEqual(failures,[],case.checks)
                        else:self.assertIn('old-source-history' if field=='historical' else 'reviewed-source-only',failures)
                path.write_bytes(original)
            path=case.root/'review.json';original=path.read_bytes();review=json.loads(original)
            for fault in ('none','error','nonboolean','extra','missing-result','missing-proposal','different-proposal','array'):
                with self.subTest(review=fault):
                    value=dict(ok=True,result=copy.deepcopy(review))
                    if fault=='error':value=dict(ok=False,error=dict(code='INVALID_REQUEST'))
                    elif fault=='nonboolean':value['ok']=1
                    elif fault=='extra':value['extra']=True
                    elif fault=='missing-result':del value['result']
                    elif fault=='missing-proposal':del value['result']['proposal']
                    elif fault=='different-proposal':value['result']['proposal']['result_state_sha256']='0'*64
                    elif fault=='array':value=[]
                    path.write_text(json.dumps(value),encoding='utf-8');case.checks.clear()
                    judge_retained(case,**copy.deepcopy(durable))
                    failures=[row['name'] for row in case.checks if row['status']=='fail']
                    self.assertEqual(failures,[] if fault=='none' else ['reviewed-source-only'],case.checks)
            path.write_bytes(original)
            session=case.root/'.inkbolt/sessions'/(sha(b'work')+'.sqlite3');raw=session.read_bytes()
            duplicate=case.root/'duplicate';duplicate.mkdir();call=case.call
            for fault in ('missing','ambiguous','corrupt'):
                with self.subTest(store=fault):
                    case.call=lambda step,command,**arguments:call(fault+'-'+step,command,**arguments)
                    if fault=='missing':session.unlink()
                    elif fault=='ambiguous':(duplicate/session.name).write_bytes(raw)
                    else:session.write_bytes(b'not a session database')
                    try:
                        with self.assertRaises(TaskFailure):durable_inputs(case)
                    finally:
                        session.write_bytes(raw);(duplicate/session.name).unlink(missing_ok=True)
            case.close()

    def test_real_extra_revisions_in_either_engine_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'extra')
            case.call('extra-source','session.apply',session_id='work',request_id='extra',expected_revision=1,
                action=dict(type='edit',operations=[dict(op='transform',id='art',matrix=[1,0,0,1,1,0])]),response_mode='compact')
            case.consumer.phase='task'
            case.consumer.call('extra-consumer','session.undo',store_root=str(case.root/'cutbolt-store'),project_id='linked',
                request_id='extra',expected_revision=3)
            case.consumer.phase='judge';judge(case)
            failures=[row['name'] for row in case.checks if row['status']=='fail']
            self.assertIn('history-valid',failures);self.assertIn('consumer-undo-retry',failures);case.close()


if __name__=='__main__':unittest.main()
