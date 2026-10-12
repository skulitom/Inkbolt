"""Engine-free admission and pinned SVG rendering for the B03 delivered layout."""
from pathlib import Path
import subprocess
import re
import xml.etree.ElementTree as ET

from benchmark_baseline import _numbers, _transform
from benchmark_diagram import delivered
from benchmark_graphics import png_check
from benchmark_large_layout import expected_picture
from benchmark_runtime import require

NS = '{http://www.w3.org/2000/svg}'


def svg_layout(raw):
    require(len(raw) <= 2*1024*1024, 'B03 SVG exceeds its delivery bound')
    text = raw.decode('utf-8')
    require('<!DOCTYPE' not in text.upper(), 'Document types are not B03 inputs')
    root = ET.fromstring(text)
    require(root.tag == NS+'svg' and set(root.attrib) <= {'width','height','viewBox','version'} and
            _numbers(root.get('width','')) == [1000] and _numbers(root.get('height','')) == [500] and
            _numbers(root.get('viewBox','0 0 1000 500')) == [0,0,1000,500], 'Layout canvas changed')
    require(len(root) == 5000 and not (root.text or '').strip(), 'Expected exactly 5,000 editable rectangles')
    for index, item in enumerate(root):
        require(item.tag == NS+'rect' and not list(item) and item.get('id') == f'cell-{index}' and
                not (item.text or '').strip() and not (item.tail or '').strip() and set(item.attrib) <=
                {'id','x','y','width','height','fill','stroke','opacity','transform'},
                'Layout object IDs, order, types or attributes changed')
        require([_numbers(item.get(key,'0')) for key in ('x','y','width','height')] ==
                [[(index%100)*10],[(index//100)*10],[6],[6]], 'Original rectangle controls changed')
        require(_transform(item.get('transform','')) == (1,0,0,1,1 if index == 2473 else 0,1 if index == 2473 else 0),
                'The target translation must be the only transform change')
        require(item.get('stroke','none') == 'none' and _numbers(item.get('opacity','1')) == [1] and
                all('url(' not in value.lower() for value in item.attrib.values()),
                'Unexpected paint, opacity or resource reference')
        fill = item.get('fill','').strip().lower()
        rgb = re.fullmatch(r'rgb\(([^()]*)\)', fill)
        require(fill == '#145096' or (rgb is not None and _numbers(rgb[1]) == [20,80,150]),
                'An original object fill changed')
    return root


def render_layout(case, tools):
    target = getattr(case, 'judge_root', case.root)/'judge-baseline.png'
    require(not target.exists(), 'Judge output already exists')
    result = subprocess.run([tools['resvg']['path'], '--skip-system-fonts',
        str(case.root/'editable.svg'), str(target)], cwd=case.root, timeout=30, capture_output=True)
    require(result.returncode == 0, 'Pinned baseline layout rasterizer failed')
    return Path(target).read_bytes()


def judge_large_layout(case, tools):
    raw = delivered(case, 'editable.svg')
    svg_layout(raw)  # Admit bounded geometry and reject resources before rendering.
    case.check('only-target-changed', lambda: svg_layout(raw))
    rendered = render_layout(case, tools)
    def picture():
        png_check(delivered(case, 'preview.png'), 1000, 500, expected_picture())
        png_check(rendered, 1000, 500, expected_picture())
    case.check('large-layout-pixels', picture)
    case.not_applicable('historical-pixels', 'The baseline preserves source.json; this check reopens an Inkbolt saved revision.')
    case.not_applicable('history-valid', 'Inkbolt session history is unavailable to the no-engine arm.')
