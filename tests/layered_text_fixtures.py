"""Original minimal text-record generators; no external defaults or artifacts."""
import struct
import layered_fixtures as f
import test_layered_metadata_cli as m


def data(value):
    if isinstance(value, dict):
        return b'<< '+b' '.join(b'/'+k.encode('ascii')+b' '+data(v) for k,v in value.items())+b' >>'
    if isinstance(value, list):return b'[ '+b' '.join(map(data,value))+b' ]'
    if isinstance(value, str):
        b=b'\xfe\xff'+value.encode('utf-16-be')
        return b'('+b.replace(b'\\',b'\\\\').replace(b'(',b'\\(').replace(b')',b'\\)')+b')'
    if isinstance(value, bool):return b'true' if value else b'false'
    return str(value).encode('ascii')


def payload(text='A\U0001f600B', lengths=None, font_indices=None):
    units=len(text.encode('utf-16-be'))//2+1
    lengths=[units] if lengths is None else lengths
    font_indices=[0]*len(lengths) if font_indices is None else font_indices
    return dict(EngineDict=dict(Editor=dict(Text=text+'\r'),
        StyleRun=dict(RunArray=[dict(StyleSheet=dict(StyleSheetData=dict(Font=i))) for i in font_indices],RunLengthArray=lengths),
        ParagraphRun=dict(RunArray=[{}],RunLengthArray=[units])),
        ResourceDict=dict(FontSet=[dict(Name='OriginalFixture-Regular'),dict(Name='OriginalFixture-Second')]))


def record(text='A\U0001f600B', engine=None, transform=(1,0,0,1,8,20), changes=None, version=1, text_version=50, warp_version=1, tail=bytes(16)):
    engine=data(payload(text)) if engine is None else engine
    fields={'Txt ':m.txt(text),'EngineData':b'tdta'+f.section(engine),
            'textGridding':m.enum('textGridding','None'),'Ornt':m.enum('Ornt','Hrzn'),
            'AntA':m.enum('Annt','Anno'),'TxMP':m.boolean(False),'TextIndex':m.integer(0)}
    fields.update(changes or {})
    warp=m.versioned('warp', [('warpStyle',m.enum('warpStyle','warpNone')),
         ('warpValue',m.number(0)),('warpPerspective',m.number(0)),
         ('warpPerspectiveOther',m.number(0)),('warpRotate',m.enum('Ornt','Hrzn'))])
    return f.U16(version)+struct.pack('>6d',*transform)+f.U16(text_version)+m.versioned('TxLr',list(fields.items()))+f.U16(warp_version)+warp+tail


def source(text='A\U0001f600B', raw=None, **kwargs):
    raw=record(text=text,**kwargs) if raw is None else raw
    layer=dict(name='Original editable label',width=1,height=1,rgba=[9,8,7,255],extra=f.tag(b'TySh',raw))
    return f.make([layer])
