"""B05 shared-palette fixture, prompt, reference solve and independent judge."""
import base64
import copy
from pathlib import Path

from benchmark_diagram import delivered
from benchmark_graphics import BLUE, GREEN, ORANGE, pixels, png_check, store, apply, source_snapshot
from benchmark_runtime import require, safe_name, strict_json
from workload_cases import document, rectangle, save, save_json, sha

PROMPT = Path(__file__).with_name('benchmark_prompts')/'B05.md'
PREVIEW_FILES = {'palette-pixels':'preview.png', 'historical-pixels':'historical.png'}


def swatch(color):
    return dict(name='Shared', definition=dict(type='process',
        color=dict(space='srgb', components=[v/255 for v in color[:3]])))


def fixture(case):
    items = [rectangle('first',2,4,8,8), rectangle('second',12,4,8,8), rectangle('unrelated',22,4,8,8,GREEN)]
    for item in items[:2]: item['content']['fill'] = dict(swatch='shared')
    case.seed(document('palette','vector',32,16,swatches=dict(shared=swatch(BLUE)),items=items))


def solve(case):
    original = store(case, dict(file_path='source.json',sha256=sha(delivered(case,'source.json'))))
    case.call('inspect-palette','swatch.inspect',document=original)
    edited = apply(case,'recolor',0,[dict(op='swatch',id='shared',swatch=swatch(ORANGE))])
    current = edited['document_ref']
    source_snapshot(case,current)
    for name, reference in (('preview',current),('historical',original)):
        result = case.call(name,'document.preview',document=reference,preview=True)
        save(case.root/(name+'.png'),base64.b64decode(result['artifact']['data'],validate=True))
    case.call('verify-history','session.verify',session_id=original['session_id'])
    save_json(case.root/'session.json',dict(session_id=original['session_id'],
        original_revision=original['revision'],current_revision=current['revision']))


def expected_picture(recolored=True):
    color = ORANGE if recolored else BLUE
    return pixels(32,16,[(2,4,8,8,color),(12,4,8,8,color),(22,4,8,8,GREEN)])


def judge(case):
    raw = delivered(case,'editable.json')
    actual = strict_json(raw)
    original = case.call('judge-source','document.validate',
        document=dict(file_path='source.json',sha256=case.sources['source.json']))
    reopened = case.call('judge-reopen','document.validate',document=dict(file_path='editable.json',sha256=sha(raw)))

    def dependencies():
        require(type(actual['revision']) is int and actual['revision'] > 0,'Missing edited revision')
        expected = copy.deepcopy(original)
        expected['revision'] = actual['revision']
        expected['swatches']['shared'] = swatch(ORANGE)
        require(actual == reopened == expected,
            'Only the shared swatch color may change; live references and unrelated state must survive')
    case.check('live-dependencies',dependencies)
    rendered = case.call('judge-preview','document.preview',
        document=dict(file_path='editable.json',sha256=sha(raw)),preview=True)
    def picture():
        png_check(delivered(case,'preview.png'),32,16,expected_picture())
        png_check(base64.b64decode(rendered['artifact']['data'],validate=True),32,16,expected_picture())
    case.check('palette-pixels',picture)

    locator = strict_json(delivered(case,'session.json'))
    require(isinstance(locator,dict) and set(locator) == {'session_id','original_revision','current_revision'},
        'Expected a session ID and the original/current revision numbers')
    safe_name(locator['session_id'])
    require(type(locator['original_revision']) is int and locator['original_revision'] == 0 and
        type(locator['current_revision']) is int and locator['current_revision'] == actual['revision'] > 0,
        'Session revisions do not identify the original and delivered snapshots')
    old = case.call('judge-original-revision','document.validate',
        document=dict(session_id=locator['session_id'],revision=locator['original_revision']))
    current = case.call('judge-current-revision','document.validate',
        document=dict(session_id=locator['session_id'],revision=locator['current_revision']))
    # Render the loaded, resource-free snapshot so captured sessions remain
    # judgeable after relocation without trusting their old absolute roots.
    historical = case.call('judge-historical','document.preview',document=old,preview=True)
    def history_picture():
        require(old == original,'The original saved revision differs from the fixture')
        png_check(delivered(case,'historical.png'),32,16,expected_picture(False))
        png_check(base64.b64decode(historical['artifact']['data'],validate=True),32,16,expected_picture(False))
    case.check('historical-pixels',history_picture)
    verified = case.call('judge-history','session.verify',session_id=locator['session_id'])
    case.check('history-valid',lambda:require(verified['valid'] and verified['revision'] == actual['revision']
        and old == original and current == actual,
        'Saved history must be valid and contain the exact original and delivered snapshots'))


def palette(case):
    fixture(case)
    case.begin(PROMPT.read_text(encoding='utf-8'))
    solve(case)
    case.begin_judging()
    judge(case)
    for check, filename in PREVIEW_FILES.items():
        if any(row['name'] == check and row['status'] == 'pass' for row in case.checks):
            case.verified_preview(delivered(case,filename))
