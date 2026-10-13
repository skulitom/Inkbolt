"""Original fabricated metadata controls; these are not actual model trials."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from benchmark_comparison import (CATEGORIES,POLICY,canonical,compare,digest,load_report,markdown,metric,rate)
from benchmark_tasks import SUITE,TASKS,CHECKS,ENGINE_CHECKS,BASELINE_NOT_APPLICABLE,check_class


H=digest(b'original synthetic metadata fixture')
TOOLS=dict(resvg=dict(path='/pinned/resvg',sha256=H,version='0.47.0'),
           python=dict(path='/pinned/python',sha256=H),pillow=dict(version='12.3.0',files_sha256=H))


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(canonical(value))


def suite(root,arm,tasks=('B01',),reps=5,kind='synthetic',edit=None):
    candidates={'original.py':H};driver=dict(config_sha256=H,files={'client.py':dict(sha256=H)})
    p=dict(arm=arm,suite=SUITE,client=dict(id='original-metadata-fixture',version='1'),model=dict(id='fixture',settings={}),
        driver_kind=kind,driver=driver,candidate_files=candidates,candidate_sha256=digest(canonical(candidates)),
        environment=dict(system='Fixture',machine='original'),conditions='Original test fixture; no model executed',
        selected_tasks=list(tasks),repetitions=reps,build=dict(executable_sha256=H) if arm=='model' else None,
        baseline_tools=TOOLS if arm=='baseline' else None,consumer_tools={k:dict(sha256=H) for k in ('cutbolt','ffmpeg','ffprobe')})
    rows=[]
    for task in tasks:
        for rep in range(1,reps+1):
            base=root/f'{rep:02d}-{task}'
            if arm=='baseline' and task in BASELINE_NOT_APPLICABLE:
                row=dict(task=task,repetition=rep,arm=arm,status='not_applicable',reason=BASELINE_NOT_APPLICABLE[task])
                save(base/'result.json',row);rows.append(row);continue
            contract=dict(task=task,repetition=rep,arm=arm,client=p['client'],model=p['model'],kind=kind,
                prompt_sha256=H,fixtures={'original.txt':H},engine_sha256=H if arm=='model' else None,
                baseline_tools={k:{a:b for a,b in v.items() if a!='path'} for k,v in TOOLS.items()} if arm=='baseline' else None)
            if task=='B20':contract['consumer_tools']=p['consumer_tools']
            checks=[dict(name=n,status='not_applicable' if arm=='baseline' and n in ENGINE_CHECKS[task] else 'pass',
                         check_class=check_class(task,n),reason='Engine-specific metadata control') for n in CHECKS[task]+('source-preservation',)]
            usage=dict(source='client_reported',model_calls=4,token_usage=dict(input_tokens=80,output_tokens=20),agent_seconds=2)
            row=dict(task=task,repetition=rep,arm=arm,status='passed',error=None,driver_failure=None,
                prompt_sha256=H,sources=contract['fixtures'],checks=checks,**{k:v for k,v in usage.items() if k!='source'},
                memory_complete=False,peak_commit_bytes=None,invalid_calls=0,retries=0,engine_commands=3 if arm=='model' else 0)
            if edit:edit(row,contract,usage)
            identity=digest(canonical(contract));result=dict(schema_version=1,contract_sha256=identity,kind=kind,client=p['client'],
                model=p['model'],transcript='transcript.jsonl',observations=usage)
            evidence=base/'evidence';save(evidence/'request.json',dict(contract=contract,contract_sha256=identity))
            save(evidence/'driver-result.json',result);(evidence/'transcript.jsonl').write_bytes(b'{"fixture":true}\n')
            execution=dict(status='passed',seconds=3);workspace={'original.txt':H}
            capture=dict(contract=contract,result_sha256=digest(canonical(result)),transcript_sha256=digest(b'{"fixture":true}\n'),
                execution=execution,host=p['environment'],workspace_files=workspace,driver_identity=driver)
            save(evidence/'capture.json',capture)
            row['driver']=dict(kind=kind,client=p['client'],model=p['model'],observations={k:v for k,v in usage.items() if k!='source'},
                contract_sha256=identity,result_sha256=capture['result_sha256'],transcript_sha256=capture['transcript_sha256'],
                workspace_sha256=digest(canonical(workspace)),original_host=p['environment'],execution=execution)
            save(base/'result.json',row);rows.append(row)
    report=dict(schema_version=2,suite=SUITE,arm=arm,transport='external-client',provenance=p,
                selected_tasks=list(tasks),repetitions=reps,inputs_unchanged=True,rows=rows)
    save(root/'report.json',report);return root/'report.json'


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def compare(self,model_options=None,baseline_options=None):
        m=suite(self.root/'model','model',**(model_options or {}));b=suite(self.root/'baseline','baseline',**(baseline_options or {}))
        return compare(load_report(m,'model'),load_report(b,'baseline'))

    def test_creation_tasks_match_empty_asset_manifests_but_reject_missing_asset_differences(self):
        def empty(row,contract,usage):
            contract['fixtures']={};row['sources']={}
        options=dict(tasks=('B02','B13'),edit=empty)
        result=self.compare(options,options)
        for row in result['tasks']:
            if row['task'] in ('B02','B13'):
                self.assertTrue(row['minimum_repetitions_met'],row['issues'])
                self.assertEqual(row['arms']['model']['artifact']['passed'],5)
        result=self.compare(options,dict(tasks=('B02','B13')))
        for row in result['tasks']:
            if row['task'] in ('B02','B13'):
                self.assertFalse(row['comparable'])
                self.assertTrue(any('different fixtures' in message for message in row['issues']))

    def test_equal_small_samples_are_signals_not_completion_or_equivalence(self):
        result=self.compare();row=result['tasks'][0]
        self.assertFalse(result['decision_ready']);self.assertFalse(result['actual_model_benchmark_complete'])
        self.assertEqual(row['arms']['model']['artifact']['passed'],5);self.assertEqual(row['arms']['baseline']['artifact']['passed'],5)
        self.assertLess(row['arms']['model']['artifact']['wilson_95'][0],.57)
        self.assertEqual(result['losing_tasks'][0]['reasons'],['baseline_artifact_success_at_least_model'])
        self.assertFalse(row['cost_comparison']['model_calls']['excessive'])
        self.assertEqual(len(result['tasks']),20);self.assertIn('synthetic_or_mixed',markdown(result))

    def test_engine_failure_keeps_artifact_score_but_fails_workflow_and_is_retained(self):
        def edit(row,contract,usage):
            if row['repetition']==2:
                row.update(status='failed',error='Original synthetic engine-history failure')
                next(c for c in row['checks'] if c['name']=='editable-source')['status']='fail'
        result=self.compare(dict(edit=edit));value=result['tasks'][0]['arms']['model']
        self.assertEqual(value['artifact']['passed'],5);self.assertEqual(value['workflow']['passed'],4)
        self.assertEqual(value['engine_checks']['editable-source']['failed'],1)
        self.assertEqual(len(result['failures']),1);self.assertEqual(result['failures'][0]['repetition'],2)

    def test_failed_artifact_and_missing_check_are_not_successful_cost_pairs(self):
        def edit(row,contract,usage):
            row['status']='failed';row['checks']=[c for c in row['checks'] if c['name']!='diagram-pixels']
        result=self.compare(dict(edit=edit));row=result['tasks'][0]
        self.assertEqual(row['arms']['model']['artifact']['passed'],0)
        self.assertEqual(row['arms']['model']['metrics']['model_calls']['all_attempts']['observed'],5)
        self.assertEqual(row['cost_comparison']['model_calls']['successful_pairs'],0)
        self.assertEqual(len(result['failures']),5);self.assertIn('diagram-pixels',result['failures'][0]['missing_checks'])

    def test_twofold_costs_need_complete_success_pairs_and_do_not_double_count_tokens(self):
        def edit(row,contract,usage):
            usage.update(model_calls=8,token_usage=dict(input_tokens=180,output_tokens=20,cached_input_tokens=99,reasoning_tokens=12))
            row.update(model_calls=usage['model_calls'],token_usage=usage['token_usage'])
        result=self.compare(dict(edit=edit));cost=result['tasks'][0]['cost_comparison']
        self.assertEqual(cost['input_output_tokens']['ratio'],2);self.assertEqual(cost['model_calls']['ratio'],2)
        self.assertEqual(len(result['losing_tasks'][0]['reasons']),3)

    def test_unknown_and_zero_usage_remain_distinct(self):
        def model(row,contract,usage):
            usage.update(model_calls=8,token_usage=None);row.update(model_calls=8,token_usage=None)
        def baseline(row,contract,usage):
            usage['model_calls']=0;row['model_calls']=0
            if row['repetition']==3:usage['token_usage']=None;row['token_usage']=None
        result=self.compare(dict(edit=model),dict(edit=baseline));row=result['tasks'][0]
        self.assertTrue(row['cost_comparison']['model_calls']['baseline_zero'])
        self.assertIsNone(row['cost_comparison']['model_calls']['ratio'])
        self.assertTrue(row['cost_comparison']['model_calls']['excessive'])
        self.assertFalse(row['cost_comparison']['input_output_tokens']['complete'])
        self.assertEqual(row['arms']['model']['metrics']['input_output_tokens']['all_attempts']['unknown'],5)

    def test_four_trials_cannot_emit_losing_signals(self):
        result=self.compare(dict(reps=4),dict(reps=4))
        self.assertTrue(result['tasks'][0]['comparable']);self.assertFalse(result['tasks'][0]['minimum_repetitions_met'])
        self.assertFalse(result['losing_tasks'])

    def test_full_metadata_gate_requires_genuine_kind_and_all_fixed_tasks(self):
        # These files only exercise acceptance logic; no model was executed.
        result=self.compare(dict(tasks=tuple(TASKS),kind='model'),dict(tasks=tuple(TASKS),kind='model'))
        self.assertTrue(result['matched_model_baseline_complete']);self.assertFalse(result['matched_cutbolt_comparison'])
        self.assertEqual(len(result['losing_tasks']),17)
        self.assertIsNone(result['tasks'][16]['arms']['baseline']['artifact'])
        self.assertEqual(result['tasks'][16]['arms']['baseline']['statuses']['not_applicable'],5)
        self.assertEqual(sorted(sum((list(v) for v in CATEGORIES.values()),[])),sorted(TASKS))

    def test_missing_trial_stays_in_denominator_and_blocks_matching(self):
        m=suite(self.root/'model','model');b=suite(self.root/'baseline','baseline')
        raw=json.loads(m.read_bytes());raw['rows'].pop();save(m,raw)
        result=compare(load_report(m,'model'),load_report(b,'baseline'));row=result['tasks'][0]
        self.assertEqual(row['arms']['model']['artifact']['total'],5);self.assertEqual(row['arms']['model']['artifact']['passed'],4)
        self.assertFalse(row['comparable']);self.assertEqual(result['failures'][0]['status'],'missing')

    def test_different_prompt_fixture_settings_host_or_conditions_block_matching(self):
        for field in ('prompt_sha256','fixtures','model','original_host','conditions','candidate_sha256','inputs_unchanged'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);m=load_report(suite(root/'m','model'),'model');b=load_report(suite(root/'b','baseline'),'baseline')
                if field in ('prompt_sha256','fixtures'):b['contracts'][('B01',1)][field]={'changed':H} if field=='fixtures' else digest(b'changed')
                elif field=='original_host':b['rows'][('B01',1)]['driver'][field]={'changed':True}
                elif field=='inputs_unchanged':b['report'][field]=False
                else:b['report']['provenance'][field]='changed'
                result=compare(m,b);self.assertFalse(result['tasks'][0]['comparable']);self.assertFalse(result['losing_tasks'])

    def test_altered_transcript_or_retained_result_cannot_score(self):
        m=suite(self.root/'model','model');b=suite(self.root/'baseline','baseline')
        (m.parent/'01-B01/evidence/transcript.jsonl').write_bytes(b'changed')
        raw=json.loads((m.parent/'02-B01/result.json').read_bytes());raw['model_calls']=999;save(m.parent/'02-B01/result.json',raw)
        result=compare(load_report(m,'model'),load_report(b,'baseline'))
        self.assertEqual(result['tasks'][0]['arms']['model']['artifact']['passed'],3)
        self.assertEqual(len(result['failures']),2);self.assertFalse(result['tasks'][0]['comparable'])
        self.assertEqual(result['tasks'][0]['arms']['model']['metrics']['model_calls']['all_attempts']['observed'],3)
        self.assertEqual(result['tasks'][0]['arms']['model']['engine_checks']['editable-source']['unverified'],2)

    def test_inputs_cannot_drift_between_otherwise_matched_repetitions(self):
        m=load_report(suite(self.root/'model','model'),'model');b=load_report(suite(self.root/'baseline','baseline'),'baseline')
        for arm in (m,b):arm['contracts'][('B01',2)]['fixtures']={'different.txt':H}
        result=compare(m,b)
        self.assertIn('Inputs or original host vary across repetitions',result['tasks'][0]['issues'])
        self.assertFalse(result['losing_tasks'])

    def test_passing_row_without_capture_cannot_vanish_from_failure_ledger(self):
        m=suite(self.root/'model','model');b=suite(self.root/'baseline','baseline');raw=json.loads(m.read_bytes())
        raw['rows'][0]['driver']=None;save(m.parent/'01-B01/result.json',raw['rows'][0]);save(m,raw)
        result=compare(load_report(m,'model'),load_report(b,'baseline'))
        self.assertEqual(result['tasks'][0]['arms']['model']['artifact']['passed'],4)
        self.assertIn('lacks captured',result['failures'][0]['evidence_error']);self.assertFalse(result['losing_tasks'])

    def test_duplicate_trial_wrong_check_class_and_false_pass_reject(self):
        path=suite(self.root/'model','model');original=json.loads(path.read_bytes())
        for change in ('duplicate','class','missing'):
            with self.subTest(change=change):
                raw=copy.deepcopy(original)
                if change=='duplicate':raw['rows'].append(raw['rows'][0])
                elif change=='class':raw['rows'][0]['checks'][0]['check_class']='engine'
                else:raw['rows'][0]['checks'].pop()
                save(path,raw)
                with self.assertRaises(ValueError):load_report(path,'model')

    def test_prepared_trials_and_client_failures_never_become_passes(self):
        def edit(row,contract,usage):row.update(status='prepared')
        result=self.compare(dict(edit=edit),dict(edit=edit))
        self.assertFalse(result['tasks'][0]['comparable']);self.assertFalse(result['losing_tasks'])
        path=self.root/'model/report.json';raw=json.loads(path.read_bytes())
        for row in raw['rows']:
            row.update(status='failed',driver=None,driver_failure='Client deadline expired',model_calls=None,token_usage=None,agent_seconds=None)
            save(path.parent/f"{row['repetition']:02d}-B01/result.json",row)
        save(path,raw)
        data=load_report(path,'model');self.assertFalse(data['issues'])
        result=compare(data,load_report(self.root/'baseline/report.json','baseline'))
        self.assertEqual(result['tasks'][0]['arms']['model']['artifact']['passed'],0)
        self.assertEqual(sum(f['driver_failure']=='Client deadline expired' for f in result['failures']),5)
        self.assertFalse(result['actual_model_benchmark_complete'])

    def test_baseline_engine_pass_is_rejected(self):
        path=suite(self.root/'baseline','baseline');raw=json.loads(path.read_bytes())
        next(c for c in raw['rows'][0]['checks'] if c['name']=='editable-source')['status']='pass'
        save(path,raw)
        with self.assertRaisesRegex(ValueError,'explicitly inapplicable'):load_report(path,'baseline')

    def test_intervals_handle_zero_full_and_partial_counts(self):
        self.assertIsNone(rate(0,0)['rate']);self.assertEqual(rate(0,5)['wilson_95'][0],0)
        self.assertAlmostEqual(rate(1,5)['wilson_95'][0],.0362241086)
        self.assertAlmostEqual(rate(1,5)['wilson_95'][1],.6244653702)

    def test_malformed_counts_and_unavailable_memory_never_become_numeric_observations(self):
        for value in (True,-1,1.5,float('nan'),float('inf')):
            with self.subTest(value=value),self.assertRaises(ValueError):metric({'model_calls':value},'model_calls')
        self.assertIsNone(metric(dict(memory_complete=False,peak_commit_bytes=123),'peak_commit_bytes'))
        self.assertIsNone(metric(dict(external_process_tree_memory=dict(available=False,peak_job_commit_bytes=123)),
                                 'client_tree_peak_job_commit_bytes'))
        self.assertEqual(metric(dict(agent_seconds=1.5),'agent_seconds'),1.5)

    def test_cli_is_create_only_and_preserves_input_reports(self):
        m=suite(self.root/'model','model');b=suite(self.root/'baseline','baseline');before=(m.read_bytes(),b.read_bytes())
        output=self.root/'comparison';argv=[sys.executable,str(ROOT/'tools/compare_agent_benchmarks.py'),
            '--model-report',str(m),'--baseline-report',str(b),'--output-root',str(output)]
        result=subprocess.run(argv,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue((output/'summary.md').is_file())
        report=(output/'report.json').read_bytes()
        self.assertNotEqual(subprocess.run(argv,capture_output=True,timeout=10).returncode,0)
        self.assertEqual((output/'report.json').read_bytes(),report);self.assertEqual(before,(m.read_bytes(),b.read_bytes()))


if __name__=='__main__':unittest.main()
