"""Engine-free B05 SVG admission and fresh pinned-renderer judging."""
import re
import subprocess
import xml.etree.ElementTree as ET

from benchmark_baseline import _numbers, _transform
from benchmark_diagram import delivered
from benchmark_graphics import png_check
from benchmark_palette import expected_picture
from benchmark_runtime import require

NS = '{http://www.w3.org/2000/svg}'


def svg_palette(raw):
    require(len(raw) <= 64*1024,'B05 SVG exceeds its delivery bound')
    text = raw.decode('utf-8')
    require('<!DOCTYPE' not in text.upper(),'Document types are not B05 inputs')
    root = ET.fromstring(text)
    require(root.tag == NS+'svg' and set(root.attrib) <= {'width','height','viewBox','version'} and
        _numbers(root.get('width','')) == [32] and _numbers(root.get('height','')) == [16] and
        _numbers(root.get('viewBox','0 0 32 16')) == [0,0,32,16], 'Palette canvas changed')
    require(len(root) == 3 and not (root.text or '').strip(),'Expected three editable rectangles')
    for item, identity, x, color in zip(root,('first','second','unrelated'),(2,12,22),((220,90,30),(220,90,30),(30,150,70))):
        require(item.tag == NS+'rect' and not list(item) and item.get('id') == identity and
            not (item.text or '').strip() and not (item.tail or '').strip() and set(item.attrib) <=
            {'id','x','y','width','height','fill','stroke','opacity','transform'},'Palette objects or attributes changed')
        require([_numbers(item.get(key,'0')) for key in ('x','y','width','height')] == [[x],[4],[8],[8]] and
            _transform(item.get('transform','')) == (1,0,0,1,0,0),'Palette rectangle controls changed')
        require(item.get('stroke','none') == 'none' and _numbers(item.get('opacity','1')) == [1] and
            all('url(' not in value.lower() for value in item.attrib.values()),'Unexpected paint or resource reference')
        fill = item.get('fill','').strip().lower()
        rgb = re.fullmatch(r'rgb\(([^()]*)\)',fill)
        require(fill == '#'+bytes(color).hex() or (rgb is not None and _numbers(rgb[1]) == list(color)),
            'Shared artwork must be orange and unrelated artwork must remain green')
    return root


def render_palette(case, tools):
    target = getattr(case,'judge_root',case.root)/'judge-baseline.png'
    require(not target.exists(),'Judge output already exists')
    result = subprocess.run([tools['resvg']['path'],'--skip-system-fonts',str(case.root/'editable.svg'),str(target)],
        cwd=case.root,timeout=30,capture_output=True)
    require(result.returncode == 0,'Pinned palette rasterizer failed')
    return target.read_bytes()


def judge_palette(case, tools):
    svg_palette(delivered(case,'editable.svg'))
    rendered = render_palette(case,tools)
    def picture():
        png_check(delivered(case,'preview.png'),32,16,expected_picture())
        png_check(rendered,32,16,expected_picture())
    case.check('palette-pixels',picture)
    case.not_applicable('live-dependencies','This check inspects live Inkbolt swatch references; the baseline retains editable SVG paints.')
    case.not_applicable('historical-pixels','The baseline preserves source.json; this check reopens an Inkbolt saved revision.')
    case.not_applicable('history-valid','Inkbolt session history is unavailable to the no-engine arm.')
