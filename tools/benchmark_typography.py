"""B07 fixture, prompt, solve and judge with authored glyph/cluster oracles."""
import base64
import json
from pathlib import Path

from benchmark_diagram import delivered, retained_font_store
from benchmark_large_layout import retained_session_store
from benchmark_graphics import BLUE, pixels, png_check, store, source_snapshot
from benchmark_runtime import require, safe_name, strict_json
from synthetic_bidi_font import bidi_font
from synthetic_font import geometric_font
from synthetic_unicode_font import sfnt
from synthetic_variable_font import tables
from workload_cases import document, save, save_json, sha


LICENSE = b'Original synthetic Inkbolt font. Permission to use, modify and redistribute with this notice.'
FONT_FAMILY = 'Inkbolt Typography Fixture'
PROMPT = Path(__file__).with_name('benchmark_prompts')/'B07.md'
PREVIEW_FILES = {'typography-pixels':'preview.png'}


# Explicit independently authored glyph IDs and logical source intervals. The
# geometric font maps distinct rectangle outlines; these are not engine output.
TYPOGRAPHY = [
    ('A \u05d0\u05d1 12 B',[(2,0,1),(1,1,2),(3,5,6),(4,6,7),(1,4,5),(18,3,4),(17,2,3),(1,7,8),(3,8,9)]),
    ('A \u0628\u0628\u062a B',[(2,0,1),(1,1,2),(16,4,5),(10,3,4),(9,2,3),(1,5,6),(3,6,7)]),
    ('A \u05d0\u05b0\u05d1 B',[(2,0,1),(1,1,2),(18,4,5),(6,2,4),(17,2,4),(1,5,6),(3,6,7)]),
    ('\u4e00 \u0915\u093f fi',[(19,0,1),(1,1,2),(23,2,4),(22,2,4),(1,4,5),(26,5,7)]),
]
# Font units from the original authored fixture specification, deliberately not
# read back from the imported font or from text.inspect.
ADVANCE = {1:300,2:600,3:650,4:500,6:0,9:600,10:600,16:600,17:700,18:700,19:1000,22:700,23:300,26:500}


def named_font():
    # Add only original name records; all outlines, metrics and shaping tables
    # remain byte-identical to the established unnamed fixture.
    data = tables(bidi_font())
    data[b'name'] = tables(geometric_font(family=FONT_FAMILY))[b'name']
    return sfnt(data)


def fixture(case):
    case.source('original.ttf',named_font())
    case.source('font-license.txt',LICENSE)
    case.source('texts.json',(json.dumps([text for text,_ in TYPOGRAPHY],ensure_ascii=True,indent=2)+'\n').encode())


def typography_document(identity, font_id, font):
    items=[dict(id=f'row-{i}',transform=[1,0,0,1,0,i*240],content=dict(type='text',frame=dict(
        text=text,width=1000,height=240,wrap=False,bidi='unicode',direction='auto',
        style=dict(font_id=font_id,size=200,fill=BLUE)))) for i,(text,_) in enumerate(TYPOGRAPHY)]
    return document(identity,'vector',1000,960,fonts={font_id:font},items=items)


def authored_geometry():
    rows=[];rects=[]
    for row,(_,glyphs) in enumerate(TYPOGRAPHY):
        pen=0;origins=[]
        for gid,start,end in glyphs:
            advance=ADVANCE[gid]//5
            x,y=(pen+60,50) if gid==6 else (pen,200)
            origins.append([gid,start,end,[x,y],advance])
            if gid==6: rects.append((x,y+row*240-20,20,20,BLUE))
            elif gid!=1: rects.append((x+10,y+row*240-80-gid,20+2*gid,80+gid,BLUE))
            pen+=advance
        rows.append(origins)
    return rows,rects


def expected_picture():
    return pixels(1000,960,authored_geometry()[1])


def observed_glyphs(info):
    require(info['indices'] == 'unicode_scalars' and info['glyph_clusters'] == 'logical_scalar_intervals',
        'Typography lost logical cluster units')
    return [[g['glyph_id'],g['start'],g['end'],g['origin'],g['advance']] for g in info['layout']['glyphs']]


def shaping_report(rows):
    return dict(indices='unicode_scalars',glyph_clusters='logical_scalar_intervals',
        rows=[dict(text=text,glyphs=glyphs) for (text,_),glyphs in zip(TYPOGRAPHY,rows,strict=True)])


