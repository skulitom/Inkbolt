"""B09 original local defect, prompt, reference solve and independent pixel judge."""
import base64
import copy
from pathlib import Path

from benchmark_diagram import delivered
from benchmark_graphics import png_check, store, apply, source_snapshot
from benchmark_large_layout import retained_session_store
from benchmark_runtime import require, safe_name, strict_json
from workload_cases import document, save, save_json, sha

PROMPT = Path(__file__).with_name('benchmark_prompts')/'B09.md'
PREVIEW_FILES = {'repaired-pixels':'preview.png','historical-pixels':'historical.png'}


def repaired_pixels():
    return bytes(v for y in range(16) for x in range(16)
        for v in (20+(x%4)*40,30+(y%4)*40,10+((x+y)%4)*50,255))


def original_pixels():
    original = bytearray(repaired_pixels())
    for y in (10,11): original[(y*16+10)*4:(y*16+12)*4] = bytes([255,0,255,255])*2
    return bytes(original)


def fixture(case):
    case.seed(document('retouch','raster',16,16,items=[dict(id='pixels',content=dict(
        type='raster',width=16,height=16,rgba_hex=original_pixels().hex()))]))


def solve(case):
    original = store(case,dict(file_path='source.json',sha256=sha(delivered(case,'source.json'))))
    edited = apply(case,'retouch',0,[dict(op='retouch',id='pixels',options=dict(source_id='pixels',
        region=dict(x=10,y=10,width=2,height=2),source_transform=[1,0,0,1,-8,-8],sampling='nearest',mode=dict(type='clone')))])
    current = edited['document_ref']; source_snapshot(case,current)
    for name,reference in (('preview',current),('historical',original)):
        result = case.call(name,'document.preview',document=reference,preview=True)
        save(case.root/(name+'.png'),base64.b64decode(result['artifact']['data'],validate=True))
    case.call('verify-history','session.verify',session_id=original['session_id'])
    save_json(case.root/'session.json',dict(session_id=original['session_id'],original_revision=0,current_revision=current['revision']))


def judge(case):
    raw = delivered(case,'editable.json'); actual = strict_json(raw)
    original = case.call('judge-source','document.validate',document=dict(file_path='source.json',sha256=case.sources['source.json']))
    reopened = case.call('judge-reopen','document.validate',document=dict(file_path='editable.json',sha256=sha(raw)))
    def repair():
        require(type(actual['revision']) is int and actual['revision'] > 0 and actual == reopened,'Missing or changed editable revision')
        require(len(actual['items']) == 1 and actual['items'][0]['content']['type'] == 'raster' and
            bytes.fromhex(actual['items'][0]['content']['rgba_hex']) == repaired_pixels(),'Repair or unaffected samples differ')
        unchanged = copy.deepcopy(actual); unchanged['revision'] = original['revision']
        unchanged['items'][0]['content']['rgba_hex'] = original['items'][0]['content']['rgba_hex']
        require(unchanged == original,'Only the defect samples and revision may change')
    case.check('exact-local-repair',repair)
    rendered = case.call('judge-preview','document.preview',document=reopened,preview=True)
    def picture():
        png_check(delivered(case,'preview.png'),16,16,repaired_pixels())
        png_check(base64.b64decode(rendered['artifact']['data'],validate=True),16,16,repaired_pixels())
    case.check('repaired-pixels',picture)
    locator = strict_json(delivered(case,'session.json'))
    require(isinstance(locator,dict) and set(locator) == {'session_id','original_revision','current_revision'},'Invalid session locator')
    safe_name(locator['session_id'])
    require(type(locator['original_revision']) is int and locator['original_revision'] == 0 and
        type(locator['current_revision']) is int and locator['current_revision'] == actual['revision'] > 0,'Invalid original/current revisions')
    session_root = retained_session_store(case,locator['session_id'])
    old = case.call('judge-original-revision','document.validate',document=dict(session_root=session_root,session_id=locator['session_id'],revision=0))
    current = case.call('judge-current-revision','document.validate',document=dict(session_root=session_root,session_id=locator['session_id'],revision=actual['revision']))
    historical = case.call('judge-historical','document.preview',document=old,preview=True)
    def historical_picture():
        require(old == original,'The saved original differs from the source fixture')
        png_check(delivered(case,'historical.png'),16,16,original_pixels())
        png_check(base64.b64decode(historical['artifact']['data'],validate=True),16,16,original_pixels())
    case.check('historical-pixels',historical_picture)
    verified = case.call('judge-history','session.verify',session_root=session_root,session_id=locator['session_id'])
    case.check('history-valid',lambda:require(verified['valid'] and verified['revision'] == actual['revision'] and
        old == original and current == actual,'History must bind the exact original fixture, delivery and current head'))


def local_retouch(case):
    fixture(case); case.begin(PROMPT.read_text(encoding='utf-8')); solve(case)
    case.begin_judging(); judge(case)
    for check,filename in PREVIEW_FILES.items():
        if any(row['name'] == check and row['status'] == 'pass' for row in case.checks):
            case.verified_preview(delivered(case,filename))
