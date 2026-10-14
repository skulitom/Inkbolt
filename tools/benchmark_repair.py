"""B16 original overflow fixture, reviewed repair and independent delivery judge."""
import base64
import copy
import json
from pathlib import Path

from benchmark_diagram import delivered
from benchmark_graphics import BLUE,GREEN,document,rectangle,pixels,png_check,store,source_snapshot
from benchmark_large_layout import retained_session_store
from benchmark_resources import reported_review
from benchmark_runtime import require,safe_name,strict_json
from benchmark_stores import retained_publication_store
from synthetic_font import geometric_font
from workload_cases import save,save_json,sha

PROMPT=Path(__file__).with_name('benchmark_prompts')/'B16.md'
PREVIEW_FILES={'repair-pixels':'review.png','preflight-delivery':'repaired.png'}
FONT_FAMILY='Inkbolt Repair Fixture'
LICENSE=b'Original synthetic Inkbolt font; permission to use and redistribute.'


def fixture(case):
    case.source('original.ttf',geometric_font());case.source('font-license.txt',LICENSE)
    case.source('renderer.ttf',geometric_font(family=FONT_FAMILY))


def initial_document(font,names=None):
    names=names or dict(document='repair',label='label',other='other',face='face')
    frame=dict(text='AA',width=12,height=24,wrap=False,style=dict(font_id=names['face'],size=20,fill=BLUE))
    return document(names['document'],'vector',48,32,fonts={names['face']:font},items=[
        dict(id=names['label'],content=dict(type='text',frame=frame)),rectangle(names['other'],32,20,8,8,GREEN)])


def original_font(case):
    return dict(sha256=case.sources['original.ttf'],license_sha256=case.sources['font-license.txt'],face_index=0,
                bytes=len(delivered(case,'original.ttf')))


def expected_picture():return pixels(48,32,[(1,2,8,14,BLUE),(13,2,8,14,BLUE),(32,20,8,8,GREEN)])


def diagnosis():
    return dict(status='fail',ready=False,code='TEXT_OVERFLOW',pointer='/items/0/content',suggested_width=24)


def reported_diagnosis(raw):
    value=strict_json(raw)
    require(isinstance(value,dict) and value==diagnosis() and value['ready'] is False,'Retained diagnosis differs')


def diagnosed(value,preflight,label):
    require(value['complete'] and value['valid_structure'] and value['status']=='fail' and preflight['ready'] is False and
        preflight['prepared_output'] is None,'Overflow must prevent preflight delivery')
    require(any(i['severity']=='error' and i['error']['code']=='TEXT_OVERFLOW' and i['error']['item_id']==label and
        i['location']['pointer']=='/items/0/content' and i['location']['retained_document_path']==[] and
        'text.inspect' in i['recovery']['commands'] for i in value['issues']),'Overflow was not located and actionable')
    require(any(i['error']['code']=='TEXT_OVERFLOW' and i['error']['item_id']==label and
        i['location']['command']=='document.publish' and 'text.inspect' in i['recovery']['commands'] for i in preflight['issues']),
        'Preflight did not preserve the actionable publication failure')


def delivery_identity(raw,prepared):
    return dict(file='repaired.png',ready=True,preflight_sha256=prepared,sha256=sha(raw))


