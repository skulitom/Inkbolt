"""Original text tasks with authored flow intervals and exact glyph geometry."""

from benchmark_graphics import (BLUE, GREEN, document, rectangle, pixels, ref,
                               store, source_snapshot, view, verify_history)
from benchmark_runtime import require
from synthetic_bidi_font import bidi_font


LICENSE = b'Original synthetic Inkbolt font. Permission to use, modify and redistribute with this notice.'


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
