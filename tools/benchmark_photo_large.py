"""Separate B10 50 MP lifecycle; the original B10 fixture and budget are unchanged."""
import base64
import copy
from pathlib import Path
import subprocess
import shutil

import benchmark_photo_large_fixture as fixture_data
import linux_process_memory
from benchmark_diagram import delivered
from benchmark_graphics import store,source_snapshot,png_check
from benchmark_large_layout import retained_session_store
from benchmark_photo import check_review,judge_memory,tiff_output
from benchmark_runtime import Trial,TaskFailure,require,safe_name,strict_json
from benchmark_tasks import ENGINE_CHECKS
from scale_oracles import check_native,check_tiff,file_hash
from workload_cases import document,save,save_json

VARIANT=fixture_data.VARIANT
PROMPT=Path(__file__).with_name('benchmark_prompts')/'B10-photo-50mp-v1.md'
PREVIEW_FILES={'photo-preview':'preview.png'}
ORIGINAL_TIFF_SHA256 = 'ad7b22173189ea6dd25cad6ce3f4e775242e536e6ee000ef0e2fc63f57e6e793'


class LinuxBudgetTrial(Trial):
    """An additional full-size reference experiment. The B10 judge stays the same."""

    def execute(self, argv, payload):
        return linux_process_memory.run(argv, payload, self.timeout,
                                        address_space_limit=fixture_data.MAX_PEAK_COMMIT_BYTES)

    def spawn(self, argv, **options):
        return linux_process_memory.Process(argv, address_space_limit=fixture_data.MAX_PEAK_COMMIT_BYTES,
                                            **options)

    def close(self):
        if self.server is not None and not self.server.closed and self.phase == 'judge':
            try:
                self.before_eof = dict(available=True, peak_virtual_bytes=self.server.process.virtual_peak_bytes())
            except (KeyError, ValueError, OSError, RuntimeError) as error:
                self.before_eof = dict(available=False, reason=str(error))
        super().close()

    def bounded_workflow(self):
        contract_fields(self)
        require(self.sources.get('original.tiff') == ORIGINAL_TIFF_SHA256,
                'The original 50 MP TIFF is required for a bounded workflow result')
        require(self.error is None and self.arm == 'reference' and self.benchmark_variant == VARIANT,
                'Requires a clean full-size reference workflow')
        statuses = {check['name']: check['status'] for check in self.checks}
        require(set(statuses) == set(self.required_checks) and len(statuses) == len(self.checks)
                and all(statuses[name] == 'pass' for name in self.required_checks if name != 'memory-budget'),
                'An original artifact, history or source check is missing or failed')
        solve = ('import', 'save', 'before', 'review', 'commit', 'edited', 'preview', 'edited-tiff',
                 'historical-tiff', 'undo', 'undo-source', 'redo', 'editable', 'verify-history')
        judge = ('judge-original-shape', 'judge-create-receipt', 'judge-edit-receipt', 'judge-undo-receipt',
                 'judge-redo-receipt', 'judge-preview', 'judge-edited', 'judge-historical', 'judge-history')
        require([(row['phase'], row['step']) for row in self.calls] ==
                [('task', step) for step in solve] + [('judge', step) for step in judge]
                and all(row['status'] == 'success' and row['response_observed'] and row['retry_of'] is None
                        for row in self.calls), 'Incomplete, unsuccessful or retried workflow')
        cli = [row for row in self.calls if self.transport == 'cli' or 'judge_workspace' in row]
        require(all(row['exit_code'] == 0 and row['timed_out'] is False for row in cli),
                'A CLI process failed or timed out')
        observations = [row['memory'] for row in cli]
        if self.transport == 'mcp':
            require(self.server is not None and self.server.closed, 'MCP server lifetime is incomplete')
            observations.append(self.server_memory)
        rss = linux_process_memory.resident_summary(observations)
        require(rss['resident_memory_complete'] and rss['resident_supervisor_sha256'] ==
                file_hash(Path(linux_process_memory.__file__)), 'Missing lifetime RSS or supervisor identity')
        cap = fixture_data.MAX_PEAK_COMMIT_BYTES
        expected = dict(method=linux_process_memory.LIMIT_METHOD, soft_bytes=cap, hard_bytes=cap)
        require(all(m.get('address_space_limit') == expected for m in observations),
                'Missing the enforced limit on an engine process')
        before_eof = getattr(self, 'before_eof', None)
        if before_eof and before_eof['available']:
            require(before_eof['peak_virtual_bytes'] <= cap, 'Server VmPeak exceeds the enforced limit')
        if statuses['memory-budget'] != 'pass':
            require(statuses['memory-budget'] == 'fail' and all(m['available'] is False
                    and m.get('peak_commit_bytes') is None for m in observations),
                    'A measured peak-commit failure cannot qualify for the bounded workflow')
        return dict(status='passed', engine_processes=len(observations), peak_resident_bytes=rss['peak_resident_bytes'])

    def extra_results(self):
        try:
            evidence = self.bounded_workflow()
        except (TaskFailure, KeyError, TypeError, ValueError, OSError) as error:
            evidence = dict(status='failed', reason=str(error))
        if self.transport == 'mcp':
            evidence['server_before_eof'] = getattr(self, 'before_eof', None)
        return dict(linux_address_space_workflow=dict(maximum_bytes=fixture_data.MAX_PEAK_COMMIT_BYTES, **evidence))


