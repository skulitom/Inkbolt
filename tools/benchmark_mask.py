"""B08 foreground fixture, prompt, reference solve and independent mask judge."""
import base64
import copy
from pathlib import Path

from benchmark_diagram import delivered
from benchmark_graphics import png_check, store, apply, source_snapshot
from benchmark_large_layout import retained_session_store
from benchmark_runtime import require, safe_name, strict_json
from workload_cases import document, save, save_json, sha

PROMPT = Path(__file__).with_name('benchmark_prompts')/'B08.md'
PREVIEW_FILES = {'masked-pixels':'preview.png','historical-pixels':'historical.png'}
POLYGON = [[4,3],[12,3],[12,7],[8,7],[8,13],[4,13]]


def original_pixels():
    return bytes(v for y in range(16) for x in range(16) for v in (x*11,y*13,(x+y)*7,255))


def selected_pixels():
    return bytes(255 if (4 <= x < 12 and 3 <= y < 7) or (4 <= x < 8 and 7 <= y < 13) else 0
        for y in range(16) for x in range(16))


def expected_picture():
    original = original_pixels()
    return b''.join(original[i*4:i*4+4] if alpha else bytes(4) for i,alpha in enumerate(selected_pixels()))


def fixture(case):
    case.seed(document('foreground','raster',16,16,items=[dict(id='pixels',content=dict(
        type='raster',width=16,height=16,rgba_hex=original_pixels().hex()))]))


def solve(case):
    original = store(case,dict(file_path='source.json',sha256=sha(delivered(case,'source.json'))))
    edited = apply(case,'mask',0,[dict(op='selection_shape',boundary=dict(shape='polygon',points=POLYGON)),
        dict(op='mask_from_selection',id='pixels',linked=True)])
    current = edited['document_ref']
    source_snapshot(case,current)
    for name,reference in (('preview',current),('historical',original)):
        result = case.call(name,'document.preview',document=reference,preview=True)
        save(case.root/(name+'.png'),base64.b64decode(result['artifact']['data'],validate=True))
    case.call('verify-history','session.verify',session_id=original['session_id'])
    save_json(case.root/'session.json',dict(session_id=original['session_id'],original_revision=0,current_revision=current['revision']))


def judge(case):
    raw = delivered(case,'editable.json'); actual = strict_json(raw)
    original = case.call('judge-source','document.validate',document=dict(file_path='source.json',sha256=case.sources['source.json']))
    reopened = case.call('judge-reopen','document.validate',document=dict(file_path='editable.json',sha256=sha(raw)))
    def selection():
        require(actual['selection']['width'] == 16 and actual['selection']['height'] == 16 and
            bytes.fromhex(actual['selection']['gray_hex']) == selected_pixels(),'Selection coverage differs from the original L-shaped polygon')
    case.check('selection-coverage',selection)
    def retained():
        require(type(actual['revision']) is int and actual['revision'] > 0 and actual == reopened,'Missing or changed editable revision')
        require(len(actual['items']) == 1 and actual['items'][0]['content']['type'] == 'raster' and
            bytes.fromhex(actual['items'][0]['content']['rgba_hex']) == original_pixels() and
            actual['items'][0]['mask']['linked'] is True,'Mask must retain every original sample and remain linked to its layer')
        unchanged = copy.deepcopy(actual); unchanged['revision'] = original['revision']
        unchanged.pop('selection'); unchanged['items'][0].pop('mask')
        # Hex case is an encoding choice, not a pixel change.
        unchanged['items'][0]['content']['rgba_hex'] = original['items'][0]['content']['rgba_hex']
        require(unchanged == original,'Only selection, linked mask and revision may change')
    case.check('retained-pixels',retained)
    rendered = case.call('judge-preview','document.preview',document=reopened,preview=True)
    def picture():
        png_check(delivered(case,'preview.png'),16,16,expected_picture())
        png_check(base64.b64decode(rendered['artifact']['data'],validate=True),16,16,expected_picture())
    case.check('masked-pixels',picture)
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


def foreground_mask(case):
    fixture(case); case.begin(PROMPT.read_text(encoding='utf-8')); solve(case)
    case.begin_judging(); judge(case)
    for check,filename in PREVIEW_FILES.items():
        if any(row['name'] == check and row['status'] == 'pass' for row in case.checks):
            case.verified_preview(delivered(case,filename))
