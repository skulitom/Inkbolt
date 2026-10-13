"""B15 original missing/corrupt fixtures, resource-only solve and independent judge."""
import base64
import copy
import json
from pathlib import Path

from benchmark_diagram import delivered
from benchmark_graphics import BLUE,GREEN,document,pixels,png_check,store,source_snapshot
from benchmark_large_layout import retained_session_store
from benchmark_runtime import require,safe_name,strict_json
from test_images_cli import png,canonical
from workload_cases import save,save_json,sha

PROMPT=Path(__file__).with_name('benchmark_prompts')/'B15.md'
PREVIEW_FILES={'repaired-pixels':'preview.png'}
BROKEN=b'original deliberately corrupt cache fixture'


def source_document():
    assets={};items=[]
    for index,color in enumerate((BLUE,GREEN)):
        assets[f'asset-{index}']=dict(width=2,height=2,sha256=sha(canonical(2,2,bytes(color)*4)),storage=dict(type='stored'))
        items.append(dict(id=f'image-{index}',transform=[1,0,0,1,index*8,0],
            content=dict(type='image',asset_id=f'asset-{index}',width=8,height=8)))
    return document('resources','vector',16,8,assets=assets,items=items)


def cache_name(index):return source_document()['assets'][f'asset-{index}']['sha256']+'.rgba8'


def fixture(case):
    for index,color in enumerate((BLUE,GREEN)):case.source(f'original-{index}.png',png(2,2,bytes(color)*4))
    case.source('broken-assets/'+cache_name(0),BROKEN);case.seed(source_document())


def expected_diagnostics():
    return dict(status='fail',issues=[dict(code='ASSET_CORRUPT',pointer='/assets/asset-0'),
                                   dict(code='ASSET_MISSING',pointer='/assets/asset-1')])


def diagnostic_summary(value):
    require(value['complete'] and value['valid_structure'] and all(i['severity']=='error' and
        i['location']['retained_document_path']==[] for i in value['issues']),'Resource diagnostics must be complete and located')
    return dict(status=value['status'],issues=sorted([dict(code=i['error']['code'],pointer=i['location']['pointer'])
        for i in value['issues']],key=lambda i:i['pointer']))


def reported_diagnostics(raw):
    value=strict_json(raw)
    require(isinstance(value,dict) and set(value)=={'status','issues'} and isinstance(value['issues'],list) and
        all(isinstance(row,dict) and set(row)=={'code','pointer'} and all(isinstance(v,str) for v in row.values()) for row in value['issues']),
        'Invalid located diagnostic report')
    return dict(status=value['status'],issues=sorted(value['issues'],key=lambda row:row['pointer']))


