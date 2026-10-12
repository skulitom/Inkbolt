"""B06 linked-story fixture, prompt, reference solve and independent judge."""
import base64
import copy
from pathlib import Path

from benchmark_diagram import delivered
from benchmark_graphics import BLUE, GREEN, pixels, png_check, store, source_snapshot
from benchmark_runtime import require, safe_name, strict_json
from synthetic_font import geometric_font
from workload_cases import document, rectangle, save, save_json, sha

PROMPT = Path(__file__).with_name('benchmark_prompts')/'B06.md'
FONT_FAMILY = 'Inkbolt Flow Fixture'
LICENSE = b'Original synthetic Inkbolt font. Permission to use, modify and redistribute with this notice.'
PREVIEW_FILES = {'flow-pixels':'preview.png'}
LINE_FIELDS = ('slot_id','column','paragraph','start','end','consumed_end')


def fixture(case):
    font = geometric_font(family=FONT_FAMILY)
    case.source('original.ttf',font)
    case.source('font-license.txt',LICENSE)
    descriptor = dict(sha256=sha(font),license_sha256=sha(LICENSE),face_index=0,bytes=len(font))
    story = dict(paragraphs=[dict(text='AAAAAAAAAAAA',style=dict(font_id='face',size=20,fill=BLUE))],
        slots=[dict(id='first',width=24,height=40),dict(id='second',width=24,height=40)],overset='error')
    items = [dict(id=name,transform=[1,0,0,1,x,0],content=dict(type='story_frame',story_id='article',slot_id=name))
        for name,x in (('first',0),('second',32))]+[rectangle('unrelated',90,40,4,4,GREEN)]
    case.seed(document('linked','vector',96,48,fonts=dict(face=descriptor),stories=dict(article=story),items=items))


def repaired(source):
    result = copy.deepcopy(source)
    result['stories']['article']['slots'][1].update(width=56,columns=2,gutter=8)
    return result


def flow_lines(layout):
    return [{key:row[key] for key in LINE_FIELDS} for row in layout['lines']]


def expected_lines(final=True):
    # Authored source intervals: two 12-pixel advances per 24-pixel column,
    # two 20-pixel lines per 40-pixel frame. The repaired second frame has
    # two columns of (56 - 8) / 2 = 24 pixels each.
    rows = [('first',0,0,2),('first',0,2,4),('second',0,4,6),('second',0,6,8)]
    if final: rows += [('second',1,8,10),('second',1,10,12)]
    return [dict(slot_id=slot,column=column,paragraph=0,start=start,end=end,consumed_end=end)
        for slot,column,start,end in rows]


def read_report(case):
    report = strict_json(delivered(case,'flow-report.json'))
    require(isinstance(report,dict) and set(report) == {'original_overset','final_overset','lines'},
        'Flow report must declare original/final overset and logical line intervals')
    # Strict types keep booleans from impersonating source offsets or columns.
    require(isinstance(report['original_overset'],dict) and
        all(type(value) is int for value in report['original_overset'].values()),'Invalid original overset coordinates')
    require(isinstance(report['lines'],list) and all(isinstance(row,dict) and set(row) == set(LINE_FIELDS) and
        isinstance(row['slot_id'],str) and all(type(row[key]) is int for key in LINE_FIELDS[1:])
        for row in report['lines']),'Invalid logical line intervals')
    return report


def solve(case):
    case.call('font','font.import',source_path='original.ttf',license_path='font-license.txt')
    source = strict_json(delivered(case,'source.json'))
    original = store(case,dict(file_path='source.json',sha256=sha(delivered(case,'source.json'))))
    before = case.call('diagnose','story.inspect',document=original,id='article')['layout']
    action = dict(type='edit',operations=[dict(op='story',id='article',story=repaired(source)['stories']['article'])])
    review = case.call('review','session.dry_run',session_id=original['session_id'],request_id='flow',expected_revision=0,action=action)
    current = case.call('apply','session.apply_proposal',proposal=review['proposal'],action=action,response_mode='compact')['document_ref']
    layout = case.call('inspect-flow','story.inspect',document=current,id='article')['layout']
    source_snapshot(case,current)
    preview = case.call('preview','document.preview',document=current,preview=True)
    save(case.root/'preview.png',base64.b64decode(preview['artifact']['data'],validate=True))
    case.call('original-flow','story.inspect',document=original,id='article')
    case.call('verify-history','session.verify',session_id=original['session_id'])
    save_json(case.root/'flow-report.json',dict(original_overset=before['overset'],final_overset=layout['overset'],lines=flow_lines(layout)))
    save_json(case.root/'session.json',dict(session_id=original['session_id'],original_revision=0,current_revision=current['revision']))


