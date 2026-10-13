"""B13 exact straight alpha, private metadata and actual duplicate refusal."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from agent_benchmark import run_task
from benchmark_screen import solve,judge,PROMPT,source_document,expected_picture,screen_color,delivery_identity
from benchmark_baseline_screen import screen_shape,judge_screen
from benchmark_driver import run_external_task,workspace_files
from benchmark_runtime import Trial,TaskFailure
from benchmark_tasks import CHECKS
from benchmark_screen_client import SVG
from test_benchmark_driver import driver,fake_tools
from test_images_cli import png,chunk
from workload_cases import sha


class ScreenBenchmarkTests(unittest.TestCase):
    def prepare(self,root,independent=False):
        case=Trial(EXE,root,'B13',1,'cli',CHECKS['B13']);self.addCleanup(case.close)
        case.begin(PROMPT.read_text(encoding='utf-8'))
        if not independent:solve(case);return case
        original=case.call
        def authored(step,command,**arguments):
            if command=='preset.create':arguments['id']='transparent-poster'
            if arguments.get('session_id')=='work':arguments['session_id']='poster-session'
            return original('artist-'+step,command,**arguments)
        case.call=authored
        with patch('benchmark_screen.source_document',side_effect=lambda preset:source_document(preset,'artwork','board')):solve(case)
        return case

    def test_original_outcomes_on_cli_and_mcp_with_separate_judge_calls(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport),tempfile.TemporaryDirectory() as directory:
                row=run_task(EXE,Path(directory)/'reference','B13',1,transport)
                self.assertEqual(row['status'],'passed',row);self.assertEqual((row['engine_commands'],row['judge_engine_commands']),(6,6))
                self.assertEqual({c['name'] for c in row['checks']},set(CHECKS['B13'])|{'source-preservation'})
                self.assertTrue(row['judge_separated']);self.assertGreater(row['first_verified_preview_seconds'],0)
                probes=[call for call in row['calls'] if 'judge_workspace' in call]
                self.assertEqual(len(probes),3);self.assertTrue(all(call['phase']=='judge' and call['transport']=='cli' for call in probes))
                for direction in ('request','response'):
                    self.assertEqual(row[direction+'_bytes']+row['judge_'+direction+'_bytes'],
                        sum(p.stat().st_size for p in (Path(directory)/'reference').glob('*.'+direction+'.json')))

    def test_independently_named_source_passes_without_solver_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'independent',True);case.results.clear();case.begin_judging();judge(case)
            row=case.finish();self.assertEqual(row['status'],'passed',row);self.assertIsNone(row['first_verified_preview_seconds'])

    def test_changed_source_alpha_metadata_identity_and_collision_fail_independent_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'negative');root=Path(directory)
            pristine={name:(case.root/name).read_bytes() for name in ('editable.json','screen.png','delivery.json')}
            original_call=case.call;case.results.clear();case.begin_judging()
            for fault in ('geometry','alpha','private','pixels','metadata','identity','collision'):
                with self.subTest(fault=fault):
                    for name,data in pristine.items():(case.root/name).write_bytes(data)
                    case.checks.clear();case.judge_root=root/fault;case.judge_root.mkdir()
                    def scoped(step,command,**arguments):
                        value=original_call(fault+'-'+step,command,**arguments)
                        if fault=='collision' and step=='judge-collision':(case.judge_root/'judge-protected.png').write_bytes(b'overwritten')
                        return value
                    case.call=scoped
                    if fault in ('geometry','alpha','private'):
                        value=json.loads(pristine['editable.json'])
                        if fault=='geometry':value['items'][1]['content']['geometry']['width']=201
                        elif fault=='alpha':value['items'][1]['content']['fill'][3]=255
                        else:value['metadata']['private']['note']='lost'
                        (case.root/'editable.json').write_text(json.dumps(value),encoding='utf-8')
                    elif fault=='pixels':(case.root/'screen.png').write_bytes(png(1,1,bytes(4)))
                    elif fault=='metadata':
                        raw=pristine['screen.png'];raw=raw[:-12]+chunk(b'iTXt',b'note\0\0\0\0\0private')+raw[-12:]
                        (case.root/'screen.png').write_bytes(raw)
                        (case.root/'delivery.json').write_text(json.dumps(delivery_identity(raw)),encoding='utf-8')
                    elif fault=='identity':
                        value=json.loads(pristine['delivery.json']);value['sha256']='0'*64
                        (case.root/'delivery.json').write_text(json.dumps(value),encoding='utf-8')
                    try:judge(case)
                    except TaskFailure:pass
                    expected='editable-source' if fault in ('geometry','alpha','private') else 'transparent-pixels' if fault=='pixels' else 'screen-color' if fault=='metadata' else 'no-overwrite'
                    self.assertIn(expected,[c['name'] for c in case.checks if c['status']=='fail'],case.checks)

    def test_external_capture_can_be_rejudged_without_writing_into_solver_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configuration=driver()
            row=run_external_task(EXE,root/'live','B13',1,'model',configuration)
            self.assertEqual(row['status'],'passed',row);before=workspace_files(root/'live/workspace')
            (root/'live').rename(root/'capture')
            imported=run_external_task(EXE,root/'import','B13',1,'model',configuration,import_source=root/'capture')
            self.assertEqual(imported['status'],'passed',imported);self.assertFalse(imported['model_trials'])
            self.assertEqual(before,workspace_files(root/'capture/workspace'));self.assertEqual(before,workspace_files(root/'import/workspace'))

    def test_baseline_checks_fresh_pixels_and_actual_protected_bytes_without_engine_access(self):
        for fault in ('none','pixels','collision','overwritten','boolean'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                def rendered(case,tools,shape,raw):
                    probe=dict(collision=False if fault=='collision' else 1 if fault=='boolean' else True,before=sha(raw),after=sha(raw))
                    return (png(1,1,bytes(4)) if fault=='pixels' else raw),probe,(b'overwritten' if fault=='overwritten' else raw)
                with patch('benchmark_baseline_screen.render_and_probe',side_effect=rendered), \
                     patch('benchmark_driver.ExternalTrial.call',side_effect=AssertionError('Baseline launched Inkbolt')):
                    row=run_external_task(None,Path(directory)/'baseline','B13',1,'baseline',driver('--preview-usage'),fake_tools())
                self.assertEqual(row['status'],'passed' if fault=='none' else 'failed',row)
                self.assertEqual(row['first_verified_preview_seconds'],None if fault=='pixels' else .5)
                self.assertEqual(next(c for c in row['checks'] if c['name']=='editable-source')['status'],'not_applicable')

    def test_bounded_svg_rejects_changed_paint_metadata_paths_and_dimensions(self):
        good=screen_shape(SVG.encode());self.assertEqual(good['color'],[20,80,150,128])
        self.assertEqual(screen_shape(SVG.replace('width="1920"','width="1920.0"').encode()),good)
        for changed in (SVG.replace('width="1920"','width="999999"'),SVG.replace('0.5019607843137255','1'),
                        SVG.replace('#145096','#0a284b'),SVG.replace('original private source note','lost'),
                        SVG.replace('<rect ','<rect href="../external" '),'< !DOCTYPE svg>'.replace('< !','<!')+SVG):
            with self.subTest(changed=changed),self.assertRaises((TaskFailure,ValueError)):screen_shape(changed.encode())

    def test_color_oracle_rejects_missing_duplicate_invalid_tags_and_private_records(self):
        raw=png(1,1,bytes([20,80,150,128]));screen_color(raw)
        with self.assertRaises(TaskFailure):screen_color(png(1,1,bytes(4),tagged=False))
        for kind,data in ((b'sRGB',b'\0'),(b'iCCP',b'profile'),(b'tEXt',b'note\0private'),(b'iTXt',b'note\0\0\0\0\0private'),
                          (b'zTXt',b'compressed'),(b'eXIf',b'private'),(b'acTL',bytes(8))):
            with self.subTest(kind=kind),self.assertRaises(TaskFailure):screen_color(raw[:-12]+chunk(kind,data)+raw[-12:])
        for data in (b'',b'\x04',b'\0\0'):
            raw=png(1,1,bytes(4),tagged=False,extra=((b'sRGB',data),))
            with self.subTest(data=data),self.assertRaises(TaskFailure):screen_color(raw)

    def test_separate_workspace_is_judge_only_confined_and_explicitly_measured(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);case=Trial(EXE,root/'workspace','B13',1,'cli',[]);self.addCleanup(case.close)
            case.begin('Original workspace boundary fixture')
            with self.assertRaises(TaskFailure):case.call('task-override','capabilities',judge_workspace=case.root)
            case.begin_judging()
            with self.assertRaises(TaskFailure):case.call('outside','capabilities',judge_workspace=root)
            case.judge_root=root/'judge';case.judge_root.mkdir()
            case.call('owned','capabilities',judge_workspace=case.judge_root)
            row=case.calls[-1];self.assertEqual(row['phase'],'judge');self.assertEqual(row['transport'],'cli')
            self.assertEqual(row['judge_workspace'],str(case.judge_root.resolve()))


if __name__=='__main__':unittest.main()
