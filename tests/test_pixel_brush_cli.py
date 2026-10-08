"""Independent vertical integrals, dab spacing, hash streams and pixel recurrences."""
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
import test_editing_cli as editing
from test_images_cli import canonical
from test_mcp import Client

INK=[30,100,210,255]

def brush(points=None,**kw):
    result=dict(points=[dict(point=p) for p in (points or [[5.5,5.5]])],diameter=4,mode=dict(type='paint',color=INK))
    result.update(kw);return result

def integrate(fn,a,b,eps=1e-10):
    def split(a,b,fa,fm,fb,area,e,depth):
        m=(a+b)/2;l=fn((a+m)/2);r=fn((m+b)/2);left=(m-a)*(fa+4*l+fm)/6;right=(b-m)*(fm+4*r+fb)/6;d=left+right-area
        if abs(d)<=15*e or depth==0:return left+right+d/15
        return split(a,m,fa,l,fm,left,e/2,depth-1)+split(m,b,fm,r,fb,right,e/2,depth-1)
    fa,fm,fb=fn(a),fn((a+b)/2),fn(b)
    return split(a,b,fa,fm,fb,(b-a)*(fa+4*fm+fb)/6,eps,24)

def kernel_area(center,diameter,hardness,x,y):
    """Integrate exact polynomial vertical slices in x; engine integrates disk area in radius^2."""
    R=diameter/2
    if not R:return 0
    x0,x1=x-center[0],x+1-center[0];y0,y1=y-center[1],y+1-center[1];inner=hardness*R
    def vertical(u,r,polynomial):
        square=r*r-u*u
        if square<=0:return 0
        side=math.sqrt(square);a,b=max(y0,-side),min(y1,side)
        if b<=a:return 0
        return square*(b-a)-(b**3-a**3)/3 if polynomial else b-a
    def f(u):
        if hardness==1:return vertical(u,R,False)
        return (vertical(u,R,True)-vertical(u,inner,True))/(R*R-inner*inner)
    breaks={x0,x1}
    for r in [R,inner]:
        breaks.update(v for v in [-r,r] if x0<v<x1)
        for yy in [y0,y1]:
            if abs(yy)<r:
                root=math.sqrt(r*r-yy*yy);breaks.update(v for v in [-root,root] if x0<v<x1)
    points=sorted(breaks)
    return max(0,min(1,sum(integrate(f,a,b) for a,b in zip(points,points[1:]))))

def pm(c):return [c[k]*c[3]/65025 for k in range(3)]+[c[3]/255]
def encoded(c):
    byte=lambda v:math.floor(max(0,min(1,v))*255+.5)
    a=byte(c[3]);return [byte(c[k]/c[3]) for k in range(3)]+[a] if a else [0]*4
def over(b,s,w):return [s[k]*w+b[k]*(1-s[3]*w) for k in range(4)]
def lerp(a,b,t):return [x+(y-x)*t for x,y in zip(a,b)]

class PixelBrushTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,w=12,h=12,colors=None):
        d=self.invoke(dict(command='document.create',id='brush-fixture',kind='raster',width=w,height=h))
        raw=bytes(v for c in colors for v in c) if colors is not None else bytes(w*h*4)
        item=dict(id='pixels',content=dict(type='raster',width=w,height=h,rgba_hex=raw.hex()))
        return self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=item)]))['document']
    def apply(self,d,stroke,expected=0,**kw):return self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='brush_stroke',id='pixels',stroke=stroke)],**kw),expected)
    def raw(self,d):return bytes.fromhex(next(i for i in d['items'] if i['id']=='pixels')['content']['rgba_hex'])
    def inspect(self,s,expected=0):return self.invoke(dict(command='brush.inspect',stroke=s,include_dabs=True),expected)
    def pixels(self,d):return editing.png_pixels(base64.b64decode(self.invoke(dict(command='document.export',document=d,format='png'))['data']))[2]

    def test_single_hard_soft_dabs_independent_coverage_and_analytic_mass(self):
        for center,diameter,hardness in [([5.5,5.5],1,1),([5,5],2,1),([5.25,5.75],5,0),([5.13,5.69],6,.4),([4.77,6.01],3,.9)]:
            s=brush([center],diameter=diameter,hardness=hardness);d=self.apply(self.document(),s)['document'];actual=self.raw(d)
            expected=[];continuous=0
            for y in range(12):
                for x in range(12):
                    area=kernel_area(center,diameter,hardness,x,y);continuous+=area;expected+=(INK[:3]+[math.floor(area*255+.5)] if area*255>=.5 else [0]*4)
            self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,expected)),1)
            self.assertAlmostEqual(continuous,math.pi*(diameter/2)**2*(1+hardness**2)/2,delta=1e-7)
            self.assertEqual(self.pixels(d),actual)

    def test_spacing_dynamic_controls_endpoints_and_exact_subdivision(self):
        s=brush([[1,2],[13,2],[13,8]],diameter=4,spacing=.5)
        s['points'][0].update(size=.25,opacity=.2);s['points'][1].update(size=1,opacity=.8);s['points'][2].update(size=.5,opacity=1)
        r=self.inspect(s);self.assertEqual(r['length'],18);self.assertEqual([d['distance'] for d in r['dabs']],list(range(0,19,2)))
        for dab in r['dabs']:
            t=dab['distance'];expected=[1+t,2] if t<=12 else [13,t-10]
            self.assertEqual(dab['center'],expected);self.assertAlmostEqual(dab['diameter'],1+t/4 if t<=12 else 4-(t-12)/3)
            self.assertAlmostEqual(dab['opacity'],.2+t*.05 if t<=12 else .8+(t-12)/30)
        split=copy.deepcopy(s);split['points'].insert(1,dict(point=[7,2],size=.625,opacity=.5))
        for a,b in zip(self.inspect(split)['dabs'],r['dabs']):
            for key in ['center','path_point']:self.assertEqual(a[key],b[key])
            for key in ['diameter','distance','opacity']:self.assertAlmostEqual(a[key],b[key],places=14)
        d=self.document(20,12);self.assertEqual(self.raw(self.apply(d,s)['document']),self.raw(self.apply(d,split)['document']))
        end=brush([[0,0],[5,0]],diameter=4,spacing=.5);self.assertEqual([d['distance'] for d in self.inspect(end)['dabs']],[0,2,4,5]);end['include_end']=False;self.assertEqual([d['distance'] for d in self.inspect(end)['dabs']],[0,2,4])

    def test_coincident_nodes_last_controls_zero_size_opacity_and_noop_preservation(self):
        s=brush([[5,5],[5,5]]);s['points'][-1].update(size=0,opacity=0)
        self.assertEqual(self.inspect(s)['dab_count'],1);self.assertEqual(self.inspect(s)['dabs'][0]['diameter'],0)
        d=self.document(2,2,[[200,20,70,0]]*4);r=self.apply(d,s);self.assertEqual(self.raw(r['document']),self.raw(d));self.assertEqual(r['changes'][0]['details']['changed_pixels'],0)
        for kw in [dict(flow=0),dict(opacity=0),dict(mode=dict(type='paint',color=[1,2,3,0]))]:self.assertEqual(self.raw(self.apply(d,brush([[1,1]],**kw))['document']),self.raw(d))

    def test_flow_accumulation_separate_whole_stroke_opacity_and_single_encoding(self):
        s=brush([[3.5,5.5],[7.5,5.5],[3.5,5.5]],diameter=2,spacing=2,flow=.3,opacity=.4,mode=dict(type='paint',color=[180,50,20,128]))
        original=[[10,40,80,64]]*144;d=self.document(colors=original);r=self.apply(d,s);pixels=self.raw(r['document']);p=5*12+3
        a=pm(original[p]);color=pm([180,50,20,128]);after=over(over(a,color,.3),color,.3)
        self.assertEqual(list(pixels[p*4:p*4+4]),encoded(lerp(a,after,.4)))
        self.assertEqual(self.raw(d),bytes(v for c in original for v in c));self.assertEqual(r['changes'][0]['details']['dab_count'],3)

    def test_stateless_scatter_matches_independent_sha256_and_repeats(self):
        s=brush([[2,4],[10,4]],diameter=2,spacing=1,scatter=1.5,seed=902)
        r=self.inspect(s)
        for i,d in enumerate(r['dabs']):
            digest=hashlib.sha256(b'inkbolt.brush.scatter.v1\0'+struct.pack('<IQ',902,i)).digest();words=struct.unpack('<II',digest[:8]);j=[2*(v+.5)/2**32-1 for v in words]
            for k in range(2):self.assertAlmostEqual(d['center'][k],d['path_point'][k]+j[k]*1.5,places=14)
        d=self.document();a=self.apply(d,s);self.assertEqual(a,self.apply(d,s));different=self.apply(d,dict(s,seed=903));self.assertNotEqual(self.raw(a['document']),self.raw(different['document']))

    def test_texture_selection_and_transformed_native_grid_are_explicit(self):
        d=self.document(4,4);d['width']=12;d['height']=12;d['items'][0]['transform']=[2,0,0,2,1,2]
        selection=bytes(128 if x<5 else 255 if x<8 else 0 for y in range(12) for x in range(12));d['selection']=dict(width=12,height=12,gray_hex=selection.hex())
        s=brush([[2,2]],diameter=20,use_selection=True,texture=dict(width=2,height=2,gray_hex='0080ff40',origin=[-.5,1],scale=[1,2]))
        out=self.raw(self.apply(d,s)['document']);tile=[0,128,255,64]
        for y in range(4):
            for x in range(4):
                t=tile[(math.floor((y+.5-1)/2)%2)*2+math.floor(x+1)%2];selected=selection[math.floor(2*(y+.5)+2)*12+math.floor(2*(x+.5)+1)];alpha=math.floor(t*selected/255+.5)
                self.assertEqual(list(out[(y*4+x)*4:(y*4+x+1)*4]),INK[:3]+[alpha] if alpha else [0]*4)
        self.assertEqual(d['selection']['gray_hex'],selection.hex())

    def test_eraser_preserves_color_and_obeys_whole_opacity(self):
        original=[[25,100,210,192]]*144;d=self.document(colors=original);s=brush([[5.5,5.5]],diameter=4,hardness=.4,flow=.6,opacity=.3,mode=dict(type='erase'))
        out=self.raw(self.apply(d,s)['document'])
        for y in range(12):
            for x in range(12):
                k=kernel_area([5.5,5.5],4,.4,x,y);alpha=math.floor(192*(1-.3*.6*k)+.5);self.assertEqual(list(out[(y*12+x)*4:(y*12+x+1)*4]),[25,100,210,alpha])

    def test_smudge_uses_pre_dab_surface_and_fractional_premultiplied_samples(self):
        w,h=8,5;original=[[20*x,30*y,120,(64,128,255)[(x+y)%3]] for y in range(h) for x in range(w)];d=self.document(w,h,original)
        for border in ['transparent','clamp']:
            centers=[[-.75,2.5],[.5,2.5],[1.75,2.5]];s=brush(centers,diameter=2.5,spacing=.5,hardness=.6,flow=.7,opacity=.8,mode=dict(type='smudge',border=border));values=list(map(pm,original))
            for previous,center in zip(centers,centers[1:]):
                before=copy.deepcopy(values);dx=center[0]-previous[0];dy=center[1]-previous[1]
                for y in range(h):
                    for x in range(w):
                        weight=kernel_area(center,2.5,.6,x,y)*.7
                        xx,yy=x-dx,y-dy;ix,iy=math.floor(xx),math.floor(yy);fx,fy=xx-ix,yy-iy;sample=[0]*4
                        for qx,qy,a in [(ix,iy,(1-fx)*(1-fy)),(ix+1,iy,fx*(1-fy)),(ix,iy+1,(1-fx)*fy),(ix+1,iy+1,fx*fy)]:
                            if border=='clamp':qx,qy=max(0,min(w-1,qx)),max(0,min(h-1,qy))
                            if 0<=qx<w and 0<=qy<h:sample=[b+c*a for b,c in zip(sample,before[qy*w+qx])]
                        values[y*w+x]=lerp(before[y*w+x],sample,weight)
            expected=[v for a,b in zip(map(pm,original),values) for v in encoded(lerp(a,b,.8))];actual=self.raw(self.apply(d,s)['document'])
            self.assertLessEqual(max(abs(a-b) for a,b in zip(expected,actual)),1)

    def test_mixer_pickup_load_and_memory_follow_independent_recurrence(self):
        original=[[20,40,200,255],[200,50,20,255],[10,180,60,255],[150,90,80,255]]*4;d=self.document(4,4,original)
        s=brush([[1,2],[3,2]],diameter=20,spacing=.05,flow=.6,opacity=.7,mode=dict(type='mixer',color=[220,40,80,192],pickup=.35,load=.2))
        color=pm(s['mode']['color']);values=list(map(pm,original));reservoir=color
        for _ in range(3):
            average=[sum(v[k] for v in values)/16 for k in range(4)];reservoir=lerp(lerp(reservoir,color,.2),average,.35);values=[over(v,reservoir,.6) for v in values]
        expected=[v for a,b in zip(map(pm,original),values) for v in encoded(lerp(a,b,.7))]
        self.assertEqual(self.raw(self.apply(d,s)['document']),bytes(expected))
        s['mode']['pickup']=0;paint=copy.deepcopy(s);paint['mode']=dict(type='paint',color=s['mode']['color']);self.assertEqual(self.raw(self.apply(d,s)['document']),self.raw(self.apply(d,paint)['document']))

    def test_details_hashes_changed_bounds_and_snapshot_delivery(self):
        d=self.document();s=brush();result=self.apply(d,s);r=result['changes'][0]['details'];out=result['document'];a,b=self.raw(d),self.raw(out)
        self.assertEqual(r['source_sha256'],hashlib.sha256(canonical(12,12,a)).hexdigest());self.assertEqual(r['result_sha256'],hashlib.sha256(canonical(12,12,b)).hexdigest());self.assertEqual(r['stroke_sha256'],self.inspect(s)['stroke_sha256'])
        changed=[i for i in range(144) if a[4*i:4*i+4]!=b[4*i:4*i+4]];self.assertEqual(r['changed_pixels'],len(changed));self.assertEqual(r['changed_bounds'],[min(i%12 for i in changed),min(i//12 for i in changed),1+max(i%12 for i in changed),1+max(i//12 for i in changed)])
        saved=self.invoke(dict(command='document.export',document=out,format='snapshot'));self.assertEqual(json.loads(saved['data']),out)

    def test_locks_atomic_rollback_cancellation_and_invalid_context(self):
        d=self.document();original=copy.deepcopy(d);d['items'][0]['locked']=True;self.assertEqual(self.apply(d,brush(),1)['code'],'LOCKED');d=original
        error=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='brush_stroke',id='pixels',stroke=brush()),dict(op='remove',id='missing')]),1);self.assertEqual(error['operation_index'],1);self.assertEqual(d,original)
        self.assertEqual(self.apply(d,brush(),1,control=dict(timeout_ms=0))['code'],'TIMEOUT');self.assertEqual(self.apply(d,brush(use_selection=True),1)['code'],'INVALID_BRUSH')
        other=copy.deepcopy(d);other['items'][0]['content']=dict(type='group');self.assertEqual(self.apply(other,brush(),1)['code'],'INVALID_OPERATION')

    def test_invalid_brush_fields_dimensions_textures_points_and_dab_budget(self):
        for kw in [dict(diameter=0),dict(diameter=513),dict(hardness=1.01),dict(flow=-1),dict(spacing=.001),dict(scatter=4.1),dict(mode=dict(type='mixer',color=INK,pickup=2,load=0)),dict(texture=dict(width=1,height=1,gray_hex='zz'))]:self.assertEqual(self.inspect(brush(**kw),1)['code'],'INVALID_BRUSH')
        self.assertEqual(self.inspect(brush([[0,0],[32768,0]],diameter=.25,spacing=.01),1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.inspect(brush([[0,0]]*1025),1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.inspect(brush(unsupported=True),1)['code'],'INVALID_REQUEST')

    def test_native_boundaries_hidden_rgb_and_extreme_hardness_remain_explicit(self):
        d=self.document(4,4,[[200,40,30,0]]*16)
        self.assertEqual(self.raw(self.apply(d,brush([[32768,-32768]]))['document']),self.raw(d))
        for h in [0,.000000001,.999999999,1]:
            a=self.raw(self.apply(d,brush([[.125,.25]],diameter=.25,hardness=h))['document']);self.assertGreater(a[3],0);self.assertEqual(a[4:],self.raw(d)[4:])

    def test_mcp_persistent_brush_undo_redo_retry_and_create_only_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            c=Client();self.addCleanup(c.close);c.initialize();s=brush([[2,3],[9,8]],hardness=.5,scatter=.2,seed=71);self.assertEqual(c.success('brush.inspect',stroke=s,include_dabs=True),self.inspect(s))
            session=dict(session_root=str(Path(temp)/'sessions'),session_id='brush');d=self.document();c.success('session.create',**session,request_id='create',document=d)
            request=dict(**session,request_id='paint',expected_revision=0,action=dict(type='edit',operations=[dict(op='brush_stroke',id='pixels',stroke=s)]));painted=c.success('session.apply',**request)['document']
            self.assertEqual(self.raw(painted),self.raw(self.apply(d,s)['document']));self.assertEqual(c.success('session.apply',**request)['document'],painted)
            undone=c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.raw(undone),self.raw(d))
            redone=c.success('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'))['document'];self.assertEqual(self.raw(redone),self.raw(painted))
            output=dict(output_root=temp,file_name='brush.png',format='png');receipt=c.success('document.publish',document=redone,output=output);self.assertEqual(receipt['sha256'],hashlib.sha256((Path(temp)/'brush.png').read_bytes()).hexdigest());self.assertTrue(c.tool('document.publish',document=redone,output=output)['isError'])

    def test_programmatic_size_opacity_ramps_match_independent_pixel_recurrence(self):
        w,h=12,10;original=[[5*x,10*y,60,128] for y in range(h) for x in range(w)];d=self.document(w,h,original)
        s=brush([[2.5,3.5],[8.5,3.5],[8.5,7.5]],diameter=4,spacing=.5,hardness=.3,flow=.65,opacity=.8,mode=dict(type='paint',color=[210,30,70,192]))
        s['points'][0].update(size=.25,opacity=.1);s['points'][1].update(size=1,opacity=.9);s['points'][2].update(size=0,opacity=.2)
        dabs=[([2.5+t,3.5],1+t*.5,.1+t*.8/6) if t<=6 else ([8.5,t-2.5],4-(t-6),.9-(t-6)*.7/4) for t in range(0,11,2)]
        values=list(map(pm,original));color=pm(s['mode']['color'])
        for center,diameter,opacity in dabs:
            for y in range(h):
                for x in range(w):values[y*w+x]=over(values[y*w+x],color,kernel_area(center,diameter,.3,x,y)*.65*opacity)
        expected=[v for a,b in zip(map(pm,original),values) for v in encoded(lerp(a,b,.8))];actual=self.raw(self.apply(d,s)['document'])
        self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,expected)),1)

    def test_large_fractional_tip_edges_match_independent_vertical_integrals(self):
        for diameter in [.25,1.3,15,128,512]:
            for hardness in [0,.65,.95,1]:
                center=[diameter/2+.137,1.619];s=brush([center],diameter=diameter,hardness=hardness);actual=self.raw(self.apply(self.document(4,4),s)['document'])
                for y in range(4):
                    for x in range(4):
                        expected=math.floor(kernel_area(center,diameter,hardness,x,y)*255+.5);self.assertLessEqual(abs(actual[(y*4+x)*4+3]-expected),1,(diameter,hardness,x,y))

    def test_work_preflight_rejects_full_frame_stamping_and_preserves_source(self):
        d=self.document(256,256);before=self.raw(d);s=brush([[64 if i%2==0 else 192,128] for i in range(90)],diameter=512,spacing=.01,mode=dict(type='smudge'))
        error=self.apply(d,s,1);self.assertEqual(error['code'],'RESOURCE_LIMIT');self.assertIn('preflight',error['message']);self.assertEqual(self.raw(d),before)
        s['opacity']=0;self.assertEqual(self.raw(self.apply(d,s)['document']),before)

if __name__=='__main__':unittest.main()