def profile(case):
    # Only direct unit probes set reduced extents. No driver or CLI setting can.
    return getattr(case,'photo_test_profile',(fixture_data.WIDTH,fixture_data.HEIGHT,fixture_data.REGION))


def fixture(case):
    fixture_data.write_fixture(case,*profile(case))


def contract_fields(case):
    require(profile(case)==(fixture_data.WIDTH,fixture_data.HEIGHT,fixture_data.REGION),
            'Reduced photo probes cannot be external trials')
    return dict(benchmark_variant=VARIANT)


def preview_options(case):
    _,_,r=profile(case)
    return dict(focus=dict(type='region',bounds=[r['x'],r['y'],r['x']+r['width'],r['y']+r['height']]),
                render_options=dict(evaluation='tiled'))


def solve(case):
    _,_,region=profile(case)
    imported=case.call('import','sample.import',source_path='original.tiff',id='photo',storage={},
                       color_policy='assume_srgb')
    save_json(case.root/'import-report.json',imported)
    saved=store(case,imported['document']);source_snapshot(case,saved,'before')
    session=saved['session_id']
    action=dict(type='edit',operations=[dict(op='retouch',id='pixels',options=dict(source_id='pixels',
        source_transform=[1,0,0,1,fixture_data.DONOR_DX,0],region=region,mode=dict(type='clone')))])
    review=case.call('review','session.dry_run',session_id=session,request_id='repair',expected_revision=0,
                     action=action,options=dict(include_document=True))
    save_json(case.root/'review.json',review)
    edited=case.call('commit','session.apply_proposal',proposal=review['proposal'],action=action,response_mode='compact')['document_ref']
    source_snapshot(case,edited,'edited')
    preview=case.call('preview','document.preview',document=edited,preview=True,options=preview_options(case))
    save(case.root/'preview.png',base64.b64decode(preview['artifact']['data'],validate=True))
    outputs={name:case.call(name+'-tiff','document.publish',document=ref,output=tiff_output(name+'.tiff'))
             for name,ref in [('edited',edited),('historical',saved)]}
    save_json(case.root/'publication-report.json',outputs)
    for name,revision,filename in [('undo',1,'undo-source'),('redo',2,'editable')]:
        result=case.call(name,'session.apply',session_id=session,request_id=name,expected_revision=revision,
                        action=dict(type=name),response_mode='compact')
        source_snapshot(case,result['document_ref'],filename)
    case.call('verify-history','session.verify',session_id=session)
    save_json(case.root/'session.json',dict(session_id=session,requests=dict(create='create',edit='repair',undo='undo',redo='redo')))


def image_file(case,name):
    path=case.root/name;width,height,_=profile(case)
    require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(case.root.resolve()) and
            path.stat().st_size<=width*height*8+1024*1024,'Missing, linked or oversized native TIFF')
    return path


