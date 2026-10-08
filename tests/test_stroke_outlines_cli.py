"""Independent original ribbon/arrow geometry, coverage and expansion contracts."""
import base64
import copy
from fractions import Fraction as F
import json
import math
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_strokes_cli as strokes
import test_editing_cli as editing
from test_mcp import Client


def polygons(g):
    out=[];p=[]
    for c in g['commands']:
        if c['verb']=='move':p=[c['to']]
        elif c['verb']=='line':p.append(c['to'])
        else:assert c['verb']=='close';out.append(p)
    return out


def area(p):return abs(sum(x*v-y*u for (x,y),(u,v) in zip(p,p[1:]+p[:1])))/2


def winding(poly,x,y):
    winding=0
    for (a,b),(c,d) in zip(poly,poly[1:]+poly[:1]):
        if b<=y<d or d<=y<b:
            crossing=a+(y-b)*(c-a)/(d-b)
            if crossing>x:winding+=1 if d>b else -1
    return winding


def contains(poly,x,y):return winding(poly,x,y)!=0


def clipped_area(poly,x,y,scale):
    p=[tuple(F(str(v)) for v in pair) for pair in poly]
    for axis,bound,sign in [(0,F(x,scale),1),(0,F(x+1,scale),-1),(1,F(y,scale),1),(1,F(y+1,scale),-1)]:
        out=[]
        for a,b in zip(p,p[1:]+p[:1]):
            inside_a=(a[axis]-bound)*sign>=0;inside_b=(b[axis]-bound)*sign>=0
            if inside_a:out.append(a)
            if inside_a!=inside_b:
                t=(bound-a[axis])/(b[axis]-a[axis]);out.append(tuple(a[k]+t*(b[k]-a[k]) for k in range(2)))
        p=out
        if not p:return F(0)
    return area(p)*scale*scale


class StrokeOutlineTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    document=strokes.StrokeCliTests.document
    pixels=strokes.StrokeCliTests.pixels

    def expand(self,d,expected=0,**ids):
        return self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='stroke_expand',id='path',fill_id='fill',stroke_id='outline',**ids)]),expected)

    def test_piecewise_width_profile_matches_independent_clipped_polygon_areas(self):
        profile=[[0,0],[.25,2],[.75,1],[1,0]]
        d=self.document(strokes.line([[4,12],[36,12]]),width_profile=profile)
        polygon=[[4+32*t,12-r] for t,r in profile]+[[4+32*t,12+r] for t,r in reversed(profile)]
        w,h,p=self.pixels(d,2)
        for y in range(h):
            for x in range(w):
                coverage=clipped_area(polygon,x,y,2);actual=p[(y*w+x)*4+3]
                # The licensed display backend uses a 4x4 coverage grid. Exact
                # clipped area is a geometry oracle, not its antialias contract.
                samples=sum(contains(polygon,F(8*x+2*sx+1,16),F(8*y+2*sy+1,16)) for sx in range(4) for sy in range(4))
                self.assertLessEqual(abs(actual-min(255,samples*16)),1,(x,y,coverage,actual,samples))
                if coverage in (0,1):self.assertEqual(actual,int(coverage*255))
        expanded=self.expand(d)['document']
        self.assertEqual(self.pixels(d,4),self.pixels(expanded,4))
        total=sum(area(p) for p in polygons(expanded['items'][2]['content']['geometry']))
        self.assertEqual(total,area(polygon))
        self.assertEqual(expanded['items'][1]['content']['geometry'],d['items'][0]['content']['geometry'])

    def test_profiles_follow_whole_contour_across_dashes_and_reset_at_subpaths(self):
        g=strokes.line([[4,8],[36,8]]);g['commands']+=strokes.line([[4,18],[36,18]])['commands']
        d=self.document(g,array=[4,4],width_profile=[[0,0],[1,4]])
        w,h,p=self.pixels(d,2)
        self.assertEqual(p[4*w*4:12*w*4],p[24*w*4:32*w*4])
        expanded=self.expand(d)['document'];polys=polygons(expanded['items'][2]['content']['geometry'])
        # Four independently predicted trapezoids per line, with increasing width.
        wanted=[4*((a/8)+(a+4)/8) for a in (0,8,16,24)]*2
        self.assertEqual([area(p) for p in polys],wanted)
        self.assertEqual(self.pixels(d,3),self.pixels(expanded,3))

    def test_all_arrow_shapes_have_independent_geometry_area_and_endpoint_placement(self):
        areas=dict(triangle=32,chevron=20.8,diamond=32,bar=64,ellipse=16*math.pi)
        for kind,wanted in areas.items():
            with self.subTest(kind=kind):
                arrow=dict(kind=kind,length=8,width=8)
                d=self.document(strokes.line([[8,12],[32,12]]),width_profile=[[0,0],[1,0]],start_arrow=arrow,end_arrow=arrow,curve_tolerance=.002)
                r=self.expand(d);expanded=r['document'];poly=polygons(expanded['items'][2]['content']['geometry'])
                self.assertEqual(len(poly),2)
                for shape in poly:self.assertAlmostEqual(area(shape),wanted,delta=.1 if kind=='ellipse' else 1e-12)
                all_points=[p for shape in poly for p in shape];self.assertAlmostEqual(min(p[0] for p in all_points),8);self.assertAlmostEqual(max(p[0] for p in all_points),32)
                for scale in (1,4):self.assertEqual(self.pixels(d,scale),self.pixels(expanded,scale))

    def test_arrow_tangents_use_original_curve_handles_and_skip_zero_handles(self):
        for controls in [([8,4],[24,4]),([8,12],[24,4]),([8,4],[24,12])]:
            g=dict(shape='path',commands=[dict(verb='move',to=[8,12]),dict(verb='cubic',control1=controls[0],control2=controls[1],to=[24,12])])
            arrow=dict(kind='triangle',length=6,width=4)
            d=self.document(g,width_profile=[[0,0],[1,0]],start_arrow=arrow,end_arrow=arrow)
            ps=polygons(self.expand(d)['document']['items'][2]['content']['geometry'])
            self.assertEqual(len(ps),2)
            start_handle=next(p for p in [*controls,[24,12]] if p!=[8,12]);end_handle=next(p for p in [*reversed(controls),[8,12]] if p!=[24,12])
            for shape,tip,other in zip(ps,[[8,12],[24,12]],[start_handle,end_handle]):
                dx,dy=tip[0]-other[0],tip[1]-other[1];length=math.hypot(dx,dy);u,v=dx/length,dy/length
                wanted=[tip,[tip[0]-6*u-2*v,tip[1]-6*v+2*u],[tip[0]-6*u+2*v,tip[1]-6*v-2*u]]
                for p in wanted:self.assertTrue(any(math.dist(p,q)<1e-10 for q in shape),(p,shape))

    def test_arrows_trim_shafts_without_projecting_caps_or_resetting_dash_phase(self):
        for kind in ('triangle','chevron','diamond','ellipse','bar'):
            arrow=dict(kind=kind,length=8,width=8)
            d=self.document(strokes.line([[8,12],[32,12]]),array=[5,3],offset=-1,cap='round',start_arrow=arrow,end_arrow=arrow,width_profile=[[0,.5],[1,2]])
            ps=polygons(self.expand(d)['document']['items'][2]['content']['geometry'])
            points=[p for poly in ps for p in poly]
            self.assertGreaterEqual(min(p[0] for p in points),8-1e-12);self.assertLessEqual(max(p[0] for p in points),32+1e-12)
            w,h,p=self.pixels(d,4)
            self.assertFalse(any(p[(y*w+x)*4+3] for y in range(h) for x in list(range(32))+list(range(128,w))))
            # The first painted interval originally spans distances 1..6. The
            # forced start cut at distance 4 retains its original end at 6.
            shaft=ps[0];self.assertAlmostEqual(min(p[0] for p in shaft),12)
            self.assertAlmostEqual(max(p[0] for p in shaft),14+(.5+1.5*6/24),delta=.02)

    def test_closed_profile_seams_degenerate_contours_and_empty_expansion(self):
        profile=[[0,1],[.25,2],[.5,.5],[.75,1.5],[1,1]]
        d=self.document(dict(shape='rect',x=8,y=6,width=16,height=12),width_profile=profile,join='round')
        expanded=self.expand(d)['document']
        for scale in (1,3):self.assertEqual(self.pixels(d,scale),self.pixels(expanded,scale))
        w,h,p=self.pixels(d);self.assertEqual(p[(12*w+16)*4+3],0)
        for cap in ('butt','round','square'):
            d=self.document(strokes.line([[12,12],[12,12]]),cap=cap,width_profile=[[0,2],[1,3]])
            r=self.expand(d);self.assertEqual(r['changes'][0]['details']['empty_stroke'],cap=='butt')
            self.assertEqual(self.pixels(d,4),self.pixels(r['document'],4))
            if cap=='butt':self.assertEqual(len(r['document']['items']),2)
        for g in [dict(shape='rect',x=8,y=6,width=16,height=12),dict(shape='path',commands=[dict(verb='move',to=[8,12]),dict(verb='cubic',control1=[8,4],control2=[24,4],to=[24,12])])]:
            d=self.document(g,width_profile=[[0,0],[1,0]],cap='round');r=self.expand(d)
            self.assertTrue(r['changes'][0]['details']['empty_stroke']);self.assertEqual(len(r['document']['items']),2);self.assertFalse(any(self.pixels(d)[2]))

    def test_profiles_arrows_and_crossing_ribbons_receive_paint_opacity_once(self):
        g=strokes.line([[4,4],[28,20],[28,4],[4,20]])
        d=self.document(g,cap='round',join='round',width_profile=[[0,1],[.5,2],[1,1]],end_arrow=dict(kind='triangle',length=12,width=10))
        d['items'][0]['content']['stroke']['color']=[30,100,210,128];d['items'][0]['opacity']=.5
        w,h,p=self.pixels(d,3);self.assertEqual(max(p[3::4]),64)
        for i in range(w*h):
            if p[4*i+3]:self.assertEqual(p[4*i:4*i+3],bytes([30,100,210]))
        self.assertEqual(self.pixels(d,3),self.pixels(self.expand(d)['document'],3))

    def test_expansion_preserves_fill_gradient_transform_masks_effects_and_blend(self):
        g=dict(shape='rect',x=6,y=6,width=16,height=10)
        d=self.document(g,width_profile=[[0,1],[.5,2],[1,1]],join='bevel')
        item=d['items'][0];item['transform']=[-1,.125,.25,1,30,0];item['opacity']=.75;item['fill_opacity']=.625;item['blend']='multiply'
        item['content']['fill']=[80,170,40,192]
        item['content']['stroke']['color']=dict(type='linear',start=[0,0],end=[32,0],stops=[dict(offset=0,color=[255,50,0,128]),dict(offset=1,color=[0,30,255,220])])
        item['clip']=dict(geometry=dict(shape='rect',x=5,y=5,width=20,height=15))
        item['mask']=dict(width=1,height=1,gray_hex='c0',transform=[40,0,0,24,0,0],sampling='nearest',clip=False)
        item['effects']=[dict(id='shadow',operator=dict(type='shadow',offset=[1,1],sigma=0),color=[10,20,50,90])]
        background=dict(id='back',content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=40,height=24),fill=[220,180,150,255]))
        d['items'].insert(0,background)
        d=json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data'])
        item=d['items'][1];before=copy.deepcopy(d);expanded=self.expand(d)['document']
        for scale in (1,2,4):self.assertEqual(self.pixels(d,scale),self.pixels(expanded,scale))
        self.assertEqual(d,before)
        group=next(i for i in expanded['items'] if i['id']=='path')
        for key in ('transform','opacity','fill_opacity','blend','clip','mask','effects'):self.assertEqual(group[key],item[key])

    def test_round_ribbons_match_independent_segment_distances_through_crossings_and_reversals(self):
        fixtures=[([[4,4],[28,20],[28,4],[4,20]],False,4),([[4,8],[28,8],[4,8]],False,4),([[12,12],[13,12],[13,13],[12,13]],True,10),([[4,8],[28,8],[5,8.1],[28,9]],False,6),([[8,4],[28,4],[20,20],[8,4],[28,4]],True,4)]
        for points,closed,width in fixtures:
            g=strokes.line(points)
            if closed:g['commands'].append(dict(verb='close'));points=points+[points[0]]
            # Independently, a constant round stroke is the set of points
            # within radius width/2 of at least one finite centerline segment.
            d=self.document(g,cap='round',join='round');d['items'][0]['content']['stroke']['width']=width
            expanded=self.expand(d)['document'];ps=polygons(expanded['items'][2]['content']['geometry'])
            def distance(x,y):
                ds=[]
                for (a,b),(c,e) in zip(points,points[1:]):
                    vx,vy=c-a,e-b;length=vx*vx+vy*vy
                    t=max(0,min(1,((x-a)*vx+(y-b)*vy)/length)) if length else 0
                    ds.append(math.hypot(x-a-t*vx,y-b-t*vy))
                return min(ds)
            for yi in range(48):
                for xi in range(80):
                    x,y=xi/2+.193,yi/2+.137;dist=distance(x,y)
                    if abs(dist-width/2)>.02:self.assertEqual(sum(winding(p,x,y) for p in ps)!=0,dist<width/2,(points,width,x,y,dist))
            w,h,p=self.pixels(d,2)
            for y in range(h):
                for x in range(w):
                    dist=distance((x+.5)/2,(y+.5)/2)
                    if abs(dist-width/2)>.4:self.assertEqual(p[(y*w+x)*4+3],255 if dist<width/2 else 0,(points,x,y,dist))
            self.assertEqual(self.pixels(d,2),self.pixels(expanded,2))

    def test_rectangular_joins_and_miter_fallback_match_independent_corner_regions(self):
        for join,limit in [('miter',4),('miter',1),('bevel',4),('round',4)]:
            d=self.document(dict(shape='rect',x=8,y=6,width=16,height=12),join=join,miter_limit=limit)
            d['items'][0]['content']['stroke']['width']=4
            ps=polygons(self.expand(d)['document']['items'][2]['content']['geometry'])
            def inside(x,y):
                dx=max(8-x,0,x-24);dy=max(6-y,0,y-18)
                metric=math.hypot(dx,dy) if join=='round' else dx+dy if join=='bevel' or limit==1 else max(dx,dy)
                return metric<2 and not(10<x<22 and 8<y<16)
            for y in (i/3+.113 for i in range(72)):
                for x in (i/3+.117 for i in range(120)):
                    # Avoid only the declared round-arc approximation band.
                    if join=='round' and abs(math.hypot(max(8-x,0,x-24),max(6-y,0,y-18))-2)<.02:continue
                    self.assertEqual(sum(winding(p,x,y) for p in ps)!=0,inside(x,y),(join,limit,x,y))

    def test_variable_corner_matches_independent_trapezoid_and_bevel_union(self):
        d=self.document(strokes.line([[4,8],[20,8],[20,20]]),width_profile=[[0,1],[4/7,2],[1,0]],join='bevel')
        ps=polygons(self.expand(d)['document']['items'][2]['content']['geometry'])
        reference=[[[4,7],[20,6],[20,10],[4,9]],[[18,8],[22,8],[20,20]],[[20,8],[20,6],[22,8]]]
        for yi in range(48):
            for xi in range(80):
                x,y=xi/2+.193,yi/2+.137
                self.assertEqual(sum(winding(p,x,y) for p in ps)!=0,any(contains(p,x,y) for p in reference),(x,y))

    def test_shared_masks_artboards_and_svg_keep_profiles_and_expansion_pixels(self):
        d=self.document(strokes.line([[4,8],[20,16],[36,8]]),cap='round',join='round',width_profile=[[0,.5],[.5,2],[1,1]],end_arrow=dict(kind='triangle',length=8,width=6))
        d['items'][0]['content']['stroke']['color']=[255]*4;direct=self.pixels(d,2)
        d['items'][0]['parent']='source'
        d['items']=[dict(id='source',content=dict(type='mask_source')),d['items'][0],dict(id='board',content=dict(type='frame',frame=dict(role='artboard',width=40,height=24))),dict(id='ink',parent='board',artwork_mask=dict(source='source',region=[0,0,40,24],mode='alpha'),content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=40,height=24),fill=[255]*4))]
        expanded=self.expand(d)['document']
        self.assertEqual(self.pixels(d,2),direct);self.assertEqual(self.pixels(expanded,2),direct)
        board=self.invoke(dict(command='artboard.export',document=expanded,format='png',scale=2))
        self.assertEqual(editing.png_pixels(base64.b64decode(board['artifacts'][0]['artifact']['data']))[:3],direct)
        svg=self.invoke(dict(command='document.export',document=d,format='svg'))['data']
        imported=self.invoke(dict(command='svg.import',id='profile-mask-import',source=dict(kind='text',text=svg)))['document']
        self.assertEqual(self.pixels(imported,2),direct)

    def test_generated_outline_document_render_mask_and_svg_range_budgets(self):
        d=self.document(strokes.line([[0,0],[1,0]]),cap='round',width_profile=[[0,1],[1,1]],curve_tolerance=.00001)
        d['width']=1;d['height']=512;d['items'][0]['content']['stroke']['width']=1024
        self.invoke(dict(command='document.validate',document=d))
        many=copy.deepcopy(d);many['items']=[dict(copy.deepcopy(d['items'][0]),id=f'p{i}',visible=False) for i in range(5)]
        self.assertIn('outline',self.invoke(dict(command='document.validate',document=many),1)['message'])
        tall=copy.deepcopy(d);tall['height']=8192
        self.assertIn('outline',self.invoke(dict(command='document.render',document=tall),1)['message'])
        source=copy.deepcopy(d['items'][0]);source['parent']='source'
        def owner(id,parent=None):return dict(id=id,parent=parent,artwork_mask=dict(source='source',region=[0,0,1,512],mode='alpha'),content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=1,height=512),fill=[255]*4))
        masks=copy.deepcopy(d);masks['items']=[dict(id='source',content=dict(type='mask_source')),source]+[owner(f'o{i}') for i in range(12)]
        self.invoke(dict(command='document.validate',document=masks))
        self.assertIn('outline',self.invoke(dict(command='document.render',document=masks),1)['message'])
        self.assertIn('outline',self.invoke(dict(command='document.export',document=masks,format='svg'),1)['message'])
        boards=copy.deepcopy(d);boards['items']=masks['items'][:2]
        for i in range(24):boards['items']+=[dict(id=f'b{i}',content=dict(type='frame',frame=dict(role='artboard',width=1,height=512))),owner(f'o{i}',f'b{i}')]
        self.assertIn('outline',self.invoke(dict(command='artboard.export',document=boards,format='svg'),1)['message'])

    def test_svg_outlines_preserve_pixels_and_report_editable_control_loss(self):
        d=self.document(strokes.line([[4,8],[20,16],[36,8]]),array=[4,2],width_profile=[[0,.5],[.5,2],[1,1]],cap='round',join='round',end_arrow=dict(kind='diamond',length=8,width=6))
        d['items'][0]['transform']=[-.75,0,.25,.75,30,2]
        svg=self.invoke(dict(command='document.export',document=d,format='svg'))
        self.assertTrue(any('Width profiles' in s and 'arrowheads' in s for s in svg['losses']))
        paths=ET.fromstring(svg['data']).findall('.//{*}path');self.assertEqual(len(paths),1);self.assertIsNone(paths[0].get('stroke'));self.assertEqual(paths[0].get('fill-rule'),'nonzero')
        imported=self.invoke(dict(command='svg.import',id='outlined-import',source=dict(kind='text',text=svg['data'])))['document']
        for scale in (1,4):self.assertEqual(self.pixels(d,scale),self.pixels(imported,scale))

    def test_atomic_validation_locks_profile_precision_and_outline_limits(self):
        d=self.document();before=copy.deepcopy(d)
        bad=[dict(width_profile=[[0,1]]),dict(width_profile=[[.1,1],[1,1]]),dict(width_profile=[[0,1],[.5,-1],[1,1]]),dict(width_profile=[[0,1],[.5,1],[.5,2],[1,1]]),dict(width_profile=[[0,1024],[1,1024]]),dict(curve_tolerance=0),dict(curve_tolerance=1.001),dict(end_arrow=dict(kind='triangle',length=0,width=2)),dict(start_arrow=dict(kind='triangle',length=2,width=2,rotation=90))]
        for settings in bad:
            b=copy.deepcopy(d);b['items'][0]['content']['stroke'].update(settings)
            self.invoke(dict(command='document.validate',document=b),1)
        b=copy.deepcopy(d);b['items'][0]['content']['geometry']=dict(shape='rect',x=4,y=4,width=12,height=12);b['items'][0]['content']['stroke']['width_profile']=[[0,1],[1,2]]
        self.assertIn('Closed-contour',self.invoke(dict(command='document.validate',document=b),1)['message'])
        for ids in [('path','outline'),('same','same'),('invalid id','outline')]:
            self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='stroke_expand',id='path',fill_id=ids[0],stroke_id=ids[1])]),1)
        locked=copy.deepcopy(d);locked['items'][0]['locked']=True;self.assertEqual(self.expand(locked,1)['code'],'LOCKED')
        dense=self.document(array=[.01,.01]);self.assertEqual(self.expand(dense,1)['code'],'RESOURCE_LIMIT')
        b=copy.deepcopy(d);b['items'][0]['content']['stroke'].update(width=1024,curve_tolerance=1e-7,cap='round');self.assertIn('outline',self.invoke(dict(command='document.validate',document=b),1)['message'])
        b=copy.deepcopy(d);b['items'][0]['content']['stroke']['width_profile']=[[0,1],[5e-324,2],[1,1]]
        self.assertEqual(self.invoke(dict(command='document.validate',document=b),1)['code'],'UNSUPPORTED')
        self.assertEqual(d,before)

    def test_mcp_expansion_schema_persistence_undo_redo_retry_and_source_retention(self):
        d=self.document(width_profile=[[0,.5],[1,2]],end_arrow=dict(kind='triangle',length=8,width=6))
        c=Client();self.addCleanup(c.close);c.initialize();operation=dict(op='stroke_expand',id='path',fill_id='fill',stroke_id='outline')
        expected=self.expand(d)['document']
        self.assertEqual(c.success('document.edit',document=d,expected_revision=d['revision'],operations=[operation])['document'],expected)
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='stroke-expansion');c.success('session.create',**session,request_id='create',document=d)
            args=dict(**session,request_id='expand',expected_revision=0,action=dict(type='edit',operations=[operation]))
            result=c.success('session.apply',**args);self.assertEqual(result['document']['items'],expected['items']);self.assertTrue(c.success('session.apply',**args)['replayed'])
            undone=c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(undone['items'],d['items'])
            redone=c.success('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'))['document'];self.assertEqual(self.pixels(redone),self.pixels(d));c.success('session.verify',**session)


if __name__=='__main__':unittest.main()
