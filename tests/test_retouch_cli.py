"""Independent dense linear systems, affine samples and retouch boundary measurements."""
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import tempfile
import unittest
import test_editing_cli as editing
from test_images_cli import canonical
from test_mcp import Client


def pm(c):
    return [c[k]*c[3]/65025 for k in range(3)]+[c[3]/255]


def encode(c):
    byte=lambda v:math.floor(max(0,min(1,v))*255+.5)
    a=byte(c[3])
    return [byte(c[k]/c[3]) for k in range(3)]+[a] if a else [0]*4


def adjacent(i,w,h):
    x,y=i%w,i//w
    return [yy*w+xx for xx,yy in [(x-1,y),(x+1,y),(x,y-1),(x,y+1)] if 0<=xx<w and 0<=yy<h]


def dense_solve(matrix,b):
    """Pivoted elimination; production uses sparse preconditioned conjugate gradients."""
    a=[list(row)+[v] for row,v in zip(matrix,b)];n=len(a)
    for j in range(n):
        pivot=max(range(j,n),key=lambda i:abs(a[i][j]));a[j],a[pivot]=a[pivot],a[j]
        assert abs(a[j][j])>1e-13
        scale=a[j][j];a[j]=[v/scale for v in a[j]]
        for i in range(n):
            if i!=j:
                scale=a[i][j];a[i]=[x-scale*y for x,y in zip(a[i],a[j])]
    return [row[-1] for row in a]


def sample(pixels,w,h,x,y,method='bilinear',border='error'):
    if method=='nearest':taps=[(math.floor(x),math.floor(y),1)]
    else:
        x-=.5;y-=.5;ix,iy=math.floor(x),math.floor(y);fx,fy=x-ix,y-iy
        taps=[(ix,iy,(1-fx)*(1-fy)),(ix+1,iy,fx*(1-fy)),(ix,iy+1,(1-fx)*fy),(ix+1,iy+1,fx*fy)]
    out=[0.0]*4
    for xx,yy,a in taps:
        if not a:continue
        if border=='clamp':xx,yy=max(0,min(w-1,xx)),max(0,min(h-1,yy))
        if not(0<=xx<w and 0<=yy<h):
            assert border!='error'
            continue
        out=[v+a*c for v,c in zip(out,pm(pixels[yy*w+xx]))]
    return out


def reference(target,source,w,h,sw,sh,options,selection=None,world=(1,0,0,1,0,0),canvas=None):
    r=options['region'];mask=bytes.fromhex(r['gray_hex']) if r.get('gray_hex') is not None else bytes([255])*r['width']*r['height']
    weights=[0.0]*(w*h)
    for y in range(r['y'],r['y']+r['height']):
        for x in range(r['x'],r['x']+r['width']):
            a=mask[(y-r['y'])*r['width']+x-r['x']]/255
            if options.get('use_selection'):
                xx=math.floor(world[0]*(x+.5)+world[2]*(y+.5)+world[4]);yy=math.floor(world[1]*(x+.5)+world[3]*(y+.5)+world[5])
                a*=selection[yy*canvas[0]+xx]/255 if 0<=xx<canvas[0] and 0<=yy<canvas[1] else 0
            weights[y*w+x]=a
    ids=[i for i,a in enumerate(weights) if a];lookup={i:j for j,i in enumerate(ids)}
    mode=options['mode'];heal=mode['type']=='heal';needed=set(ids)
    if heal:needed.update(j for i in ids for j in adjacent(i,w,h))
    m=options.get('source_transform',[1,0,0,1,0,0]);field={}
    for i in needed:
        x,y=i%w+.5,i//w+.5
        field[i]=sample(source,sw,sh,m[0]*x+m[2]*y+m[4],m[1]*x+m[3]*y+m[5],options.get('sampling','bilinear'),options.get('border','error'))
    before=list(map(pm,target));values={i:field[i][:] for i in ids}
    if heal and ids:
        matrix=[]
        for i in ids:
            row=[0.0]*len(ids);row[lookup[i]]=len(adjacent(i,w,h))+mode.get('screening',0)
            for j in adjacent(i,w,h):
                if j in lookup:row[lookup[j]]-=1
            matrix.append(row)
        for k in range(4):
            b=[sum(before[j][k]-field[j][k] for j in adjacent(i,w,h) if j not in lookup) for i in ids]
            corrections=dense_solve(matrix,b)
            for i,c in zip(ids,corrections):values[i][k]+=c
    out=copy.deepcopy(target);clamped=0
    for i in ids:
        raw=values[i];a=max(0,min(1,raw[3]));v=[max(0,min(a,c)) for c in raw[:3]]+[a];clamped+=v!=raw
        t=weights[i]*options.get('opacity',1);v=[old+(new-old)*t for old,new in zip(before[i],v)]
        if v!=before[i]:out[i]=encode(v)
    return out,weights,clamped


