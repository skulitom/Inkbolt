"""Direct scalar fields and conditional-silhouette ink references."""
import copy
from fractions import Fraction as F
import hashlib
import itertools
from pathlib import Path
import tempfile
import unittest
import pdf_reader
import test_native_coverage_cli as coverage_tests
from test_native_blending_cli import over, addresses, MODES
from test_native_knockout_cli import partition
from test_extended_effects_cli import field
from test_effects_coverage_cli import effect, threshold
from test_native_images_cli import fill, raster, process
from test_vector_plates_cli import named, color, rect
from test_knockout_cli import group
from test_native_print_cli import page_image
from test_mcp import Client
from test_samples_cli import layer
from test_profiles_cli import embedded, linear_profile
from cmyk_fixtures import cmyk_profile


def evaluate(colors,alpha,w,h,fx,effect_color,back=None,back_alpha=None,fill_opacity=F(1),source_address=None,light=225,scale=1):
    """Evaluate actual colors against a supplied backdrop, without ink-retention storage."""
    n=len(colors[0]);count=len(alpha);back=back or [[F(0)]*n for _ in alpha];back_alpha=back_alpha or [F(0)]*count
    source_address=source_address or [[True]*n for _ in alpha]
    behind=[(list(b),a) for b,a in zip(back,back_alpha)]
    for e in fx:
        if e.get('enabled',True) and e['operator']['type'] in ['shadow','lit_shadow']:
            fields=field(alpha,w,h,e,light,scale)
            for i,value in enumerate(fields):
                c,a,address=effect_color(e,i);behind[i]=over(*behind[i],c,a*F(str(e.get('opacity',1)))*value,address)
    content=[over(*b,c,a*fill_opacity,address) for b,c,a,address in zip(behind,colors,alpha,source_address)]
    intrinsic=[a*fill_opacity for a in alpha]
    for e in fx:
        if e.get('enabled',True) and e['operator']['type']=='overlay':
            fields=field(alpha,w,h,e,light,scale)
            for i,value in enumerate(fields):
                c,a,address=effect_color(e,i);q=a*F(str(e.get('opacity',1)));current,actual_alpha=content[i];bg,ba=behind[i];local=intrinsic[i]
                conditional=[(v-(1-local)*b)/local if local else b for v,b in zip(current,bg)]
                replacement=[v if take else old for v,old,take in zip(c,conditional,address)]
                full=[(1-value)*b+value*v for b,v in zip(bg,replacement)]
                content[i]=([(1-q)*v+q*r for v,r in zip(current,full)],(1-q)*actual_alpha+q*(value+(1-value)*ba))
                intrinsic[i]=(1-q)*local+q*value
    for e in fx:
        if e.get('enabled',True) and e['operator']['type']=='stroke':
            fields=field(alpha,w,h,e,light,scale)
            for i,value in enumerate(fields):
                c,a,address=effect_color(e,i);content[i]=over(*content[i],c,a*F(str(e.get('opacity',1)))*value,address)
    return content


