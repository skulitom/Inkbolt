"""Engine-free B06 source retention, logical flow and pinned SVG rendering."""
import re
import subprocess
import xml.etree.ElementTree as ET

from benchmark_baseline import _numbers
from benchmark_diagram import delivered
from benchmark_flow import FONT_FAMILY, repaired, read_report, expected_lines, expected_picture
from benchmark_graphics import png_check
from benchmark_runtime import require, strict_json

NS = '{http://www.w3.org/2000/svg}'


def same_json(actual, expected):
    if isinstance(expected,dict):
        return isinstance(actual,dict) and actual.keys() == expected.keys() and all(same_json(actual[k],v) for k,v in expected.items())
    if isinstance(expected,list):
        return isinstance(actual,list) and len(actual) == len(expected) and all(same_json(a,b) for a,b in zip(actual,expected))
    if type(expected) in (int,float): return type(actual) in (int,float) and actual == expected
    return type(actual) is type(expected) and actual == expected


def paint(value, rgb):
    value = value.strip().lower(); match = re.fullmatch(r'rgb\(([^()]*)\)',value)
    return value == '#'+bytes(rgb).hex() or (match is not None and _numbers(match[1]) == list(rgb))


def svg_flow(raw):
    require(len(raw) <= 64*1024,'B06 SVG exceeds its delivery bound')
    text = raw.decode('utf-8')
    require('<!DOCTYPE' not in text.upper(),'Document types are not B06 inputs')
    root = ET.fromstring(text)
    require(root.tag == NS+'svg' and set(root.attrib) <= {'width','height','viewBox','version'} and
        _numbers(root.get('width','')) == [96] and _numbers(root.get('height','')) == [48] and
        _numbers(root.get('viewBox','0 0 96 48')) == [0,0,96,48], 'Flow canvas changed')
    require(len(root) == 3 and not (root.text or '').strip(),'Expected two text frames and the unrelated rectangle')
    lines = []
    for frame, identity, x, width, count in zip(root[:2],('first','second'),(0,32),(24,56),(2,4)):
        require(frame.tag == NS+'svg' and set(frame.attrib) <= {'id','x','y','width','height','viewBox'} and
            frame.get('id') == identity and len(frame) == count and not (frame.text or '').strip() and
            not (frame.tail or '').strip(),'Frame IDs, reading order or text counts changed')
        require([_numbers(frame.get(key,'')) for key in ('x','y','width','height')] == [[x],[0],[width],[40]] and
            _numbers(frame.get('viewBox',f'0 0 {width} 40')) == [0,0,width,40],'Frame dimensions or placement changed')
        for index, node in enumerate(frame):
            require(node.tag == NS+'text' and not list(node) and node.text == 'AA' and not (node.tail or '').strip() and
                set(node.attrib) == {'x','y','font-family','font-size','fill','data-start','data-end'},
                'Expected editable text and its exact logical source interval')
            require(_numbers(node.get('x','')) == [32*(index//2)] and _numbers(node.get('y','')) == [16+20*(index%2)] and
                node.get('font-family') == FONT_FAMILY and _numbers(node.get('font-size','')) == [20] and
                paint(node.get('fill',''),(20,80,150)),'Text placement, font or paint changed')
            require(all(re.fullmatch(r'0|[1-9][0-9]*',node.get(key,'')) for key in ('data-start','data-end')),
                'Logical source offsets must be nonnegative decimal integers')
            start,end = int(node.get('data-start')),int(node.get('data-end'))
            lines.append(dict(slot_id=identity,column=index//2,paragraph=0,start=start,end=end,consumed_end=end))
    other = root[2]
    require(other.tag == NS+'rect' and not list(other) and not (other.text or '').strip() and not (other.tail or '').strip() and
        set(other.attrib) == {'id','x','y','width','height','fill'} and other.get('id') == 'unrelated' and
        [_numbers(other.get(key,'')) for key in ('x','y','width','height')] == [[90],[40],[4],[4]] and
        paint(other.get('fill',''),(30,150,70)),'The unrelated artwork changed')
    require(lines == expected_lines(),'SVG text intervals drop, duplicate or reorder the logical story')
    return lines


def render_flow(case, tools):
    target = getattr(case,'judge_root',case.root)/'judge-baseline.png'
    require(not target.exists(),'Judge output already exists')
    result = subprocess.run([tools['resvg']['path'],'--skip-system-fonts','--use-font-file',str(case.root/'original.ttf'),
        '--font-family',FONT_FAMILY,str(case.root/'editable.svg'),str(target)],cwd=case.root,timeout=30,capture_output=True)
    require(result.returncode == 0,'Pinned flow rasterizer failed')
    return target.read_bytes()


def judge_flow(case, tools):
    report = read_report(case)
    lines = svg_flow(delivered(case,'editable.svg'))
    case.check('original-overflow',lambda:require(report['original_overset'] == dict(paragraph=0,offset=8),
        'Original diagnosis differs from the authored two-frame capacity'))
    case.check('reading-order',lambda:require(report['final_overset'] is None and report['lines'] == lines == expected_lines(),
        'Flow report must agree with the editable text and independently authored intervals'))
    def retained():
        actual = strict_json(delivered(case,'layout.json'))
        expected = repaired(strict_json(delivered(case,'source.json')))
        require(same_json(actual,expected),'Only the second slot dimensions/columns may change in the retained layout source')
        font = actual['fonts']['face']
        require(font['sha256'] == case.sources['original.ttf'] and font['license_sha256'] == case.sources['font-license.txt'],
            'Original font/license identity changed')
    case.check('retained-source',retained)
    rendered = render_flow(case,tools)
    def picture():
        png_check(delivered(case,'preview.png'),96,48,expected_picture())
        png_check(rendered,96,48,expected_picture())
    case.check('flow-pixels',picture)
    case.not_applicable('historical-flow','The baseline preserves source.json; this check inspects an Inkbolt saved revision.')
    case.not_applicable('history-valid','Inkbolt session history is unavailable to the no-engine arm.')
