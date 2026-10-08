"""Original motif geometry, independent placement arithmetic and durable edits."""
import base64
import copy
import json
import math
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
from test_strokes_cli import line
from test_stroke_outlines_cli import polygons, area, winding
from test_mcp import Client

COLOR=[30,100,210,255]
def rect(x=-.5,y=-.5,w=1,h=1):return dict(shape='rect',x=x,y=y,width=w,height=h)
def ring():
    g=line([[-1,-1],[1,-1],[1,1],[-1,1]]);g['commands'].append(dict(verb='close'))
    g['commands']+=line([[-.5,-.5],[-.5,.5],[.5,.5],[.5,-.5]])['commands']+[dict(verb='close')]
    return g
def point(m,p):return [m[0]*p[0]+m[2]*p[1]+m[4],m[1]*p[0]+m[3]*p[1]+m[5]]
def center(poly):return [sum(p[k] for p in poly)/len(poly) for k in (0,1)]
def item(d,id='path'):return next(i for i in d['items'] if i['id']==id)

class VectorBrushTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,g=None,brush=None,**stroke):
        d=self.invoke(dict(command='document.create',id='brush-fixture',kind='vector',width=64,height=48))
        style=dict(color=COLOR,width=2,brush=brush or dict(motif=rect(),spacing=4));style.update(stroke)
        return self.edit(d,dict(op='add',item=dict(id='path',content=dict(type='vector',geometry=g or line([[8,12],[40,12]]),stroke=style))))
    def edit(self,d,*ops,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=list(ops)),expected)
        return r if expected else r['document']
    def expand(self,d,id='path',expected=0):
        return self.edit(d,dict(op='stroke_expand',id=id,fill_id=id+'-fill',stroke_id=id+'-outline'),expected=expected)
    def geometry(self,d):return item(self.expand(d),'path-outline')['content']['geometry']
    def pixels(self,d,scale=1):
        p=self.invoke(dict(command='document.export',document=d,format='png',scale=scale))
        return editing.png_pixels(base64.b64decode(p['data']))[:3]
    def set_stroke(self,d,stroke):
        return dict(op='vector',id='path',geometry=item(d)['content']['geometry'],fill=item(d)['content'].get('fill'),stroke=stroke)
    def assert_points(self,actual,expected,tolerance=1e-10):
        self.assertEqual(len(actual),len(expected))
        for a,b in zip(actual,expected):self.assertLessEqual(math.dist(a,b),tolerance,(a,b))

    def test_fixed_spacing_phase_and_exact_axis_aligned_pixels(self):
        for phase in (-9,-1,0,1,4,9):
            d=self.document(brush=dict(motif=rect(),spacing=4,phase=phase))
            centers=[8+2*(phase%4)+8*k for k in range(5) if 2*(phase%4)+8*k<=32]
            ps=polygons(self.geometry(d));self.assert_points([center(p) for p in ps],[[x,12] for x in centers])
            for scale in (1,2):
                w,h,p=self.pixels(d,scale)
                expected=bytes(v for y in range(h) for x in range(w) for v in (COLOR if 11<=(y+.5)/scale<13 and any(c-1<=(x+.5)/scale<c+1 for c in centers) else [0]*4))
                self.assertEqual(p,expected)

    def test_uniform_fit_closes_spacing_without_duplicate_seam(self):
        for closed in (False,True):
            g=line([[8,12],[30,12]])
            if closed:g['commands'].append(dict(verb='close'))
            for phase in (0,1,-1):
                d=self.document(g,dict(motif=rect(),spacing=4,phase=phase,fit='uniform'))
                n=6 if closed else 3;length=44 if closed else 22
                distances=[(k+(phase%4)/4)*length/n for k in range(n+1)]
                distances=[v for v in distances if v<length or (not closed and v==length)]
                expected=[[8+min(v,44-v) if closed else 8+v,12] for v in distances]
                self.assert_points([center(p) for p in polygons(self.geometry(d))],expected)

    def test_variable_width_scales_both_motif_axes_without_resetting_spacing(self):
        profile=[[0,0],[.25,2],[.75,1],[1,0]]
        d=self.document(width_profile=profile)
        ps=polygons(self.geometry(d))
        self.assert_points([center(p) for p in ps],[[16,12],[24,12],[32,12]])
        self.assertEqual([area(p) for p in ps],[16,9,4])
        self.assertEqual(self.pixels(d,3),self.pixels(self.expand(d),3))

    def test_corners_use_custom_orientations_and_distance_clearance(self):
        g=line([[8,12],[24,12],[24,28]])
        motif=rect(-.5,-.25,1,.5);corner=rect(-1,-.25,2,.5)
        for orientation,u in [('incoming',[1,0]),('outgoing',[0,1]),('bisector',[2**-.5,2**-.5])]:
            b=dict(motif=motif,spacing=2,corner_motif=corner,corner_orientation=orientation,corner_clearance=2)
            d=self.document(g,b);ps=polygons(self.geometry(d))
            self.assert_points([center(p) for p in ps[:-1]],[[8,12],[12,12],[16,12],[24,20],[24,24],[24,28]])
            expected=[point([2*u[0],2*u[1],-2*u[1],2*u[0],24,12],p) for p in [[-1,-.25],[1,-.25],[1,.25],[-1,.25]]]
            self.assert_points(ps[-1],expected)
            self.assertEqual(self.pixels(d,3),self.pixels(self.expand(d),3))
        b['corner_angle']=100
        self.assertEqual(len(polygons(self.geometry(self.document(g,b)))),9)

    def test_closed_corners_include_seam_and_cyclic_clearance(self):
        g=rect(12,12,16,16)
        b=dict(motif=rect(),spacing=2,fit='uniform',corner_motif=rect(-1,-.25,2,.5),corner_clearance=2,corner_orientation='outgoing')
        ps=polygons(self.geometry(self.document(g,b)))
        self.assert_points([center(p) for p in ps],[[20,12],[28,20],[20,28],[12,20],[12,12],[28,12],[28,28],[12,28]])
        # Different seam factors would create inconsistent repeated artwork.
        bad=self.document(g,b);item(bad)['content']['stroke']['width_profile']=[[0,1],[1,2]]
        self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'INVALID_DOCUMENT')

    def test_endpoint_motifs_clearance_degenerate_paths_and_reversals(self):
        b=dict(motif=rect(),spacing=2,start_motif=rect(-1,-.5,1,1),end_motif=rect(0,-.5,2,1),end_clearance=2)
        ps=polygons(self.geometry(self.document(line([[8,12],[24,12]]),b)))
        self.assert_points([center(p) for p in ps],[[16,12],[7,12],[26,12]])
        reverse=polygons(self.geometry(self.document(line([[24,12],[8,12]]),b)))
        self.assert_points([center(p) for p in reverse],[[16,12],[25,12],[6,12]])
        d=self.document(line([[16,16],[16,16]]),dict(motif=rect(),spacing=2,phase=1))
        self.assert_points([center(p) for p in polygons(self.geometry(d))],[[16,16]])
        d=self.document(line([[8,12],[24,12],[8,12]]),dict(motif=rect(),spacing=2,corner_motif=rect(-1,-.25,2,.5),corner_clearance=1))
        ps=polygons(self.geometry(d));self.assert_points(ps[-1],[[26,12.5],[22,12.5],[22,11.5],[26,11.5]])
        empty=self.document(width_profile=[[0,0],[1,0]])
        expanded=self.expand(empty);self.assertEqual(len(expanded['items']),2);self.assertFalse(any(self.pixels(empty)[2]))

    def test_compound_centerlines_reset_phase_and_compound_motifs_retain_holes(self):
        g=line([[8,12],[40,12]]);g['commands']+=line([[8,28],[40,28]])['commands']
        d=self.document(g,dict(motif=ring(),spacing=4))
        ps=polygons(self.geometry(d));self.assertEqual(len(ps),20)
        w,h,p=self.pixels(d)
        expected=bytes(v for y in range(h) for x in range(w) for v in (COLOR if any(abs(x+.5-cx)<2 and abs(y+.5-cy)<2 and not(abs(x+.5-cx)<1 and abs(y+.5-cy)<1) for cy in [12,28] for cx in [8,16,24,32,40]) else [0]*4))
        self.assertEqual(p,expected);self.assertEqual(self.pixels(d,3),self.pixels(self.expand(d),3))
        for y in range(48):
            for x in range(64):self.assertEqual(sum(winding(poly,x+.5,y+.5) for poly in ps)!=0,expected[(y*64+x)*4+3]!=0)

    def test_cubic_centerline_matches_independent_dense_arc_length_and_tangent(self):
        controls=[[8,30],[8,2],[44,2],[44,30]]
        g=dict(shape='path',commands=[dict(verb='move',to=controls[0]),dict(verb='cubic',control1=controls[1],control2=controls[2],to=controls[3])])
        def bez(t):return [sum(controls[i][k]*v for i,v in enumerate([(1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3])) for k in (0,1)]
        n=20000;table=[(0,0,bez(0))];length=0
        for i in range(1,n+1):
            p=bez(i/n);length+=math.dist(p,table[-1][2]);table.append((length,i/n,p))
        d=self.document(g,dict(motif=rect(),spacing=4),curve_tolerance=.0001)
        ps=polygons(self.geometry(d));self.assertEqual(len(ps),math.floor(length/8)+1)
        cursor=0
        for k,p in enumerate(ps):
            at=k*8
            while cursor+1<len(table) and table[cursor+1][0]<at:cursor+=1
            a,b=table[cursor:cursor+2];f=(at-a[0])/(b[0]-a[0]);t=a[1]*(1-f)+b[1]*f
            self.assertLess(math.dist(center(p),bez(t)),.0002)
            tangent=[sum(3*(controls[i+1][j]-controls[i][j])*v for i,v in enumerate([(1-t)**2,2*t*(1-t),t*t])) for j in (0,1)]
            norm=math.hypot(*tangent);u=[v/norm for v in tangent];actual=[(p[1][j]-p[0][j])/2 for j in (0,1)]
            self.assertLess(math.dist(u,actual),.004)
        self.assertEqual(self.pixels(d,2),self.pixels(self.expand(d),2))

    def test_curved_motif_controls_are_transformed_without_flattening(self):
        motif=dict(shape='path',commands=[dict(verb='move',to=[-.5,0]),dict(verb='cubic',control1=[-.5,-1],control2=[.5,-1],to=[.5,0]),dict(verb='cubic',control1=[.5,1],control2=[-.5,1],to=[-.5,0]),dict(verb='close')])
        d=self.document(line([[20,8],[20,24]]),dict(motif=motif,spacing=4))
        commands=self.geometry(d)['commands'];self.assertEqual(len(commands),12)
        for k in range(3):
            for a,b in zip(commands[k*4:k*4+4],motif['commands']):
                self.assertEqual(a['verb'],b['verb'])
                for key in ('to','control1','control2'):
                    if key in b:self.assertEqual(a[key],point([0,2,-2,0,20,8+8*k],b[key]))

    def test_scaling_policies_and_affine_hierarchy_have_independent_geometry(self):
        for scaling in ('object','document'):
            d=self.document(line([[0,0],[8,0]]),dict(motif=rect(),spacing=2),scaling=scaling)
            m=[3,0,1,2,8,12]
            d=self.edit(d,dict(op='group',ids=['path'],new_id='parent'),dict(op='transform',id='parent',matrix=m))
            ps=polygons(self.geometry(d));world=[[point(m,p) for p in poly] for poly in ps]
            centers=[[8+12*k,12] for k in range(3)] if scaling=='object' else [[8+4*k,12] for k in range(7)]
            self.assert_points([center(p) for p in world],centers)
            self.assertEqual([round(area(p),9) for p in world],[24 if scaling=='object' else 4]*len(world))
            self.assertEqual(self.pixels(d,3),self.pixels(self.expand(d),3))
        d=self.document(line([[0,0],[8,0]]),dict(motif=rect(),spacing=2),scaling='document')
        m=[-2,1,.5,2,40,12];item(d)['transform']=m;ps=polygons(self.geometry(d))
        a,b=point(m,[0,0]),point(m,[8,0]);length=math.dist(a,b);u=[(b[k]-a[k])/length for k in (0,1)]
        world=[[point(m,p) for p in poly] for poly in ps]
        for k,poly in enumerate(world):self.assert_points([center(poly)],[[a[j]+4*k*u[j] for j in (0,1)]]);self.assertAlmostEqual(area(poly),4)

    def test_overlap_coverage_paint_opacity_and_expansion_appearance(self):
        d=self.document(brush=dict(motif=ring(),spacing=1),color=[30,100,210,128])
        item(d)['opacity']=.5
        self.assertEqual(max(self.pixels(d,3)[2][3::4]),64)
        item(d)['content']['stroke']['color']=dict(type='linear',start=[0,0],end=[64,0],stops=[dict(offset=0,color=[255,20,0,255]),dict(offset=1,color=[0,40,255,128])])
        item(d)['clip']=dict(geometry=rect(10,6,32,16))
        item(d)['mask']=dict(width=1,height=1,gray_hex='c0',transform=[64,0,0,48,0,0],sampling='nearest',clip=False)
        item(d)['effects']=[dict(id='shadow',operator=dict(type='shadow',offset=[1,2],sigma=0),color=[0,0,0,100])]
        item(d)['content']['fill']=[100,80,60,180];item(d)['transform']=[1,.125,.25,1,0,0]
        d=json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data'])
        before=copy.deepcopy(d);expanded=self.expand(d)
        self.assertEqual(self.pixels(d,3),self.pixels(expanded,3));self.assertEqual(d,before)
        self.assertEqual(item(expanded,'path-fill')['content']['geometry'],item(d)['content']['geometry'])
        for key in ('opacity','transform','clip','mask','effects'):self.assertEqual(item(expanded)[key],item(d)[key])

    def test_shared_mask_and_component_placements_evaluate_fixed_document_spacing(self):
        d=self.document(line([[2,4],[10,4]]),dict(motif=rect(),spacing=2),scaling='document',color=[255]*4)
        source=item(d);source['parent']='mask'
        d['items']=[dict(id='mask',content=dict(type='mask_source')),source]
        for id,m in [('large',[2,0,0,2,4,4]),('small',[1,0,0,1,36,4])]:
            d['items'].append(dict(id=id,transform=m,content=dict(type='vector',geometry=rect(0,0,12,8),fill=COLOR),artwork_mask=dict(source='mask',region=[0,0,12,8],mode='alpha')))
        w,h,p=self.pixels(d)
        centers=[(x,12) for x in (8,12,16,20,24)]+[(x,8) for x in (38,42,46)]
        expected=bytes(v for y in range(h) for x in range(w) for v in (COLOR if any(cx-1<=x<cx+1 and cy-1<=y<cy+1 for cx,cy in centers) else [0]*4))
        self.assertEqual(p,expected);self.assertEqual(self.expand(d,expected=1)['code'],'UNSUPPORTED')
        component=copy.deepcopy(d);component['items'][0]['content']['type']='component_source';source=item(component);source['content']['stroke']['color']=COLOR
        component['items']=component['items'][:2]+[dict(id='copy',transform=[2,0,0,2,4,4],content=dict(type='instance',instance=dict(source='mask')))]
        detached=self.edit(component,dict(op='instance_unlink',id='copy'));child=next(i['id'] for i in detached['items'] if i['id']!='path' and i['content']['type']=='vector')
        self.assertEqual(self.pixels(component,2),self.pixels(self.expand(detached,child),2))

    def test_svg_and_artboard_delivery_retain_outlines_and_disclose_editing_loss(self):
        d=self.document(line([[8,12],[24,12],[24,28]]),dict(motif=ring(),spacing=4,corner_motif=rect(),corner_clearance=1))
        result=self.invoke(dict(command='document.export',document=d,format='svg'))
        self.assertTrue(any('brush' in loss.lower() for loss in result['losses']))
        root=ET.fromstring(result['data']);self.assertFalse(any('stroke-dasharray' in node.attrib for node in root.iter()))
        imported=self.invoke(dict(command='svg.import',id='brush-import',source=dict(kind='text',text=result['data'])))['document']
        self.assertEqual(self.pixels(d,3),self.pixels(imported,3))
        item(d)['parent']='board';d['items'].insert(0,dict(id='board',transform=[.5,0,0,.5,20,5],content=dict(type='frame',frame=dict(role='artboard',width=64,height=48))))
        artifact=self.invoke(dict(command='artboard.export',document=d,format='png',scale=2))['artifacts'][0]['artifact']
        plain=copy.deepcopy(d);plain['items']=plain['items'][1:];item(plain)['parent']=None
        self.assertEqual(editing.png_pixels(base64.b64decode(artifact['data']))[:3],self.pixels(plain,2))

    def test_spacing_edit_snapshot_inspection_and_source_retention(self):
        d=self.document();before=copy.deepcopy(d);stroke=copy.deepcopy(item(d)['content']['stroke']);stroke['brush']['spacing']=2;stroke['brush']['phase']=1
        changed=self.edit(d,self.set_stroke(d,stroke))
        self.assertEqual(len(polygons(self.geometry(d))),5);self.assertEqual(len(polygons(self.geometry(changed))),8);self.assertEqual(d,before)
        inspected=self.invoke(dict(command='document.inspect',document=changed))
        self.assertEqual(inspected['items'][0]['stroke'],stroke)
        restored=json.loads(self.invoke(dict(command='document.export',document=changed,format='snapshot'))['data'])
        self.assertEqual(restored,changed);self.assertEqual(self.pixels(restored,2),self.pixels(changed,2))

    def test_mcp_durable_spacing_edit_expansion_retries_undo_redo_and_publication(self):
        d=self.document();stroke=copy.deepcopy(item(d)['content']['stroke']);stroke['brush']['spacing']=2
        c=Client();self.addCleanup(lambda client=c:client.close() if not client.process.stdin.closed else None);c.initialize()
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='vector-brush')
            c.success('session.create',**session,request_id='create',document=d)
            args=dict(**session,request_id='spacing',expected_revision=0,action=dict(type='edit',operations=[self.set_stroke(d,stroke)]))
            edited=c.success('session.apply',**args)['document'];self.assertTrue(c.success('session.apply',**args)['replayed'])
            c.close();c=Client();self.addCleanup(c.close);c.initialize()
            expanded=c.success('session.apply',**session,request_id='expand',expected_revision=1,action=dict(type='edit',operations=[dict(op='stroke_expand',id='path',fill_id='f',stroke_id='s')]))['document']
            self.assertEqual(self.pixels(edited,2),self.pixels(expanded,2))
            undone=c.success('session.apply',**session,request_id='undo',expected_revision=2,action=dict(type='undo'))['document'];self.assertEqual(undone['items'],edited['items'])
            redone=c.success('session.apply',**session,request_id='redo',expected_revision=3,action=dict(type='redo'))['document'];self.assertEqual(redone['items'],expanded['items'])
            published=c.success('session.publish',**session,expected_revision=4,output=dict(format='png',output_root=root,file_name='brush.png'))
            self.assertTrue(published);c.success('session.verify',**session)

    def test_strict_controls_open_motifs_combinations_and_atomic_locked_edits(self):
        d=self.document()
        for patch in [dict(spacing=0),dict(spacing=1025),dict(phase=32769),dict(corner_angle=0),dict(motif=line([[0,0],[1,0]])),dict(motif=rect(16,0,1,1)),dict(warp=True),dict(fit='stretch'),dict(corner_clearance=1),dict(end_clearance=1)]:
            bad=copy.deepcopy(d);item(bad)['content']['stroke']['brush'].update(patch)
            self.invoke(dict(command='document.validate',document=bad),1)
        for patch in [dict(dash=dict(array=[])),dict(cap='round'),dict(join='bevel'),dict(miter_limit=3),dict(end_arrow=dict(kind='triangle',length=2,width=2))]:
            bad=copy.deepcopy(d);item(bad)['content']['stroke'].update(patch)
            self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'UNSUPPORTED')
        locked=copy.deepcopy(d);item(locked)['locked']=True
        self.assertEqual(self.expand(locked,expected=1)['code'],'LOCKED')
        stroke=copy.deepcopy(item(d)['content']['stroke']);stroke['brush']['spacing']=2
        self.edit(d,self.set_stroke(d,stroke),dict(op='stroke_expand',id='path',fill_id='same',stroke_id='same'),expected=1)
        self.assertEqual(item(d)['content']['stroke']['brush']['spacing'],4)

    def test_hidden_patterns_storage_generated_work_and_world_bounds_are_limited(self):
        d=self.document()
        for width,spacing,transform in [(2,.001,[1,0,0,1,0,0]),(.001,1,[1,0,0,1,0,0]),(2,1,[512,0,0,1,0,0])]:
            bad=copy.deepcopy(d);node=item(bad);node['visible']=False;node['transform']=transform;node['content']['stroke'].update(width=width,scaling='document');node['content']['stroke']['brush']['spacing']=spacing
            self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'LIMIT_EXCEEDED')
        bad=copy.deepcopy(d);commands=ring()['commands']*410;item(bad)['content']['stroke']['brush']['motif']=dict(shape='path',commands=commands)
        self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'RESOURCE_LIMIT')
        # Each stored motif fits individually; their aggregate must also fit.
        bad=copy.deepcopy(d);motif=dict(shape='path',commands=ring()['commands']*110);b=item(bad)['content']['stroke']['brush'];b.update(motif=motif,start_motif=motif,end_motif=motif,corner_motif=motif)
        self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'RESOURCE_LIMIT')

    def test_mixed_open_closed_contours_endpoint_policy_and_original_corner_anchors(self):
        g=line([[8,8],[24,8],[24,8],[24,24]])
        g['commands']+=line([[36,8],[52,8],[52,24],[36,24]])['commands']+[dict(verb='close')]
        b=dict(motif=rect(),spacing=4,start_motif=rect(-1,-.5,1,1),end_motif=rect(0,-.5,1,1),corner_motif=rect(),corner_clearance=0)
        ps=polygons(self.geometry(self.document(g,b)))
        # One open corner despite the duplicate vertex; four closed corners.
        self.assertEqual(len(ps),13)
        self.assert_points([center(p) for p in ps[:5]],[[16,8],[24,16],[7,8],[24,25],[24,8]])
        self.assert_points([center(p) for p in ps[-4:]],[[36,8],[52,8],[52,24],[36,24]])
        g=dict(shape='path',commands=[dict(verb='move',to=[8,24]),dict(verb='cubic',control1=[8,8],control2=[40,8],to=[40,24])])
        plain=self.document(g,dict(motif=rect(),spacing=4),curve_tolerance=.001)
        corner=self.document(g,dict(motif=rect(),spacing=4,corner_motif=rect(-1,-1,2,2)),curve_tolerance=.001)
        self.assertEqual(self.geometry(plain),self.geometry(corner))

    def test_decimal_seams_and_corner_replacement_obey_distance_precision(self):
        for w,h,n in [(.15,.3,3),(.3,.15,3),(.3,.3,4)]:
            d=self.document(rect(10,10,w,h),dict(motif=rect(-.01,-.01,.02,.02),spacing=.3),width=1)
            ps=polygons(self.geometry(d));self.assertEqual(len(ps),n)
            self.assertTrue(all(math.dist(center(p),center(ps[0]))>.1 for p in ps[1:]))
        b=dict(motif=rect(-.01,-.01,.02,.02),spacing=.3,corner_motif=rect(-.02,-.01,.04,.02),corner_orientation='outgoing')
        d=self.document(line([[10,10],[10.3,10],[10.3,10.3]]),b,width=1)
        ps=polygons(self.geometry(d));self.assertEqual(len(ps),3)
        self.assert_points([center(p) for p in ps],[[10,10],[10.3,10.3],[10.3,10]])
        # The allowance includes cumulative addition, not just cancellation
        # at individual coordinates: 3000 * 0.7 / 14 is exactly 150 periods.
        g=line([[.7 if i%2 else 0,0] for i in range(3001)]);g['commands'].append(dict(verb='close'))
        d=self.document(g,dict(motif=rect(-.01,-.01,.02,.02),spacing=14),width=1)
        self.assertEqual(len(polygons(self.geometry(d))),150)
        # A requested interval smaller than the declared conservative
        # measurement bound fails instead of silently merging placements.
        bad=self.document(line([[10,10],[10.00000000000001,10]]),dict(motif=rect(),spacing=4))
        item(bad)['content']['stroke']['brush']['fit']='uniform'
        self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'UNSUPPORTED')

    def test_dense_valid_strokes_have_atomic_expansion_and_aggregate_work_limits(self):
        d=self.document(brush=dict(motif=rect(),spacing=.015))
        before=copy.deepcopy(d)
        self.assertEqual(self.expand(d,expected=1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(d,before)
        bad=copy.deepcopy(d);bad['items']=[]
        for i in range(7):
            node=copy.deepcopy(item(d));node['id']='dense-'+str(i);node['visible']=False;bad['items'].append(node)
        self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'LIMIT_EXCEEDED')
        bad=self.document();item(bad)['content']['geometry']=line([[8+(i%2),8+i*.1] for i in range(150)])
        item(bad)['content']['stroke']['brush'].update(spacing=.1,corner_motif=rect())
        self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'LIMIT_EXCEEDED')

if __name__=='__main__':unittest.main()
