"""Original path labels: analytic glyphs, independent arc integration and durable edits."""
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_text_cli as text_tests
import test_editing_cli as editing
import test_boards_cli as boards
from test_mcp import Client


def line(a=(10,25),b=(65,25),**kw):
    return dict(geometry=dict(shape='path',commands=[dict(verb='move',to=list(a)),dict(verb='line',to=list(b))]),**kw)


CURVE=[[5,35],[12,0],[54,0],[65,30]]
def curved(points=CURVE,**kw):return dict(geometry=dict(shape='path',commands=[dict(verb='move',to=points[0]),dict(verb='cubic',control1=points[1],control2=points[2],to=points[3])]),**kw)
def mapping(matrix,p):return [matrix[0]*p[0]+matrix[2]*p[1]+matrix[4],matrix[1]*p[0]+matrix[3]*p[1]+matrix[5]]


def cubic(points,t):
    weights=[(1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3]
    return [sum(w*p[c] for w,p in zip(weights,points)) for c in range(2)]


def derivative(points,t):return [3*sum(w*(points[i+1][c]-points[i][c]) for i,w in enumerate([(1-t)**2,2*t*(1-t),t*t])) for c in range(2)]


def integral(f,a,b,tolerance=1e-10):
    def simpson(a,b,fa,fb,fm):return (b-a)*(fa+4*fm+fb)/6
    def step(a,b,fa,fb,fm,old,epsilon,depth):
        mid=(a+b)/2;left=f((a+mid)/2);right=f((mid+b)/2)
        first=simpson(a,mid,fa,fm,left);second=simpson(mid,b,fm,fb,right);delta=first+second-old
        if depth==0 or abs(delta)<=15*epsilon:return first+second+delta/15
        return step(a,mid,fa,fm,left,first,epsilon/2,depth-1)+step(mid,b,fm,fb,right,second,epsilon/2,depth-1)
    fa=f(a);fb=f(b);fm=f((a+b)/2)
    return step(a,b,fa,fb,fm,simpson(a,b,fa,fb,fm),tolerance,22)


class ArcOracle:
    def __init__(self,points):self.points=points;self.speed=lambda t:math.hypot(*derivative(points,t));self.length=integral(self.speed,0,1)
    def sample(self,distance,flip=False):
        d=self.length-distance if flip else distance
        lo=0.;hi=1.
        if d<=0:t=0.
        elif d>=self.length:t=1.
        else:
            for _ in range(38):
                mid=(lo+hi)/2
                if integral(self.speed,0,mid)<d:lo=mid
                else:hi=mid
            t=(lo+hi)/2
        p=cubic(self.points,t);v=derivative(self.points,t);n=math.hypot(*v);v=[x/n for x in v]
        extra=d-min(self.length,max(0,d));p=[p[c]+v[c]*extra for c in range(2)]
        return p,[-x for x in v] if flip else v


class PathTextTests(unittest.TestCase):
    invoke=text_tests.TextCliTests.invoke
    setUp=text_tests.TextCliTests.setUp
    edit=text_tests.TextCliTests.edit
    inspect=text_tests.TextCliTests.inspect
    pixels=text_tests.TextCliTests.pixels
    def document(self,path=None,text='AB',kind='vector',**kw):
        return text_tests.TextCliTests.document(self,kind,text,wrap=False,path=path or line(),**kw)
    def replace(self,d,expected=0,**kw):
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame.update(kw)
        return self.edit(d,[dict(op='text',id='label',frame=frame)],expected)
    def layout(self,d,**kw):return self.inspect(d,include_outlines=True,**kw)['layout']
    def assert_points(self,a,b,tolerance=1e-9):
        self.assertEqual(len(a),len(b))
        for x,y in zip(a,b):self.assertLessEqual(abs(x-y),tolerance,(a,b))
    def exported(self,d,format,**kw):return self.invoke(dict(command='document.export',document=d,format=format,font_root=str(self.store),**kw))

    def test_straight_editable_baseline_kerning_origins_and_exact_interior_pixels(self):
        for kind in ('vector','raster'):
            d=self.document(kind=kind);layout=self.layout(d)
            self.assertEqual(layout['baseline_path']['length'],55)
            # The shaper divides the -1 unit kern equally between advances and
            # offsets: the glyph origins still differ by exactly five units.
            self.assertEqual([g['advance'] for g in layout['glyphs']],[5.5,11.5])
            for g,p in zip(layout['glyphs'],[[10,25],[15,25]]):self.assert_points(g['origin'],p)
            self.assert_points(layout['glyphs'][0]['ink_bounds'],[10.5,18,14.5,25]);self.assert_points(layout['glyphs'][1]['ink_bounds'],[15,20,25,25])
            w,h,p=self.pixels(d)
            for y in range(h):
                for x in range(w):
                    if 11<=x<14 and 18<=y<25:self.assertEqual(p[(y*w+x)*4:][:4],bytes([25,100,200,255]))
                    elif x<10 or x>=26 or y<18 or y>=25:self.assertEqual(p[(y*w+x)*4:][:4],bytes(4))
            restored=json.loads(self.exported(d,'snapshot')['data']);self.assertEqual(restored,d)
            self.assertEqual(self.layout(restored),layout)

    def test_diagonal_offsets_glyph_outlines_have_independent_rigid_poses(self):
        d=self.document(line((5,15),(41,63),start_offset=2,normal_offset=3));layout=self.layout(d)
        for glyph,origin,advance,path in zip(layout['glyphs'],[0,5],[5.5,11.5],layout['paths']):
            center=origin+advance/2;distance=2+center;point=[5+.6*distance,15+.8*distance]
            pose=[.6,.8,-.8,.6,point[0]-.8*3-.6*center,point[1]+.6*3-.8*center]
            self.assert_points(glyph['path']['point'],point);self.assert_points(glyph['path']['tangent'],[.6,.8]);self.assert_points(glyph['path']['transform'],pose)
            self.assert_points(glyph['origin'],mapping(pose,[origin,0]))
            commands=path['geometry']['commands']
            if origin==0:
                expected=[[.5,0],[.5,-7],[4.5,-7],[4.5,0]]
                for command,p in zip(commands,expected):self.assert_points(command['to'],mapping(pose,p))
            else:
                self.assert_points(commands[0]['to'],mapping(pose,[5,0]));c=commands[1]
                self.assert_points(c['control1'],mapping(pose,[5+10/3,-20/3]));self.assert_points(c['control2'],mapping(pose,[5+20/3,-20/3]));self.assert_points(c['to'],mapping(pose,[15,0]))

    def test_curved_glyph_placement_matches_independent_arc_integrals_and_tangents(self):
        oracle=ArcOracle(CURVE)
        for flip in (False,True):
            path=curved(start_offset=4,normal_offset=-2,flip=flip,tolerance=.0001)
            d=self.document(path,text='ABAB');layout=self.layout(d);report=layout['baseline_path']
            self.assertLessEqual(report['length_interval'][0],oracle.length);self.assertGreaterEqual(report['length_interval'][1],oracle.length)
            self.assertLess(report['baseline_position_error_bound'],.001)
            for glyph in layout['glyphs']:
                p,v=oracle.sample(glyph['path']['distance'],flip)
                self.assert_points(glyph['path']['point'],p,report['baseline_position_error_bound']+1e-8)
                self.assert_points(glyph['path']['tangent'],v,3e-5)
                pose=glyph['path']['transform'];self.assertAlmostEqual(pose[0]*pose[3]-pose[1]*pose[2],1,12)
            self.assertEqual(d['items'][0]['content']['frame']['path']['geometry'],path['geometry'])

    def test_alignment_tracking_flipping_and_closed_single_lap(self):
        for align,offset in [('left',0),('center',21.5),('right',43)]:
            d=self.document(line(start_offset=2,normal_offset=1,flip=True),text='AA',align=align,overflow='visible')
            g=self.layout(d)['glyphs'];self.assert_points(g[0]['origin'],[65-2-offset,24]);self.assert_points(g[1]['origin'],[59-2-offset,24])
            self.assertEqual([s['path']['tangent'] for s in g],[[-1,0],[-1,0]])
        d=self.document(dict(geometry=dict(shape='rect',x=10,y=15,width=20,height=15),flip=True),text='AA')
        r=self.layout(d);self.assertEqual(r['baseline_path']['length'],70);self.assertTrue(r['baseline_path']['closed'])
        self.assert_points(r['glyphs'][0]['origin'],[10,15]);self.assert_points(r['glyphs'][0]['path']['tangent'],[0,1])
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['style']['tracking']=2
        d=self.edit(d,[dict(op='text',id='label',frame=frame)]);self.assertEqual([g['advance'] for g in self.layout(d)['glyphs']],[8,6])

    def test_overflow_error_midpoint_clipping_and_visible_tangent_extension(self):
        d=self.document(line((10,25),(20,25)),text='AAAA',overflow='error')
        self.assertEqual(self.inspect(d,1)['code'],'TEXT_OVERFLOW')
        clip=self.replace(d,overflow='clip',width=1,height=1);r=self.layout(clip)
        self.assertTrue(r['overflowed']);self.assertEqual([g['path']['drawn'] for g in r['glyphs']],[True,True,False,False]);self.assertEqual(len(r['paths']),2)
        self.assertEqual([g['ink_bounds'] for g in r['glyphs'][2:]],[None,None])
        # Path clipping uses midpoint distance; the nominal rectangular frame is
        # unrelated to glyph visibility, including a glyph's endpoint overhang.
        self.assertGreater(sum(self.pixels(clip)[2][3::4]),0)
        visible=self.replace(d,overflow='visible')
        for g,p in zip(self.layout(visible)['glyphs'],[[10,25],[16,25],[22,25],[28,25]]):self.assert_points(g['origin'],p)
        for doc in (clip,visible):self.assertEqual(self.pixels(doc),self.pixels(self.edit(doc,[dict(op='text_outline',id='label')])))
        negative=self.replace(clip,path=line((10,25),(20,25),start_offset=-9))
        self.assertEqual([g['path']['drawn'] for g in self.layout(negative)['glyphs']],[False,True,True,False])

    def test_text_range_and_path_edits_preserve_source_and_use_current_font_metrics(self):
        d=self.document(text='AA');before=copy.deepcopy(d)
        d=self.edit(d,[dict(op='text_range',id='label',start=0,end=2,text='AB')])
        for g,p in zip(self.layout(d)['glyphs'],[[10,25],[15,25]]):self.assert_points(g['origin'],p)
        moved=self.replace(d,path=line((12,27),(67,27)))
        for g,p in zip(self.layout(moved)['glyphs'],[[12,27],[17,27]]):self.assert_points(g['origin'],p)
        style=dict(font_id='geometry',size=20,fill=[200,40,80,128])
        styled=self.edit(moved,[dict(op='text_range',id='label',start=1,end=2,style=style)])
        self.assertEqual([g['advance'] for g in self.layout(styled)['glyphs']],[6,24]);self.assert_points(self.layout(styled)['glyphs'][1]['ink_bounds'],[18,17,38,27])
        self.assertEqual(before['items'][0]['content']['frame']['text'],'AA');self.assertEqual(before['items'][0]['content']['frame']['path'],self.document()['items'][0]['content']['frame']['path'])

    def test_outlined_svg_roundtrip_matches_live_text_with_transforms_and_alpha(self):
        d=self.document(curved(normal_offset=1),text='ABAB')
        d=self.edit(d,[dict(op='transform',id='label',matrix=[1,.15,.1,1,2,1]),dict(op='properties',id='label',opacity=.6)])
        original=copy.deepcopy(d);outlined=self.edit(d,[dict(op='text_outline',id='label')])
        self.assertEqual(self.pixels(d),self.pixels(outlined))
        artifact=self.exported(d,'svg');root=ET.fromstring(artifact['data']);self.assertEqual(len(root.findall('.//{*}path')),4);self.assertFalse(root.findall('.//{*}text'))
        self.assertEqual(artifact['text_paths'][0]['baseline'],self.layout(d)['baseline_path'])
        self.assertTrue(any('Text exports as glyph outlines' in s for s in artifact['losses']))
        reopened=self.invoke(dict(command='svg.import',id='reopened',source=dict(kind='text',text=artifact['data'])))['document']
        self.assertEqual(self.pixels(d),self.pixels(reopened));self.assertEqual(d,original)
        self.assertEqual(outlined['items'][0]['content']['type'],'group')

    def test_subdivision_invariance_and_nonuniform_collinear_parameterization(self):
        oracle=ArcOracle(CURVE);p=CURVE
        def midpoint(a,b):return [(x+y)/2 for x,y in zip(a,b)]
        a=midpoint(p[0],p[1]);b=midpoint(p[1],p[2]);c=midpoint(p[2],p[3]);d=midpoint(a,b);e=midpoint(b,c);f=midpoint(d,e)
        split=curved();split['geometry']['commands']=[dict(verb='move',to=p[0]),dict(verb='cubic',control1=a,control2=d,to=f),dict(verb='cubic',control1=e,control2=c,to=p[3])]
        layouts=[self.layout(self.document(path,text='ABAB')) for path in (curved(),split)]
        for left,right in zip(layouts[0]['glyphs'],layouts[1]['glyphs']):self.assert_points(left['origin'],right['origin'],.001)
        p=[[10,25],[10,25],[11,25],[65,25]];r=self.layout(self.document(curved(p),text='ABAB'))
        for glyph,origin in zip(r['glyphs'],[10,15,27,32]):self.assert_points(glyph['origin'],[origin,25],.001)

    def test_invalid_baselines_strict_fields_and_paragraph_conflicts_are_explicit(self):
        d=self.document();before=copy.deepcopy(d)
        for kw in [dict(wrap=True),dict(leading=12),dict(text='A\nB')]:self.assertEqual(self.replace(d,expected=1,**kw)['code'],'UNSUPPORTED')
        for path in [line(start_offset=32769),line(normal_offset=32769),line(tolerance=0),line(tolerance=.5),line(unknown=True)]:self.replace(d,expected=1,path=path)
        compound=line();compound['geometry']['commands']+=line((30,25),(50,25))['geometry']['commands']
        self.assertEqual(self.replace(d,expected=1,path=compound)['code'],'UNSUPPORTED')
        collapsed=self.replace(d,path=line((10,25),(10,25)));self.assertEqual(self.inspect(collapsed,1)['code'],'INVALID_DOCUMENT')
        self.assertEqual(d,before)

    def test_curved_alignment_uses_full_measured_length_and_empty_text_stays_empty(self):
        oracle=ArcOracle(CURVE)
        for align in ('center','right'):
            for flip in (False,True):
                d=self.document(curved(flip=flip),text='ABAB',align=align);layout=self.layout(d)
                start=(oracle.length-34)/(2 if align=='center' else 1)
                for g,center in zip(layout['glyphs'],[2.75,10.75,19.75,27.75]):
                    p,_=oracle.sample(start+center,flip)
                    self.assert_points(g['path']['point'],p,layout['baseline_path']['baseline_position_error_bound']+1e-8)
        empty=self.document(curved(),text='');layout=self.layout(empty)
        self.assertEqual(layout['glyphs'],[]);self.assertEqual(layout['paths'],[]);self.assertFalse(layout['overflowed']);self.assertFalse(any(self.pixels(empty)[2]))

    def test_fractional_endpoint_midpoints_are_pinned_and_outside_clip_stays_hidden(self):
        start=[.123456789,15.974154520370698];end=[.8564308130740324,15.986065364285442]
        length=math.dist(start,end)
        d=self.document(line(start,end,start_offset=length-.003),text='A',overflow='visible',style=dict(font_id='geometry',size=.01,fill=[0,0,0,255]))
        g=self.layout(d)['glyphs'][0]
        self.assert_points(g['path']['point'],end,1e-15)
        d=self.replace(d,path=line(start,end,start_offset=-.003),overflow='clip');g=self.layout(d)['glyphs'][0]
        self.assertEqual(g['path']['point'],start);self.assertTrue(g['path']['drawn'])
        d=self.replace(d,path=line(start,end,start_offset=-.0030001));self.assertFalse(self.layout(d)['glyphs'][0]['path']['drawn'])

    def test_baseline_command_and_subdivision_resource_limits_fail_explicitly(self):
        d=self.document();path=line();path['geometry']['commands']=[dict(verb='move',to=[0,20])]+[dict(verb='line',to=[i/32,20+i%2]) for i in range(1024)]
        self.assertEqual(self.replace(d,expected=1,path=path)['code'],'RESOURCE_LIMIT')
        path=curved([[0,0],[32000,32000],[-32000,32000],[0,0]],tolerance=.000001)
        large=self.replace(d,path=path)
        self.assertEqual(self.inspect(large,1)['code'],'RESOURCE_LIMIT')

    def test_ellipse_baseline_reports_conversion_and_matches_independent_quarter_curve(self):
        k=4*(math.sqrt(2)-1)/3
        oracle=ArcOracle([[55,30],[55,30+20*k],[35+20*k,50],[35,50]])
        d=self.document(dict(geometry=dict(shape='ellipse',cx=35,cy=30,rx=20,ry=20)))
        layout=self.layout(d);report=layout['baseline_path']
        self.assertTrue(report['closed']);self.assertIn('four_cubic_ellipse',report['geometry_interpretation'])
        self.assertLess(report['length_interval'][0],4*oracle.length);self.assertGreater(report['length_interval'][1],4*oracle.length)
        for glyph in layout['glyphs']:
            p,v=oracle.sample(glyph['path']['distance'])
            self.assert_points(glyph['path']['point'],p,report['baseline_position_error_bound'])
            self.assert_points(glyph['path']['tangent'],v,3e-5)
        self.assertEqual(json.loads(self.exported(d,'snapshot')['data'])['items'][0]['content']['frame']['path']['geometry'],dict(shape='ellipse',cx=35,cy=30,rx=20,ry=20))

    def test_font_failures_locks_and_batch_rollback_preserve_editable_path(self):
        d=self.document(curved());before=copy.deepcopy(d)
        locked=self.edit(d,[dict(op='properties',id='label',locked=True)])
        self.assertEqual(self.replace(locked,expected=1,path=line())['code'],'LOCKED')
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['path']=line()
        error=self.edit(d,[dict(op='text',id='label',frame=frame),dict(op='remove',id='missing')],1);self.assertEqual(error['operation_index'],1);self.assertEqual(d,before)
        self.assertEqual(self.invoke(dict(command='text.inspect',document=d,id='label'),1)['code'],'FONT_ROOT_REQUIRED')
        missing=self.replace(d,text='X');self.assertEqual(self.inspect(missing,1)['code'],'MISSING_GLYPH')

    def test_artboard_bleed_and_create_only_publication_keep_path_sources(self):
        d=self.document(curved(),text='ABAB');B=boards.BoardCliTests();board=B.board('page',70,45,bleed=dict(top=2,right=2,bottom=2,left=2))
        d['items']=[board,dict(d['items'][0],parent='page')];d=self.invoke(dict(command='document.validate',document=d));before=copy.deepcopy(d)
        result=self.invoke(dict(command='artboard.export',document=d,format='png',font_root=str(self.store),include_bleed=True))['artifacts'][0]['artifact']
        w,h,p,_=editing.png_pixels(base64.b64decode(result['data']));self.assertEqual((w,h),(74,49));self.assertGreater(sum(p[3::4]),0)
        for format,ext in [('png','png'),('svg','svg'),('snapshot','json')]:
            output=dict(output_root=str(self.directory),file_name='path.'+ext,format=format)
            receipt=self.invoke(dict(command='document.publish',document=d,resources=dict(font_root=str(self.store)),output=output))
            data=(self.directory/('path.'+ext)).read_bytes();self.assertEqual(receipt['sha256'],hashlib.sha256(data).hexdigest())
            if format=='svg':self.assertEqual(receipt['text_paths'],self.exported(d,'svg')['text_paths'])
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,resources=dict(font_root=str(self.store)),output=output),1)['code'],'OUTPUT_EXISTS')
            if format=='snapshot':self.assertEqual(json.loads(data),d)
        self.assertEqual(d,before)

    def test_mcp_persistent_path_edit_undo_redo_and_outline_snapshot(self):
        c=Client();self.addCleanup(c.close);c.initialize();d=self.document();session=dict(session_root=str(self.directory/'sessions'),session_id='path-label')
        created=c.success('session.create',**session,request_id='create',document=d,resources=dict(font_root=str(self.store)));d=created['document']
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['path']=line((12,27),(67,27))
        action=dict(type='edit',operations=[dict(op='text',id='label',frame=frame)])
        changed=c.success('session.apply',**session,expected_revision=0,request_id='move',action=action)['document']
        for g,p in zip(c.success('text.inspect',document=changed,id='label',font_root=str(self.store))['layout']['glyphs'],[[12,27],[17,27]]):self.assert_points(g['origin'],p)
        undone=c.success('session.apply',**session,expected_revision=1,request_id='undo',action=dict(type='undo'))['document'];self.assertEqual(undone['items'],d['items'])
        redone=c.success('session.apply',**session,expected_revision=2,request_id='redo',action=dict(type='redo'))['document'];self.assertEqual(redone['items'],changed['items'])
        self.assertEqual(json.loads(c.success('document.export',document=redone,format='snapshot')['data']),redone)


if __name__=='__main__':unittest.main()