def report_glyphs(case):
    report = strict_json(delivered(case,'shaping.json'))
    require(isinstance(report,dict) and set(report) == {'indices','glyph_clusters','rows'} and
        report['indices'] == 'unicode_scalars' and report['glyph_clusters'] == 'logical_scalar_intervals' and
        isinstance(report['rows'],list) and len(report['rows']) == 4,'Invalid shaping report or cluster units')
    result = []
    for row,(text,_) in zip(report['rows'],TYPOGRAPHY,strict=True):
        require(isinstance(row,dict) and set(row) == {'text','glyphs'} and row['text'] == text and
            isinstance(row['glyphs'],list),'Shaping report changed the logical Unicode text')
        for glyph in row['glyphs']:
            require(isinstance(glyph,list) and len(glyph) == 5 and all(type(v) is int for v in glyph[:3]) and
                isinstance(glyph[3],list) and len(glyph[3]) == 2 and
                all(type(v) in (int,float) for v in [*glyph[3],glyph[4]]),'Invalid glyph/cluster coordinates')
        result.append(row['glyphs'])
    return result


def solve(case):
    font = case.call('font','font.import',source_path='original.ttf',license_path='font-license.txt')
    saved = store(case,typography_document('multilingual','face',font))
    layouts = [case.call(f'inspect-{i}','text.inspect',document=saved,id=f'row-{i}') for i in range(4)]
    source_snapshot(case,saved)
    preview = case.call('preview','document.preview',document=saved,preview=True)
    save(case.root/'preview.png',base64.b64decode(preview['artifact']['data'],validate=True))
    case.call('verify-history','session.verify',session_id=saved['session_id'])
    save_json(case.root/'shaping.json',shaping_report([observed_glyphs(row) for row in layouts]))
    save_json(case.root/'session.json',dict(session_id=saved['session_id'],current_revision=saved['revision']))


def judge(case):
    report = report_glyphs(case)
    font_root = retained_font_store(case)
    raw = delivered(case,'editable.json'); actual = strict_json(raw)
    reopened = case.call('judge-reopen','document.validate',document=dict(file_path='editable.json',sha256=sha(raw)))
    require(len(actual['items']) == 4 and len(actual['fonts']) == 1,'Expected four editable text rows and one original font')
    font_id = next(iter(actual['fonts']))
    font = dict(sha256=case.sources['original.ttf'],license_sha256=case.sources['font-license.txt'],face_index=0,
        bytes=len(delivered(case,'original.ttf')))
    expected = typography_document(actual['id'],font_id,font)
    expected['revision'] = actual['revision']
    # Creation task: authors choose IDs, labels and descriptive metadata. These
    # do not affect the independently prescribed text, formatting or geometry.
    if 'metadata' in actual: expected['metadata'] = actual['metadata']
    for target,item in zip(expected['items'],actual['items'],strict=True):
        target.update(id=item['id'],name=item['name'])
        if 'metadata' in item: target['metadata'] = item['metadata']
        # The prompt prescribes baseline positions, not a particular placement
        # control. Authored glyph origins and fresh pixels still judge placement.
        frame = item['content']['frame']
        if 'first_baseline' in frame:
            target['content']['frame']['first_baseline'] = frame['first_baseline']
    normalized = case.call('judge-expected','document.validate',document=expected)
    case.check('editable-text-and-font',lambda:require(type(actual['revision']) is int and actual['revision'] >= 0 and
        actual == reopened == normalized,'Typography changed editable text, frame geometry, formatting or original font/license'))
    layouts = [case.call(f'judge-inspect-{i}','text.inspect',document=reopened,id=item['id'],font_root=font_root) for i,item in enumerate(actual['items'])]
    case.check('glyph-cluster-order',lambda:require(report == [observed_glyphs(row) for row in layouts] == authored_geometry()[0],
        'Glyph forms, visual order, logical clusters, origins or advances differ'))
    rendered = case.call('judge-preview','document.preview',document=reopened,font_root=font_root,preview=True)
    def picture():
        png_check(delivered(case,'preview.png'),1000,960,expected_picture())
        png_check(base64.b64decode(rendered['artifact']['data'],validate=True),1000,960,expected_picture())
    case.check('typography-pixels',picture)
    locator = strict_json(delivered(case,'session.json'))
    require(isinstance(locator,dict) and set(locator) == {'session_id','current_revision'},'Invalid session locator')
    safe_name(locator['session_id'])
    session_root = retained_session_store(case, locator['session_id'])
    require(type(locator['current_revision']) is int and locator['current_revision'] == actual['revision'],'Invalid current revision')
    saved = case.call('judge-current-revision','document.validate',
        document=dict(session_id=locator['session_id'],revision=locator['current_revision'],session_root=session_root))
    verified = case.call('judge-history','session.verify',session_id=locator['session_id'],session_root=session_root)
    case.check('history-valid',lambda:require(verified['valid'] and verified['revision'] == actual['revision'] and saved == actual,
        'Valid saved history must contain the exact delivered snapshot at its current head'))


def multilingual(case):
    fixture(case); case.begin(PROMPT.read_text(encoding='utf-8')); solve(case)
    case.begin_judging(); judge(case)
    if any(row['name'] == 'typography-pixels' and row['status'] == 'pass' for row in case.checks):
        case.verified_preview(delivered(case,'preview.png'))