def expected_picture():
    return pixels(96,48,[(x,y,8,14,BLUE) for x in (1,13,33,45,65,77) for y in (2,22)]+[(90,40,4,4,GREEN)])


def judge(case):
    report = read_report(case)
    raw = delivered(case,'editable.json'); actual = strict_json(raw)
    original = case.call('judge-source','document.validate',document=dict(file_path='source.json',sha256=case.sources['source.json']))
    reopened = case.call('judge-reopen','document.validate',document=dict(file_path='editable.json',sha256=sha(raw)))
    diagnosis = case.call('judge-original-flow','story.inspect',document=original,id='article')['layout']
    layout = case.call('judge-current-flow','story.inspect',document=reopened,id='article')['layout']
    case.check('original-overflow',lambda:require(report['original_overset'] == diagnosis['overset'] == dict(paragraph=0,offset=8)
        and flow_lines(diagnosis) == expected_lines(False),'The original overflow diagnosis differs from the authored source capacity'))
    case.check('reading-order',lambda:require(report['final_overset'] is None and layout['overset'] is None and
        report['lines'] == flow_lines(layout) == expected_lines(),'Flow dropped, duplicated or reordered a source interval'))
    def retained():
        require(type(actual['revision']) is int and actual['revision'] > 0,'Missing edited revision')
        expected = repaired(original); expected['revision'] = actual['revision']
        require(actual == reopened == expected,'Only the second slot dimensions/columns and document revision may change')
        font = actual['fonts']['face']
        require(font['sha256'] == case.sources['original.ttf'] and font['license_sha256'] == case.sources['font-license.txt'],
            'The original font or license identity changed')
    case.check('retained-source',retained)
    rendered = case.call('judge-preview','document.preview',document=reopened,preview=True)
    def picture():
        png_check(delivered(case,'preview.png'),96,48,expected_picture())
        png_check(base64.b64decode(rendered['artifact']['data'],validate=True),96,48,expected_picture())
    case.check('flow-pixels',picture)
    locator = strict_json(delivered(case,'session.json'))
    require(isinstance(locator,dict) and set(locator) == {'session_id','original_revision','current_revision'},'Invalid session locator')
    safe_name(locator['session_id'])
    require(type(locator['original_revision']) is int and locator['original_revision'] == 0 and
        type(locator['current_revision']) is int and locator['current_revision'] == actual['revision'] > 0,'Invalid original/current revisions')
    old = case.call('judge-original-revision','document.validate',document=dict(session_id=locator['session_id'],revision=0))
    current = case.call('judge-current-revision','document.validate',document=dict(session_id=locator['session_id'],revision=actual['revision']))
    # A captured session retains its old absolute roots. Inspect its exact
    # snapshot using the current workspace's captured, content-checked fonts.
    historical = case.call('judge-historical-flow','story.inspect',document=old,id='article')['layout']
    case.check('historical-flow',lambda:require(old == original and historical == diagnosis,
        'Historical source or overflow changed'))
    verified = case.call('judge-history','session.verify',session_id=locator['session_id'])
    case.check('history-valid',lambda:require(verified['valid'] and verified['revision'] == actual['revision'] and
        old == original and current == actual,'History must bind the exact original fixture, final delivery and session head'))


def linked_overflow(case):
    fixture(case); case.begin(PROMPT.read_text(encoding='utf-8')); solve(case)
    case.begin_judging(); judge(case)
    if any(row['name'] == 'flow-pixels' and row['status'] == 'pass' for row in case.checks):
        case.verified_preview(delivered(case,'preview.png'))