def judge(case):
    width,height,region=profile(case)
    with fixture_data.Rows(image_file(case,'original.tiff'),width,height,region) as rows:
        _judge(case,rows,width,height)
    judge_memory(case,fixture_data.MAX_PEAK_COMMIT_BYTES)


def publication_workspace(case):
    if not hasattr(case,'judge_root'):return case.root,None
    # External judging cannot publish into the solver workspace or escape its
    # boundary. Reopen the already independently verified native blocks in an
    # owned judge workspace; engine resource hashes verify the streamed copies.
    root=case.judge_root/'native-publication';root.mkdir()
    assets=root/'.inkbolt/assets';assets.mkdir(parents=True)
    for source in sorted((case.root/'.inkbolt/assets').glob('*.native-tile')):
        require(source.is_file() and not source.is_symlink(),'Linked or missing judge source block')
        with source.open('rb') as before,(assets/source.name).open('xb') as after:
            shutil.copyfileobj(before,after)
    return root,root


def _judge(case,rows,width,height):
    names={'create':'before.json','edit':'edited.json','undo':'undo-source.json','redo':'editable.json'}
    snapshots={role:strict_json(delivered(case,name)) for role,name in names.items()}
    before,edited,current=(snapshots[k] for k in ('create','edit','redo'))
    original,changed=rows.manifest(),rows.manifest(True)
    imported=strict_json(delivered(case,'import-report.json'))
    wanted_before=case.call('judge-original-shape','document.validate',document=document(before['id'],'raster',width,height,
        items=[dict(id='pixels',content=dict(type='stored_samples',
        grid=dict(storage_version=2,base=original)))]))
    case.check('native-import',lambda:require(before==wanted_before and imported['document']==before and
        imported['source_sha256']==case.sources['original.tiff'] and imported['source_changed'] is False and
        imported['storage']['kind']=='native_tiles' and imported['storage']['manifest_sha256']==original['sha256'],
        'Import must retain the full native 50 MP source and interpretation'))
    def immutable():
        expected=set(original['tiles'])|set(changed['tiles'])
        files=list((case.root/'.inkbolt/assets').glob('*.native-tile'))
        require(all(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(case.root.resolve()) for p in files) and
                {p.name:file_hash(p) for p in files}=={h+'.native-tile':h for h in expected},
                'Native store contains missing, changed or unexpected blocks')
        check_native(case.root,before,width,height,rows.row)
        check_native(case.root,edited,width,height,lambda y:rows.row(y,True))
    case.check('immutable-tiles',immutable)
    locator=strict_json(delivered(case,'session.json'))
    require(isinstance(locator,dict) and set(locator)=={'session_id','requests'} and
            isinstance(locator['requests'],dict) and set(locator['requests'])==set(names),'Invalid photo session locator')
    safe_name(locator['session_id']);require(len(set(locator['requests'].values()))==4,'Photo request IDs must differ')
    session_root=retained_session_store(case,locator['session_id']);receipts={}
    for role in names:
        safe_name(locator['requests'][role])
        receipts[role]=case.call('judge-'+role+'-receipt','session.receipt',session_root=session_root,
                                session_id=locator['session_id'],request_id=locator['requests'][role])
    wanted=copy.deepcopy(wanted_before);wanted['revision']=1;wanted['items'][0]['content']['grid']['base']=changed
    pending=set(changed['tiles'])-set(original['tiles'])
    blocks={name:blob for name,blob in rows.blocks(True) if name in pending}
    transfer=dict(version=1,manifest=changed,pending=[dict(sha256=name,data_hex=blocks[name].hex()) for name in sorted(blocks)])
    review=strict_json(delivered(case,'review.json'))
    def exact():
        require(edited==wanted and receipts['edit']['document']==edited,'Only the exact native repair and revision may change')
        check_review(review,receipts,edited,transfer)
    case.check('editable-exact-patch',exact)
    for role,revision,source in [('undo',2,wanted_before),('redo',3,wanted)]:
        expected=copy.deepcopy(source);expected['revision']=revision
        case.check(role+'-editability',lambda role=role,expected=expected:require(
            snapshots[role]==expected and receipts[role]['document']==expected and receipts[role]['receipt']['action']==role,
            'Undo/redo must preserve the entire native document'))
    rendered=case.call('judge-preview','document.preview',document=current,preview=True,options=preview_options(case))
    def preview():
        r=rows.region;pixels=rows.preview()
        png_check(delivered(case,'preview.png'),r['width'],r['height'],pixels)
        png_check(base64.b64decode(rendered['artifact']['data'],validate=True),r['width'],r['height'],pixels)
    case.check('photo-preview',preview)
    publications=strict_json(delivered(case,'publication-report.json'))
    require(isinstance(publications,dict) and set(publications)=={'edited','historical'},'Missing native publication receipts')
    directory,judge_workspace=publication_workspace(case)
    for name,doc,is_edited in [('edited',current,True),('historical',before,False)]:
        options=tiff_output('judge-'+name+'.tiff');options['output_root']=str(directory.resolve())
        fresh=case.call('judge-'+name,'document.publish',document=doc,output=options,judge_workspace=judge_workspace)
        target=directory/options['file_name']
        def pixels(name=name,target=target,is_edited=is_edited,fresh=fresh):
            source=image_file(case,name+'.tiff')
            require(publications[name]['sha256']==file_hash(source) and fresh['sha256']==file_hash(target),
                    'TIFF delivery differs from its publication receipt')
            for path in (source,target):
                with fixture_data.Rows(path,width,height,rows.region):pass
                check_tiff(path,width,height,lambda y:rows.row(y,is_edited))
        case.check(name+'-native-samples',pixels)
    verified=case.call('judge-history','session.verify',session_root=session_root,session_id=locator['session_id'])
    case.check('history-valid',lambda:require(verified['valid'] and verified['revision']==3 and
        all(receipts[role]['document']==snapshots[role] and receipts[role]['receipt']['revision']==revision and
            receipts[role]['receipt']['request_id']==locator['requests'][role] for revision,role in enumerate(names)) and
        receipts['create']['document']==wanted_before,'History must bind original, review, undo, redo and final head'))


