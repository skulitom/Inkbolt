"""Independent full 2D rational/Decimal convolution and reversible effect evidence."""
import base64
import copy
from decimal import Decimal, localcontext
from fractions import Fraction as F
import json
import tempfile
import unittest
import test_adjustments_cli as tone
import test_editing_cli as editing
from test_mcp import Client


def premult(values):
    return [[F(c*a,65025) for c in (r,g,b)]+[F(a,255)] for r,g,b,a in values]


def fetch(pixels,w,h,x,y,border):
    def coord(v,n):
        if border=='transparent':return v if 0<=v<n else None
        if border=='clamp':return min(n-1,max(0,v))
        if border=='wrap':return v%n
        # Build the infinite sequence a,b,c,c,b,a,a,b,c,c,b,a explicitly.
        return (list(range(n))+list(range(n-1,-1,-1)))[v%(2*n)]
    x,y=coord(x,w),coord(y,h)
    return [F(0)]*4 if x is None or y is None else pixels[y*w+x]


def bilinear(pixels,w,h,x,y,border):
    ix,iy=x//1,y//1;fx,fy=x-ix,y-iy
    return [sum(fetch(pixels,w,h,int(ix)+dx,int(iy)+dy,border)[c]*wx*wy for dx,wx in ((0,1-fx),(1,fx)) for dy,wy in ((0,1-fy),(1,fy))) for c in range(4)]


def convolution(pixels,w,h,kernel,border):
    r=len(kernel)//2
    return [[sum(fetch(pixels,w,h,x+dx,y+dy,border)[c]*kernel[dx+r]*kernel[dy+r] for dy in range(-r,r+1) for dx in range(-r,r+1)) for c in range(4)] for y in range(h) for x in range(w)]


def unpremult(pixels):
    return [v for p in pixels for v in ([p[c]/p[3] for c in range(3)]+[p[3]] if tone.byte(p[3]) else [F(0)]*4)]


class FilterTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    document=tone.AdjustmentCliTests.document
    edit=tone.AdjustmentCliTests.edit
    source=tone.AdjustmentCliTests.source
    pixels=tone.AdjustmentCliTests.pixels
    saved=tone.AdjustmentCliTests.saved
    assert_quantized=tone.AdjustmentCliTests.assert_quantized

    def filter(self,op,id='blur',**kw):return dict(id=id,operator=op,**kw)
    def filtered(self,d,filters,id='source',expected=0):return self.edit(d,[dict(op='filters',id=id,filters=filters)],expected)
    def chart(self,w=7,h=5):return [(x*31,y*47,((x+3*y)*31)%256,(0,1,89,255)[(x+2*y)%4]) for y in range(h) for x in range(w)]

    def test_box_full_2d_reference_all_borders_transparent_colors_and_singleton(self):
        for w,h in ((7,5),(1,1),(1,4),(4,1)):
            values=self.chart(w,h);d=self.source(values,w);original=copy.deepcopy(d)
            for border in ('transparent','clamp','reflect','wrap'):
                for radius in (0,1,3):
                    out=self.filtered(d,[self.filter(dict(type='box',radius=radius),border=border)])
                    wanted=convolution(premult(values),w,h,[F(1,2*radius+1)]*(2*radius+1),border)
                    self.assert_quantized(self.pixels(out),unpremult(wanted))
                    self.assertEqual(out['items'][0]['content'],original['items'][0]['content'])
                    self.assertEqual(self.saved(out),out)
            self.assertEqual(d,original)
        # Invisible green cannot contaminate a blurred red edge.
        d=self.source([(255,0,0,255),(0,255,0,0),(0,255,0,0)])
        p=self.pixels(self.filtered(d,[self.filter(dict(type='box',radius=1))]))
        self.assertEqual(p[:8],bytes([255,0,0,28,255,0,0,28]))

    def test_gaussian_high_precision_impulse_symmetry_normalization_and_borders(self):
        with localcontext() as ctx:
            ctx.prec=45
            for sigma in (Decimal('.5'),Decimal('1'),Decimal('1.7')):
                radius=int((3*sigma).to_integral_value(rounding='ROUND_CEILING'))
                k=[(-(Decimal(i)**2)/(2*sigma*sigma)).exp() for i in range(-radius,radius+1)]
                total=sum(k);k=[F(v/total) for v in k]
                values=[(240,100,20,255) if x==4 and y==4 else (10,200,90,0) for y in range(9) for x in range(9)]
                d=self.source(values,9)
                for border in ('transparent','reflect','wrap','clamp'):
                    out=self.filtered(d,[self.filter(dict(type='gaussian',sigma=float(sigma)),border=border)])
                    ideal=unpremult(convolution(premult(values),9,9,k,border))
                    # Decimal reference has no half-byte ties here.
                    self.assertEqual(self.pixels(out),bytes(tone.byte(v) for v in ideal))
                edge_values=self.chart(3,3);edge=self.source(edge_values,3)
                for border in ('transparent','reflect','wrap','clamp'):
                    ideal=unpremult(convolution(premult(edge_values),3,3,k,border))
                    actual=self.pixels(self.filtered(edge,[self.filter(dict(type='gaussian',sigma=float(sigma)),border=border)]))
                    self.assertEqual(actual,bytes(tone.byte(v) for v in ideal))
                if sigma<=1:
                    p=self.pixels(out)
                    self.assertEqual([p[(4*9+x)*4+3] for x in range(9)],[p[(y*9+4)*4+3] for y in range(9)])
            flat=self.source([(81,172,231,79)]*25,5)
            for border in ('clamp','reflect','wrap'):
                self.assertEqual(self.pixels(self.filtered(flat,[self.filter(dict(type='gaussian',sigma=2.5),border=border)])),self.pixels(flat))
            for sigma in (0,1e-200):
                self.assertEqual(self.pixels(self.filtered(flat,[self.filter(dict(type='gaussian',sigma=sigma))])),self.pixels(flat))

    def test_directional_horizontal_vertical_fractional_sampling_and_identity(self):
        w,h=7,5;values=self.chart(w,h);d=self.source(values,w);p=premult(values)
        for length in (F(0),F(3),F(5,2)):
            for angle in (0,90):
                for border in ('transparent','clamp','wrap','reflect'):
                    positions=[(F(j,4)-F(1,2))*length for j in range(5)]
                    expected=[[sum(bilinear(p,w,h,F(x)+(v if angle==0 else 0),F(y)+(v if angle==90 else 0),border)[c] for v in positions)/5 for c in range(4)] for y in range(h) for x in range(w)]
                    out=self.filtered(d,[self.filter(dict(type='directional',length=float(length),angle=angle,samples=5),border=border)])
                    self.assert_quantized(self.pixels(out),unpremult(expected))

    def test_radial_spin_and_zoom_local_center_transforms_and_borders(self):
        w=h=5;values=self.chart(w,h);d=self.source(values,w);p=premult(values)
        for angle,zoom in ((0,F(1)),(180,F(0)),(180,F(-1)),(0,F(0))):
            for border in ('transparent','wrap','reflect','clamp'):
                expected=[]
                for y in range(h):
                    for x in range(w):
                        coordinates=[]
                        for t in (F(-1,2),F(0),F(1,2)):
                            a,b=F(x-2),F(y-2)
                            if angle and t<0:a,b=b,-a
                            if angle and t>0:a,b=-b,a
                            coordinates.append((2+a*(1+zoom*t),2+b*(1+zoom*t)))
                        expected.append([sum(bilinear(p,w,h,a,b,border)[c] for a,b in coordinates)/3 for c in range(4)])
                op=dict(type='radial',center=[2.5,2.5],angle=angle,zoom=float(zoom),samples=3)
                self.assert_quantized(self.pixels(self.filtered(d,[self.filter(op,border=border)])),unpremult(expected))
        # Translate a small source and its local radial center; reference operates on the larger viewport.
        large=self.document(9,9);source=copy.deepcopy(d['items'][0]);source['transform']=[1,0,0,1,2,2]
        large=self.edit(large,[dict(op='add',item=source)])
        f=self.filter(dict(type='radial',center=[2.5,2.5],angle=180,samples=3))
        raw=self.pixels(self.filtered(large,[f]));small=self.pixels(self.filtered(d,[f]))
        self.assertEqual(b''.join(raw[(y*9+2)*4:(y*9+7)*4] for y in range(2,7)),small)

    def test_surface_range_gate_flat_fields_defects_alpha_and_threshold(self):
        w,h=7,3
        values=[(10 if x<3 else (190 if x==5 and y==1 else 200),)*3+(255,) for y in range(h) for x in range(w)]
        d=self.source(values,w);p=premult(values)
        for threshold in (F(0),F(1,10),F(1)):
            wanted=[]
            for y in range(h):
                for x in range(w):
                    neighbors=[fetch(p,w,h,x+dx,y+dy,'clamp') for dy in (-1,0,1) for dx in (-1,0,1)]
                    neighbors=[q for q in neighbors if all(abs(q[c]-p[y*w+x][c])<=threshold for c in range(4))]
                    wanted.append([sum(q[c] for q in neighbors)/len(neighbors) for c in range(4)])
            out=self.filtered(d,[self.filter(dict(type='surface',radius=1,threshold=float(threshold)),border='clamp')])
            self.assert_quantized(self.pixels(out),unpremult(wanted))
            if threshold==F(1,10):
                raw=self.pixels(out);self.assertEqual(raw[(1*w+2)*4],10);self.assertEqual(raw[(1*w+3)*4],200);self.assertEqual(raw[(1*w+5)*4],199)
        transparent=self.source([(255,0,0,255),(0,255,0,0),(0,0,255,89)])
        self.assertEqual(self.pixels(self.filtered(transparent,[self.filter(dict(type='surface',radius=2,threshold=0))])),self.pixels(transparent))

    def test_stack_order_masks_opacity_blend_and_parameter_replacement(self):
        w,h=5,3;values=self.chart(w,h);d=self.source(values,w);p=premult(values)
        filtered=convolution(p,w,h,[F(1,3)]*3,'reflect')
        mask=bytes([0,64,128,192,255]*h)
        for blend in ('normal','multiply','screen'):
            f=self.filter(dict(type='box',radius=1),border='reflect',opacity=.75,blend=blend,mask=dict(width=w,height=h,gray_hex=mask.hex()))
            expected=[]
            for i,(a,b) in enumerate(zip(p,filtered)):
                t=F(3,4)*F(mask[i],255);alpha=(1-t)*a[3]+t*b[3];pixel=[]
                for c in range(3):
                    ac=a[c]/a[3] if a[3] else F(0);bc=b[c]/b[3] if b[3] else F(0)
                    color=bc if blend=='normal' else ac*bc if blend=='multiply' else ac+bc-ac*bc
                    effect=(1-a[3])*bc+a[3]*color
                    pixel.append((1-t)*a[c]+t*b[3]*effect)
                expected.append(pixel+[alpha])
            out=self.filtered(d,[f]);self.assert_quantized(self.pixels(out),unpremult(expected))
            f['enabled']=False;self.assertEqual(self.pixels(self.filtered(out,[f])),self.pixels(d))
            f['enabled']=True;f['opacity']=0;self.assertEqual(self.pixels(self.filtered(out,[f])),self.pixels(d))
        a=self.filter(dict(type='box',radius=1),id='spread',border='clamp');b=self.filter(dict(type='surface',radius=1,threshold=.1),id='protect',border='clamp')
        self.assertNotEqual(self.pixels(self.filtered(d,[a,b])),self.pixels(self.filtered(d,[b,a])))
        self.assertEqual(self.pixels(self.filtered(self.filtered(d,[a,b]),[])),self.pixels(d))

    def test_vector_effect_geometry_nested_isolation_clip_and_scale(self):
        d=self.invoke(dict(command='document.create',id='vector-blur',kind='vector',width=9,height=9))
        rect=dict(id='source',content=dict(type='vector',geometry=dict(shape='rect',x=3,y=3,width=3,height=3),fill=[200,80,30,255]))
        d=self.edit(d,[dict(op='add',item=rect)]);f=self.filter(dict(type='box',radius=1));out=self.filtered(d,[f])
        self.assertEqual(out['items'][0]['content'],d['items'][0]['content']);self.assertNotEqual(self.pixels(out),self.pixels(d));self.assertEqual(self.saved(out),out)
        self.assertEqual(self.invoke(dict(command='document.export',document=out,format='svg'),1)['code'],'UNSUPPORTED')
        for scale in (1,2,4):
            r=self.invoke(dict(command='document.render',document=out,scale=scale));w=9*scale
            source=[(200,80,30,255) if 3*scale<=x<6*scale and 3*scale<=y<6*scale else (0,0,0,0) for y in range(w) for x in range(w)]
            self.assert_quantized(bytes.fromhex(r['data']),unpremult(convolution(premult(source),w,w,[F(1,2*scale+1)]*(2*scale+1),'transparent')))
        group=self.edit(d,[dict(op='group',ids=['source'],new_id='group',isolated=True)])
        group=self.filtered(group,[f],id='group');self.assertEqual(self.pixels(group),self.pixels(out))
        self.assertEqual(self.edit(group,[dict(op='ungroup',id='group')],1)['code'],'UNSUPPORTED')
        clipped=self.edit(out,[dict(op='clip',id='source',clip=dict(geometry=dict(shape='rect',x=3,y=3,width=3,height=3)))])
        raw=self.pixels(clipped)
        for y in range(9):
            for x in range(9):
                if not(3<=x<6 and 3<=y<6):self.assertEqual(raw[(y*9+x)*4:(y*9+x+1)*4],bytes(4))

    def test_masks_inversion_density_feather_linking_and_artboard_bleed(self):
        # The same processed field used as an item mask on the filtered-only result must match
        # per-filter mixing where the original is transparent at the probed spread pixels.
        d=self.document(7,5);item=dict(id='source',transform=[1,0,0,1,2,2],content=dict(type='raster',width=1,height=1,rgba_hex='ff0000ff'))
        d=self.edit(d,[dict(op='add',item=item)]);f=self.filter(dict(type='box',radius=1))
        mask=dict(width=3,height=3,gray_hex='0080ff'*3,invert=True,density=.7,feather=1,transform=[1,0,0,1,-1,-1],sampling='bilinear')
        out=self.filtered(d,[dict(f,mask=mask)]);all_filtered=self.filtered(d,[f]);item_masked=self.edit(all_filtered,[dict(op='mask',id='source',mask=mask)])
        a,b=self.pixels(out),self.pixels(item_masked)
        for i in range(35):
            if i!=16:self.assertEqual(a[i*4:i*4+4],b[i*4:i*4+4])
        unlinked=copy.deepcopy(mask);unlinked['linked']=False;unlinked['transform']=[1,0,0,1,1,1]
        self.assertEqual(a,self.pixels(self.filtered(d,[dict(f,mask=unlinked)])))
        self.assertEqual(self.edit(self.edit(all_filtered,[dict(op='mask',id='source',mask=mask)]),[dict(op='mask_apply',id='source')],1)['code'],'UNSUPPORTED')
        board=dict(id='board',transform=[1,0,0,1,4,3],content=dict(type='frame',frame=dict(role='artboard',width=7,height=5,bleed=dict(left=1,right=1,top=1,bottom=1))))
        framed=self.document(16,12);child=copy.deepcopy(d['items'][0]);child['parent']='board';child['filters']=[dict(f,mask=dict(unlinked,transform=[1,0,0,1,5,4]))]
        framed=self.edit(framed,[dict(op='add',item=board),dict(op='add',item=child)])
        artifact=self.invoke(dict(command='artboard.export',document=framed,format='png'))['artifacts'][0]['artifact']
        self.assertEqual(editing.png_pixels(base64.b64decode(artifact['data']))[2],a)
        bleed=self.invoke(dict(command='artboard.export',document=framed,format='png',include_bleed=True))['artifacts'][0]['artifact']
        bw,bh,bp,_=editing.png_pixels(base64.b64decode(bleed['data']));self.assertEqual((bw,bh),(9,7))
        self.assertEqual(b''.join(bp[((y+1)*bw+1)*4:((y+1)*bw+8)*4] for y in range(5)),a)
        moved=self.edit(framed,[dict(op='transform',id='board',matrix=[2,0,0,2,4,3])])
        # Linked masks and centers follow local geometry; unlinked masks stay in document coordinates.
        self.assertNotEqual(self.pixels(moved),self.pixels(framed))

    def test_mcp_session_revisions_reorder_diff_undo_reopen_and_source_preservation(self):
        d=self.source(self.chart(5,3),5);source=copy.deepcopy(d)
        with tempfile.TemporaryDirectory() as root:
            c=Client();c.initialize()
            try:
                c.success('session.create',session_root=root,session_id='filters',request_id='create',document=d)
                first=c.success('session.apply',session_root=root,session_id='filters',expected_revision=0,request_id='blur',action=dict(type='edit',operations=[dict(op='filters',id='source',filters=[self.filter(dict(type='gaussian',sigma=1))])]))
                self.assertEqual(first['document']['revision'],1)
            finally:c.close()
            c=Client();c.initialize()
            try:
                reopened=c.success('session.read',session_root=root,session_id='filters');out=reopened['document']
                self.assertNotEqual(self.pixels(out),self.pixels(d));self.assertEqual(out['items'][0]['content'],d['items'][0]['content'])
                diff=c.success('session.diff',session_root=root,session_id='filters',from_revision=0,to_revision=1,compare_pixels=True)
                self.assertEqual(diff['items'][0]['fields'],['filters']);self.assertGreater(diff['rendered_pixels']['changed_pixels'],0)
                revised=[self.filter(dict(type='box',radius=1),id='first'),self.filter(dict(type='surface',radius=1,threshold=.1),id='second')]
                c.success('session.apply',session_root=root,session_id='filters',expected_revision=1,request_id='revise',action=dict(type='edit',operations=[dict(op='filters',id='source',filters=revised)]))
                second=c.success('session.read',session_root=root,session_id='filters')['document']
                third=c.success('session.apply',session_root=root,session_id='filters',expected_revision=2,request_id='reorder',action=dict(type='edit',operations=[dict(op='filters',id='source',filters=revised[::-1])]))['document']
                self.assertNotEqual(self.pixels(second),self.pixels(third))
                undone=c.success('session.apply',session_root=root,session_id='filters',expected_revision=3,request_id='undo-order',action=dict(type='undo'))['document']
                self.assertEqual(self.pixels(undone),self.pixels(second))
                c.success('session.apply',session_root=root,session_id='filters',expected_revision=4,request_id='undo-revise',action=dict(type='undo'))
                c.success('session.apply',session_root=root,session_id='filters',expected_revision=5,request_id='undo',action=dict(type='undo'))
                restored=c.success('session.read',session_root=root,session_id='filters')['document'];self.assertEqual(self.pixels(restored),self.pixels(d));self.assertNotIn('filters',restored['items'][0])
                c.success('session.verify',session_root=root,session_id='filters')
            finally:c.close()
        self.assertEqual(d,source)

    def test_invalid_parameters_atomic_edits_locks_depths_and_resource_limits(self):
        d=self.source(self.chart(5,3),5);original=copy.deepcopy(d)
        bad=[dict(type='box',radius=33),dict(type='gaussian',sigma=-1),dict(type='gaussian',sigma=16.1),dict(type='directional',length=65,angle=0),dict(type='directional',length=3,angle=0,samples=4),dict(type='radial',center=[0,0],angle=181),dict(type='radial',center=[0,0],angle=0,zoom=2),dict(type='surface',radius=17,threshold=.1),dict(type='surface',radius=1,threshold=-.1)]
        for op in bad:self.assertEqual(self.filtered(d,[self.filter(op)],expected=1)['code'],'INVALID_DOCUMENT')
        f=self.filter(dict(type='box',radius=1))
        self.assertEqual(self.filtered(d,[f,f],expected=1)['code'],'INVALID_DOCUMENT')
        self.assertEqual(self.filtered(d,[dict(f,id=str(i)) for i in range(9)],expected=1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.filtered(d,[dict(f,opacity=2)],expected=1)['code'],'INVALID_DOCUMENT')
        locked=self.edit(d,[dict(op='properties',id='source',locked=True)])
        self.assertEqual(self.filtered(locked,[f],expected=1)['code'],'LOCKED')
        group=self.edit(d,[dict(op='group',ids=['source'],new_id='group',isolated=False)])
        self.assertEqual(self.filtered(group,[f],id='group',expected=1)['code'],'UNSUPPORTED')
        adjustment=dict(id='adjust',content=dict(type='adjustment',adjustment=dict(operators=[dict(type='invert')])))
        adjusted=self.edit(d,[dict(op='add',item=adjustment)])
        self.assertEqual(self.filtered(adjusted,[f],id='adjust',expected=1)['code'],'UNSUPPORTED')
        self.edit(d,[dict(op='filters',id='source',filters=[f]),dict(op='filters',id='source',filters=[self.filter(bad[0])])],1);self.assertEqual(d,original)
        huge=self.document(512,512);huge=self.edit(huge,[dict(op='add',item=dict(id='source',content=dict(type='fill',width=512,height=512,paint=[1,2,3,255])))])
        huge=self.filtered(huge,[self.filter(dict(type='surface',radius=16,threshold=.1))])
        self.assertEqual(self.invoke(dict(command='document.render',document=huge),1)['code'],'RESOURCE_LIMIT')
        high=copy.deepcopy(d);high['color_space']='linear_hdr';self.assertEqual(self.invoke(dict(command='document.render',document=high),1)['code'],'INVALID_REQUEST')

    def test_document_filter_and_preparation_limits_include_hidden_disabled_effects(self):
        d=self.document(1,1);items=[]
        for n in range(9):
            item=dict(id=str(n),visible=False,content=dict(type='fill',width=1,height=1,paint=[1,2,3,255]),filters=[self.filter(dict(type='box',radius=0),id=str(k),enabled=False) for k in range(8)])
            items.append(dict(op='add',item=item))
        self.assertEqual(self.edit(d,items,1)['code'],'RESOURCE_LIMIT')
        # Padded feather fields exceed aggregate preparation work even while disabled.
        f=self.filter(dict(type='box',radius=0),enabled=False,mask=dict(width=1,height=128,gray_hex='ff'*128,feather=32,enabled=False))
        items=[]
        for n in range(8):
            item=dict(id=str(n),content=dict(type='fill',width=1,height=1,paint=[1,2,3,255]),filters=[dict(f,id=str(k)) for k in range(8)])
            items.append(dict(op='add',item=item))
        self.assertEqual(self.edit(d,items,1)['code'],'RESOURCE_LIMIT')


if __name__=='__main__':unittest.main()
