"""Independent retained-raw signal, lens, sidecar and agent-history checks."""
import base64
import copy
from contextlib import closing
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import test_editing_cli as editing
import test_raw_cli as raw
from test_sample_conversion_cli import values
from test_samples_cli import decode
from test_mcp import Client


def lens(w=9,h=7,**kw):
    v=dict(center=[(w-1)/2,(h-1)/2],focal=[w,h],radial=[0,0,0],tangential=[0,0],border='clamp');v.update(kw);return v


def correction_reference(linear,w,h,corrections):
    # Fraction arithmetic with separate gather-by-channel convolution and pull map.
    data=[list(map(F,linear[i:i+4])) for i in range(0,len(linear),4)]
    def neighborhood(v,kind):
        nonlocal data
        source=copy.deepcopy(data);radius=v['radius'];threshold=F(v['threshold']);amount=F(v['amount'])
        for y in range(h):
            for x in range(w):
                p=source[y*w+x]
                if not p[3]:continue
                neighbors=[source[yy*w+xx] for yy in range(max(0,y-radius),min(h,y+radius+1)) for xx in range(max(0,x-radius),min(w,x+radius+1))]
                if kind=='denoise':neighbors=[q for q in neighbors if max(abs(q[c]-p[c]) for c in range(3))<=threshold]
                total=sum(q[3] for q in neighbors)
                for c in range(3):
                    mean=sum(q[c]*q[3] for q in neighbors)/total;delta=mean-p[c]
                    if kind=='denoise':data[y*w+x][c]=p[c]+amount*delta
                    elif abs(delta)>threshold:data[y*w+x][c]=p[c]-amount*delta
    if corrections.get('denoise'):neighborhood(corrections['denoise'],'denoise')
    if corrections.get('lens'):
        source=copy.deepcopy(data);v=corrections['lens'];cx,cy=map(F,v['center']);fx,fy=map(F,v['focal']);k1,k2,k3=map(F,v['radial']);p1,p2=map(F,v['tangential'])
        for y in range(h):
            for x in range(w):
                u=(x-cx)/fx;t=(y-cy)/fy;r=u*u+t*t;scale=1+k1*r+k2*r*r+k3*r*r*r
                sx=cx+fx*(u*scale+2*p1*u*t+p2*(r+2*u*u));sy=cy+fy*(t*scale+p1*(r+2*t*t)+2*p2*u*t)
                if v['border']=='clamp':sx=max(F(0),min(F(w-1),sx));sy=max(F(0),min(F(h-1),sy))
                ix=sx.numerator//sx.denominator;iy=sy.numerator//sy.denominator
                weighted=[(source[yy*w+xx],(1-abs(sx-xx))*(1-abs(sy-yy))) for yy in [iy,iy+1] for xx in [ix,ix+1] if 0<=xx<w and 0<=yy<h]
                alpha=sum(q[3]*weight for q,weight in weighted)
                data[y*w+x]=[sum(q[c]*q[3]*weight for q,weight in weighted)/alpha if alpha else F(0) for c in range(3)]+[alpha]
    if corrections.get('detail'):neighborhood(corrections['detail'],'detail')
    return [float(v) for p in data for v in p]


class RetainedRawTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.data,self.capture,self.codes=raw.fixture(9,7,signal=lambda x,y,c:20+2*x+4*y+8*c)
        self.source=self.root/'original.sensor';self.source.write_bytes(self.data)
    def retain(self,options=None,corrections=None,expected=0,**kw):
        r=self.invoke(dict(command='raw.retain',source_path=str(self.source),id='retained',capture=self.capture,settings=options or raw.settings(),corrections=corrections or {},**kw),expected)
        self.assertEqual(self.source.read_bytes(),self.data)
        return r if expected else r['document']
    def edit(self,d,operations,expected=0,**kw):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=operations,**kw),expected)
        return r if expected else r['document']
    def change(self,d,corrections=None,settings=None,expected=0):
        return self.edit(d,[dict(op='raw_settings',id='raw',settings=settings or raw.settings(),corrections=corrections or {})],expected)
    def expanded(self,d):return self.edit(d,[dict(op='raw_expand',id='raw')])
    def output(self,d):return values(self.expanded(d))
    def compare(self,actual,expected):
        self.assertEqual(len(actual),len(expected))
        for a,e in zip(actual,expected):self.assertAlmostEqual(a,e,delta=max(2e-8,abs(e)*1.2e-7))
    def reference(self,options=None,corrections=None):
        linear=raw.reference(self.capture,self.codes,options or raw.settings())
        return correction_reference(linear,9,7,corrections or {})

    def test_exact_sensor_padding_retained_and_basic_parity_without_external_source(self):
        d=self.retain();spec=d['items'][0]['content']['raw']
        self.assertEqual(bytes.fromhex(spec['source_hex']),self.data)
        self.assertEqual(spec['recipe']['source_sha256'],hashlib.sha256(self.data).hexdigest())
        self.assertEqual(self.output(d),raw.floats(self.reference()))
        self.source.unlink()
        self.assertEqual(self.output(d),raw.floats(self.reference()))
        self.assertEqual(json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data']),d)

    def test_radial_tangential_and_both_border_modes_match_rational_pull_maps(self):
        for radial,tangential in [([.25,0,0],[0,0]),([-.25,.125,0],[0,0]),([0,0,.125],[.015625,-.0078125]),([0,0,0],[.03125,.015625])]:
            for border in ['clamp','transparent']:
                corrections=dict(lens=lens(radial=radial,tangential=tangential,border=border))
                self.compare(self.output(self.retain(corrections=corrections)),self.reference(corrections=corrections))
        self.assertEqual(self.output(self.retain(corrections=dict(lens=lens()))),self.output(self.retain()))

    def test_noise_reduction_is_range_gated_linear_and_amount_controlled(self):
        self.data,self.capture,self.codes=raw.fixture(9,7,signal=lambda x,y,c:40+((x*13+y*23+c*7)%17)-8)
        self.source.write_bytes(self.data);base=self.reference()
        for radius in [1,2,4]:
            for threshold in [0,.071,16]:
                corrections=dict(denoise=dict(radius=radius,threshold=threshold,amount=.75))
                self.compare(self.output(self.retain(corrections=corrections)),self.reference(corrections=corrections))
        smoothed=self.output(self.retain(corrections=dict(denoise=dict(radius=2,threshold=16,amount=1))))
        energy=lambda p:sum((p[(y*9+x)*4+c]-p[(y*9+x-1)*4+c])**2 for y in range(7) for x in range(1,9) for c in range(3))
        self.assertLess(energy(smoothed),energy(base))

    def test_detail_threshold_amount_and_signed_overshoot(self):
        self.data,self.capture,self.codes=raw.fixture(9,7,signal=lambda x,y,c:0 if x<4 else 128)
        self.source.write_bytes(self.data)
        for radius,threshold,amount in [(1,0,1),(2,.03125,.5),(4,16,4)]:
            corrections=dict(detail=dict(radius=radius,threshold=threshold,amount=amount))
            actual=self.output(self.retain(corrections=corrections));self.compare(actual,self.reference(corrections=corrections))
            if threshold==0:self.assertLess(min(actual),0);self.assertGreater(max(actual),1)
        corrections=dict(detail=dict(radius=1,threshold=0,amount=0))
        self.assertEqual(self.output(self.retain(corrections=corrections)),raw.floats(self.reference()))

    def test_joint_order_noise_lens_detail_then_output_projection_and_alpha(self):
        corrections=dict(denoise=dict(radius=1,threshold=.2,amount=.625),lens=lens(radial=[.25,0,0],tangential=[.015625,0],border='transparent'),detail=dict(radius=2,threshold=.003,amount=1.5))
        options=raw.settings(exposure_stops=1.5);wanted=self.reference(options,corrections)
        d=self.retain(options,corrections);self.compare(self.output(d),wanted)
        self.assertTrue(any(0<v<1 for v in self.output(d)[3::4]))
        for output,bits in [('srgb8',8),('srgb16',16)]:
            opts=dict(options,output=output,range='clip');out=self.output(self.retain(opts,corrections))
            expected=[raw.encoded(v,bits) if i%4!=3 else int(v*((1<<bits)-1)+.5) for i,v in enumerate(wanted)]
            self.assertEqual(out,expected)

    def test_settings_recompute_original_and_preserve_masks_transforms_and_scene_density(self):
        d=self.retain();source=copy.deepcopy(d['items'][0]['content']['raw'])
        d=self.edit(d,[dict(op='properties',id='raw',opacity=.5),dict(op='transform',id='raw',matrix=[1,0,0,1,1,1]),dict(op='mask',id='raw',mask=dict(width=9,height=7,gray_hex='80'*63))])
        settings=raw.settings(exposure_stops=2,resolution_ppi=600);changed=self.change(d,dict(detail=dict(radius=1,threshold=0,amount=1)),settings)
        self.assertEqual(changed['items'][0]['content']['raw']['source_hex'],source['source_hex'])
        self.assertEqual(changed['items'][0]['transform'],d['items'][0]['transform']);self.assertEqual(changed['items'][0]['opacity'],.5)
        self.assertEqual(changed['resolution_ppi'],d['resolution_ppi']);self.assertEqual(changed['items'][0]['mask'],d['items'][0]['mask'])
        reset=self.change(changed);self.assertEqual(reset['items'][0]['content'],d['items'][0]['content'])
        measured=lambda doc:self.invoke(dict(command='sample.measure',document=doc,points=[[3,3],[6,4]]))['samples']
        self.assertEqual(measured(reset),measured(d));self.assertEqual(measured(changed),measured(self.expanded(changed)))

    def test_sidecar_roundtrip_exact_settings_source_pins_and_no_file_mutation(self):
        corrections=dict(lens=lens(radial=[-.125,.03125,0]),denoise=dict(radius=2,threshold=.1,amount=.25),detail=dict(radius=1,threshold=.01,amount=.75))
        d=self.retain(corrections=corrections);r=self.invoke(dict(command='raw.recipe',document=d,id='raw'))
        self.assertEqual(json.loads(r['data']),r['recipe']);self.assertEqual(r['sha256'],hashlib.sha256(r['data'].encode()).hexdigest())
        sidecar=self.root/'settings.json'
        with sidecar.open('x',encoding='utf8') as f:f.write(r['data'])
        for _ in range(3):
            reopened=self.invoke(dict(command='raw.reopen',source_path=str(self.source),recipe_path=str(sidecar),id='retained'))['document']
            self.assertEqual(reopened,d);self.assertEqual(self.output(reopened),self.output(d))
        self.assertEqual(sidecar.read_text(),r['data']);self.assertEqual(self.source.read_bytes(),self.data)
        self.source.write_bytes(self.data[:-1]+bytes([self.data[-1]^1]))
        self.assertEqual(self.invoke(dict(command='raw.reopen',source_path=str(self.source),recipe_path=str(sidecar),id='retained'),1)['code'],'SOURCE_MISMATCH')

    def test_sidecars_reject_unknown_versions_algorithms_fields_duplicate_keys_and_truncation(self):
        recipe=self.invoke(dict(command='raw.recipe',document=self.retain(),id='raw'))['recipe'];sidecar=self.root/'bad.json'
        for key,value in [('schema_version',3),('algorithm','future'),('unexpected',True),('source_sha256','bad')]:
            modified=copy.deepcopy(recipe);modified[key]=value;sidecar.write_text(json.dumps(modified))
            self.invoke(dict(command='raw.reopen',source_path=str(self.source),recipe_path=str(sidecar),id='raw'),1)
        for text in ['{','{"schema_version":2,"schema_version":2}', ' '*16385]:
            sidecar.write_text(text);self.invoke(dict(command='raw.reopen',source_path=str(self.source),recipe_path=str(sidecar),id='raw'),1)

    def test_atomic_failure_locks_folds_controls_hashes_and_cancellation(self):
        d=self.retain();before=copy.deepcopy(d)
        for corrections in [dict(lens=lens(radial=[-1,0,0],focal=[1,1])),dict(lens=lens(focal=[0,1])),dict(denoise=dict(radius=5,threshold=.1,amount=1)),dict(detail=dict(radius=1,threshold=-1,amount=1))]:
            self.change(d,corrections,expected=1)
        locked=self.edit(d,[dict(op='properties',id='raw',locked=True)])
        self.assertEqual(self.change(locked,expected=1)['code'],'LOCKED')
        self.assertEqual(self.edit(locked,[dict(op='raw_expand',id='raw')],1)['code'],'LOCKED')
        self.edit(d,[dict(op='raw_settings',id='raw',settings=raw.settings(exposure_stops=1),corrections={}),dict(op='remove',id='absent')],1)
        bad=copy.deepcopy(d);bad['items'][0]['content']['raw']['source_hex']='00'+bad['items'][0]['content']['raw']['source_hex'][2:]
        self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'SOURCE_MISMATCH')
        self.assertEqual(self.retain(expected=1,control=dict(timeout_ms=0))['code'],'TIMEOUT')
        self.assertEqual(self.edit(d,[dict(op='raw_expand',id='raw')],1,control=dict(timeout_ms=0))['code'],'TIMEOUT')
        self.assertEqual(d,before)

    def test_retained_source_size_aggregate_pixels_and_float_context_are_explicit(self):
        data,capture,codes=self.data,self.capture,self.codes
        try:
            self.data,self.capture,self.codes=raw.fixture(2,34,padding=4096,signal=lambda x,y,c:64);self.source.write_bytes(self.data)
            self.assertEqual(self.retain(expected=1)['code'],'RESOURCE_LIMIT')
        finally:self.data,self.capture,self.codes=data,capture,codes;self.source.write_bytes(data)
        d=self.retain(raw.settings(output='srgb16',range='clip'))
        self.assertEqual(self.change(d,settings=raw.settings(),expected=1)['code'],'UNSUPPORTED_HDR_MODE')
        d=self.retain();d['kind']='vector';self.invoke(dict(command='document.validate',document=d),1)
        self.data,self.capture,self.codes=raw.fixture(128,128,padding=0,signal=lambda x,y,c:64);self.source.write_bytes(self.data)
        d=self.retain();item=d['items'][0];d['items']=[dict(copy.deepcopy(item),id='r'+str(i)) for i in range(5)]
        self.assertEqual(self.invoke(dict(command='document.validate',document=d),1)['code'],'RESOURCE_LIMIT')

    def test_native_pixel_edit_requires_expansion_then_undo_can_restore_source(self):
        d=self.retain()
        self.edit(d,[dict(op='sample_replace',id='raw',region=dict(x=0,y=0,width=1,height=1),data_hex='00'*16)],1)
        expanded=self.expanded(d);self.assertEqual(expanded['items'][0]['content']['type'],'samples')
        changed=self.edit(expanded,[dict(op='sample_replace',id='raw',region=dict(x=0,y=0,width=1,height=1),data_hex='00'*16)])
        self.assertEqual(values(changed)[:4],[0]*4);self.assertEqual(d['items'][0]['content']['type'],'raw')

    def test_render_and_native_tiff_are_equal_to_expansion_with_scene_controls(self):
        options=raw.settings(output='srgb16',range='clip');corrections=dict(lens=lens(radial=[.125,0,0],border='transparent'),detail=dict(radius=1,threshold=.01,amount=.5))
        d=self.retain(options,corrections);d=self.edit(d,[dict(op='properties',id='raw',opacity=.75)])
        expanded=self.expanded(d)
        for scale in [1,2,4]:
            self.assertEqual(self.invoke(dict(command='document.render',document=d,scale=scale))['data'],self.invoke(dict(command='document.render',document=expanded,scale=scale))['data'])
        for doc in [d,expanded]:
            image=self.invoke(dict(command='document.export',document=doc,format='tiff',image_options=dict(depth='u16',channels='rgba')))
            if doc==d:actual=decode(image)[0]
            else:self.assertEqual(decode(image)[0],actual)
        self.invoke(dict(command='document.export',document=d,format='svg'),1)
        self.invoke(dict(command='document.export',document=d,format='pdf'),1)

    def test_mcp_sessions_reopen_settings_undo_redo_retry_and_source_independence(self):
        d=self.retain();session=dict(session_root=str(self.root/'sessions'),session_id='raw')
        action=dict(type='edit',operations=[dict(op='raw_settings',id='raw',settings=raw.settings(exposure_stops=1),corrections=dict(detail=dict(radius=1,threshold=0,amount=.5)))])
        with closing(Client()) as c:
            c.initialize();c.success('session.create',**session,request_id='create',document=d)
            changed=c.success('session.apply',**session,request_id='change',expected_revision=0,action=action)['document']
            undo=c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(undo,dict(d,revision=2))
            redo=c.success('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'))['document']
            recipe=c.success('raw.recipe',document=redo,id='raw');self.assertEqual(recipe['recipe'],redo['items'][0]['content']['raw']['recipe'])
        self.source.unlink()
        with closing(Client()) as c:
            c.initialize();self.assertEqual(c.success('session.read',**session)['document'],redo)
            self.assertTrue(c.success('session.apply',**session,request_id='change',expected_revision=0,action=action)['replayed'])
            self.assertEqual(self.output(redo),self.output(changed));self.assertTrue(c.success('session.verify',**session)['valid'])


if __name__=='__main__':unittest.main()
