"""Independent rational neighborhoods, high-precision sharpening and seeded distribution checks."""
import base64
import copy
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import hashlib
import math
import statistics
import struct
import tempfile
import unittest
import test_adjustments_cli as tone
import test_editing_cli as editing
import test_filters_cli as blur
from test_mcp import Client


def detail(**operator):return dict(type='detail',operator=operator)
def spatial(**operator):return dict(type='spatial',operator=operator)
def seeded(seed,x,y,c,distribution):
    digest=hashlib.sha256(b'Inkbolt noise v1\0'+struct.pack('<IIIB',seed,x,y,c)).digest()
    a,b=struct.unpack('<QQ',digest[:16]);u=F(2*(a>>12)+1,2**53);v=F(2*(b>>12)+1,2**53)
    return 2*u-1 if distribution=='uniform' else math.sqrt(-2*math.log(float(u)))*math.cos(math.tau*float(v))


class DetailSpatialTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    document=tone.AdjustmentCliTests.document
    edit=tone.AdjustmentCliTests.edit
    source=tone.AdjustmentCliTests.source
    pixels=tone.AdjustmentCliTests.pixels
    saved=tone.AdjustmentCliTests.saved
    assert_quantized=tone.AdjustmentCliTests.assert_quantized
    filter=blur.FilterTests.filter
    filtered=blur.FilterTests.filtered
    chart=blur.FilterTests.chart

    def test_sharpen_exact_cardinal_kernel_alpha_flat_fields_and_overshoot(self):
        values=self.chart(7,5);p=blur.premult(values);d=self.source(values,7)
        for border in ('transparent','clamp','reflect','wrap'):
            for amount in (F(0),F(1,2),F(4),F(8)):
                wanted=[]
                for y in range(5):
                    for x in range(7):
                        center=p[y*7+x];ns=[blur.fetch(p,7,5,x+dx,y+dy,border) for dx,dy in [(-1,0),(1,0),(0,-1),(0,1)]]
                        alpha=sum(q[3] for q in ns);colors=[]
                        for c in range(3):
                            a=center[c]/center[3] if center[3] else F(0);b=sum(q[c] for q in ns)/alpha if alpha else a
                            colors.append(max(0,min(1,a+amount*(a-b))) if center[3] else F(0))
                        wanted.extend(colors+[center[3]])
                out=self.filtered(d,[self.filter(detail(type='sharpen',amount=float(amount)),border=border)])
                self.assert_quantized(self.pixels(out),wanted);self.assertEqual(out['items'][0]['content'],d['items'][0]['content'])
        flat=self.source([(83,147,218,a) for a in (0,1,51,255,37,0,255)])
        self.assertEqual(self.pixels(self.filtered(flat,[self.filter(detail(type='sharpen',amount=8))])),self.pixels(flat))
        step=self.source([(40,40,40,255),(40,40,40,255),(210,210,210,255),(210,210,210,255)])
        self.assertEqual(self.pixels(self.filtered(step,[self.filter(detail(type='sharpen',amount=4),border='clamp')])),bytes([40,40,40,255,0,0,0,255,255,255,255,255,210,210,210,255]))

    def test_unsharp_decimal_gaussian_thresholds_clipping_and_zero_controls(self):
        values=[(20,30,240,255),(50,50,210,73),(130,150,90,255),(150,145,95,1),(240,230,10,255),(22,111,88,0)];d=self.source(values)
        with localcontext() as ctx:
            ctx.prec=45
            for sigma in (D('.6'),D('1.3')):
                r=int((3*sigma).to_integral_value(rounding='ROUND_CEILING'));k=[(-D(i*i)/(2*sigma*sigma)).exp() for i in range(-r,r+1)];total=sum(k);k=[v/total for v in k]
                for amount,threshold in ((D('0'),D('0')),(D('1.75'),D('.08')),(D('8'),D('0')),(D('2'),D('1'))):
                    expected=[]
                    for x,p in enumerate(values):
                        neighbors=[values[min(5,max(0,x+j))] for j in range(-r,r+1)]
                        alpha=sum(D(q[3])/255*v for q,v in zip(neighbors,k))
                        color=[]
                        for c in range(3):
                            current=D(p[c])/255;average=sum(D(q[c]*q[3])/D(65025)*v for q,v in zip(neighbors,k))/alpha
                            delta=current-average;value=current+amount*delta if abs(delta)>=threshold else current
                            color.append(int(max(D(0),min(D(1),value))*255+D('.5')) if p[3] else 0)
                        expected.extend(color+[p[3]])
                    out=self.filtered(d,[self.filter(detail(type='unsharp',sigma=float(sigma),amount=float(amount),threshold=float(threshold)),border='clamp')])
                    self.assertEqual(self.pixels(out),bytes(expected))
            self.assertEqual(self.pixels(self.filtered(d,[self.filter(detail(type='unsharp',sigma=0,amount=8))])),self.pixels(d))
            flat=self.source([(113,210,71,a) for a in (0,1,255,12,88,0,255)])
            self.assertEqual(self.pixels(self.filtered(flat,[self.filter(detail(type='unsharp',sigma=2,amount=8))])),self.pixels(flat))

    def test_median_independent_order_statistics_defects_even_counts_and_alpha(self):
        w,h=7,5;values=self.chart(w,h);d=self.source(values,w)
        for border in ('transparent','clamp','reflect','wrap'):
            for radius in (0,1,2):
                p=blur.premult(values);wanted=[]
                for y in range(h):
                    for x in range(w):
                        ns=[blur.fetch(p,w,h,x+dx,y+dy,border) for dy in range(-radius,radius+1) for dx in range(-radius,radius+1)];ns=[q for q in ns if q[3]]
                        a=values[y*w+x][3]
                        wanted.extend([sorted(q[c]/q[3] for q in ns)[len(ns)//2] for c in range(3)]+[F(a,255)] if a else [F(0)]*4)
                self.assert_quantized(self.pixels(self.filtered(d,[self.filter(detail(type='median',radius=radius),border=border)])),wanted)
        flat=[(81,140,210,255)]*49
        for defect in ((0,0,0,255),(255,255,255,255)):
            damaged=flat.copy();damaged[24]=defect
            self.assertEqual(self.pixels(self.filtered(self.source(damaged,7),[self.filter(detail(type='median',radius=1),border='clamp')])),bytes(v for p in flat for v in p))

    def test_noise_sha_reference_exact_uniform_gaussian_alpha_and_seed_changes(self):
        w,h=17,9;values=[(80+x*5,60+y*15,130,(0,1,79,255)[(x+y)%4]) for y in range(h) for x in range(w)];d=self.source(values,w)
        for distribution in ('uniform','gaussian'):
            for mono in (True,False):
                for seed in (0,4294967295):
                    ideal=[]
                    for i,p in enumerate(values):
                        for c in range(3):
                            v=F(p[c],255)+F(1,8)*seeded(seed,i%w,i//w,0 if mono else c,distribution)
                            ideal.append(max(0,min(1,v)) if p[3] else F(0))
                        ideal.append(F(p[3],255))
                    f=self.filter(detail(type='noise',amount=.125,seed=seed,distribution=distribution,monochrome=mono));out=self.filtered(d,[f])
                    actual=self.pixels(out)
                    self.assertEqual(actual,bytes(tone.byte(v) for v in ideal));self.assertEqual(self.pixels(self.saved(out)),actual)
                    changed=self.filtered(d,[self.filter(detail(type='noise',amount=.125,seed=seed^123,distribution=distribution,monochrome=mono))]);self.assertNotEqual(self.pixels(changed),actual)
        self.assertEqual(self.pixels(self.filtered(d,[self.filter(detail(type='noise',amount=0,seed=7))])),self.pixels(d))

    def test_noise_distribution_mean_variance_tails_color_independence_and_scale(self):
        w=h=128;d=self.document(w,h);d=self.edit(d,[dict(op='add',item=dict(id='source',content=dict(type='fill',width=w,height=h,paint=[128,128,128,255])))])
        for distribution in ('uniform','gaussian'):
            out=self.filtered(d,[self.filter(detail(type='noise',amount=.06,seed=739,distribution=distribution,monochrome=False))]);raw=self.pixels(out)
            channels=[[(raw[i*4+c]-128)/(255*.06) for i in range(w*h)] for c in range(3)]
            for sample in channels:
                self.assertLess(abs(statistics.mean(sample)),.025)
                self.assertAlmostEqual(statistics.pvariance(sample),F(1,3) if distribution=='uniform' else 1,delta=.035)
                if distribution=='uniform':self.assertLessEqual(max(map(abs,sample)),1+.5/(255*.06))
                else:self.assertTrue(.035<sum(abs(x)>2 for x in sample)/len(sample)<.055)
            for c in (1,2):self.assertLess(abs(statistics.correlation(channels[0],channels[c])),.025)
        small=self.source([(128,128,128,255)]*12,4);small=self.filtered(small,[self.filter(detail(type='noise',amount=.1,seed=123))]);one=self.pixels(small)
        for scale in (2,4):
            raw=bytes.fromhex(self.invoke(dict(command='document.render',document=small,scale=scale))['data'])
            expected=b''.join(one[((y//scale)*4+x//scale)*4:((y//scale)*4+x//scale+1)*4] for y in range(3*scale) for x in range(4*scale))
            self.assertEqual(raw,expected)

    def test_offset_fractional_premultiplied_sampling_all_borders_and_identity(self):
        w,h=7,5;values=self.chart(w,h);d=self.source(values,w);p=blur.premult(values)
        for dx,dy in ((F(0),F(0)),(F(2),F(-1)),(F(-3,2),F(5,4))):
            for border in ('transparent','clamp','reflect','wrap'):
                ideal=[blur.bilinear(p,w,h,F(x)-dx,F(y)-dy,border) for y in range(h) for x in range(w)]
                out=self.filtered(d,[self.filter(spatial(type='offset',offset=[float(dx),float(dy)]),border=border)])
                self.assert_quantized(self.pixels(out),blur.unpremult(ideal));self.assertEqual(out['items'][0]['content'],d['items'][0]['content'])

    def test_displacement_coordinate_map_neutral_controls_bilinear_and_transform(self):
        w,h=7,5;values=self.chart(w,h);d=self.source(values,w);p=blur.premult(values)
        field=dict(width=2,height=2,vectors=[[-1,-1],[1,-1],[-1,1],[1,1]],transform=[4,0,0,3,1,0],sampling='bilinear')
        for border in ('transparent','clamp','reflect','wrap'):
            ideal=[]
            for y in range(h):
                for x in range(w):
                    gx=max(0,min(1,(F(x)+F(1,2)-1)/4-F(1,2)));gy=max(0,min(1,(F(y)+F(1,2))/3-F(1,2)))
                    ideal.append(blur.bilinear(p,w,h,F(x)+F(3,2)*(2*gx-1),F(y)-F(1,2)*(2*gy-1),border))
            out=self.filtered(d,[self.filter(spatial(type='displace',map=field,amount=[1.5,-.5]),border=border)])
            self.assert_quantized(self.pixels(out),blur.unpremult(ideal));self.assertEqual(self.saved(out),out)
        neutral=dict(width=1,height=1,vectors=[[0,0]])
        self.assertEqual(self.pixels(self.filtered(d,[self.filter(spatial(type='displace',map=neutral,amount=[256,256]))])),self.pixels(d))
        self.assertEqual(self.pixels(self.filtered(d,[self.filter(spatial(type='displace',map=field,amount=[0,0]))])),self.pixels(d))
        # Map nearest sampling uses local pixel cells; pull +1 is exactly an offset of -1.
        constant=dict(width=1,height=1,vectors=[[1,0]])
        a=self.filtered(d,[self.filter(spatial(type='displace',map=constant,amount=[1,0]),border='wrap')])
        b=self.filtered(d,[self.filter(spatial(type='offset',offset=[-1,0]),border='wrap')]);self.assertEqual(self.pixels(a),self.pixels(b))

    def test_mosaic_exact_block_means_partial_cells_alpha_and_identity(self):
        w,h=7,5;values=self.chart(w,h);d=self.source(values,w);p=blur.premult(values)
        for size in (1,2,3,128):
            ideal=[]
            for y in range(h):
                for x in range(w):
                    cell=[p[b*w+a] for b in range(y//size*size,min(h,(y//size+1)*size)) for a in range(x//size*size,min(w,(x//size+1)*size))]
                    ideal.append([sum(v[c] for v in cell)/len(cell) for c in range(4)])
            out=self.filtered(d,[self.filter(spatial(type='mosaic',size=size))]);self.assert_quantized(self.pixels(out),blur.unpremult(ideal))
        identity=self.filtered(d,[self.filter(spatial(type='mosaic',size=1))])
        self.assertEqual(self.invoke(dict(command='document.render',document=identity,scale=4))['data'],self.invoke(dict(command='document.render',document=d,scale=4))['data'])

    def test_new_operators_order_mask_opacity_persistence_and_mcp_undo(self):
        d=self.source(self.chart(7,5),7);before=copy.deepcopy(d)
        first=self.filter(detail(type='median',radius=1),id='clean',border='reflect')
        second=self.filter(detail(type='noise',amount=.1,seed=471),id='texture',opacity=.5,mask=dict(width=7,height=5,gray_hex='00'*7+'ff'*28))
        third=self.filter(spatial(type='mosaic',size=3),id='blocks')
        a=self.filtered(d,[first,second,third]);b=self.filtered(d,[third,second,first]);self.assertNotEqual(self.pixels(a),self.pixels(b))
        with tempfile.TemporaryDirectory() as root:
            args=dict(session_root=root,session_id='detail');c=Client();c.initialize()
            try:
                c.success('session.create',**args,request_id='create',document=d)
                changed=c.success('session.apply',**args,request_id='filter',expected_revision=0,action=dict(type='edit',operations=[dict(op='filters',id='source',filters=[first,second,third])]))['document']
                self.assertEqual(self.pixels(changed),self.pixels(a));self.assertEqual(self.saved(changed),changed)
            finally:c.close()
            c=Client();c.initialize()
            try:
                self.assertEqual(self.pixels(c.success('session.read',**args)['document']),self.pixels(a))
                restored=c.success('session.apply',**args,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.pixels(restored),self.pixels(d));c.success('session.verify',**args)
            finally:c.close()
        self.assertEqual(before,d)

    def test_invalid_detail_and_maps_depth_lock_and_work_fail_without_mutation(self):
        d=self.source(self.chart(7,5),7)
        invalid=[detail(type='sharpen',amount=-1),detail(type='sharpen',amount=8.1),detail(type='unsharp',sigma=17,amount=1),detail(type='unsharp',sigma=1,amount=1,threshold=1.1),detail(type='median',radius=9),detail(type='noise',amount=1.1,seed=0),spatial(type='offset',offset=[257,0]),spatial(type='mosaic',size=0),spatial(type='mosaic',size=129),spatial(type='displace',map=dict(width=2,height=1,vectors=[[0,0]]),amount=[1,1]),spatial(type='displace',map=dict(width=1,height=1,vectors=[[1.1,0]]),amount=[1,1])]
        for op in invalid:self.assertEqual(self.filtered(d,[self.filter(op)],expected=1)['code'],'INVALID_DOCUMENT')
        self.assertEqual(self.filtered(d,[self.filter(detail(type='noise',amount=1,seed=4294967296))],expected=1)['code'],'INVALID_REQUEST')
        bad=spatial(type='displace',map=dict(width=65,height=64,vectors=[[0,0]]*(65*64)),amount=[1,1]);self.assertEqual(self.filtered(d,[self.filter(bad)],expected=1)['code'],'RESOURCE_LIMIT')
        high=copy.deepcopy(d);high['color_space']='rgb16';self.assertEqual(self.invoke(dict(command='document.render',document=high),1)['code'],'INVALID_REQUEST')
        huge=self.document(512,512);huge=self.edit(huge,[dict(op='add',item=dict(id='source',content=dict(type='fill',width=512,height=512,paint=[128,128,128,255])))])
        huge=self.filtered(huge,[self.filter(detail(type='median',radius=8))]);self.assertEqual(self.invoke(dict(command='document.render',document=huge),1)['code'],'RESOURCE_LIMIT')
        locked=self.edit(d,[dict(op='properties',id='source',locked=True)]);self.assertEqual(self.filtered(locked,[self.filter(invalid[0])],expected=1)['code'],'LOCKED')

    def test_displacement_item_coordinates_artboard_bleed_and_map_storage_budget(self):
        # A document-space chart is shifted through a map owned by its translated image item.
        d=self.document(8,6);image=dict(id='source',transform=[1,0,0,1,2,1],content=dict(type='raster',width=3,height=3,rgba_hex=bytes(v for y in range(3) for x in range(3) for v in (x*80,y*90,40,255)).hex()))
        d=self.edit(d,[dict(op='add',item=image)]);field=dict(width=3,height=1,vectors=[[-1,0],[0,0],[1,0]])
        f=self.filter(spatial(type='displace',map=field,amount=[1,0]));filtered=self.filtered(d,[f]);base=self.pixels(d)
        original=[tuple(base[i:i+4]) for i in range(0,len(base),4)];p=blur.premult(original)
        desired=[blur.bilinear(p,8,6,F(x)+(-1 if x<3 else 0 if x==3 else 1),F(y),'transparent') for y in range(6) for x in range(8)]
        self.assert_quantized(self.pixels(filtered),blur.unpremult(desired))
        # Board-owned map must shift with bleed when the board placement is removed.
        canvas=self.document(20,14);board=dict(id='board',transform=[1,0,0,1,5,4],filters=[f],content=dict(type='frame',frame=dict(role='artboard',width=8,height=6,bleed=dict(left=1,right=1,top=1,bottom=1))))
        child=copy.deepcopy(image);child['parent']='board'
        canvas=self.edit(canvas,[dict(op='add',item=board),dict(op='add',item=child)])
        def export(bleed):return editing.png_pixels(base64.b64decode(self.invoke(dict(command='artboard.export',document=canvas,format='png',include_bleed=bleed))['artifacts'][0]['artifact']['data']))
        w,h,trim,_=export(False);bw,bh,padded,_=export(True);self.assertEqual((w,h,bw,bh),(8,6,10,8))
        self.assertEqual(b''.join(padded[((y+1)*bw+1)*4:((y+1)*bw+9)*4] for y in range(6)),trim)
        bad=copy.deepcopy(f);bad['operator']['operator']['map']['transform']=[0,0,0,0,0,0]
        self.assertEqual(self.filtered(d,[bad],expected=1)['code'],'UNSUPPORTED')
        map_filter=self.filter(spatial(type='displace',map=dict(width=64,height=64,vectors=[[0,0]]*4096),amount=[0,0]),enabled=False)
        crowded=self.document(1,1)
        for n in range(2):
            crowded=self.edit(crowded,[dict(op='add',item=dict(id=str(n),content=dict(type='fill',width=1,height=1,paint=[1,2,3,255]),filters=[dict(map_filter,id=str(k)) for k in range(8)]))])
        self.assertEqual(self.edit(crowded,[dict(op='add',item=dict(id='overflow',content=dict(type='fill',width=1,height=1,paint=[1,2,3,255]),filters=[map_filter]))],1)['code'],'RESOURCE_LIMIT')


if __name__=='__main__':unittest.main()
