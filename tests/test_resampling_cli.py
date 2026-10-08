"""Independent rational-area/Hermite and decimal-sinc reconstruction evidence."""
import base64
import copy
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
from functools import lru_cache
import hashlib
import math
import tempfile
import unittest
import test_editing_cli as editing
from test_layer_clipping_cli import layer
from test_images_cli import canonical
from test_mcp import Client

METHODS=('area','bicubic','lanczos3')


def hermite(a,b,c,d,t):
    # Endpoint values and centered endpoint derivatives, independent of the
    # production piecewise convolution polynomial.
    return (2*t**3-3*t*t+1)*b+(t**3-2*t*t+t)*(c-a)/2+(-2*t**3+3*t*t)*c+(t**3-t*t)*(d-b)/2


def cubic_impulse(x):
    j=x.numerator//x.denominator
    return hermite(*[F(int(n==0)) for n in range(j-1,j+3)],x-j)


@lru_cache(None)
def sinc_decimal(x):
    if not x:return D(1)
    if x.denominator==1:return D(0)
    with localcontext() as ctx:
        ctx.prec=70
        pi=D('3.141592653589793238462643383279502884197169399375105820974944592307816406')
        reduced=(x+1)%2-1
        v=D(reduced.numerator)/D(reduced.denominator)*pi
        term=v;total=v
        for n in range(1,100):
            term*=-v*v/D(2*n*(2*n+1));total+=term
            if abs(term)<D('1e-68'):break
        return total/(D(x.numerator)/D(x.denominator)*pi)


def weights(method,center,width,extent):
    if method!='area':width=max(F(1),width)
    radius=width*({'area':F(1,2),'bicubic':2,'lanczos3':3}[method])
    values={}
    for i in range(math.floor(center-radius)-2,math.ceil(center+radius)+2):
        if method=='area':v=max(F(0),min(center+radius,i+1)-max(center-radius,i))
        else:
            x=(F(2*i+1,2)-center)/width
            v=cubic_impulse(x) if method=='bicubic' else sinc_decimal(x)*sinc_decimal(x/3) if abs(x)<3 else D(0)
        index=max(0,min(extent-1,i));values[index]=values.get(index,0)+v
    total=sum(values.values());return [(i,v/total) for i,v in values.items() if v]


def reference(colors,sw,sh,w,h,method):
    with localcontext() as ctx:
        ctx.prec=60
        xs=[weights(method,F(2*x+1,2)*sw/w,F(sw,w),sw) for x in range(w)]
        ys=[weights(method,F(2*y+1,2)*sh/h,F(sh,h),sh) for y in range(h)]
        values=[]
        for y in range(h):
            for x in range(w):
                alpha=0;rgb=[0,0,0]
                for sy,wy in ys[y]:
                    for sx,wx in xs[x]:
                        p=colors[sy*sw+sx];a=p[3]*wx*wy;alpha+=a
                        for c in range(3):rgb[c]+=p[c]*a
                alpha=max(0,min(255,alpha));rgb=[max(0,min(255*alpha,v))/alpha if alpha else 0 for v in rgb]
                values.append(rgb+[alpha] if alpha>=F(1,2) else [0]*4)
        return values


class ResamplingTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,w,h,colors,kind='raster'):
        d=self.invoke(dict(command='document.create',id='resampling',kind=kind,width=w,height=h))
        return self.edit(d,[dict(op='add',item=layer('pixels',colors,w))])
    def edit(self,d,ops,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops),expected)
        return r if expected else r['document']
    def scaled(self,d,w,h,method):
        return self.edit(d,[dict(op='canvas',action=dict(type='scale',width=w,height=h,sampling=method))])
    def pixels(self,d,scale=1):
        r=self.invoke(dict(command='document.export',document=d,format='png',scale=scale))
        return editing.png_pixels(base64.b64decode(r['data']))[2]
    def matches(self,p,values):
        for actual,wanted in zip(p,[c for v in values for c in v],strict=True):
            value=D(wanted.numerator)/D(wanted.denominator) if isinstance(wanted,F) else D(wanted)
            rounded=int((value+D('.5')).to_integral_value(rounding='ROUND_FLOOR'))
            if actual!=rounded:
                self.assertLess(abs(value-(D(rounded)-D('.5'))),D('1e-8'),(actual,value))
                self.assertEqual(actual,rounded-1)

    def test_area_exact_uneven_pixel_overlap_and_alpha_at_both_resize_directions(self):
        colors=[[x*31+y*7,210-x*13,17+y*49,[0,64,192,255][(x+y)%4]] for y in range(4) for x in range(6)]
        d=self.document(6,4,colors)
        for w,h in [(1,1),(3,2),(5,3),(9,7),(12,8)]:
            c=self.scaled(d,w,h,'area');self.matches(self.pixels(c),reference(colors,6,4,w,h,'area'))
            self.assertEqual(c['items'][0]['content']['rgba_hex'],d['items'][0]['content']['rgba_hex'])

    def test_bicubic_matches_cardinal_hermite_and_reproduces_interior_quadratics(self):
        colors=[[15+x*x*3,30+y*y*7,20+x*y*4,255] for y in range(5) for x in range(7)]
        d=self.document(7,5,colors);c=self.scaled(d,21,15,'bicubic');p=self.pixels(c)
        self.matches(p,reference(colors,7,5,21,15,'bicubic'))
        for y in range(5,10):
            for x in range(6,15):
                sx=F(2*x+1,6)-F(1,2);sy=F(2*y+1,6)-F(1,2)
                self.matches(p[(y*21+x)*4:][:4],[[15+sx*sx*3,30+sy*sy*7,20+sx*sy*4,255]])

    def test_lanczos_matches_high_precision_sinc_with_alpha_and_ringing_projection(self):
        colors=[[250,12,91,0],[20,230,40,255],[200,20,230,64],[30,80,140,128],[5,6,7,255],[220,180,90,192]]
        d=self.document(3,2,colors)
        for method in ('bicubic','lanczos3'):
            for w,h in [(9,6),(2,1),(5,3),(3,2)]:
                c=self.scaled(d,w,h,method);self.matches(self.pixels(c),reference(colors,3,2,w,h,method))

    def test_downsampling_suppresses_checkerboard_alias_and_constants_stay_constant(self):
        colors=[[255*((x+y)%2)]*3+[255] for y in range(16) for x in range(16)]
        d=self.document(16,16,colors)
        for method in METHODS:
            c=self.scaled(d,4,4,method);self.matches(self.pixels(c),reference(colors,16,16,4,4,method))
            self.assertTrue(all(124<=v<=131 for v in self.pixels(c)[::4]))
            constant=self.document(9,7,[[45,101,211,73]]*63)
            self.assertEqual(self.pixels(self.scaled(constant,2,3,method)),bytes([45,101,211,73])*6)
        self.assertEqual(self.pixels(self.scaled(d,4,4,'nearest')),bytes([0,0,0,255])*16)

    def test_export_scale_recomputes_footprint_from_immutable_pixels(self):
        colors=[[12*x,23*y,10*(x+y),255] for y in range(5) for x in range(8)]
        d=self.document(8,5,colors)
        for method in METHODS:
            c=self.scaled(d,3,2,method)
            for scale in (1,2,3):self.matches(self.pixels(c,scale),reference(colors,8,5,3*scale,2*scale,method))
            restored=self.scaled(c,8,5,method)
            self.assertEqual(self.pixels(restored),bytes(v for p in colors for v in p))

    def test_scalar_selection_and_channels_use_same_kernels_with_final_clamp(self):
        gray=[0,20,240,255,60,0,190,90,220,255,20,100]
        d=self.document(4,3,[[v,v,v,255] for v in gray]);plane=dict(width=4,height=3,gray_hex=bytes(gray).hex())
        d=self.edit(d,[dict(op='selection_set',selection=plane),dict(op='channel_put',id='saved',channel=dict(name='Original selection',plane=plane))])
        for method in METHODS:
            for w,h in [(7,5),(2,1)]:
                c=self.scaled(d,w,h,method);values=bytes.fromhex(c['selection']['gray_hex'])
                self.assertEqual(c['selection'],c['channels']['saved']['plane'])
                self.assertTrue(all(abs(a-b)<=1 for a,b in zip(values,self.pixels(c)[::4],strict=True)))
                self.assertEqual(c['channels']['saved']['name'],'Original selection')

    def test_cropped_embedded_image_reflection_and_right_angle_rotation(self):
        colors=[[10+30*x,20+60*y,80,255] for y in range(3) for x in range(5)]
        raw=bytes(v for p in colors for v in p);asset=dict(width=5,height=3,sha256=hashlib.sha256(canonical(5,3,raw)).hexdigest(),storage=dict(type='embedded',rgba_hex=raw.hex()))
        selected=[colors[y*5+x] for y in range(1,3) for x in range(1,4)]
        for method in METHODS:
            d=self.invoke(dict(command='document.create',id='resampling',kind='vector',width=5,height=7))
            d=self.edit(d,[dict(op='asset_put',id='source',asset=asset),dict(op='add',item=dict(id='image',transform=[0,1,-1,0,5,0],content=dict(type='image',asset_id='source',width=7,height=5,crop=dict(x=1,y=1,width=3,height=2),sampling=method)))])
            expected=reference(selected,3,2,7,5,method)
            rotated=[expected[(4-x)*7+y] for y in range(7) for x in range(5)]
            self.matches(self.pixels(d),rotated)
            reflected=self.edit(d,[dict(op='transform',id='image',matrix=[0,1,1,0,0,0])])
            self.matches(self.pixels(reflected),[expected[x*7+y] for y in range(7) for x in range(5)])
            self.assertEqual(d['assets'],reflected['assets'])

    def test_unsupported_mask_map_and_svg_contexts_fail_explicitly(self):
        d=self.document(1,1,[[20,80,150,255]])
        for method in METHODS:
            err=self.edit(d,[dict(op='mask',id='pixels',mask=dict(width=1,height=1,gray_hex='ff',sampling=method))],1)
            self.assertEqual(err['code'],'UNSUPPORTED')
            operator=dict(type='spatial',operator=dict(type='displace',map=dict(width=1,height=1,vectors=[[0,0]],sampling=method),amount=[1,1]))
            self.assertEqual(self.edit(d,[dict(op='filters',id='pixels',filters=[dict(id='map',operator=operator)])],1)['code'],'UNSUPPORTED')
            raw=bytes([20,80,150,255]);asset=dict(width=1,height=1,sha256=hashlib.sha256(canonical(1,1,raw)).hexdigest(),storage=dict(type='embedded',rgba_hex=raw.hex()))
            v=self.invoke(dict(command='document.create',id='v',kind='vector',width=1,height=1))
            v=self.edit(v,[dict(op='asset_put',id='source',asset=asset),dict(op='add',item=dict(id='image',visible=False,content=dict(type='image',asset_id='source',width=1,height=1,sampling=method)))])
            self.assertEqual(self.invoke(dict(command='document.export',document=v,format='svg'),1)['code'],'UNSUPPORTED')

    def test_limits_account_for_kernel_taps_hidden_items_and_artboard_ranges(self):
        d=self.document(1,1,[[20,80,150,255]])
        tiny=copy.deepcopy(d);tiny['items'][0]['transform']=[.0001,0,0,.0001,0,0]
        tiny['items'][0]['content']['sampling']='lanczos3'
        # 60002 taps in each axis pass the axis cap but exceed aggregate work.
        self.assertEqual(self.invoke(dict(command='document.render',document=tiny),1)['code'],'RESOURCE_LIMIT')
        too_wide=copy.deepcopy(d);too_wide['items'][0]['transform']=[.00005,0,0,.0002,0,0];too_wide['items'][0]['content']['sampling']='lanczos3'
        self.assertEqual(self.invoke(dict(command='document.render',document=too_wide),1)['code'],'RESOURCE_LIMIT')
        crowded=self.invoke(dict(command='document.create',id='work',kind='raster',width=512,height=512))
        items=[layer(str(i),[[20,80,150,255]],visible=False) for i in range(3)]
        for item in items:item['content']['sampling']='lanczos3'
        crowded=self.edit(crowded,[dict(op='add',item=i) for i in items])
        self.assertEqual(self.invoke(dict(command='document.render',document=crowded),1)['code'],'RESOURCE_LIMIT')
        boards=self.invoke(dict(command='document.create',id='boards',kind='raster',width=512,height=512))
        items=[]
        for i in range(5):items += [dict(id=f'b{i}',content=dict(type='frame',frame=dict(role='artboard',width=512,height=512))),layer(f'p{i}',[[20,80,150,255]],parent=f'b{i}')]
        for item in items:
            if item['content']['type']=='raster':item['content']['sampling']='lanczos3'
        boards=self.edit(boards,[dict(op='add',item=i) for i in items])
        self.assertEqual(self.invoke(dict(command='artboard.export',document=boards,format='png'),1)['code'],'RESOURCE_LIMIT')

    def test_mcp_resampler_persistence_retry_reopen_snapshot_and_undo(self):
        colors=[[x*17,y*31,85,255] for y in range(4) for x in range(6)];d=self.document(6,4,colors)
        with tempfile.TemporaryDirectory() as root:
            params=dict(session_root=root,session_id='resampling');c=Client();c.initialize()
            action=dict(type='edit',operations=[dict(op='canvas',action=dict(type='scale',width=9,height=7,sampling='lanczos3'))])
            try:
                c.success('session.create',**params,request_id='create',document=d)
                changed=c.success('session.apply',**params,request_id='scale',expected_revision=0,action=action)
                self.matches(self.pixels(changed['document']),reference(colors,6,4,9,7,'lanczos3'))
                c.success('session.apply',**params,request_id='save',expected_revision=1,action=dict(type='snapshot',name='scaled'))
            finally:c.close()
            c=Client();c.initialize()
            try:
                self.assertEqual(c.success('session.apply',**params,request_id='scale',expected_revision=0,action=action)['document'],changed['document'])
                self.assertEqual(c.success('session.read',**params,snapshot='scaled')['document']['items'],changed['document']['items'])
                undo=c.success('session.apply',**params,request_id='undo',expected_revision=2,action=dict(type='undo'))
                self.assertEqual(self.pixels(undo['document']),self.pixels(d));c.success('session.verify',**params)
            finally:c.close()


    def test_sheared_area_footprint_matches_independent_pixel_corner_projection(self):
        colors=[[x*x*5,y*y*20,x*y*9,255] for y in range(4) for x in range(6)]
        d=self.document(6,4,colors);d['width']=10;d['height']=8
        d=self.edit(d,[dict(op='sampling',id='pixels',sampling='area'),dict(op='transform',id='pixels',matrix=[1,.25,.5,1,2,1])])
        p=self.pixels(d);checked=0
        def local(x,y):return ((x-2)*F(8,7)-(y-1)*F(4,7),-(x-2)*F(2,7)+(y-1)*F(8,7))
        for y in range(8):
            for x in range(10):
                corners=[local(F(x+dx),F(y+dy)) for dx in (0,1) for dy in (0,1)]
                if not all(0<sx<6 and 0<sy<4 for sx,sy in corners):continue
                sx,sy=local(F(2*x+1,2),F(2*y+1,2))
                fw=max(v[0] for v in corners)-min(v[0] for v in corners);fh=max(v[1] for v in corners)-min(v[1] for v in corners)
                wx=weights('area',sx,fw,6);wy=weights('area',sy,fh,4)
                expected=[sum(colors[j*6+i][c]*a*b for i,a in wx for j,b in wy) for c in range(4)]
                self.matches(p[(y*10+x)*4:][:4],[expected]);checked+=1
        self.assertGreaterEqual(checked,8)

    def test_auxiliary_tap_limit_and_native_mask_application_keep_sampling_contract(self):
        d=self.document(1,1,[[80,100,120,255]]);d['width']=32768
        d=self.edit(d,[dict(op='selection_set',selection=dict(width=32768,height=1,gray_hex='80'*32768))])
        error=self.edit(d,[dict(op='canvas',action=dict(type='scale',width=1,height=32768,sampling='lanczos3'))],1)
        self.assertEqual(error['code'],'RESOURCE_LIMIT');self.assertIn('tap',error['message'])
        colors=[[210,20,70,255],[20,200,50,128],[90,5,20,0],[10,60,220,64]]
        for method in METHODS:
            d=self.document(4,1,colors)
            d=self.edit(d,[dict(op='mask',id='pixels',mask=dict(width=4,height=1,gray_hex='ff'*4)),dict(op='sampling',id='pixels',sampling=method)])
            baked=self.edit(d,[dict(op='mask_apply',id='pixels')])
            self.assertEqual(baked['items'][0]['content']['sampling'],method)
            # The oracle uses original RGBA; hidden RGB at zero alpha must not
            # affect reconstruction after native mask application.
            self.matches(self.pixels(self.scaled(baked,9,3,method)),reference(colors,4,1,9,3,method))


    def test_reconstruction_capabilities_and_strict_persisted_schema(self):
        c=self.invoke(dict(command='capabilities'))
        self.assertEqual(c['canvas_operations']['sampling'],['nearest','bilinear','area','bicubic','lanczos3'])
        self.assertTrue(c['canvas_operations']['advanced_resamplers'])
        self.assertEqual(c['reconstruction']['max_axis_taps'],65536)
        self.assertEqual(c['reconstruction']['max_work'],67108864)
        self.assertEqual(c['reconstruction']['bicubic_parameter'],-.5)
        self.assertEqual(c['reconstruction']['footprint'],'inverse_pixel_source_axis_bounds')
        self.assertEqual(c['masks']['sampling'],['nearest','bilinear'])
        d=self.document(1,1,[[20,40,80,255]])
        self.assertEqual(self.edit(d,[dict(op='sampling',id='pixels',sampling='undefined_kernel')],1)['code'],'INVALID_REQUEST')


if __name__=='__main__':unittest.main()
