"""Original text tasks with authored flow intervals and exact glyph geometry."""
import copy

from benchmark_graphics import (BLUE, GREEN, document, rectangle, pixels, ref,
                               store, source_snapshot, view, verify_history)
from benchmark_runtime import require
from synthetic_font import geometric_font
from synthetic_bidi_font import bidi_font


LICENSE = b'Original synthetic Inkbolt font. Permission to use, modify and redistribute with this notice.'


def linked_overflow(case):
    case.source('original.ttf',geometric_font())
    case.source('font-license.txt',LICENSE)
    case.begin('Create a 96x48 document containing the shared story AAAAAAAAAAAA at size 20. '
        'Place first at (0,0) and second at (32,0), each initially 24x40 with one column. '
        'Use original.ttf and strict overset. Diagnose the overflow, then review and apply '
        'only a second-slot change to 56x40, two columns, gutter 8. Preserve source text, '
        'reading order, font/license, first frame and unrelated green rectangle (90,40,4,4). '
        'Review the complete repaired image and preserve the overflowing original revision.')
    font=case.call('font','font.import',source_path='original.ttf',license_path='font-license.txt')
    story=dict(paragraphs=[dict(text='AAAAAAAAAAAA',style=dict(font_id='face',size=20,fill=BLUE))],
        slots=[dict(id='first',width=24,height=40),dict(id='second',width=24,height=40)],overset='error')
    items=[dict(id=name,transform=[1,0,0,1,x,0],content=dict(type='story_frame',story_id='article',slot_id=name))
           for name,x in [('first',0),('second',32)]]+[rectangle('unrelated',90,40,4,4,GREEN)]
    saved=store(case,document('linked','vector',96,48,fonts=dict(face=font),stories=dict(article=story),items=items))
    before=source_snapshot(case,saved,'before')
    diagnosis=case.call('diagnose','story.inspect',document=saved,id='article')['layout']
    case.check('original-overflow',lambda:require(diagnosis['overset']==dict(paragraph=0,offset=8),
        'The original story did not retain its exact unplaced tail'))
    repaired=copy.deepcopy(before['stories']['article'])
    repaired['slots'][1].update(width=56,columns=2,gutter=8)
    action=dict(type='edit',operations=[dict(op='story',id='article',story=repaired)])
    review=case.call('review','session.dry_run',session_id='work',request_id='flow',expected_revision=0,action=action)
    case.call('apply','session.apply_proposal',proposal=review['proposal'],action=action,response_mode='compact')
    layout=case.call('inspect-flow','story.inspect',document=ref(1),id='article')['layout']
    expected=[('first',0,0,2,2),('first',0,2,4,4),('second',0,4,6,6),
              ('second',0,6,8,8),('second',1,8,10,10),('second',1,10,12,12)]
    case.check('reading-order',lambda:require(layout['overset'] is None and
        [(x['slot_id'],x['column'],x['start'],x['end'],x['consumed_end']) for x in layout['lines']]==expected,
        'Flow dropped, duplicated or reordered a source interval'))
    current=source_snapshot(case,ref(1))
    wanted=copy.deepcopy(before);wanted['revision']=1;wanted['stories']['article']=repaired
    case.check('retained-source',lambda:require(current==wanted and
        current['fonts']['face']['sha256']==case.sources['original.ttf'] and
        current['fonts']['face']['license_sha256']==case.sources['font-license.txt'],
        'Flow repair changed unrelated state or font identity'))
    rects=[(x,y,8,14,BLUE) for x in [1,13,33,45,65,77] for y in [2,22]]+[(90,40,4,4,GREEN)]
    view(case,'preview',ref(1),'flow-pixels',96,48,pixels(96,48,rects))
    old=case.call('original-flow','story.inspect',document=saved,id='article')['layout']
    case.check('historical-flow',lambda:require(old==diagnosis,'Repair rewrote historical flow'))
    verify_history(case)


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


def multilingual(case):
    case.source('original.ttf',bidi_font())
    case.source('font-license.txt',LICENSE)
    texts=[text for text,_ in TYPOGRAPHY]
    case.begin('Create a 1000x960 editable typography sheet using original.ttf at size 200, '
        'blue fill, Unicode bidi with automatic base direction and no wrapping. Place the '
        'four exact logical strings '+repr(texts)+' at y=0,240,480,720, x=0 in 1000x240 frames. '
        'Preserve logical Unicode source, font/license and editable clusters. Inspect Hebrew '
        'and Arabic visual order, Arabic joining, combining-mark anchors, Indic prebase order, '
        'Han glyphs and the fi ligature; review the entire delivered image.')
    font=case.call('font','font.import',source_path='original.ttf',license_path='font-license.txt')
    items=[dict(id=f'row-{i}',transform=[1,0,0,1,0,i*240],content=dict(type='text',frame=dict(
        text=text,width=1000,height=240,wrap=False,bidi='unicode',direction='auto',
        style=dict(font_id='face',size=200,fill=BLUE)))) for i,text in enumerate(texts)]
    saved=store(case,document('multilingual','vector',1000,960,fonts=dict(face=font),items=items))
    layouts=[case.call(f'inspect-{i}','text.inspect',document=saved,id=f'row-{i}') for i in range(4)]
    expected_origins=[];rects=[]
    for row,(_,glyphs) in enumerate(TYPOGRAPHY):
        pen=0;origins=[]
        for gid,start,end in glyphs:
            advance=ADVANCE[gid]//5
            x,y=(pen+60,50) if gid==6 else (pen,200)
            origins.append([gid,start,end,[x,y],advance])
            if gid==6: rects.append((x,y+row*240-20,20,20,BLUE))
            elif gid!=1: rects.append((x+10,y+row*240-80-gid,20+2*gid,80+gid,BLUE))
            pen+=advance
        expected_origins.append(origins)
    def shaped():
        for info,expected in zip(layouts,expected_origins,strict=True):
            require(info['indices']=='unicode_scalars' and info['glyph_clusters']=='logical_scalar_intervals',
                    'Typography lost logical cluster units')
            actual=[[g['glyph_id'],g['start'],g['end'],g['origin'],g['advance']] for g in info['layout']['glyphs']]
            require(actual==expected,'Glyph forms, visual order, logical clusters or anchors differ')
    case.check('glyph-cluster-order',shaped)
    actual=source_snapshot(case,saved)
    case.check('editable-text-and-font',lambda:require(
        [i['content']['frame']['text'] for i in actual['items']]==texts and
        actual['fonts']['face']['sha256']==case.sources['original.ttf'] and
        actual['fonts']['face']['license_sha256']==case.sources['font-license.txt'],
        'Typography normalized/reordered stored text or replaced its font'))
    view(case,'preview',saved,'typography-pixels',1000,960,pixels(1000,960,rects))
    verify_history(case)
