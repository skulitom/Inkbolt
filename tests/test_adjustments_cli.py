"""Independent tone ramps, integer measurements and contextual layer-compositing evidence."""
import base64
import copy
from decimal import Decimal, localcontext
from fractions import Fraction as F
import json
import tempfile
import unittest
import test_editing_cli as editing
from test_mcp import Client


def byte(v):
    return int(max(0,min(1,v))*255+F(1,2))


def rgba(values):
    return bytes(v for p in values for v in p)


class AdjustmentCliTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke

    def document(self,w=256,h=1):return self.invoke(dict(command='document.create',id='tone-fixture',kind='raster',width=w,height=h))
    def edit(self,d,ops,expected=0):
        result=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops),expected)
        return result if expected else result['document']
    def layer(self,operators,id='adjust',clipped=False,clip_to=None,**kw):return dict(id=id,content=dict(type='adjustment',adjustment=dict(operators=operators,clip_to=clip_to or ('source' if clipped else None))),**kw)
    def pixels(self,d):return editing.png_pixels(base64.b64decode(self.invoke(dict(command='document.export',document=d,format='png'))['data']))[2]
    def saved(self,d):return self.invoke(dict(command='document.validate',document=json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data'])))
    def source(self,values,width=None):
        width=width or len(values);d=self.document(width,len(values)//width)
        return self.edit(d,[dict(op='add',item=dict(id='source',content=dict(type='raster',width=width,height=len(values)//width,rgba_hex=rgba(values).hex())))])
    def adjusted(self,d,ops,**kw):
        if kw.get('clipped') and 'clip_to' not in kw:
            kw['clip_to']=next(i['id'] for i in reversed(d['items']) if i.get('parent')==kw.get('parent') and i['content']['type']!='adjustment')
        return self.edit(d,[dict(op='add',item=self.layer(ops,**kw))])
    def measure(self,d,**options):return self.invoke(dict(command='document.measure',document=d,options=options))

    def assert_quantized(self,actual,ideal):
        """Exact reference except mathematical half-byte ties may choose either neighbor.

        Decimal JSON parameters are f64 approximations; only exact rational ties
        permit one byte ambiguity, not arbitrary per-channel error.
        """
        self.assertEqual(len(actual),len(ideal))
        for n,(a,v) in enumerate(zip(actual,ideal)):
            scaled=max(0,min(1,v))*255
            allowed=[byte(v)]
            if scaled.denominator==2:allowed.append(int(scaled))
            self.assertIn(a,allowed,(n,a,v,allowed))

    def test_basic_tone_ramps_invert_threshold_levels_and_posterize_declared_rounding(self):
        values=[(i,255-i,(i*37)%256,255) for i in range(256)];d=self.source(values)
        cases=[
            (dict(type='invert'),lambda p:[255-v for v in p[:3]]),
            (dict(type='threshold',level=0.5),lambda p:[255 if 2126*p[0]+7152*p[1]+722*p[2]>=1275000 else 0]*3),
        ]
        for levels in (2,3,7,16,256):
            cases.append((dict(type='posterize',levels=levels),lambda p,n=levels-1:[byte(F((2*v*n+255)//510,n)) for v in p[:3]]))
        for op,expected in cases:
            with self.subTest(op=op):
                changed=self.adjusted(d,[op]);self.assertEqual(self.pixels(changed),rgba([expected(p)+[255] for p in values]))
                self.assertEqual(changed['items'][0],d['items'][0]);self.assertEqual(self.pixels(self.saved(changed)),self.pixels(changed))
        self.assertEqual(bytes.fromhex(d['items'][0]['content']['rgba_hex']),rgba(values))
        adjusted=self.adjusted(d,[dict(type='levels',input=[0.2,0.8],gamma=1,output=[0.1,0.9])])
        ideal=[v for p in values for v in [F(1,10)+F(4,5)*max(0,min(1,F(n-51,153))) for n in p[:3]]+[F(1)]]
        self.assert_quantized(self.pixels(adjusted),ideal)

    def test_gamma_levels_and_exposure_match_high_precision_scalar_reference(self):
        values=[(i,(i*17)%256,255-i,a) for i in range(256) for a in (0,1,73,255)]
        d=self.source(values,256)
        def encode(v):return v*Decimal('12.92') if v<=Decimal('0.0031308') else Decimal('1.055')*v**(Decimal(1)/Decimal('2.4'))-Decimal('.055')
        def decode(v):return v/Decimal('12.92') if v<=Decimal('.04045') else ((v+Decimal('.055'))/Decimal('1.055'))**Decimal('2.4')
        with localcontext() as ctx:
            ctx.prec=40
            for stops,offset,gamma in ((1,0,1),(-2,0,1),(0,0.02,1.3),(2,-0.03,0.7)):
                op=dict(type='exposure',stops=stops,offset=offset,gamma=gamma);expected=[]
                for p in values:
                    colors=[]
                    for channel in p[:3]:
                        v=decode(Decimal(channel)/255)*Decimal(2)**stops+Decimal(str(offset));v=max(Decimal(0),min(Decimal(1),v))**(Decimal(1)/Decimal(str(gamma)))
                        colors.append(int(encode(v)*255+Decimal('.5')))
                    expected.append(colors+[p[3]] if p[3] else [0]*4)
                self.assertEqual(self.pixels(self.adjusted(d,[op])),rgba(expected))
            ramp=self.source([(i,i,i,255) for i in range(256)])
            expected=rgba([[int((Decimal(i)/255).sqrt()*255+Decimal('.5'))]*3+[255] for i in range(256)])
            self.assertEqual(self.pixels(self.adjusted(ramp,[dict(type='levels',input=[0,1],gamma=2,output=[0,1])])),expected)

    def test_piecewise_curves_independent_rational_interpolation_and_channel_targeting(self):
        values=[(i,255-i,(i*3)%256,255) for i in range(256)];d=self.source(values)
        points=[[0,0.1],[0.25,0.8],[0.75,0.3],[1,1]];exact=[[F(str(x)),F(str(y))] for x,y in points]
        def curve(v):
            x=F(v,255)
            for (a,b),(c,e) in zip(exact,exact[1:]):
                if a<=x<=c:return byte(b+(x-a)*(e-b)/(c-a))
            raise AssertionError(x)
        for channel in ('rgb','red','green','blue'):
            expected=[[curve(v) if channel=='rgb' or c==('red','green','blue').index(channel) else v for c,v in enumerate(p[:3])]+[255] for p in values]
            out=self.adjusted(d,[dict(type='curve',points=points,channel=channel)])
            self.assertEqual(self.pixels(out),rgba(expected));self.assertEqual(self.saved(out),out)

    def test_brightness_contrast_and_shadow_highlight_weights_match_rational_reference(self):
        values=[(i,255-i,(i*7)%256,255) for i in range(256)];d=self.source(values)
        def shifted(x,a):return x+(1-x)*a if a>=0 else x*(1+a)
        for brightness,contrast in ((F(1,4),F(1,2)),(F(-1,4),F(-1,2)),(F(0),F(0)),(F(1),F(1)),(F(-1),F(-1))):
            slope=F(2)**(int(4*contrast));wanted=rgba([[byte(shifted(max(0,min(1,(F(v,255)-F(1,2))*slope+F(1,2))),brightness)) for v in p[:3]]+[255] for p in values])
            self.assertEqual(self.pixels(self.adjusted(d,[dict(type='brightness_contrast',brightness=float(brightness),contrast=float(contrast))])),wanted)
        for shadows,highlights in ((F(3,4),F(1,2)),(F(-1,2),F(-3,4)),(F(0),F(0))):
            wanted=[]
            for p in values:
                y=F(2126*p[0]+7152*p[1]+722*p[2],2550000);amount=shadows*(1-y)**2-highlights*y*y
                wanted.append([byte(shifted(F(v,255),amount)) for v in p[:3]]+[255])
            out=self.adjusted(d,[dict(type='shadows_highlights',shadows=float(shadows),highlights=float(highlights))])
            self.assertEqual(self.pixels(out),rgba(wanted))

    def test_operator_order_uses_unrounded_colors_alpha_and_identity_controls(self):
        values=[(i,(i*5)%256,255-i,a) for i,a in zip(range(64),([0,1,17,255]*16))];d=self.source(values)
        # Two inverse operators restore all visible source pixels, even at alpha one.
        identity=[dict(type='invert'),dict(type='invert'),dict(type='exposure',stops=0),dict(type='curve',points=[[0,0],[1,1]]),dict(type='brightness_contrast',brightness=0,contrast=0),dict(type='shadows_highlights',shadows=0,highlights=0)]
        self.assertEqual(self.pixels(self.adjusted(d,identity)),self.pixels(d))
        ops=[dict(type='levels',input=[0,1],gamma=1,output=[0.1,0.9]),dict(type='invert')]
        ideal=[v for p in values for v in ([1-(F(1,10)+F(4,5)*F(n,255)) for n in p[:3]]+[F(p[3],255)] if p[3] else [F(0)]*4)]
        self.assert_quantized(self.pixels(self.adjusted(d,ops)),ideal)
        ordered=self.adjusted(d,[dict(type='threshold',level=0.2),dict(type='invert')])
        reversed_doc=self.adjusted(d,[dict(type='invert'),dict(type='threshold',level=0.2)])
        self.assertNotEqual(self.pixels(ordered),self.pixels(reversed_doc))

    def test_adjustment_mask_clip_opacity_and_transform_preserve_every_source_alpha(self):
        values=[(20+x*20,60+y*20,170,(37*x+23*y)%256) for y in range(4) for x in range(8)];d=self.source(values,8)
        mask=bytes([0,64,128,255]*4)
        adjusted=self.adjusted(d,[dict(type='invert')],opacity=0.75,transform=[1,0,0,1,2,0],mask=dict(width=4,height=4,gray_hex=mask.hex()),clip=dict(geometry=dict(shape='rect',x=1,y=1,width=2,height=2)))
        expected=[]
        for i,p in enumerate(values):
            x,y=i%8,i//8;weight=F(3,4)*F(mask[y*4+x-2],255) if 3<=x<5 and 1<=y<3 else 0
            expected.append([byte(F(v,255)+weight*(1-2*F(v,255))) for v in p[:3]]+[p[3]] if p[3] else [0]*4)
        self.assertEqual(self.pixels(adjusted),rgba(expected));self.assertEqual(adjusted['items'][0],d['items'][0]);self.assertEqual(self.saved(adjusted),adjusted)
        hidden=self.edit(adjusted,[dict(op='properties',id='adjust',visible=False)]);self.assertEqual(self.pixels(hidden),self.pixels(d))
        disabled=self.edit(adjusted,[dict(op='mask',id='adjust',mask=dict(width=4,height=4,gray_hex=mask.hex(),enabled=False))]);self.assertNotEqual(self.pixels(disabled),self.pixels(adjusted))

    def test_clipped_adjustment_chain_modifies_only_base_before_blend_and_alpha(self):
        background=(90,120,180,255);d=self.source([background]*24,8)
        source=[(40+x*20,80,160,64+x*32) for x in range(4)]
        d=self.edit(d,[dict(op='add',item=dict(id='base',opacity=0.5,blend='multiply',transform=[1,0,0,1,2,1],content=dict(type='raster',width=4,height=1,rgba_hex=rgba(source).hex())))])
        changed=self.adjusted(d,[dict(type='invert')],clipped=True,opacity=0.5)
        changed=self.adjusted(changed,[dict(type='levels',input=[0,1],gamma=1,output=[0.2,0.6])],id='second',clipped=True)
        expected=[]
        for y in range(3):
            for x in range(8):
                if y==1 and 2<=x<6:
                    p=source[x-2];alpha=F(p[3],510)
                    # Half inversion makes each RGB channel 0.5; levels maps it to 0.4.
                    expected.append([byte(F(b,255)*(1-alpha)+F(2,5)*F(b,255)*alpha) for b in background[:3]]+[255])
                else:expected.append(list(background))
        self.assertEqual(self.pixels(changed),rgba(expected));self.assertEqual(changed['items'][:2],d['items']);self.assertEqual(self.saved(changed),changed)
        hidden=self.edit(changed,[dict(op='properties',id='base',visible=False)]);self.assertEqual(self.pixels(hidden),rgba([background]*24))
        # Removing the base must not silently redirect its clipped adjustments.
        self.assertEqual(self.edit(changed,[dict(op='remove',id='base')],1)['code'],'INVALID_DOCUMENT')

    def test_group_isolation_passthrough_and_clipped_groups_have_declared_scope(self):
        d=self.source([(30,60,90,255)]*8)
        group=dict(id='g',content=dict(type='group',isolated=True))
        d=self.edit(d,[dict(op='add',item=group),dict(op='add',item=dict(id='pixel',parent='g',transform=[1,0,0,1,2,0],content=dict(type='raster',width=2,height=1,rgba_hex='6496c8ff'*2))),dict(op='add',item=self.layer([dict(type='invert')],parent='g'))])
        expected=[(30,60,90,255)]*8;expected[2:4]=[(155,105,55,255)]*2
        self.assertEqual(self.pixels(d),rgba(expected));self.assertEqual(self.edit(d,[dict(op='ungroup',id='g')],1)['code'],'UNSUPPORTED')
        passthrough=self.edit(d,[dict(op='group_options',id='g',isolated=False)])
        expected2=[(225,195,165,255)]*8;expected2[2:4]=expected[2:4];self.assertEqual(self.pixels(passthrough),rgba(expected2))
        clipped=self.adjusted(d,[dict(type='invert')],id='outer',clipped=True)
        expected[2:4]=[(100,150,200,255)]*2;self.assertEqual(self.pixels(clipped),rgba(expected))
        self.assertEqual(self.adjusted_error(passthrough,dict(op='add',item=self.layer([dict(type='invert')],id='invalid',clipped=True)))['code'],'INVALID_DOCUMENT')

    def adjusted_error(self,d,operation):return self.edit(d,[operation],1)

    def test_stable_clipped_bindings_duplicate_reorder_and_adjustment_blends(self):
        d=self.source([(40,80,160,255)]*4)
        d=self.edit(d,[dict(op='group',ids=['source'],new_id='g'),dict(op='add',item=self.layer([dict(type='invert')],parent='g',clip_to='source'))])
        copied=self.edit(d,[dict(op='duplicate',id='g',new_id='g-copy',descendant_ids={'source':'source-copy','adjust':'adjust-copy'})])
        adjustment=next(i for i in copied['items'] if i['id']=='adjust-copy')['content']['adjustment']
        self.assertEqual(adjustment['clip_to'],'source-copy');self.assertEqual(self.pixels(copied),self.pixels(d))
        removed=self.edit(copied,[dict(op='remove',id='g')]);self.assertEqual(self.pixels(removed),self.pixels(d))
        self.assertEqual(self.edit(d,[dict(op='reorder',id='adjust',index=0)],1)['code'],'INVALID_DOCUMENT')
        for blend in ('normal','multiply','screen'):
            source=self.source([(40,80,160,255)]*4)
            adjusted=self.adjusted(source,[dict(type='invert')],blend=blend,opacity=0.25)
            colors=[]
            for v in (40,80,160):
                x=F(v,255);q=1-x
                y=q if blend=='normal' else (x*q if blend=='multiply' else x+q-x*q)
                colors.append(byte(x+F(1,4)*(y-x)))
            self.assertEqual(self.pixels(adjusted),rgba([colors+[255]]*4))
        source=self.source([(10,80,150,255)])
        ordered=self.adjusted(source,[dict(type='threshold',level=0.2)])
        ordered=self.adjusted(ordered,[dict(type='invert')],id='second')
        reordered=self.edit(ordered,[dict(op='reorder',id='second',index=1)])
        self.assertNotEqual(self.pixels(ordered),self.pixels(reordered));self.assertEqual(self.saved(reordered),reordered)

    def test_artboard_adjustments_export_local_masks_and_count_operator_work(self):
        d=self.document(20,12)
        board=dict(id='board',transform=[1,0,0,1,5,3],content=dict(type='frame',frame=dict(role='artboard',width=6,height=4)))
        d=self.edit(d,[dict(op='add',item=board),dict(op='add',item=dict(id='source',parent='board',content=dict(type='raster',width=6,height=4,rgba_hex='2850a0ff'*24))),dict(op='add',item=self.layer([dict(type='invert')],parent='board',clip_to='source',mask=dict(width=3,height=4,gray_hex='ff'*12,linked=False,transform=[1,0,0,1,7,3])))])
        exported=self.invoke(dict(command='artboard.export',document=d,format='png'))['artifacts'][0]['artifact']
        w,h,p=editing.png_pixels(base64.b64decode(exported['data']))[:3]
        self.assertEqual((w,h),(6,4));self.assertEqual(p,rgba([(215,175,95,255) if 2<=x<5 else (40,80,160,255) for y in range(4) for x in range(6)]))
        self.assertEqual(self.saved(d),d)
        big=self.document(1024,1024)
        big=self.edit(big,[dict(op='add',item=dict(id='board',content=dict(type='frame',frame=dict(role='artboard',width=1024,height=1024)))),dict(op='add',item=self.layer([dict(type='curve',points=[[0,0],[1,1]])]*16,parent='board'))])
        self.assertEqual(self.invoke(dict(command='artboard.export',document=big,format='png'),1)['code'],'RESOURCE_LIMIT')

    def test_revised_parameters_order_masks_persistence_locks_and_session_mcp_undo(self):
        client=Client();self.addCleanup(client.close);client.initialize()
        with tempfile.TemporaryDirectory() as root:
            args=dict(session_root=root,session_id='adjustments');d=self.source([(30,80,120,255),(200,150,50,128)])
            client.success('session.create',**args,request_id='create',document=d)
            action=dict(type='edit',operations=[dict(op='add',item=self.layer([dict(type='invert')]))])
            changed=client.success('session.apply',**args,request_id='invert',expected_revision=0,action=action)['document']
            measured=client.success('document.measure',document=changed,options=dict(samples=[[0,0],[1,0]]));self.assertEqual(measured['samples'][0]['rgba'],[225,175,135,255])
            revised=client.success('session.apply',**args,request_id='revise',expected_revision=1,action=dict(type='edit',operations=[dict(op='adjustment',id='adjust',adjustment=dict(operators=[dict(type='posterize',levels=2)]))]))['document']
            self.assertNotEqual(self.pixels(revised),self.pixels(changed));self.assertEqual(revised['items'][0],d['items'][0]);self.assertEqual(self.saved(revised),revised)
            undone=client.success('session.apply',**args,request_id='undo',expected_revision=2,action=dict(type='undo'))['document'];self.assertEqual(self.pixels(undone),self.pixels(changed))
            replay=client.success('session.apply',**args,request_id='revise',expected_revision=1,action=dict(type='edit',operations=[dict(op='adjustment',id='adjust',adjustment=dict(operators=[dict(type='posterize',levels=2)]))]));self.assertEqual(replay['current_revision'],3)
            client.success('session.verify',**args)
            locked=self.edit(changed,[dict(op='group',ids=['source','adjust'],new_id='locked'),dict(op='properties',id='locked',locked=True)])
            self.assertEqual(self.edit(locked,[dict(op='adjustment',id='adjust',adjustment=dict(operators=[dict(type='invert')]))],1)['code'],'LOCKED')

    def test_measurements_histograms_samples_and_statistics_match_all_original_pixels(self):
        values=[(i%16*17,(i*5)%256,255-i,i) for i in range(256)];d=self.source(values,16)
        result=self.measure(d,samples=[[0,0],[15,15],[3,7]])
        rendered=[list(p) if p[3] else [0]*4 for p in values]
        self.assertEqual(result['pixel_count'],256);self.assertEqual(result['total_weight_units'],256*65025);self.assertEqual(result['depth'],8)
        for c,channel in enumerate(result['channels']):
            bins=[0]*256
            for p in rendered:bins[p[c]]+=65025
            self.assertEqual(channel['histogram_weight_units'],bins)
            self.assertEqual(channel['sum_weighted_values'],sum(p[c] for p in rendered)*65025)
            self.assertEqual(channel['sum_weighted_squares'],sum(p[c]**2 for p in rendered)*65025)
            mean=sum(p[c] for p in rendered)/256;self.assertEqual(channel['mean'],mean)
            self.assertAlmostEqual(channel['variance'],sum((p[c]-mean)**2 for p in rendered)/256,places=10)
            self.assertEqual((channel['minimum'],channel['maximum']),(min(p[c] for p in rendered),max(p[c] for p in rendered)))
        for sample in result['samples']:
            x,y=sample['position'];self.assertEqual(sample['rgba'],rendered[y*16+x])
        self.assertEqual(self.saved(d),d);self.assertEqual(self.measure(d),json.loads(json.dumps(self.measure(d))))

    def test_measurements_selection_alpha_region_weights_are_exact_including_empty(self):
        values=[(i*15,200-i*9,100,i*17) for i in range(16)];d=self.source(values,4)
        selection=bytes([0,85,170,255]*4);d=self.edit(d,[dict(op='selection_set',selection=dict(width=4,height=4,gray_hex=selection.hex()))])
        for alpha in ('ignore','exclude_transparent','weight'):
            for use_selection in (False,True):
                options=dict(region=dict(x=0,y=0,width=3,height=4),use_selection=use_selection,alpha=alpha,samples=[[0,0],[2,3]])
                result=self.measure(d,**options);bins=[[0]*256 for _ in range(4)];total=included=0
                for y in range(4):
                    for x in range(3):
                        n=y*4+x;p=list(values[n]) if values[n][3] else [0]*4
                        w=(selection[n] if use_selection else 255)*(p[3] if alpha=='weight' else (0 if alpha=='exclude_transparent' and p[3]==0 else 255));total+=w;included+=w>0
                        for c in range(4):bins[c][p[c]]+=w
                self.assertEqual(result['total_weight_units'],total);self.assertEqual(result['included_pixel_count'],included)
                self.assertEqual([c['histogram_weight_units'] for c in result['channels']],bins)
        empty=self.edit(d,[dict(op='selection_fill',selected=False)]);measured=self.measure(empty,use_selection=True)
        self.assertEqual(measured['total_weight_units'],0)
        for c in measured['channels']:
            for key in ('mean','variance','minimum','maximum'):self.assertIsNone(c[key])
            self.assertEqual(sum(c['histogram_weight_units']),0)
        self.assertEqual(self.pixels(empty),self.pixels(d))

    def test_invalid_adjustments_measurements_and_resource_budgets_fail_atomically(self):
        d=self.source([(20,40,60,255)])
        invalid=[[],[dict(type='posterize',levels=1)],[dict(type='levels',input=[0.5,0.5],gamma=1,output=[0,1])],[dict(type='curve',points=[[0,0],[0,1]])],[dict(type='curve',points=[])],[dict(type='curve',points=[[0.1,0],[1,1]])],[dict(type='exposure',stops=17)],[dict(type='brightness_contrast',brightness=0,contrast=1.1)],[dict(type='shadows_highlights',shadows=-1.1,highlights=0)],[dict(type='invert')]*17]
        for ops in invalid:
            self.assertEqual(self.edit(d,[dict(op='properties',id='source',name='candidate'),dict(op='add',item=self.layer(ops))],1)['operation_index'],1)
        self.assertEqual(d['items'][0]['name'],'')
        empty=self.document(1,1);self.assertEqual(self.edit(empty,[dict(op='add',item=self.layer([dict(type='invert')],clipped=True))],1)['code'],'INVALID_DOCUMENT')
        for options in (dict(use_selection=True),dict(samples=[[1,0]]),dict(samples=[[0,0]]*257),dict(region=dict(x=0,y=0,width=0,height=1)),dict(region=dict(x=0,y=0,width=2**32-1,height=1))):
            self.assertEqual(self.invoke(dict(command='document.measure',document=d,options=options),1)['code'],'INVALID_REQUEST')
        bad=copy.deepcopy(d);bad['depth']=16;self.assertEqual(self.invoke(dict(command='document.measure',document=bad),1)['code'],'INVALID_REQUEST')
        large=self.document(1024,1024)
        large=self.edit(large,[dict(op='add',item=self.layer([dict(type='curve',points=[[0,0],[1,1]])]*16,id=f'adjust{i}')) for i in range(2)])
        self.assertEqual(self.invoke(dict(command='document.render',document=large),1)['code'],'RESOURCE_LIMIT')
        many=self.document(1,1);many=self.edit(many,[dict(op='add',item=self.layer([dict(type='invert')]*16,id=f'adjust{i}')) for i in range(16)])
        self.assertEqual(self.edit(many,[dict(op='add',item=self.layer([dict(type='invert')],id='overflow'))],1)['code'],'RESOURCE_LIMIT')


if __name__=='__main__':unittest.main()
