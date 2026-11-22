"""B13 screen artifact, history and workspace checks on original deliveries."""
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_cli import EXE, ROOT
sys.path.insert(0, str(ROOT / 'tools'))
from benchmark_screen import solve, judge, PROMPT, NOTE, source_document, screen_color, delivery_identity, contains_source_note
from benchmark_runtime import Trial, TaskFailure
from benchmark_tasks import CHECKS
from test_images_cli import png, chunk


class ScreenJudgeTests(unittest.TestCase):
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

    def test_independently_named_source_passes_without_solver_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            case=self.prepare(Path(directory)/'independent',True);case.results.clear();case.begin_judging();judge(case)
            row=case.finish();self.assertEqual(row['status'],'passed',row);self.assertIsNone(row['first_verified_preview_seconds'])

    def test_source_note_allows_author_keys_but_requires_unchanged_value(self):
        variants=[('document',{'note':NOTE},True),('document',{'private':{'review':NOTE},'tags':['context']},True),
                  ('frame',{'tags':[NOTE]},True),('rectangle',{'note':NOTE},True),('document',{},False),
                  ('rectangle',{'note':'lost'},False),('frame',{'note':NOTE+' changed'},False)]
        self.assertFalse(contains_source_note({NOTE:'key only'}))
        self.assertTrue(contains_source_note({'tags':[NOTE]}))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);case=self.prepare(root/'workspace');source=json.loads((case.root/'editable.json').read_bytes())
            case.results.clear();case.begin_judging();original_call=case.call
            for index,(owner,metadata,valid) in enumerate(variants):
                with self.subTest(owner=owner,metadata=metadata):
                    doc=copy.deepcopy(source);del doc['metadata']
                    target={'document':doc,'frame':doc['items'][0],'rectangle':doc['items'][1]}[owner]
                    target['metadata']=metadata
                    doc['items'][0]['name']='Screen artboard'
                    # A label may be chosen freely, but cannot stand in for a metadata note.
                    doc['items'][1]['name']=NOTE
                    (case.root/'editable.json').write_text(json.dumps(doc),encoding='utf-8')
                    case.checks.clear();case.judge_root=root/str(index);case.judge_root.mkdir()
                    case.call=lambda step,command,**arguments:original_call(str(index)+'-'+step,command,**arguments)
                    if valid:
                        judge(case);self.assertEqual({c['name'] for c in case.checks if c['status']=='pass'},set(CHECKS['B13']))
                    else:
                        with self.assertRaises(TaskFailure):judge(case)
                        self.assertIn('editable-source',[c['name'] for c in case.checks if c['status']=='fail'])

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

    def test_precise_solid_checks_each_source_channel_before_png_quantization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = self.prepare(root / 'workspace')
            path = case.root / 'editable.json'
            source = json.loads(path.read_bytes())
            exact = [n / 255 for n in (20, 80, 150, 128)]
            original_call = case.call
            case.begin_judging()
            for index in range(5):
                with self.subTest(changed_channel=index if index < 4 else None):
                    channels = exact.copy()
                    if index < 4:
                        channels[index] = math.nextafter(channels[index], 1.0)
                    source['items'][1]['content']['fill'] = {'rgba': channels}
                    path.write_text(json.dumps(source), encoding='utf-8')
                    case.checks.clear()
                    case.judge_root = root / f'judge-{index}'
                    case.judge_root.mkdir()
                    case.call = lambda step, command, **kw: original_call(f'{index}-{step}', command, **kw)
                    if index < 4:
                        with self.assertRaises(TaskFailure):
                            judge(case)
                        self.assertIn('editable-source', [c['name'] for c in case.checks if c['status'] == 'fail'])
                    else:
                        judge(case)
                        self.assertEqual({c['name'] for c in case.checks if c['status'] == 'pass'}, set(CHECKS['B13']))

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