def reviewed_fingerprint(frame,label):
    action=dict(type='edit',label='',operations=[dict(op='text',id=label,frame=frame)])
    return sha(json.dumps(dict(expected_revision=0,action=action),sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())


def solve(case):
    font=case.call('font','font.import',source_path='original.ttf',license_path='font-license.txt')
    doc=initial_document(font);saved=store(case,doc);before=source_snapshot(case,saved,'before')
    report=case.call('diagnose','document.check',document=saved)
    output=dict(file_name='repaired.png',format='png')
    failed=case.call('failed-preflight','document.preflight',document=saved,output=output)
    label=doc['items'][0]['id'];diagnosed(report,failed,label);save_json(case.root/'diagnostics.json',diagnosis())
    frame=copy.deepcopy(before['items'][0]['content']['frame']);frame['width']=24
    action=dict(type='edit',operations=[dict(op='text',id=label,frame=frame)])
    review=case.call('review','session.dry_run',session_id=saved['session_id'],request_id='repair',expected_revision=0,
        action=action,options=dict(preview=True),preview=True)
    save(case.root/'review.png',base64.b64decode(review['preview']['data'],validate=True))
    current=case.call('apply-repair','session.apply_proposal',proposal=review['proposal'],action=action,response_mode='compact')['document_ref']
    source_snapshot(case,current)
    ready=case.call('preflight','document.preflight',document=current,output=output)
    require(ready['ready'] and not (case.root/'repaired.png').exists(),'Preflight failed or wrote output')
    case.call('deliver','session.publish',session_id=saved['session_id'],expected_revision=current['revision'],
        output=output,receipt=dict(request_id='delivery'))
    case.call('verify-history','session.verify',session_id=saved['session_id'])
    save_json(case.root/'review.json',review)
    save_json(case.root/'delivery.json',delivery_identity(delivered(case,'repaired.png'),ready['prepared_output']['sha256']))
    save_json(case.root/'session.json',dict(session_id=saved['session_id'],before_revision=0,after_revision=current['revision'],
        creation='create',repair=review['proposal']['request_id'],publication='delivery'))


def judge(case):
    before=strict_json(delivered(case,'before.json'));after=strict_json(delivered(case,'editable.json'))
    require(len(before['items'])==2 and len(before['fonts'])==1,'Expected one text frame, one rectangle and one font')
    names=dict(document=before['id'],label=before['items'][0]['id'],other=before['items'][1]['id'],face=next(iter(before['fonts'])))
    normalized=case.call('judge-template','document.validate',document=initial_document(original_font(case),names))
    reopened={key:case.call('judge-reopen-'+key,'document.validate',document=dict(file_path=file,sha256=sha(delivered(case,file))))
        for key,file in [('before','before.json'),('after','editable.json')]}
    before,after=reopened['before'],reopened['after']
    def unchanged():
        require(type(after['revision']) is int and after['revision']==1,'Expected one committed repair')
        wanted=copy.deepcopy(normalized);wanted['revision']=1;wanted['items'][0]['content']['frame']['width']=24
        require(before==normalized and after==wanted,
            'Repair changed text, font, overflow policy, unrelated artwork or other controls')
        for suffix,name in (('.font','original.ttf'),('.license','font-license.txt')):
            require(delivered(case,'.inkbolt/fonts/'+case.sources[name]+suffix)==delivered(case,name),'Imported font/license bytes differ')
    require(case.check('no-collateral-edits',unchanged),'Repair source was not admitted')
    resources=dict(font_root='.inkbolt/fonts',asset_root=None)
    broken=case.call('judge-diagnose','document.check',document=before,resources=resources)
    output=dict(file_name='judge-repaired.png',format='png')
    require(not (case.root/output['file_name']).exists(),'Judge preflight output must be new')
    failed=case.call('judge-failed-preflight','document.preflight',document=before,resources=resources,output=output)
    def overflow():
        diagnosed(broken,failed,names['label'])
        reported_diagnosis(delivered(case,'diagnostics.json'))
    case.check('seeded-diagnosis',overflow)
    preview=case.call('judge-preview','document.preview',document=after,font_root='.inkbolt/fonts',options={},preview=True)
    def picture():
        for raw in (delivered(case,'review.png'),base64.b64decode(preview['artifact']['data'],validate=True)):
            png_check(raw,48,32,expected_picture())
    case.check('repair-pixels',picture)
    ready=case.call('judge-preflight','document.preflight',document=after,resources=resources,output=output)
    def delivery():
        raw=delivered(case,'repaired.png');value=strict_json(delivered(case,'delivery.json'))
        require(ready['ready'] and not (case.root/output['file_name']).exists() and
            value==delivery_identity(raw,ready['prepared_output']['sha256']) and value['ready'] is True and value['sha256']==value['preflight_sha256'],
            'Fresh preflight and retained delivery identity differ')
        png_check(raw,48,32,expected_picture())
    case.check('preflight-delivery',delivery)
    locator=strict_json(delivered(case,'session.json'))
    require(set(locator)=={'session_id','before_revision','after_revision','creation','repair','publication'} and
        type(locator['before_revision']) is int and type(locator['after_revision']) is int and
        locator['before_revision']==0 and locator['after_revision']==1,'Invalid repair session locator')
    for key in ('session_id','creation','repair','publication'):safe_name(locator[key])
    publication=case.call('judge-publication','publication.receipt',request_id=locator['publication'],
        receipt_root=retained_publication_store(case,locator['publication']))
    session_root=retained_session_store(case,locator['session_id'])
    receipts={key:case.call('judge-receipt-'+key,'session.receipt',session_root=session_root,session_id=locator['session_id'],request_id=locator[key])
        for key in ('creation','repair')}
    current=case.call('judge-current','session.read',session_root=session_root,session_id=locator['session_id'])
    verified=case.call('judge-history','session.verify',session_root=session_root,session_id=locator['session_id'])
    def history():
        result=publication['result']
        require(publication['state']=='complete' and result['sha256']==sha(delivered(case,'repaired.png')) and result['format']=='png' and
            result['revision']==1 and result['document_id']==after['id'],'Durable publication differs from the repaired output')
        old,new=receipts['creation'],receipts['repair'];review=reported_review(delivered(case,'review.json'));proposal=review['proposal']
        require(old['receipt']['action']=='create' and old['receipt']['revision']==0 and old['document']==before and
            new['receipt']['action']=='edit' and new['receipt']['revision']==1 and new['document']==after and
            old['resources']==new['resources']==current['resources']==review['proposed_resources'],'Saved repair changed source or resource bindings')
        require(review['dry_run'] is True and review['committed'] is False and review['source_changed'] is False and
            review['predicted_receipt']==new['receipt'] and proposal['version']==1 and
            proposal['request_fingerprint']==reviewed_fingerprint(after['items'][0]['content']['frame'],names['label']) and
            proposal['session_id']==locator['session_id'] and proposal['request_id']==locator['repair'] and
            proposal['expected_revision']==new['receipt']['from_revision']==0 and
            proposal['base_state_sha256']==old['receipt']['state_sha256'] and proposal['result_state_sha256']==new['receipt']['state_sha256'],
            'Retained review differs from the durable repair')
        require(base64.b64decode(review['preview']['data'],validate=True)==delivered(case,'review.png'),
            'Retained review image differs from the reviewed PNG')
        require(verified['valid'] and current['document']==after and verified['revision']==current['revision']==current['current_revision']==1 and
            current['state_sha256']==new['receipt']['state_sha256'],'Verified current history differs from the saved repair')
    case.check('history-valid',history)


def seeded_repair(case):
    fixture(case);case.begin(PROMPT.read_text(encoding='utf-8'));solve(case);case.begin_judging();judge(case)
    for check,name in PREVIEW_FILES.items():
        if any(c['name']==check and c['status']=='pass' for c in case.checks):case.verified_preview(delivered(case,name))