def options(w=3,h=3,x=2,y=2,mode='clone',**kw):
    result=dict(source_id='source',region=dict(x=x,y=y,width=w,height=h),mode=dict(type=mode) if isinstance(mode,str) else mode)
    result.update(kw);return result


class RetouchTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,w,h,target,source=None,sw=None,sh=None):
        d=self.invoke(dict(command='document.create',id='original-retouch-fixture',kind='raster',width=w,height=h))
        def item(id,pixels,w,h):return dict(id=id,visible=id=='pixels',content=dict(type='raster',width=w,height=h,rgba_hex=bytes(v for c in pixels for v in c).hex()))
        items=[item('pixels',target,w,h)]
        if source is not None:items.append(item('source',source,sw or w,sh or h))
        return self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items]))['document']
    def apply(self,d,o,expected=0,**kw):return self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='retouch',id='pixels',options=o)],**kw),expected)
    def colors(self,d,id='pixels'):
        raw=bytes.fromhex(next(i for i in d['items'] if i['id']==id)['content']['rgba_hex'])
        return [list(raw[i:i+4]) for i in range(0,len(raw),4)]
    def close_pixels(self,a,b,limit=1):self.assertLessEqual(max((abs(x-y) for aa,bb in zip(a,b) for x,y in zip(aa,bb)),default=0),limit)

    def test_clone_overlap_reads_frozen_source_and_preserves_original(self):
        w,h=8,6;pixels=[[x*25,y*35,70,255] for y in range(h) for x in range(w)];d=self.document(w,h,pixels);saved=copy.deepcopy(d)
        o=options(6,6,2,0,source_id='pixels',source_transform=[1,0,0,1,-2,0]);result=self.apply(d,o);actual=self.colors(result['document'])
        expected=[pixels[y*w+(x-2 if x>=2 else x)] for y in range(h) for x in range(w)]
        self.assertEqual(actual,expected);self.assertEqual(d,saved)
        receipt=result['changes'][0]['details'];self.assertEqual(receipt['source_sha256'],receipt['target_before_sha256']);self.assertEqual(receipt['region_pixels'],36)

    def test_fractional_affine_clone_matches_premultiplied_samples_and_soft_mask(self):
        rng=random.Random(63);w,h=7,6
        src=[[rng.randrange(256) for _ in range(4)] for _ in range(w*h)];dst=[[rng.randrange(256) for _ in range(4)] for _ in range(w*h)]
        o=options(4,3,1,1,source_transform=[.8,.1,-.05,1.1,1.2,-.1],opacity=.63,region=dict(x=1,y=1,width=4,height=3,gray_hex=bytes([0,64,128,255]*3).hex()))
        result=self.apply(self.document(w,h,dst,src),o);expected,_,_=reference(dst,src,w,h,w,h,o)
        self.close_pixels(self.colors(result['document']),expected);self.assertEqual(self.colors(result['document'],'source'),src)

    def test_nearest_reflection_and_explicit_source_border_policies(self):
        w,h=4,3;src=[[x*70,y*80,90,255] for y in range(h) for x in range(w)];dst=[[50,60,70,200]]*(w*h);d=self.document(w,h,dst,src)
        for sampling in ['nearest','bilinear']:
            for border in ['clamp','transparent']:
                o=options(w,h,0,0,source_transform=[-1,0,0,1,3.7,-.6],sampling=sampling,border=border)
                expected,_,_=reference(dst,src,w,h,w,h,o);self.close_pixels(self.colors(self.apply(d,o)['document']),expected)
        o['border']='error';self.assertEqual(self.apply(d,o,1)['code'],'INVALID_RETOUCH')
        o=options(1,1,1,1,source_transform=[1,0,0,1,0,0]);self.assertTrue(self.apply(d,o)['document'])

    def test_heal_matches_independent_dense_system_for_color_alpha_and_screening(self):
        rng=random.Random(17);w,h=7,6
        src=[[rng.randrange(30,220) for _ in range(3)]+[rng.randrange(80,256)] for _ in range(w*h)]
        dst=[[rng.randrange(30,220) for _ in range(3)]+[rng.randrange(80,256)] for _ in range(w*h)]
        for screening in [0,.7,16]:
            o=options(4,3,1,1,mode=dict(type='heal',screening=screening,tolerance=1e-12),opacity=.8,region=dict(x=1,y=1,width=4,height=3,gray_hex=bytes([255,128,0,255,255,255,255,64,255,255,255,255]).hex()))
            expected,weights,_=reference(dst,src,w,h,w,h,o);r=self.apply(self.document(w,h,dst,src),o);actual=self.colors(r['document']);self.close_pixels(actual,expected)
            self.assertTrue(all(actual[i]==dst[i] for i,a in enumerate(weights) if not a));self.assertLessEqual(max(r['changes'][0]['details']['solver_residuals']),1e-12)

    def test_healing_restores_original_texture_with_boundary_color_offset(self):
        w=h=9;src=[[40+x*4+(y%2)*7,60+y*3,80+x+y,255] for y in range(h) for x in range(w)]
        clean=[[r+40,g+20,b+10,a] for r,g,b,a in src];damaged=copy.deepcopy(clean)
        for y in range(3,6):
            for x in range(3,6):damaged[y*w+x]=[240,10,20,255]
        d=self.document(w,h,damaged,src);o=options(3,3,3,3,mode='heal');result=self.apply(d,o);self.assertEqual(self.colors(result['document']),clean)
        details=result['changes'][0]['details'];self.assertLess(details['boundary_rms_after'],details['boundary_rms_before']/10);self.assertEqual(details['boundary_edges'],12)
        o['mode']=dict(type='clone');cloned=self.colors(self.apply(d,o)['document']);self.assertNotEqual(cloned,clean)

    def test_image_edge_healing_and_unanchored_screening_are_explicit(self):
        w,h=5,4;src=[[20,50,90,255]]*(w*h);dst=[[80+x*8,100+y*7,120,255] for y in range(h) for x in range(w)];d=self.document(w,h,dst,src)
        o=options(3,3,0,0,mode='heal');expected,_,_=reference(dst,src,w,h,w,h,o);self.close_pixels(self.colors(self.apply(d,o)['document']),expected)
        full=options(w,h,0,0,mode='heal');self.assertEqual(self.apply(d,full,1)['code'],'INVALID_RETOUCH');full['mode']['screening']=.5
        self.assertEqual(self.colors(self.apply(d,full)['document']),src)
        single=self.document(1,1,[[10,20,30,255]],[[70,80,90,255]]);o=options(1,1,0,0,mode=dict(type='heal',screening=1));self.assertEqual(self.colors(self.apply(single,o)['document']),[[70,80,90,255]])

    def test_disconnected_regions_holes_perimeter_and_measured_boundary_rms(self):
        w=h=7;src=[[80,120,160,255]]*(w*h);dst=[[40+x*8,60+y*7,90,255] for y in range(h) for x in range(w)];mask=bytes(255 if (x in [0,2] and y<3) or (x==3 and y==3) else 0 for y in range(4) for x in range(4))
        o=options(region=dict(x=1,y=1,width=4,height=4,gray_hex=mask.hex()),mode='heal');expected,weights,_=reference(dst,src,w,h,w,h,o);r=self.apply(self.document(w,h,dst,src),o);actual=self.colors(r['document']);self.close_pixels(actual,expected)
        edges=[(i,j) for i,a in enumerate(weights) if a for j in adjacent(i,w,h) if not weights[j]];detail=r['changes'][0]['details'];self.assertEqual(detail['boundary_edges'],len(edges));self.assertEqual(detail['components'],3);self.assertEqual(detail['perimeter'],len(edges))
        for name,colors in [('before',dst),('after',actual)]:
            value=math.sqrt(sum((pm(colors[i])[k]-pm(dst[j])[k])**2 for i,j in edges for k in range(4))/(4*len(edges)))
            self.assertAlmostEqual(detail['boundary_rms_'+name],value,delta=1e-14)

    def test_world_mapped_selection_ignores_source_scene_appearance_and_lock(self):
        w=h=6;src=[[180,30,40,255]]*(w*h);dst=[[20,60,100,255]]*(w*h);d=self.document(w,h,dst,src)
        d['items'][0]['transform']=[.5,0,0,1,2,0];d['items'][1].update(locked=True,opacity=.1,transform=[2,0,0,2,20,30]);selection=bytes((i*19)%256 for i in range(w*h))
        d['selection']=dict(width=w,height=h,gray_hex=selection.hex());o=options(4,4,1,1,use_selection=True,mode=dict(type='heal',screening=.6),opacity=.5)
        expected,_,_=reference(dst,src,w,h,w,h,o,selection,d['items'][0]['transform'],(w,h));r=self.apply(d,o);self.close_pixels(self.colors(r['document']),expected);self.assertGreater(r['changes'][0]['details']['changed_pixels'],0);self.assertEqual(r['document']['items'][1],d['items'][1]);self.assertEqual(r['document']['selection'],d['selection'])

    def test_empty_and_zero_opacity_preserve_invisible_rgb_and_source_bytes(self):
        w=h=4;dst=[[190,30,70,0]]*(w*h);src=[[100,50,20,255]]*(w*h);d=self.document(w,h,dst,src)
        for o in [options(w,h,0,0,region=dict(x=0,y=0,width=w,height=h,gray_hex='00'*(w*h)),mode='heal'),options(w,h,0,0,mode='heal',opacity=0,source_transform=[1,0,0,1,100,100])]:
            r=self.apply(d,o);self.assertEqual(self.colors(r['document']),dst);self.assertEqual(self.colors(r['document'],'source'),src);self.assertEqual(r['changes'][0]['details']['changed_pixels'],0);self.assertIsNone(r['changes'][0]['details']['changed_bounds'])

    def test_solver_failure_deadline_and_cancellation_leave_source_unchanged(self):
        w=h=8;src=[[20,30,40,255]]*(w*h);dst=[[20+x*20,30+y*y,100,255] for y in range(h) for x in range(w)];d=self.document(w,h,dst,src);saved=copy.deepcopy(d);o=options(5,5,1,1,mode=dict(type='heal',max_iterations=1,tolerance=1e-12))
        self.assertEqual(self.apply(d,o,1)['code'],'RETOUCH_PRECISION');self.assertEqual(d,saved)
        self.assertEqual(self.apply(d,options(),1,control=dict(timeout_ms=0))['code'],'TIMEOUT')
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'cancel';p.write_text('stop');self.assertEqual(self.apply(d,options(),1,control=dict(cancel_file=str(p)))['code'],'CANCELLED')

    def test_strict_options_regions_transforms_and_unsupported_contexts(self):
        d=self.document(6,6,[[20,30,40,255]]*36,[[70,80,90,255]]*36)
        for update in [dict(opacity=-1),dict(region=dict(x=0,y=0,width=0,height=3)),dict(region=dict(x=4294967295,y=0,width=4,height=3)),dict(region=dict(x=0,y=0,width=3,height=3,gray_hex='zz'*9)),dict(mode=dict(type='heal',screening=-1)),dict(mode=dict(type='heal',tolerance=1e-15)),dict(mode=dict(type='heal',max_iterations=0)),dict(use_selection=True)]:
            self.assertEqual(self.apply(d,options(**update),1)['code'],'INVALID_RETOUCH')
        self.assertEqual(self.apply(d,options(unknown=True),1)['code'],'INVALID_REQUEST')
        self.assertEqual(self.apply(d,options(source_transform=[0]*6),1)['code'],'UNSUPPORTED')
        for index in [0,1]:
            other=copy.deepcopy(d);other['items'][index]['content']=dict(type='group');self.assertEqual(self.apply(other,options(),1)['code'],'INVALID_OPERATION')
        self.assertEqual(self.apply(d,options(source_id='missing'),1)['code'],'NOT_FOUND')

    def test_target_locks_and_later_batch_failure_are_atomic(self):
        d=self.document(6,6,[[20,30,40,255]]*36,[[70,80,90,255]]*36);o=options();locked=copy.deepcopy(d);locked['items'][0]['locked']=True
        self.assertEqual(self.apply(locked,o,1)['code'],'LOCKED');saved=copy.deepcopy(d)
        error=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='retouch',id='pixels',options=o),dict(op='remove',id='missing')]),1)
        self.assertEqual(error['operation_index'],1);self.assertEqual(d,saved)

    def test_hashes_changed_bounds_repeatability_and_lossless_delivery(self):
        w=h=6;src=[[80+x*9,40+y*11,140,255] for y in range(h) for x in range(w)];dst=[[20,50,90,200]]*(w*h);d=self.document(w,h,dst,src);o=options(mode=dict(type='heal',screening=.7));r=self.apply(d,o);self.assertEqual(r,self.apply(d,copy.deepcopy(o)))
        actual=self.colors(r['document']);detail=r['changes'][0]['details'];flat=lambda c:bytes(v for p in c for v in p)
        for key,c in [('source_sha256',src),('target_before_sha256',dst),('result_sha256',actual)]:self.assertEqual(detail[key],hashlib.sha256(canonical(w,h,flat(c))).hexdigest())
        changed=[i for i,(a,b) in enumerate(zip(actual,dst)) if a!=b];self.assertEqual(detail['changed_pixels'],len(changed));self.assertEqual(detail['changed_bounds'],[min(i%w for i in changed),min(i//w for i in changed),max(i%w for i in changed)+1,max(i//w for i in changed)+1])
        png=self.invoke(dict(command='document.export',document=r['document'],format='png'));self.assertEqual(editing.png_pixels(base64.b64decode(png['data']))[2],flat(actual))
        snapshot=self.invoke(dict(command='document.export',document=r['document'],format='snapshot'));self.assertEqual(json.loads(snapshot['data']),r['document'])
        explicit=copy.deepcopy(o);explicit.update(source_transform=[1,0,0,1,0,0],sampling='bilinear',border='error',opacity=1,use_selection=False);explicit['region']['gray_hex']=None;explicit['mode'].update(tolerance=1e-9,max_iterations=2048)
        self.assertEqual(self.apply(d,explicit)['changes'][0]['details']['settings_sha256'],detail['settings_sha256'])

    def test_mcp_retouch_session_undo_redo_retries_and_create_only_delivery(self):
        d=self.document(7,7,[[20,30,40,255]]*49,[[80,90,100,255]]*49);o=options(mode=dict(type='heal',screening=.7))
        with tempfile.TemporaryDirectory() as temp:
            c=Client();self.addCleanup(c.close);c.initialize();session=dict(session_root=str(Path(temp)/'sessions'),session_id='retouch');c.success('session.create',**session,request_id='create',document=d)
            request=dict(**session,request_id='heal',expected_revision=0,action=dict(type='edit',operations=[dict(op='retouch',id='pixels',options=o)]))
            r=c.success('session.apply',**request);self.assertEqual(c.success('session.apply',**request)['document'],r['document'])
            current=c.success('session.read',**session)['document'];self.assertEqual(self.colors(current),self.colors(self.apply(d,o)['document']));self.assertNotEqual(self.colors(current),self.colors(d))
            undo=c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'));self.assertEqual(self.colors(undo['document']),self.colors(d))
            redo=c.success('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'));self.assertEqual(self.colors(redo['document']),self.colors(current))
            output=dict(output_root=temp,file_name='retouched.png',format='png');c.success('document.publish',document=redo['document'],output=output)
            self.assertTrue(c.tool('document.publish',document=redo['document'],output=output)['isError'])

    def test_hole_boundaries_and_different_source_dimensions_retain_known_regions(self):
        w=h=7;sw,sh=10,9;src=[[30+x*9,40+y*11,100+x*3,255] for y in range(sh) for x in range(sw)];dst=[[20+x*8,50+y*7,90,255] for y in range(h) for x in range(w)]
        mask=bytes(0 if 1<=x<=3 and 1<=y<=3 else 255 for y in range(5) for x in range(5))
        o=options(mode=dict(type='heal',screening=.2),source_transform=[1,0,0,1,1.25,.75],region=dict(x=1,y=1,width=5,height=5,gray_hex=mask.hex()))
        expected,weights,_=reference(dst,src,w,h,sw,sh,o);r=self.apply(self.document(w,h,dst,src,sw,sh),o);actual=self.colors(r['document']);self.close_pixels(actual,expected)
        self.assertTrue(all(actual[i]==dst[i] for i,a in enumerate(weights) if not a));self.assertEqual(r['changes'][0]['details']['perimeter'],32);self.assertEqual(r['changes'][0]['details']['components'],1)

    def test_large_healing_work_budget_and_in_work_deadline_fail_without_output(self):
        w=h=256;pixels=[[(x*7+y*13)%256,(x*3+y*5)%256,(x+y)%256,255] for y in range(h) for x in range(w)]
        d=self.document(w,h,pixels);saved=copy.deepcopy(d)
        o=options(254,254,1,1,source_id='pixels',source_transform=[1,0,0,1,40,0],border='clamp',mode=dict(type='heal',max_iterations=4096,tolerance=1e-12))
        self.assertEqual(self.apply(d,o,1)['code'],'RESOURCE_LIMIT');self.assertEqual(d,saved)
        self.assertEqual(self.apply(d,o,1,control=dict(timeout_ms=5))['code'],'TIMEOUT');self.assertEqual(d,saved)

    def test_healing_reports_premultiplied_gamut_clamping_and_retains_alpha(self):
        src=[[0,0,0,255] for _ in range(9)];src[4]=[255,200,100,128]
        dst=[[255,255,255,255] for _ in range(9)];dst[4]=[30,60,90,200]
        o=options(1,1,1,1,mode='heal');r=self.apply(self.document(3,3,dst,src),o);actual=self.colors(r['document'])
        self.assertEqual(actual[4],[255,255,255,128]);self.assertEqual(r['changes'][0]['details']['clamped_pixels'],1)
        self.assertEqual([c for i,c in enumerate(actual) if i!=4],[c for i,c in enumerate(dst) if i!=4]);self.assertEqual(self.colors(r['document'],'source'),src)


if __name__=='__main__':unittest.main()
