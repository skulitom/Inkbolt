"""B03 source fixture, prompt, reference solve and delivery/history judge."""
import base64
import copy
from pathlib import Path

from benchmark_diagram import delivered
from benchmark_graphics import BLUE, pixels, png_check, store, apply, source_snapshot
from benchmark_runtime import require, safe_name, strict_json
from workload_cases import document, rectangle, save, save_json, sha

PROMPT = Path(__file__).with_name('benchmark_prompts')/'B03.md'
PREVIEW_FILES = {'large-layout-pixels':'preview.png', 'historical-pixels':'historical.png'}


def fixture(case):
    case.seed(document('large-layout', 'vector', 1000, 500, resource_profile='large_vector',
        items=[rectangle(f'cell-{i}', (i%100)*10, (i//100)*10, 6, 6, BLUE) for i in range(5000)]))


def solve(case):
    original = store(case, dict(file_path='source.json', sha256=sha(delivered(case, 'source.json'))))
    case.call('inspect-target', 'document.inspect.page', document=original,
        options=dict(view=dict(collection='items', ids=['cell-2473'], fields=['geometry','transform','bounds'])))
    moved = apply(case, 'move', 0, [dict(op='transform', id='cell-2473', matrix=[1,0,0,1,1,1], space='world')])
    current = moved['document_ref']
    source_snapshot(case, current)
    for name, reference in (('preview',current), ('historical',original)):
        result = case.call(name, 'document.preview', document=reference,
            options=dict(render_options=dict(evaluation='tiled')), preview=True)
        save(case.root/(name+'.png'), base64.b64decode(result['artifact']['data'], validate=True))
    case.call('verify-history', 'session.verify', session_id=original['session_id'])
    save_json(case.root/'session.json', dict(session_id=original['session_id'],
        original_revision=original['revision'], current_revision=current['revision']))


def expected_picture(moved=True):
    rectangles = [((i%100)*10, (i//100)*10, 6, 6, BLUE) for i in range(5000)]
    if moved: rectangles[2473] = (731, 241, 6, 6, BLUE)
    return pixels(1000, 500, rectangles)


def retained_session_store(case, session_id):
    """Locate the delivered session inside the capture; the engine still verifies its contents."""
    root = case.root.resolve()
    name = sha(session_id.encode('utf-8'))+'.sqlite3'
    stores = []
    for path in sorted(root.rglob('*.sqlite3')):
        if path.name != name:
            continue
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root)
                and not any((root/parent).is_symlink() for parent in path.relative_to(root).parents),
                'Linked or external session store')
        stores.append(path.parent.relative_to(root).as_posix())
    require(len(stores) == 1, 'Missing or ambiguous captured session store for the delivered session ID')
    return stores[0]


def judge(case):
    raw = delivered(case, 'editable.json')
    actual = strict_json(raw)
    original = case.call('judge-source', 'document.validate',
        document=dict(file_path='source.json', sha256=case.sources['source.json']))
    reopened = case.call('judge-reopen', 'document.validate',
        document=dict(file_path='editable.json', sha256=sha(raw)))

    def structure():
        require(type(actual['revision']) is int and actual['revision'] > 0, 'Missing edited revision')
        expected = copy.deepcopy(original)
        expected['revision'] = actual['revision']
        expected['items'][2473]['transform'] = [1,0,0,1,1,1]
        require(actual == reopened == expected, 'The requested translation must be the only content change')
    case.check('only-target-changed', structure)
    rendered = case.call('judge-preview', 'document.preview',
        document=dict(file_path='editable.json', sha256=sha(raw)),
        options=dict(render_options=dict(evaluation='tiled')), preview=True)
    def picture():
        png_check(delivered(case, 'preview.png'), 1000, 500, expected_picture())
        png_check(base64.b64decode(rendered['artifact']['data'], validate=True), 1000, 500, expected_picture())
    case.check('large-layout-pixels', picture)

    locator = strict_json(delivered(case, 'session.json'))
    require(isinstance(locator, dict) and set(locator) == {'session_id','original_revision','current_revision'},
            'Expected a session ID and the original/current revision numbers')
    safe_name(locator['session_id'])
    require(type(locator['original_revision']) is int and locator['original_revision'] == 0 and
            type(locator['current_revision']) is int and locator['current_revision'] == actual['revision'] > 0,
            'Session revisions do not identify the original and delivered snapshots')
    session_root = retained_session_store(case, locator['session_id'])
    old_ref = dict(session_root=session_root, session_id=locator['session_id'], revision=locator['original_revision'])
    new_ref = dict(session_root=session_root, session_id=locator['session_id'], revision=locator['current_revision'])
    old = case.call('judge-original-revision', 'document.validate', document=old_ref)
    current = case.call('judge-current-revision', 'document.validate', document=new_ref)
    # Re-render the exact saved snapshot read above. This resource-free fixture
    # needs no captured absolute resource roots when its workspace is relocated.
    historical = case.call('judge-historical', 'document.preview', document=old,
        options=dict(render_options=dict(evaluation='tiled')), preview=True)
    def history_picture():
        require(old == original, 'The original saved revision differs from the fixture')
        png_check(delivered(case, 'historical.png'), 1000, 500, expected_picture(False))
        png_check(base64.b64decode(historical['artifact']['data'], validate=True), 1000, 500, expected_picture(False))
    case.check('historical-pixels', history_picture)
    verified = case.call('judge-history', 'session.verify', session_root=session_root, session_id=locator['session_id'])
    case.check('history-valid', lambda: require(verified['valid'] and verified['revision'] == actual['revision']
        and old == original and current == actual,
        'Saved history must be valid and contain the exact original and delivered snapshots'))


def large_layout(case):
    fixture(case)
    case.begin(PROMPT.read_text(encoding='utf-8'))
    solve(case)
    case.begin_judging()
    judge(case)
    for check, filename in PREVIEW_FILES.items():
        if any(row['name'] == check and row['status'] == 'pass' for row in case.checks):
            case.verified_preview(delivered(case, filename))
