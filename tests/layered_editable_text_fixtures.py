"""Original complete point authoring records with deliberately unrelated caches."""
import copy
import layered_fixtures as f
import layered_text_fixtures as t
import test_layered_story_cli as s
import test_layered_metadata_cli as m

NAME='OriginalFixture-Regular'


def style(**changes):
    result=dict(Font=0,FontSize=20.0,FillColor=dict(Type=1,Values=[1.0,1.0,0.0,0.0]),
        FillFlag=True,StrokeFlag=False,AutoLeading=False,Leading=24.0,
        Tracking=0,HorizontalScale=1.0,VerticalScale=1.0,BaselineShift=0.0,
        FontCaps=0,FontBaseline=0,AutoKerning=True,Kerning=0,Ligatures=False,DLigatures=False)
    result.update(changes);return result


def local(text='AA',styles=None,lengths=None):
    p=t.payload(text,lengths=lengths);e=p['EngineDict'];p['ResourceDict']['FontSet']=[dict(Name=NAME)]
    styles=styles or [style()]
    e['StyleRun']['RunArray']=[dict(StyleSheet=dict(StyleSheetData=v)) for v in styles]
    e['ParagraphRun']['RunArray']=[dict(ParagraphSheet=dict(Properties=dict(Justification=0,AutoHyphenate=False)))]
    e.update(AntiAlias=0,UseFractionalGlyphWidths=True,Rendered=dict(Version=1,Shapes=dict(WritingDirection=0,Children=[dict(
        ShapeType=0,Procession=0,Lines=dict(WritingDirection=0,Children=[]),Cookie=dict(OriginalGeometry=dict(
            ShapeType=0,PointBase=[0.0,0.0],Base=dict(ShapeType=0,TransformPoint0=[1.0,0.0],TransformPoint1=[0.0,1.0],TransformPoint2=[0.0,0.0]))))])))
    return p


def layer(text='AA',payload=None,index=0,matrix=(1,0,0,1,8,30),**kw):
    raw=t.record(text,engine=t.data(local(text) if payload is None else payload),transform=matrix,changes={'TextIndex':m.integer(index)})
    return dict(name='Editable point',width=1,height=1,xy=(1,2),rgba=[9,80,7,255],extra=f.tag(b'TySh',raw),**kw)


def global_data(texts=('AA',)):
    g=s.global_data();g['0']['1']['0']=[{'0':{'0':{'0':NAME}}}]
    g['0']['8']={'0':[{'0':{'2':{}}} for _ in texts]};g['1']['1']=[]
    for i,text in enumerate(texts):
        story=s.story(text);story['1']={'0':[{'0':i}]}
        props={'0':0,'1':20.0,'4':False,'5':24.0,'6':1.0,'7':1.0,'8':0,'9':0.0,
               '11':1,'12':0,'13':0,'15':0,'16':0,'18':False,'19':False,
               '53':{'99':s.Name('SimplePaint'),'0':{'0':1,'1':[1.0,1.0,0.0,0.0]}}}
        story['0']['6']['0'][0]['0']['0']['6']=props
        story['0']['5']['0'][0]['0']={'0':{'5':{'0':0,'9':False}}}
        g['1']['1'].append(story)
    return g


def source(layers=None,g=None,version=1):
    return f.make([layer()] if layers is None else layers,w=64,h=48,version=version,
                  global_extra=b'' if g is None else s.tag(s.entries(g)))