class NativeEffectTests(unittest.TestCase):
    invoke=coverage_tests.NativeCoverageTests.invoke
    document=coverage_tests.NativeCoverageTests.document
    planes=coverage_tests.NativeCoverageTests.planes
    values=coverage_tests.NativeCoverageTests.values
    assertValues=coverage_tests.NativeCoverageTests.assertValues
    edit=coverage_tests.NativeCoverageTests.edit
    export=coverage_tests.NativeCoverageTests.export
    colors={'b':[F(1,2),F(1,4),F(1,8),F(0),F(0)],'p':[F(1,4),F(3,4),F(0),F(1,8),F(0)],'s':[F(0)]*4+[F(3,4)]}

    def ink(self,e,i):
        p=e['color'];c=self.colors[p['swatch']];c=[v*F(str(p.get('tint',1))) for v in c]
        return c,F(str(p.get('opacity',1))),addresses(c,p.get('overprint','knockout'),p['swatch']=='s')

    def scene(self,w=7,h=5):
        d=self.document(w,h);d['swatches']['p']=color(list(map(float,self.colors['p'][:4])))
        # The base spot fixture has full tint one; use .75 references to match
        # the independent effect color tuple above.
        d['swatches']['s']['definition']['alternate']['components']=[.25,.5,.75,.125]
        d['swatches']['s-alias']=dict(name='Effect tint',definition=dict(type='tint',base='s',tint=.75))
        alpha=[F([0,1,3,4][(x+2*y)%4],4) for y in range(h) for x in range(w)]
        d['items']=[group('art',knockout=False)]+[fill(f'p{i}',named('b',opacity=float(a)),box=(i%w,i//w,1,1),parent='art') for i,a in enumerate(alpha)]
        return d,alpha

    def apply_fx(self,d,fx,**kw):
        # References use a .75 spot as their base, stored through a tint alias.
        d=copy.deepcopy(d);actual=copy.deepcopy(fx)
        for e in actual:
            if isinstance(e['color'],dict) and e['color'].get('swatch')=='s':e['color']['swatch']='s-alias'
        d['items'][0].update(effects=actual,**kw);return d

    def test_scalar_effect_fields_order_contours_and_native_named_colors(self):
        d,alpha=self.scene();colors=[self.colors['b']]*35
        fx=[effect('shadow','shadow',named('p',opacity=.625),sigma=.5,offset=[1.25,-.5]),effect('edge','stroke',named('s',opacity=.5),radius=1,position='center'),effect('wash','overlay',named('p',opacity=.375))]
        fx[0].update(scale=1.25,contour=[[0,0],[.5,.875],[1,.25]]);fx[2]['contour']=[[0,0],[.25,.75],[1,.125]]
        for fill_opacity in [0,.25,1]:
            actual=self.values(self.apply_fx(d,fx,fill_opacity=fill_opacity))
            expected=evaluate(colors,alpha,7,5,fx,self.ink,fill_opacity=F(str(fill_opacity)))
            for row,(p,a) in zip(actual,expected):self.assertValues(row,p,3e-12)

    def test_overlay_overprint_preserves_conditional_inks_through_alpha_changes(self):
        for policy,fill_opacity,contour in itertools.product(['knockout','preserve','preserve_nonzero'],[0,.25,1],[[],[[0,0],[.5,1],[1,0]]]):
            d,alpha=self.scene(1,1);alpha=[F(3,4)];d['items']=[fill('back',named('p'),box=(0,0,1,1)),fill('art',named('b',opacity=.75,overprint='preserve_nonzero'),box=(0,0,1,1),fill_opacity=fill_opacity)]
            fx=[effect('one','overlay',named('s',opacity=.625,overprint=policy)),effect('two','overlay',named('p',opacity=.375,overprint='preserve_nonzero'))];fx[0]['contour']=contour
            actual=copy.deepcopy(fx);actual[0]['color']['swatch']='s-alias';d['items'][-1]['effects']=actual
            b=self.colors['p'];s=self.colors['b'];expected=evaluate([s],alpha,1,1,fx,self.ink,back=[b],back_alpha=[F(1)],fill_opacity=F(str(fill_opacity)),source_address=[addresses(s,'preserve_nonzero')])[0][0]
            with self.subTest(policy=policy,fill=fill_opacity,contour=contour):self.assertValues(self.values(d)[0],expected)

    def test_contour_amplification_retains_tiny_original_ink_coverage(self):
        for alpha in [1e-20,1e-200]:
            d,_=self.scene(1,1);fx=effect('amplify','overlay',named('s-alias',overprint='preserve'));fx['contour']=[[0,0],[alpha,1],[1,1]]
            d['items']=[fill('back',named('p'),box=(0,0,1,1)),fill('art',named('b',opacity=alpha),box=(0,0,1,1),effects=[fx])]
            self.assertValues(self.values(d)[0],self.colors['b'][:4]+[F(3,4)])

    def test_global_local_light_and_fractional_effect_scale(self):
        d,alpha=self.scene(5,3);fx=[effect('global','lit_shadow',named('s',opacity=.5,overprint='preserve'),distance=1.25,sigma=.5),effect('local','lit_shadow',named('p',opacity=.625),distance=1,sigma=0,azimuth=90)];fx[0]['scale']=.75
        for light in [0,90,180,270,360,-90,30,225]:
            d['global_light']=dict(azimuth=light);actual=self.values(self.apply_fx(d,fx,fill_opacity=.25));expected=evaluate([self.colors['b']]*15,alpha,5,3,fx,self.ink,fill_opacity=F(1,4),light=light)
            for row,(p,a) in zip(actual,expected):self.assertValues(row,p,3e-12)

    def test_all_item_blends_resolve_decorated_overprint_against_actual_backdrop(self):
        for mode in MODES:
            d,alpha=self.scene(3,1);d['items']=[fill('back',named('p'),box=(0,0,3,1)),fill('art',named('b',opacity=.75,overprint='preserve_nonzero'),box=(0,0,3,1),blend=mode,opacity=.625,fill_opacity=.25)]
            alpha=[F(3,4)]*3;fx=[effect('shadow','shadow',named('s',opacity=.5,overprint='preserve'),sigma=0,offset=[1,0]),effect('overlay','overlay',named('p',opacity=.375,overprint='preserve_nonzero'))];actual=copy.deepcopy(fx);actual[0]['color']['swatch']='s-alias';d['items'][-1]['effects']=actual
            b=self.colors['p'];s=self.colors['b'];kw=dict(source_address=[addresses(s,'preserve_nonzero')]*3,fill_opacity=F(1,4))
            local=evaluate([s]*3,alpha,3,1,fx,self.ink,**kw);resolved=evaluate([s]*3,alpha,3,1,fx,self.ink,back=[b]*3,back_alpha=[F(1)]*3,**kw)
            for row,(p,a),(r,_) in zip(self.values(d),local,resolved):
                conditional=[(v-(1-a)*bg)/a for v,bg in zip(r,b)];expected,_=over(b,F(1),conditional,a*F(5,8),[True]*5,mode);self.assertValues(row,expected,3e-12)

    def test_nonmonotone_effect_footprint_contains_actual_alpha_in_knockout(self):
        d,alpha=self.scene(1,1);b=self.colors['p'];s=self.colors['b'];d['items']=[fill('back',named('p'),box=(0,0,1,1)),group('outer',False),fill('previous',named('p',opacity=.5),box=(0,0,1,1),parent='outer'),group('art',True,False,parent='outer',fill_opacity=0,opacity=.625),fill('source',named('b',opacity=.75),box=(0,0,1,1),parent='art',opacity=.25)]
        fx=[effect('overlay','overlay',named('s'))];fx[0]['contour']=[[0,0],[.25,1],[1,0]];actual=copy.deepcopy(fx);actual[0]['color']['swatch']='s-alias';d['items'][3]['effects']=actual
        p,a=evaluate([s],[F(3,16)],1,1,fx,self.ink,fill_opacity=F(0))[0];shape=evaluate([s],[F(3,4)],1,1,fx,self.ink)[0][1];shape=max(shape,a)
        expected=partition((b,F(1)),(b,F(1)),[v/a for v in p],shape,a*F(5,8)/shape,[True]*5)[0];self.assertValues(self.values(d)[0],expected)

    def test_disabled_effects_preserve_arithmetic_and_do_not_allocate_spot_planes(self):
        d,alpha=self.scene(3,1);a=self.planes(d);fx=[effect('disabled','shadow',named('s'),sigma=16,offset=[0,0])];fx[0]['enabled']=False
        changed=self.apply_fx(d,fx);b=self.planes(changed);self.assertEqual(a['interleaved_sha256'],b['interleaved_sha256']);self.assertEqual(len(b['plates']),4)

    def test_shared_paint_colors_are_converted_before_native_decoration(self):
        lo,hi=[240,40,90,128],[20,190,220,255];stops=[dict(offset=0,color=lo),dict(offset=1,color=hi)]
        cases=[(dict(type='linear',start=[0,0],end=[4,0],stops=stops),[F(1,8),F(3,8),F(5,8),F(7,8)]),(dict(type='radial',center=[2,.5],radius=2,stops=stops),[F(3,4),F(1,4),F(1,4),F(3,4)]),(dict(type='freeform',anchors=[dict(point=[.5,.5],color=lo),dict(point=[3.5,.5],color=hi)]),[F(0),F(1,5),F(4,5),F(1)]),(dict(type='pattern',width=2,height=1,rgba_hex=bytes(lo+hi).hex()),[F(0),F(1),F(0),F(1)])]
        for paint,amounts in cases:
            d=self.document(4,1,kind='vector');d['items']=[rect('art',named('b'),box=(0,0,4,1),transform=[-1,0,0,1,4,0],fill_opacity=0,effects=[effect('overlay','overlay',paint)])]
            for row,t in zip(self.values(d),reversed(amounts)):
                rgba=[F(a,255)*(1-t)+F(b,255)*t for a,b in zip(lo,hi)];self.assertValues(row,[v*float(rgba[3]) for v in process(list(map(float,rgba[:3])))],5e-5)

    def test_profiled_float_image_alpha_remains_continuous_through_effects(self):
        alpha=[F(0),F(1,8),F(3,8),F(5,8),F(1)];rgb=[.25,.5,.75];d,_=self.scene(5,1)
        fx=[effect('shadow','shadow',named('s',opacity=.625),sigma=.5,offset=[.5,0]),effect('stroke','stroke',named('p',opacity=.375),radius=1,position='outside')];actual=copy.deepcopy(fx);actual[0]['color']['swatch']='s-alias'
        d['items']=[layer([v for a in alpha for v in rgb+[float(a)]],depth='f32',w=5,effects=actual,fill_opacity=.375)]
        for gamma in [None,2]:
            if gamma:d['items'][0]['content']['grid'].update(encoding='profiled_rgb',profile=embedded(linear_profile(gamma=gamma)))
            original=copy.deepcopy(d);source=[F(v) for v in process(rgb,gamma=gamma)]+[F(0)]
            expected=evaluate([source]*5,alpha,5,1,fx,self.ink,fill_opacity=F(3,8))
            for row,(p,a) in zip(self.values(d),expected):self.assertValues(row,p,5e-5)
            self.assertEqual(d,original)

    def test_clipped_member_effects_then_base_effects_masks_and_dissolve(self):
        d,_=self.scene(8,1);b=self.colors['p'];s=self.colors['b'];top=[F(0)]*4+[F(3,4)]
        base_fx=[effect('base-overlay','overlay',named('p',opacity=.375))]
        clip_fx=[effect('clip-shadow','shadow',named('p',opacity=.5),sigma=0,offset=[1,0])]
        d['items']=[fill('back',named('p'),box=(0,0,8,1)),fill('base',named('b',opacity=.5),box=(0,0,8,1),fill_opacity=.25,opacity=.625,mask=dict(width=8,height=1,gray_hex='ad'*8),coverage=dict(type='dissolve',seed=23),effects=base_fx),fill('clip',named('s-alias',opacity=.75,overprint='preserve'),box=(0,0,8,1),clip_to='base',effects=clip_fx,fill_opacity=.5)]
        clipped=evaluate([top]*8,[F(3,4)]*8,8,1,clip_fx,self.ink,back=[s]*8,back_alpha=[F(1)]*8,fill_opacity=F(1,2),source_address=[addresses(top,'preserve',True)]*8)
        local=evaluate([p for p,a in clipped],[F(1,2)]*8,8,1,base_fx,self.ink,fill_opacity=F(1,4))
        for x,(row,(p,a)) in enumerate(zip(self.values(d),local)):
            active=F(a*F(5,8)*F(173,255)>threshold(23,x,0));expected=[active*v/a+(1-active)*bg for v,bg in zip(p,b)];self.assertValues(row,expected)

    def test_opaque_background_decoration_precedes_matte_and_clipping(self):
        for mode in ['normal','multiply','screen','color']:
            d,_=self.scene(4,1);fx=[effect('shadow','shadow',named('s-alias',opacity=.625,overprint='preserve'),sigma=0,offset=[1,0])]
            d['items']=[raster([[20,70,210,128]]*2,2,transform=[1,0,0,1,1,0],effects=fx,fill_opacity=.25,opacity=.625,blend=mode),fill('clip',named('p',opacity=.375),box=(0,0,4,1),clip_to='pixels')];d['background']=dict(item_id='pixels',matte=[230,190,140])
            converted=self.edit(d,[dict(op='background',id='pixels',action=dict(type='to_layer',source_id='retained',matte_id='paper'))])
            self.assertEqual(self.planes(d)['interleaved_sha256'],self.planes(converted)['interleaved_sha256'])

    def test_selected_artboard_bleed_scale_and_saved_light_keep_native_effects(self):
        d=self.document(8,3,kind='vector');d['global_light']=dict(azimuth=180)
        d['items']=[dict(id='board',transform=[1,0,0,1,4,0],content=dict(type='frame',frame=dict(role='artboard',width=4,height=3,bleed=dict(left=1,right=1,top=1,bottom=1)))),rect('art',named('b'),box=(1,1,1,1),parent='board',fill_opacity=0,effects=[effect('light','lit_shadow',named('s',tint=.75,opacity=.5),distance=1,sigma=0)])]
        for scale in [1,2,4]:
            points=[[x,y] for y in [0,2*scale,3*scale] for x in range(6*scale)]
            # The inspection contract accepts at most 64 explicit samples.
            points=points[:64];p=self.planes(d,artboard_id='board',include_bleed=True,raster_scale=scale,samples=points)
            self.assertEqual((p['width'],p['height']),(6*scale,5*scale))
            for (x,y),sample in zip(points,p['samples']):self.assertValues(sample['ink_fractions'],[0,0,0,0,F(3,8) if 3*scale<=x<4*scale and 2*scale<=y<3*scale else 0])

    def test_active_effect_work_limits_and_cancelled_publication_preserve_inputs(self):
        d=self.document(512,512,kind='vector');d['items']=[rect('art',named('b'),box=(0,0,512,512),effects=[dict(effect('edge','stroke',named('s'),radius=32),enabled=False)])]
        before=copy.deepcopy(d);self.planes(d);d['items'][0]['effects'][0]['enabled']=True;self.assertEqual(self.planes(d,1)['code'],'RESOURCE_LIMIT')
        with tempfile.TemporaryDirectory() as root:
            output=dict(output_root=root,file_name='cancelled.pdf',format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()),spot_fallback='multiplicative_declared')))
            error=self.invoke(dict(command='document.publish',document=d,output=output,control=dict(timeout_ms=0)),1);self.assertEqual(error['code'],'TIMEOUT');self.assertFalse((Path(root)/'cancelled.pdf').exists())
        d['items'][0]['effects'][0]['enabled']=False;self.assertEqual(d,before)

    def test_source_preserving_effect_edits_undo_redo_retry_and_PDF_delivery(self):
        d,alpha=self.scene(8,4);fx=[effect('shadow','lit_shadow',named('s',opacity=.625),distance=1,sigma=.5)];d=self.apply_fx(d,fx,fill_opacity=.25);d=self.invoke(dict(command='document.validate',document=d));original=copy.deepcopy(d)
        c=Client();c.initialize();self.addCleanup(c.close)
        with tempfile.TemporaryDirectory() as root:
            s=dict(session_root=str(Path(root)/'sessions'),session_id='native-effects');c.success('session.create',**s,request_id='create',document=d);before=self.planes(d)
            request=dict(request_id='light',expected_revision=0,action=dict(type='edit',operations=[dict(op='global_light',light=dict(azimuth=90)),dict(op='effects_scale',ids=['art'],factor=.5)]))
            changed=c.success('session.apply',**s,**request)['document'];after=self.planes(changed);self.assertNotEqual(before['interleaved_sha256'],after['interleaved_sha256'])
            artifact=self.export(changed);self.assertEqual(hashlib.sha256(page_image(pdf_reader.Pdf(artifact))[1]).hexdigest(),after['interleaved_sha256'])
            undone=c.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.planes(undone)['interleaved_sha256'],before['interleaved_sha256'])
            c.success('session.apply',**s,request_id='redo',expected_revision=2,action=dict(type='redo'));self.assertTrue(c.success('session.apply',**s,**request)['replayed']);self.assertTrue(c.success('session.verify',**s)['valid']);self.assertEqual(d,original)

    def test_capability_and_plane_PDF_effect_receipts_agree(self):
        d,_=self.scene(8,4);d=self.apply_fx(d,[effect('outline','stroke',named('s'),radius=1)])
        caps=self.invoke(dict(command='capabilities'))['native_prepress'];p=self.planes(d);a=self.export(d)
        self.assertNotIn('effects',caps['unsupported']);self.assertEqual(caps['effects']['operators'],['shadow','lit_shadow','stroke','overlay'])
        self.assertEqual(caps['effects'],p['coverage_sources']['effects']);self.assertEqual(p['coverage_sources'],a['pages'][0]['coverage_sources'])


if __name__=='__main__':unittest.main()
