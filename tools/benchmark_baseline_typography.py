"""B07 editable Unicode SVG and declared source-cluster artifact judging."""
import subprocess
import xml.etree.ElementTree as ET

from benchmark_baseline import _numbers
from benchmark_baseline_flow import paint
from benchmark_diagram import delivered
from benchmark_graphics import png_check
from benchmark_runtime import require, TaskFailure
from benchmark_typography import FONT_FAMILY, TYPOGRAPHY, report_glyphs, authored_geometry, expected_picture

NS = '{http://www.w3.org/2000/svg}'
SPACE = '{http://www.w3.org/XML/1998/namespace}space'


def svg_typography(raw):
    require(len(raw) <= 64*1024,'B07 SVG exceeds its delivery bound')
    text = raw.decode('utf-8')
    require('<!DOCTYPE' not in text.upper(),'Document types are not B07 inputs')
    root = ET.fromstring(text)
    require(root.tag == NS+'svg' and set(root.attrib) <= {'width','height','viewBox','version'} and
        _numbers(root.get('width','')) == [1000] and _numbers(root.get('height','')) == [960] and
        _numbers(root.get('viewBox','0 0 1000 960')) == [0,0,1000,960] and
        len(root) == 4 and not (root.text or '').strip(),'Expected a 1000 by 960 canvas with four text rows')
    identities = set()
    for index,(node,(logical,_)) in enumerate(zip(root,TYPOGRAPHY,strict=True)):
        require(node.tag == NS+'text' and set(node.attrib) <= {'id','x','y','font-family','font-size','fill',SPACE,'direction'} and
            len(node) <= 16 and not (node.tail or '').strip(),'Expected bounded editable text rows')
        if node.get('id') is not None:
            require(node.get('id') and node.get('id') not in identities,'Duplicate or empty row ID')
            identities.add(node.get('id'))
        require(_numbers(node.get('x','')) == [0] and _numbers(node.get('y','')) == [200+240*index] and
            node.get('font-family') == FONT_FAMILY and _numbers(node.get('font-size','')) == [200] and
            paint(node.get('fill',''),(20,80,150)) and node.get(SPACE,'default') in ('default','preserve') and
            node.get('direction','ltr') == 'ltr','Row placement, original font, size, paint or base direction changed')
        for span in node:
            require(span.tag == NS+'tspan' and not list(span) and set(span.attrib) <= {'x',SPACE} and
                span.get(SPACE,'default') in ('default','preserve'),'Only flat editable text spans are admitted')
            if span.get('x') is not None:
                values = _numbers(span.get('x'))
                require(len(values) == 1 and 0 <= values[0] <= 1000,'Span position exceeds the bounded text row')
        require(''.join(node.itertext()) == logical,'SVG normalized, reordered, dropped or substituted the logical Unicode source')
    return root


def render_typography(case, tools):
    target = getattr(case,'judge_root',case.root)/'judge-baseline.png'
    require(not target.exists(),'Judge output already exists')
    result = subprocess.run([tools['resvg']['path'],'--skip-system-fonts','--use-font-file',str(case.root/'original.ttf'),
        '--font-family',FONT_FAMILY,str(case.root/'editable.svg'),str(target)],cwd=case.root,timeout=30,capture_output=True)
    require(result.returncode == 0,'Pinned typography rasterizer failed')
    return target.read_bytes()


def judge_typography(case, tools):
    svg_typography(delivered(case,'editable.svg'))
    report = report_glyphs(case)
    rendered = render_typography(case,tools)
    # Decode the fresh source render once, but require it for both checks. The
    # renderer does not expose internal clusters: shaping.json is an explicit
    # delivered source mapping, checked against authored intervals/metrics and
    # the glyph-distinct raster, never reported as measured renderer internals.
    error = None
    try: png_check(rendered,1000,960,expected_picture())
    except TaskFailure as failure: error = str(failure)
    def shaped():
        require(report == authored_geometry()[0],'Declared glyph forms, logical clusters, origins or advances differ')
        require(error is None,error or 'Fresh source render differs')
    case.check('glyph-cluster-order',shaped)
    def picture():
        require(error is None,error or 'Fresh source render differs')
        png_check(delivered(case,'preview.png'),1000,960,expected_picture())
    case.check('typography-pixels',picture)
    case.not_applicable('editable-text-and-font','This check reopens an Inkbolt snapshot; the baseline retains editable Unicode SVG and the original font.')
    case.not_applicable('history-valid','Inkbolt session history is unavailable to the no-engine arm.')
