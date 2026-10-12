"""B02 fixture, prompt, reference solver and independent delivered-artifact judge."""
import base64
from pathlib import Path

from benchmark_diagram import delivered
from benchmark_graphics import BLUE, GREEN, ORANGE, pixels, png_check, store, source_snapshot
from benchmark_runtime import require, strict_json
from workload_cases import rectangle, save, sha

PROMPT = Path(__file__).with_name('benchmark_prompts')/'B02.md'
COLORS = (BLUE, GREEN, ORANGE)
PREVIEW_FILES = {f'board-{i}-pixels':f'board-{i}.png' for i in range(3)}


def fixture(case):
    """This creation task has no source assets; the versioned prompt is its input."""


def solve(case):
    document = case.call('create', 'document.create', id='icons', kind='vector', width=112, height=32)
    for index, color in enumerate(COLORS):
        board = f'board-{index}'
        document['items'].append(dict(id=board, transform=[1,0,0,1,index*40,0],
            content=dict(type='frame', frame=dict(role='artboard', width=32, height=32))))
        item = rectangle(f'icon-{index}', 12, 11, 8, 10, color)
        item['parent'] = board
        document['items'].append(item)
    saved = store(case, document)
    source_snapshot(case, saved)
    for index in range(3):
        preview = case.call(f'preview-{index}', 'document.preview', document=saved,
                            options=dict(focus=dict(type='artboard', id=f'board-{index}')), preview=True)
        save(case.root/f'board-{index}.png', base64.b64decode(preview['artifact']['data'], validate=True))


def expected_board(index):
    return pixels(32, 32, [(12, 11, 8, 10, COLORS[index])])


def judge(case):
    raw = delivered(case, 'editable.json')
    actual = strict_json(raw)

    def structure():
        require((actual['width'], actual['height']) == (112, 32), 'Icon sheet canvas changed')
        items = actual['items']
        require([i['id'] for i in items] == ['board-0','icon-0','board-1','icon-1','board-2','icon-2'],
                'The task-specified stable IDs or board order changed')
        for index in range(3):
            board, icon = items[index*2:index*2+2]
            require(board.get('parent') is None and board['transform'] == [1,0,0,1,index*40,0],
                    'Board spacing or ownership changed')
            require(board['content']['type'] == 'frame' and board['content']['frame']['role'] == 'artboard'
                    and (board['content']['frame']['width'], board['content']['frame']['height']) == (32,32),
                    'Each board must remain an independent 32x32 artboard')
            require(icon['parent'] == f'board-{index}', 'Icon ownership changed')

    case.check('sheet-structure', structure)
    reopened = case.call('judge-reopen', 'document.validate', document=dict(file_path='editable.json', sha256=sha(raw)))
    for index in range(3):
        rendered = case.call(f'judge-board-{index}', 'document.preview',
            document=dict(file_path='editable.json', sha256=sha(raw)),
            options=dict(focus=dict(type='artboard', id=f'board-{index}')), preview=True)
        def picture(index=index, rendered=rendered):
            png_check(delivered(case, f'board-{index}.png'), 32, 32, expected_board(index))
            png_check(base64.b64decode(rendered['artifact']['data'], validate=True), 32, 32, expected_board(index))
        case.check(f'board-{index}-pixels', picture)
    case.check('editable-source', lambda: require(reopened == actual and
        all(i['content']['type'] == 'vector' for i in actual['items'][1::2]),
        'The delivered snapshot must reopen exactly with editable vector icons'))


def icons(case):
    fixture(case)
    case.begin(PROMPT.read_text(encoding='utf-8'))
    solve(case)
    case.begin_judging()
    judge(case)
    for check, filename in PREVIEW_FILES.items():
        if any(row['name'] == check and row['status'] == 'pass' for row in case.checks):
            case.verified_preview(delivered(case, filename))