def reviewed_fingerprint(resources,revision):
    return sha(json.dumps(dict(expected_revision=revision,action=dict(type='resources',resources=resources)),
        sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8'))


def expected_picture():return pixels(16,8,[(0,0,8,8,BLUE),(8,0,8,8,GREEN)])


def solve(case):
    seed=dict(file_path='source.json',sha256=sha(delivered(case,'source.json')))
    saved=store(case,seed,resources=dict(asset_root='broken-assets'))
    diagnosed=case.call('diagnose','document.check',document=saved)
    save_json(case.root/'diagnostics.json',diagnostic_summary(diagnosed))
    for i in range(2):case.call(f'repair-{i}','asset.import',source_path=f'original-{i}.png',store_root='repaired-assets')
    source_snapshot(case,saved,'before')
    action=dict(type='resources',resources=dict(asset_root='repaired-assets'))
    review=case.call('review','session.dry_run',session_id=saved['session_id'],request_id='repair',expected_revision=saved['revision'],action=action)
    current=case.call('apply-repair','session.apply_proposal',proposal=review['proposal'],action=action,response_mode='compact')['document_ref']
    source_snapshot(case,current)
    result=case.call('preview','document.preview',document=current,options={},preview=True)
    save(case.root/'preview.png',base64.b64decode(result['artifact']['data'],validate=True))
    case.call('old-diagnostics','document.check',document=saved)
    case.call('verify-history','session.verify',session_id=saved['session_id'])
    save_json(case.root/'review.json',review)
    save_json(case.root/'bindings.json',dict(before='broken-assets',after='repaired-assets'))
    save_json(case.root/'session.json',dict(session_id=saved['session_id'],before_revision=saved['revision'],after_revision=current['revision'],
        creation='create',repair=review['proposal']['request_id'],workspace_root=str(case.root.resolve())))


def preserved_broken(case):
    require(delivered(case,'broken-assets/'+cache_name(0))==BROKEN,'The original corrupt cache changed')
    require(not (case.root/'broken-assets'/cache_name(1)).exists() and not (case.root/'broken-assets'/cache_name(1)).is_symlink(),
        'The historical missing cache was silently repaired')


def replacements(case):
    for index,color in enumerate((BLUE,GREEN)):
        require(delivered(case,'repaired-assets/'+cache_name(index))==canonical(2,2,bytes(color)*4),
            'Replacement dimensions, samples or canonical identity differ')
    preserved_broken(case)


def binding_manifest(case):
    require(strict_json(delivered(case,'bindings.json'))==dict(before='broken-assets',after='repaired-assets'),
        'Only the intended resource binding may change')


def path_parts(value):
    require(isinstance(value,str),'A recorded resource path must be a string')
    if value.startswith('\\\\?\\'):value=value[4:]
    path=Path(value)
    require(path.is_absolute() and '..' not in path.parts,'Recorded resource paths must be absolute and normalized')
    return path


def judge(case):
    source=case.call('judge-template','document.validate',document=dict(file_path='source.json',sha256=case.sources['source.json']))
    before=strict_json(delivered(case,'before.json'));after=strict_json(delivered(case,'editable.json'))
    reopened={name:case.call('judge-reopen-'+name,'document.validate',document=dict(file_path=file,sha256=sha(delivered(case,file))))
        for name,file in [('before','before.json'),('after','editable.json')]}
    def unchanged():
        binding_manifest(case)
        for name,value in [('before',before),('after',after)]:
            expected=copy.deepcopy(source);expected['revision']=value['revision']
            require(value==expected==reopened[name],'Repair changed artwork, resources or unrelated document controls')
    require(case.check('unchanged-artwork',unchanged),'Resource repair source was not admitted')
    broken=case.call('judge-broken','document.check',document=before,resources=dict(asset_root='broken-assets',font_root=None))
    case.check('located-diagnostics',lambda:require(diagnostic_summary(broken)==reported_diagnostics(delivered(case,'diagnostics.json'))==expected_diagnostics(),
        'The corrupt and missing resources were not independently located'))
    case.check('verified-replacements',lambda:replacements(case))
    rendered=case.call('judge-render','document.preview',document=after,asset_root='repaired-assets',options={},preview=True)
    def picture():
        for raw in (delivered(case,'preview.png'),base64.b64decode(rendered['artifact']['data'],validate=True)):
            png_check(raw,16,8,expected_picture())
    case.check('repaired-pixels',picture)
    locator=strict_json(delivered(case,'session.json'))
    require(set(locator)=={'session_id','before_revision','after_revision','creation','repair','workspace_root'} and
        all(type(locator[k]) is int and locator[k]>=0 for k in ('before_revision','after_revision')) and
        locator['before_revision']==0 and locator['after_revision']>0,'Invalid repair session locator')
    for key in ('session_id','creation','repair'):safe_name(locator[key])
    session_root=retained_session_store(case,locator['session_id'])
    records={key:case.call('judge-receipt-'+key,'session.receipt',session_root=session_root,session_id=locator['session_id'],request_id=locator[key]) for key in ('creation','repair')}
    current=case.call('judge-current','session.read',session_root=session_root,session_id=locator['session_id'])
    old_saved=case.call('judge-old','document.validate',document=dict(session_root=session_root,session_id=locator['session_id'],revision=locator['before_revision']))
    verified=case.call('judge-history','session.verify',session_root=session_root,session_id=locator['session_id'])
    def bindings():
        old,new=records['creation'],records['repair'];base=path_parts(locator['workspace_root'])
        require(path_parts(old['resources']['asset_root'])==base/'broken-assets' and
            path_parts(new['resources']['asset_root'])==base/'repaired-assets' and
            old['resources']['font_root']==new['resources']['font_root'] and current['resources']==new['resources'],
            'Historical or current resource bindings changed beyond the reviewed root replacement')
        require(old['receipt']['action']=='create' and old['receipt']['revision']==0 and old['document']==before==old_saved and
            new['receipt']['action']=='resources' and new['document']==after and new['receipt']['revision']==locator['after_revision'],
            'The durable create/repair receipts do not retain their original artwork and revisions')
        review=strict_json(delivered(case,'review.json'));proposal=review['proposal']
        require(review['dry_run'] and review['committed'] is False and review['source_changed'] is False and
            review['predicted_receipt']==new['receipt'] and review['proposed_resources']==new['resources'] and
            proposal['version']==1 and proposal['request_fingerprint']==reviewed_fingerprint(new['resources'],0) and
            proposal['session_id']==locator['session_id'] and proposal['request_id']==locator['repair'] and
            proposal['expected_revision']==new['receipt']['from_revision']==0 and
            proposal['base_state_sha256']==old['receipt']['state_sha256'] and
            proposal['result_state_sha256']==new['receipt']['state_sha256'],'Retained review and committed resource change differ')
        preserved_broken(case)
    case.check('old-bindings-preserved',bindings)
    case.check('history-valid',lambda:require(verified['valid'] and current['document']==after and
        verified['revision']==current['revision']==current['current_revision']==locator['after_revision']==after['revision'] and
        before['revision']==locator['before_revision'] and current['state_sha256']==records['repair']['receipt']['state_sha256'],
        'Verified current history differs from the saved repair'))


def resource_repair(case):
    fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));solve(case);case.begin_judging();judge(case)
    if any(c['name']=='repaired-pixels' and c['status']=='pass' for c in case.checks):case.verified_preview(delivered(case,'preview.png'))
