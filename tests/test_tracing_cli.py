"""Independent cell membership, graph topology, area, palette and delivery checks."""
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
from test_images_cli import png, canonical
from test_mcp import Client

ZERO=(0,0,0,0)
INK=(24,100,210,255)

def source(w,h,colors):
    return dict(type='pixels',width=w,height=h,rgba_hex=bytes(v for c in colors for v in c).hex())

def loops(item):
    result=[]
    for c in item['content']['geometry']['commands']:
        if c['verb']=='move': result.append([c['to']])
        elif c['verb']=='line':result[-1].append(c['to'])
        else:assert c['verb']=='close'
    return result

def winding(polygons,x,y):
    n=0
    for p in polygons:
        for a,b in zip(p,p[1:]+p[:1]):
            cross=(b[0]-a[0])*(y-a[1])-(x-a[0])*(b[1]-a[1])
            if a[1]<=y<b[1] and cross>0:n+=1
            if b[1]<=y<a[1] and cross<0:n-=1
    return n

def topology(colors,w,h,color):
    # Independent set expansion rather than contour walking. Foreground 4, complement 8.
    def components(points,diagonal):
        parts=[]
        while points:
            todo={points.pop()};part=set(todo)
            while todo:
                x,y=todo.pop()
                near={(x+dx,y+dy) for dx in (-1,0,1) for dy in (-1,0,1) if (abs(dx)+abs(dy)==1 or diagonal and (dx or dy))}
                added=near&points;points-=added;todo|=added;part|=added
            parts.append(part)
        return parts
    foreground={(x,y) for y in range(h) for x in range(w) if colors[y*w+x]==color}
    background={(x,y) for y in range(h) for x in range(w)}-foreground
    holes=sum(all(0<x<w-1 and 0<y<h-1 for x,y in c) for c in components(background,True))
    return len(components(foreground,False)),holes

class TraceTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def trace(self,w,h,colors,mode=None,expected=0,**options):
        return self.invoke(dict(command='image.trace',id='traced',source=source(w,h,colors),options=dict(mode=mode or dict(type='exact'),**options)),expected)
    def pixels(self,d,scale=1):
        r=self.invoke(dict(command='document.export',document=d,format='png',scale=scale))
        return editing.png_pixels(base64.b64decode(r['data']))[2]
    def verify_cells(self,result,colors,w,h,topological=True):
        d=result['document'];self.assertEqual((d['width'],d['height']),(w,h));self.assertEqual(d['kind'],'vector')
        self.assertEqual(len(result['colors']),len(d['items']))
        for item,report in zip(d['items'],result['colors']):
            color=tuple(item['content']['fill']);polygons=loops(item)
            self.assertEqual(item['content']['fill_rule'],'nonzero')
            area=sum(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(p,p[1:]+p[:1]))/2 for p in polygons)
            perimeter=sum(math.dist(a,b) for p in polygons for a,b in zip(p,p[1:]+p[:1]))
            self.assertEqual(area,colors.count(color));self.assertEqual(report['area'],area);self.assertEqual(report['perimeter'],perimeter)
            if topological:self.assertEqual((report['components'],report['holes']),topology(colors,w,h,color))
            for y in range(h):
                for x in range(w):
                    for u,v in ((.25,.25),(.5,.5),(.75,.75)):
                        self.assertEqual(winding(polygons,x+u,y+v),int(colors[y*w+x]==color),(x,y,polygons))
            for p in polygons:
                for a,b,c in zip(p[-1:]+p[:-1],p,p[1:]+p[:1]):
                    self.assertTrue(a[0]==b[0] or a[1]==b[1]);self.assertNotEqual((b[0]-a[0])*(c[1]-b[1]),(b[1]-a[1])*(c[0]-b[0]))
        self.assertEqual(self.pixels(d),bytes(v for c in colors for v in c))
        identity=hashlib.sha256(canonical(w,h,bytes(v for c in colors for v in c))).hexdigest()
        self.assertEqual(result['provenance']['classified_identity'],identity)

    def test_all_512_binary_three_by_three_topologies_and_exact_pixels(self):
        for mask in range(512):
            colors=[INK if mask&(1<<n) else ZERO for n in range(9)]
            with self.subTest(mask=mask):self.verify_cells(self.trace(3,3,colors),colors,3,3)

    def test_seeded_multicolor_alpha_holes_and_corner_contacts(self):
        rng=random.Random(941);palette=[ZERO,INK,(245,90,20,128),(8,220,100,64)]
        for _ in range(18):
            colors=[rng.choice(palette) for _ in range(36)]
            self.verify_cells(self.trace(6,6,colors),colors,6,6)

    def test_nested_rings_exact_area_perimeter_and_negative_hole_winding(self):
        colors=[INK if max(abs(x-6),abs(y-6)) in (5,3,1) else ZERO for y in range(13) for x in range(13)]
        result=self.trace(13,13,colors);self.verify_cells(result,colors,13,13)
        self.assertEqual((result['colors'][0]['components'],result['colors'][0]['holes']),(3,3))
        self.assertEqual(result['provenance']['contour_error_pixels'],0)

    def test_binary_alpha_threshold_endpoints_inversion_and_invisible_rgb(self):
        original=[(250,40,10,a) for a in (0,1,63,64,127,128,254,255)]
        for threshold in (0,1,64,128,255):
            for invert in (False,True):
                mode=dict(type='binary',channel='alpha',threshold=threshold,invert=invert,color=list(INK))
                colors=[INK if a and ((a>=threshold)!=invert) else ZERO for *_,a in original]
                self.verify_cells(self.trace(8,1,original,mode,alpha_min=0),colors,8,1)

    def test_luma_threshold_uses_encoded_rgb_and_separate_alpha_gate(self):
        original=[(r,g,b,a) for r,g,b in [(255,0,0),(0,255,0),(0,0,255),(127,127,127),(128,128,128)] for a in (63,64,255)]
        mode=dict(type='binary',channel='luma',threshold=128,color=[90,30,200,128])
        colors=[tuple(mode['color']) if a>=64 and 2126*r+7152*g+722*b>=1280000 else ZERO for r,g,b,a in original]
        self.verify_cells(self.trace(15,1,original,mode,alpha_min=64),colors,15,1)

    def test_quantization_exact_endpoints_rounding_alpha_and_error_metrics(self):
        original=[(x,255-x,83,a) for x in (0,42,43,127,128,212,213,255) for a in (0,1,63,64,127,128,254,255)]
        def quant(v,n):return math.floor(math.floor(v*(n-1)/255+.5)*255/(n-1)+.5)
        colors=[tuple(quant(c,3 if i==3 else 4) for i,c in enumerate(p)) for p in original]
        colors=[p if p[3] else ZERO for p in colors]
        result=self.trace(8,8,original,dict(type='quantized',rgb_levels=4,alpha_levels=3));self.verify_cells(result,colors,8,8)
        differences=[(a-b)/65025 for p,q in zip(original,colors) for a,b in zip([p[i]*p[3] for i in range(3)]+[p[3]*255],[q[i]*q[3] for i in range(3)]+[q[3]*255])]
        self.assertAlmostEqual(result['comparison']['maximum_channel_error'],max(map(abs,differences)),places=15)
        self.assertAlmostEqual(result['comparison']['rms_channel_error'],math.sqrt(sum(x*x for x in differences)/len(differences)),places=15)

    def test_explicit_palette_premultiplied_metric_tie_order_and_zero_alpha(self):
        palette=[(0,0,0,255),(2,0,0,255),(220,40,10,64),ZERO]
        original=[(1,0,0,255),(220,40,10,60),(255,255,255,0),(100,120,130,1),(250,20,40,128)]
        def pm(c):return [c[i]*c[3] for i in range(3)]+[c[3]*255]
        colors=[min(palette,key=lambda q:sum((a-b)**2 for a,b in zip(pm(p),pm(q)))) if p[3] else ZERO for p in original]
        r=self.trace(5,1,original,dict(type='palette',colors=palette));self.verify_cells(r,colors,5,1);self.assertEqual(colors[0],palette[0])

    def test_noise_islands_removed_by_color_four_connectivity_before_hole_fill(self):
        original=[INK if 1<=x<=5 and 1<=y<=5 or (x,y) in ((7,1),(8,2)) else ZERO for y in range(8) for x in range(10)]
        original[3*10+3]=ZERO;original[4*10+4]=(220,10,20,255)
        colors=[INK if 1<=x<=5 and 1<=y<=5 else ZERO for y in range(8) for x in range(10)]
        result=self.trace(10,8,original,min_region_pixels=2,max_hole_pixels=2);self.verify_cells(result,colors,10,8)
        self.assertEqual(result['provenance']['removed_pixels'],3);self.assertEqual(result['provenance']['filled_hole_pixels'],2)

    def test_noise_hole_gate_preserves_mixed_surrounds_diagonal_openings_and_large_holes(self):
        original=[INK]*49;original[24]=ZERO;original[23]=(220,10,20,255)
        self.verify_cells(self.trace(7,7,original,max_hole_pixels=1),original,7,7)
        original=[INK]*49
        for i in (0,8,16,24):original[i]=ZERO
        self.verify_cells(self.trace(7,7,original,max_hole_pixels=4),original,7,7)
        original=[INK]*49
        for i in (24,25):original[i]=ZERO
        self.verify_cells(self.trace(7,7,original,max_hole_pixels=1),original,7,7)

    def test_source_identity_options_and_snapshot_provenance_are_repeatable(self):
        original=[(11,40,180,0),INK,INK,ZERO];r=self.trace(2,2,original);self.assertEqual(r,self.trace(2,2,original))
        self.assertEqual(r['provenance']['source_identity'],hashlib.sha256(canonical(2,2,bytes(v for c in original for v in c))).hexdigest())
        self.assertEqual(json.loads(r['document']['metadata']['properties']['inkbolt.trace']),r['provenance'])
        self.assertEqual(r['provenance']['options'],dict(mode=dict(type='exact'),alpha_min=1,min_region_pixels=1,max_hole_pixels=0))
        saved=self.invoke(dict(command='document.export',document=r['document'],format='snapshot'))
        self.assertEqual(self.invoke(dict(command='document.validate',document=json.loads(saved['data']))),r['document'])

    def test_imported_asset_embedded_equivalence_and_source_bytes_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);original=[INK,ZERO,(220,10,20,128),INK];path=root/'source.png';path.write_bytes(png(2,2,bytes(v for c in original for v in c)));before=path.read_bytes()
            imported=self.invoke(dict(command='asset.import',source_path=str(path),store_root=str(root/'assets')));asset=imported['asset'];asset_bytes=(root/'assets'/(asset['sha256']+'.rgba8')).read_bytes()
            req=dict(command='image.trace',id='traced',source=dict(type='asset',asset=asset),options=dict(mode=dict(type='exact')),asset_root=str(root/'assets'))
            r=self.invoke(req);self.assertEqual(r,self.trace(2,2,original))
            embedded=self.invoke(dict(command='asset.embed',asset=asset,asset_root=str(root/'assets')));req['source']['asset']=embedded;req.pop('asset_root');self.assertEqual(self.invoke(req),r)
            self.assertEqual(path.read_bytes(),before);self.assertEqual((root/'assets'/(asset['sha256']+'.rgba8')).read_bytes(),asset_bytes)
            req['source']['asset']=asset;self.assertEqual(self.invoke(req,1)['code'],'ASSET_ROOT_REQUIRED')
            req['asset_root']=str(root/'missing');self.assertEqual(self.invoke(req,1)['code'],'ASSET_MISSING')

    def test_svg_reimport_structure_pixels_scaled_delivery_and_alpha(self):
        colors=[INK if x<4 else (240,20,70,128) if y<4 else ZERO for y in range(8) for x in range(8)]
        result=self.trace(8,8,colors);d=result['document'];svg=self.invoke(dict(command='document.export',document=d,format='svg'))
        back=self.invoke(dict(command='svg.import',id='returned',source=dict(kind='text',text=svg['data'])))['document']
        self.assertEqual(self.pixels(back),self.pixels(d))
        expected=bytes(v for y in range(32) for x in range(32) for v in colors[(y//4)*8+x//4]);self.assertEqual(self.pixels(d,4),expected)

    def test_editable_anchor_color_transforms_and_locked_atomic_rollback(self):
        r=self.trace(2,2,[INK]*4);d=r['document'];original=copy.deepcopy(d);id=d['items'][0]['id']
        moved=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='path',id=id,action=dict(type='anchors',points=[dict(command_index=0,to=[.5,0])]))]))['document']
        self.assertEqual(moved['items'][0]['content']['geometry']['commands'][0]['to'],[.5,0]);self.assertEqual(d,original)
        locked=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='properties',id=id,locked=True)]))['document']
        error=self.invoke(dict(command='document.edit',document=locked,expected_revision=locked['revision'],operations=[dict(op='transform',id=id,matrix=[1,0,0,1,1,0])]),1);self.assertEqual(error['code'],'LOCKED')
        content=copy.deepcopy(d['items'][0]['content']);content.pop('type');content['fill']=[220,20,60,128]
        changed=self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=[dict(op='vector',id=id,**content)]))['document']
        self.assertEqual(self.pixels(changed),bytes([220,20,60,128])*4)
        failed=self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=[dict(op='vector',id=id,**content),dict(op='remove',id='missing')]),1)
        self.assertEqual(failed['operation_index'],1);self.assertEqual(d,original)

    def test_create_only_publication_keeps_source_and_provenance(self):
        d=self.trace(4,4,[INK if n%3 else ZERO for n in range(16)])['document']
        with tempfile.TemporaryDirectory() as root:
            for fmt,ext in [('png','png'),('svg','svg'),('snapshot','json')]:
                q=dict(command='document.publish',document=d,output=dict(output_root=root,file_name='trace.'+ext,format=fmt));r=self.invoke(q);data=(Path(root)/('trace.'+ext)).read_bytes()
                self.assertEqual(r['sha256'],hashlib.sha256(data).hexdigest());self.assertEqual(self.invoke(q,1)['code'],'OUTPUT_EXISTS');self.assertEqual((Path(root)/('trace.'+ext)).read_bytes(),data)
                if fmt=='snapshot':self.assertEqual(json.loads(data),d)

    def test_invalid_settings_strict_fields_inputs_and_color_complexity_fail(self):
        for options in [dict(alpha_min=256),dict(min_region_pixels=0),dict(max_hole_pixels=1048577)]:self.assertEqual(self.trace(1,1,[INK],expected=1,**options)['code'],'INVALID_TRACE')
        for mode in [dict(type='quantized',rgb_levels=1,alpha_levels=2),dict(type='palette',colors=[]),dict(type='palette',colors=[INK,INK]),dict(type='palette',colors=[[1,2,3,0]])]:self.assertEqual(self.trace(1,1,[INK],mode,expected=1)['code'],'INVALID_TRACE')
        req=dict(command='image.trace',id='bad',source=source(1,1,[INK]),options=dict(mode=dict(type='exact')))
        req['source']['rgba_hex']='xx';self.assertEqual(self.invoke(req,1)['code'],'INVALID_TRACE');req['source']=source(1,1,[INK]);req['options']['smooth']=True;self.assertEqual(self.invoke(req,1)['code'],'INVALID_REQUEST')
        self.assertEqual(self.trace(65,1,[(n,0,0,255) for n in range(65)],expected=1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.trace(42,42,[INK if (n%42+n//42)%2 else ZERO for n in range(1764)],expected=1)['code'],'RESOURCE_LIMIT')

    def test_cancellation_and_deadline_leave_no_partial_result(self):
        with tempfile.TemporaryDirectory() as temp:
            marker=Path(temp)/'cancel';marker.write_text('stop');req=dict(command='image.trace',id='traced',source=source(1,1,[INK]),options=dict(mode=dict(type='exact')),control=dict(cancel_file=str(marker)))
            self.assertEqual(self.invoke(req,1)['code'],'CANCELLED');req['control']=dict(timeout_ms=0);self.assertEqual(self.invoke(req,1)['code'],'TIMEOUT')

    def test_large_simple_asset_boundary_budget_and_source_dimension_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'large.png';path.write_bytes(png(1024,1024,bytes(INK)*1048576))
            asset=self.invoke(dict(command='asset.import',source_path=str(path),store_root=str(root/'assets')))['asset']
            r=self.invoke(dict(command='image.trace',id='large',source=dict(type='asset',asset=asset),asset_root=str(root/'assets'),options=dict(mode=dict(type='exact'))))
            self.assertEqual(r['colors'][0]['area'],1048576);self.assertEqual(r['colors'][0]['commands'],5);self.assertEqual(r['unit_edges'],4096)
            asset['height']=1025;self.assertEqual(self.invoke(dict(command='image.trace',id='large',source=dict(type='asset',asset=asset),options=dict(mode=dict(type='exact'))),1)['code'],'RESOURCE_LIMIT')

    def test_mcp_trace_persistent_edits_undo_and_reopen(self):
        with tempfile.TemporaryDirectory() as temp:
            c=Client();self.addCleanup(c.close);c.initialize();r=c.success('image.trace',id='traced',source=source(2,2,[INK]*4),options=dict(mode=dict(type='exact')));d=r['document'];self.assertEqual(r,self.trace(2,2,[INK]*4))
            session=dict(session_root=str(Path(temp)/'sessions'),session_id='trace')
            c.success('session.create',**session,request_id='create',document=d)
            action=dict(type='edit',operations=[dict(op='transform',id=d['items'][0]['id'],matrix=[1,0,0,1,.5,0])])
            moved=c.success('session.apply',**session,request_id='move',expected_revision=0,action=action)['document'];self.assertNotEqual(moved['items'],d['items'])
            restored=c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(restored['items'],d['items']);self.assertEqual(restored['metadata'],d['metadata'])
            self.assertEqual(c.success('session.read',**session)['document'],restored)

    def test_original_sampled_disk_and_triangle_contour_distance_bound(self):
        for name,inside in [('disk',lambda x,y:math.hypot(x-12,y-12)<=8),('triangle',lambda x,y:4<=y<=20 and abs(x-12)<=(y-4)/2)]:
            colors=[INK if inside(x+.5,y+.5) else ZERO for y in range(24) for x in range(24)]
            result=self.trace(24,24,colors);self.verify_cells(result,colors,24,24)
            self.assertEqual((result['colors'][0]['components'],result['colors'][0]['holes']),(1,0))
            # The engine bounds error against the classified cells exactly. Independently
            # check the sampled curves against their original analytic input, too.
            if name=='disk':
                segments=[(a,b) for p in loops(result['document']['items'][0]) for a,b in zip(p,p[1:]+p[:1])]
                def distance(p,a,b):
                    v=[b[i]-a[i] for i in range(2)];t=max(0,min(1,sum((p[i]-a[i])*v[i] for i in range(2))/sum(q*q for q in v)))
                    return math.dist(p,[a[i]+t*v[i] for i in range(2)])
                for i in range(720):
                    t=i*math.pi/360;p=[12+8*math.cos(t),12+8*math.sin(t)]
                    self.assertLessEqual(min(distance(p,a,b) for a,b in segments),math.sqrt(2))
                for a,b in segments:
                    for k in range(5):self.assertLessEqual(abs(math.hypot(a[0]+(b[0]-a[0])*k/4-12,a[1]+(b[1]-a[1])*k/4-12)-8),math.sqrt(2))

    def test_unit_edge_limit_rejects_large_checkerboard_without_modifying_asset(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);w=512;pixels=b''.join(bytes(INK if (x+y)%2 else ZERO) for y in range(w) for x in range(w));path=root/'checker.png';path.write_bytes(png(w,w,pixels));before=path.read_bytes()
            asset=self.invoke(dict(command='asset.import',source_path=str(path),store_root=str(root/'assets')))['asset']
            request=dict(command='image.trace',id='edges',source=dict(type='asset',asset=asset),asset_root=str(root/'assets'),options=dict(mode=dict(type='exact')))
            error=self.invoke(request,1);self.assertEqual(error['code'],'RESOURCE_LIMIT');self.assertIn('unit boundary edges',error['message']);self.assertEqual(path.read_bytes(),before)

if __name__=='__main__':unittest.main()
