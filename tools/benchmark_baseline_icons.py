"""Independent SVG viewport admission and pinned-renderer B02 judging."""
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from benchmark_baseline import _numbers, _point, _transform
from benchmark_diagram import delivered
from benchmark_graphics import png_check
from benchmark_icons import expected_board
from benchmark_runtime import require
from workload_cases import save

NS = '{http://www.w3.org/2000/svg}'


def svg_boards(raw):
    require(len(raw) <= 1024*1024 and b'<!DOCTYPE' not in raw.upper(),
            'B02 SVG is too large or has a document type')
    root = ET.fromstring(raw)
    require(root.tag == NS+'svg' and set(root.attrib) <= {'width','height','viewBox','version'},
            'Expected the bounded outer SVG canvas')
    require(_numbers(root.get('width','')) == [112] and _numbers(root.get('height','')) == [32]
            and _numbers(root.get('viewBox','0 0 112 32')) == [0,0,112,32], 'Icon sheet canvas changed')
    boards = list(root)
    require(len(boards) == 3, 'Expected three independent SVG boards')
    standalone = []
    for index, board in enumerate(boards):
        require(board.tag == NS+'svg' and set(board.attrib) <=
                {'id','x','y','width','height','viewBox','overflow'}, 'Unexpected board element or attributes')
        require(board.get('id') == f'board-{index}' and _numbers(board.get('x','0')) == [index*40]
                and _numbers(board.get('y','0')) == [0], 'Board IDs, order or spacing changed')
        require(_numbers(board.get('width','')) == [32] and _numbers(board.get('height','')) == [32]
                and _numbers(board.get('viewBox','0 0 32 32')) == [0,0,32,32]
                and board.get('overflow','hidden') == 'hidden', 'Board viewport changed')
        require(len(board) == 1, 'Each board must own exactly one editable icon')
        icon = board[0]
        require(icon.tag == NS+'rect' and not list(icon) and icon.get('id') == f'icon-{index}'
                and set(icon.attrib) <= {'id','x','y','width','height','fill','stroke','stroke-width','opacity','transform'},
                'Expected the task-specified editable rectangle')
        require(all('url(' not in value.lower() for value in icon.attrib.values()), 'External paints are not task inputs')
        x,y,w,h = [float(icon.get(key,'0')) for key in ('x','y','width','height')]
        require(all(math.isfinite(v) for v in (x,y,w,h)) and w > 0 and h > 0, 'Invalid icon geometry')
        matrix = _transform(icon.get('transform',''))
        require({_point(matrix,px,py) for px,py in ((x,y),(x+w,y),(x,y+h),(x+w,y+h))} ==
                {(12,11),(20,11),(12,21),(20,21)}, 'Icon local placement changed')
        # Clone by value; source bytes remain untouched. Only sheet placement is
        # removed when this independent viewport becomes a standalone SVG.
        separate = ET.fromstring(ET.tostring(board))
        separate.attrib.pop('x', None); separate.attrib.pop('y', None)
        standalone.append(ET.tostring(separate, encoding='utf-8'))
    return standalone


def render_board(case, tools, index, source):
    directory = getattr(case, 'judge_root', case.root)
    source_path, target = directory/f'judge-board-{index}.svg', directory/f'judge-board-{index}.png'
    require(not source_path.exists() and not target.exists(), 'Judge board output already exists')
    save(source_path, source)
    result = subprocess.run([tools['resvg']['path'], '--skip-system-fonts', str(source_path), str(target)],
                            cwd=case.root, timeout=30, capture_output=True)
    require(result.returncode == 0, 'Pinned baseline board rasterizer failed')
    return Path(target).read_bytes()


def judge_icons(case, tools):
    raw = delivered(case, 'editable.svg')
    # Reject resources and unbounded viewports before starting the rasterizer.
    boards = svg_boards(raw)
    case.check('sheet-structure', lambda: svg_boards(raw))
    for index, source in enumerate(boards):
        rendered = render_board(case, tools, index, source)
        def picture(index=index, rendered=rendered):
            png_check(delivered(case, f'board-{index}.png'), 32, 32, expected_board(index))
            png_check(rendered, 32, 32, expected_board(index))
        case.check(f'board-{index}-pixels', picture)
    case.not_applicable('editable-source', 'This check validates an Inkbolt snapshot; the baseline delivers three editable SVG viewports.')