def judge_baseline(case,tools):
    width,height,region=profile(case)
    with fixture_data.Rows(image_file(case,'original.tiff'),width,height,region) as rows:
        def samples():
            manifest=strict_json(delivered(case,'editable.json'))
            require(manifest==dict(width=width,height=height,image='edited.tiff',depth='u16',channels='rgba',
                encoding='encoded_srgb',transform=[1,0,0,1,0,0]) and
                type(manifest['width']) is int and type(manifest['height']) is int and
                all(type(v) in (int,float) for v in manifest['transform']),'Wrong editable native TIFF manifest')
            path=image_file(case,'edited.tiff')
            with fixture_data.Rows(path,width,height,region):pass
            check_tiff(path,width,height,lambda y:rows.row(y,True))
            probe="from PIL import Image;import sys;im=Image.open(sys.argv[1]);assert im.format=='TIFF' and im.size==(int(sys.argv[2]),int(sys.argv[3])) and im.n_frames==1 and im.mode=='RGBA';assert im.tag_v2[262]==2 and im.tag_v2[258]==(16,16,16,16);im.load()"
            result=subprocess.run([tools['python']['path'],'-I','-c',probe,str(path),str(width),str(height)],
                                  capture_output=True,timeout=120)
            require(result.returncode==0 and not result.stderr,'Pinned Pillow cannot reopen the native TIFF')
        case.check('edited-native-samples',samples)
        case.check('photo-preview',lambda:png_check(delivered(case,'preview.png'),region['width'],region['height'],rows.preview()))
    for name in ENGINE_CHECKS['B10']:
        case.not_applicable(name,'The baseline retains its editable native TIFF; engine session/storage checks do not apply.')
    judge_memory(case,fixture_data.MAX_PEAK_COMMIT_BYTES)


def photograph(case):
    fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));solve(case)
    case.begin_judging();judge(case)
    if any(c['name']=='photo-preview' and c['status']=='pass' for c in case.checks):
        case.verified_preview(delivered(case,'preview.png'))
