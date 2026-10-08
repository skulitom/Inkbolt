"""Exact scalar algebra, original connectivity fixtures and edge-quality contracts."""
import base64
import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import test_editing_cli as editing
from test_mcp import Client


def plane(w, h, values):
    return dict(width=w, height=h, gray_hex=bytes(values).hex())


def calc(id, source, **kw):
    return dict(op='channel_calculate', id=id, name='Saved '+id,
                calculation=dict(type='copy', source=source), **kw)


def rounded(value):
    return (value.numerator*2+value.denominator)//(2*value.denominator)


class ChannelsSelectionTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke

    def document(self, w=8, h=6, pixels=None, kind='raster'):
        d=self.invoke(dict(command='document.create', id='channels-fixture', kind=kind, width=w, height=h))
        if pixels is not None:
            d=self.edit(d,[dict(op='add',item=dict(id='pixels',content=dict(type='raster',width=w,height=h,rgba_hex=bytes(v for p in pixels for v in p).hex())))])
        return d

    def edit(self,d,ops,expected=0,**kw):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops,**kw),expected)
        return r if expected else r['document']

    def png(self,d):
        r=self.invoke(dict(command='document.export',document=d,format='png'))
        return base64.b64decode(r['data'])

    def values(self,d,id=None):
        return bytes.fromhex((d['channels'][id]['plane'] if id else d['selection'])['gray_hex'])

    def test_named_alpha_save_load_combine_identity_and_nonprinting_exports(self):
        values=bytes([0,1,31,64,127,128,254,255]*6)
        for kind in ('raster','vector'):
            d=self.document(kind=kind);before=self.png(d)
            d=self.edit(d,[dict(op='selection_set',selection=plane(8,6,values)),calc('region',dict(type='selection'))])
            self.assertEqual(self.values(d,'region'),values)
            self.assertEqual(d['channels']['region']['role'],dict(type='alpha'))
            self.assertEqual(self.png(d),before)
            cleared=self.edit(d,[dict(op='selection_set',selection=None)])
            loaded=self.edit(cleared,[dict(op='channel_load',id='region')])
            self.assertEqual(self.values(loaded),values)
            for mode in ('add','subtract','intersect'):
                base=self.edit(loaded,[dict(op='selection_invert')])
                result=self.edit(base,[dict(op='channel_load',id='region',combine=mode)])
                expected=[max(255-v,v) if mode=='add' else max(0,255-2*v) if mode=='subtract' else min(255-v,v) for v in values]
                self.assertEqual(self.values(result),bytes(expected))
            info=self.invoke(dict(command='document.inspect',document=d))['channels'][0]
            self.assertEqual((info['id'],info['name'],info['nonprinting']),('region','Saved region',True))
            self.assertEqual(info['coverage']['sha256'],hashlib.sha256(values).hexdigest())
            snapshot=self.invoke(dict(command='document.export',document=d,format='snapshot'))
            self.assertEqual(self.invoke(dict(command='document.validate',document=json.loads(snapshot['data']))),d)
            removed=self.edit(d,[dict(op='channel_remove',id='region')]);self.assertNotIn('channels',removed)
            diff=self.invoke(dict(command='document.diff',before=d,after=removed,compare_pixels=True))
            self.assertEqual(diff['rendered_pixels']['changed_pixels'],0)
            self.assertEqual([v['field'] for v in diff['metadata']],['channels'])

    def test_all_scalar_calculations_exhaustive_byte_pairs_and_inversion(self):
        a=bytes(x for y in range(256) for x in range(256));b=bytes(y for y in range(256) for x in range(256))
        d=self.document(256,256)
        d=self.edit(d,[dict(op='channel_put',id=id,channel=dict(name=id,plane=plane(256,256,values))) for id,values in [('a',a),('b',b)]])
        functions={
            'add':lambda a,b:min(255,a+b),'subtract':lambda a,b:max(0,a-b),
            'difference':lambda a,b:abs(a-b),'multiply':lambda a,b:rounded(Fraction(a*b,255)),
            'screen':lambda a,b:255-rounded(Fraction((255-a)*(255-b),255)),
            'minimum':min,'maximum':max,'average':lambda a,b:rounded(Fraction(a+b,2)),
        }
        for mode,f in functions.items():
            for inverted in (False,True):
                result=self.edit(d,[dict(op='channel_calculate',id='result',name='Result',calculation=dict(type='combine',left=dict(type='channel',id='a'),right=dict(type='channel',id='b'),mode=mode,invert_left=inverted,invert_right=not inverted))])
                self.assertEqual(self.values(result,'result'),bytes(f(255-x if inverted else x,y if inverted else 255-y) for x,y in zip(a,b)),mode)
        inverse=self.edit(d,[dict(op='channel_calculate',id='a',name='Inverted',replace_existing=True,calculation=dict(type='copy',source=dict(type='channel',id='a'),invert=True))])
        self.assertEqual(self.values(inverse,'a'),bytes(255-v for v in a))
        self.assertEqual(self.values(d,'a'),a)

    def test_component_isolation_reads_composite_rgba_and_encoded_luma(self):
        pixels=[(x,255-x,(x*17)%256,[0,1,79,255][x%4]) for x in range(256)]
        d=self.document(32,8,pixels)
        rendered=editing.png_pixels(self.png(d))[2]
        rgba=list(zip(*[iter(rendered)]*4))
        d=self.edit(d,[calc(c,dict(type='component',component=c)) for c in ('red','green','blue','alpha','luma')])
        for c,index in [('red',0),('green',1),('blue',2),('alpha',3)]:
            self.assertEqual(self.values(d,c),bytes(p[index] for p in rgba))
        expected=bytes(rounded(Fraction(2126*r+7152*g+722*b,10000)) for r,g,b,a in rgba)
        self.assertEqual(self.values(d,'luma'),expected)
        # Sampling the latest candidate includes edits earlier in this same atomic batch.
        adjusted=self.edit(d,[dict(op='pixel_fill',id='pixels',rect=dict(x=0,y=0,width=32,height=8),color=[17,44,88,255]),calc('latest',dict(type='component',component='green'))])
        self.assertEqual(self.values(adjusted,'latest'),bytes([44])*256)

    def test_spot_identity_tint_bytes_previews_and_explicit_replacement(self):
        values=bytes([0,1,64,128,200,254,255,17]*6)
        role=dict(type='spot',ink_id='ocean-ink',alternate_srgb=[12,80,170])
        d=self.document();before=self.png(d)
        d=self.edit(d,[dict(op='channel_put',id='plate',channel=dict(name='Ocean ink',role=role,plane=plane(8,6,values)))])
        for display in ('gray','ink'):
            result=self.invoke(dict(command='channel.export',document=d,id='plate',display=display))
            raw=editing.png_pixels(base64.b64decode(result['data']))[2]
            expected=bytes(c for v in values for c in ((v,v,v,255) if display=='gray' else (12,80,170,v) if v else (0,0,0,0)))
            self.assertEqual(raw,expected);self.assertEqual(result['role'],role)
            self.assertEqual(result['coverage_sha256'],hashlib.sha256(values).hexdigest())
            self.assertIn('not inside PNG',result['fidelity'])
        self.assertEqual(self.png(d),before)
        error=self.edit(d,[calc('collision',dict(type='constant',value=255),role=role)],1)
        self.assertEqual(error['code'],'INVALID_DOCUMENT')
        self.assertEqual(self.edit(d,[calc('plate',dict(type='constant',value=0))],1)['code'],'INVALID_OPERATION')
        replaced=self.edit(d,[calc('plate',dict(type='constant',value=0),replace_existing=True)])
        self.assertEqual(replaced['channels']['plate']['role'],dict(type='alpha'))
        self.assertEqual(self.values(replaced,'plate'),bytes(48))
        self.assertEqual(self.invoke(dict(command='channel.export',document=replaced,id='plate',display='ink'),1)['code'],'INVALID_REQUEST')

    def test_color_range_exact_distance_feather_targets_and_alpha_policy(self):
        pixels=[(x,x//2,255-x,[0,1,128,255][x%4]) for x in range(256)]
        d=self.document(32,8,pixels);rgba=list(zip(*[iter(editing.png_pixels(self.png(d))[2])]*4))
        colors=[[100,50,155,255],[200,100,55,128]]
        for components in ('rgb','rgba'):
            for tolerance,feather in ((0,0),(18,0),(18,37),(240,100)):
                result=self.edit(d,[dict(op='selection_sample',method=dict(type='color_range',colors=colors,tolerance=tolerance,feather=feather,components=components))])
                expected=[]
                for p in rgba:
                    delta=min(max(abs(p[c]-q[c]) for c in range(3 if components=='rgb' else 4)) for q in colors)
                    value=255 if delta<=tolerance else 0 if feather==0 else min(255,max(0,rounded(Fraction(255*(tolerance+feather-delta),feather))))
                    expected.append(value)
                self.assertEqual(self.values(result),bytes(expected))
                self.assertEqual(self.png(result),self.png(d))

    def test_connected_four_eight_islands_multiseed_and_no_color_drift(self):
        pixels=[(255,0,0,255) if (x+y)%2==0 else (0,0,255,255) for y in range(6) for x in range(8)]
        d=self.document(pixels=pixels)
        for connectivity in ('four','eight'):
            result=self.edit(d,[dict(op='selection_sample',method=dict(type='connected',seeds=[[0,0]],tolerance=0,connectivity=connectivity))])
            self.assertEqual(self.values(result),bytes(255 if (i==0 if connectivity=='four' else (i%8+i//8)%2==0) else 0 for i in range(48)))
        result=self.edit(d,[dict(op='selection_sample',method=dict(type='connected',seeds=[[0,0],[2,2],[2,2]],tolerance=0))])
        self.assertEqual(self.values(result),bytes(255 if i in (0,18) else 0 for i in range(48)))
        # Neighbor colors change gradually, but the criterion stays relative to fixed seed colors.
        ramp=self.document(16,1,[(x*16,0,0,255) for x in range(16)])
        result=self.edit(ramp,[dict(op='selection_sample',method=dict(type='connected',seeds=[[0,0]],tolerance=32,feather=32))])
        self.assertEqual(self.values(result),bytes([255,255,255,128]+[0]*12))
        bridged=self.edit(ramp,[dict(op='selection_sample',method=dict(type='connected',seeds=[[0,0],[5,0]],tolerance=32,feather=32))])
        self.assertEqual(self.values(bridged),bytes([255]*8+[128]+[0]*7))

    def test_edge_refinement_fractional_reference_preserves_boundaries_and_repairs_errors(self):
        w,h=8,6;pixels=[(0,0,0,255) if x<4 else (255,255,255,255) for y in range(h) for x in range(w)]
        truth=[255 if x<4 else 0 for y in range(h) for x in range(w)]
        original=truth[:];original[2*w+2]=0;original[3*w+5]=255
        d=self.document(w,h,pixels);d=self.edit(d,[dict(op='selection_set',selection=plane(w,h,original))])
        for radius,tolerance,black,white in ((0,0,0,255),(1,0,0,255),(2,0,32,224),(2,255,0,255)):
            result=self.edit(d,[dict(op='selection_sample',method=dict(type='edge',radius=radius,tolerance=tolerance,black=black,white=white))])
            expected=[]
            for i,p in enumerate(pixels):
                x,y=i%w,i//w
                neighbors=[(j,(radius+1-abs(j%w-x))*(radius+1-abs(j//w-y))) for j,q in enumerate(pixels) if abs(j%w-x)<=radius and abs(j//w-y)<=radius and max(abs(a-b) for a,b in zip(p,q))<=tolerance]
                mean=Fraction(sum(original[j]*weight for j,weight in neighbors),sum(weight for _,weight in neighbors))
                expected.append(min(255,max(0,rounded((mean-black)*255/(white-black)))))
            self.assertEqual(self.values(result),bytes(expected))
            if black==32:
                self.assertLess(sum(abs(a-b) for a,b in zip(expected,truth)),sum(abs(a-b) for a,b in zip(original,truth)))
            if radius==1:
                # Reduce each local defect without crossing the known vertical image boundary.
                self.assertGreater(expected[2*w+2],original[2*w+2]);self.assertLess(expected[3*w+5],original[3*w+5])
                self.assertEqual([expected[y*w+3] for y in (0,5)],[255,255])
                self.assertEqual([expected[y*w+4] for y in (0,5)],[0,0])
        for v in (0,73,255):
            full=self.edit(d,[dict(op='selection_set',selection=plane(w,h,[v]*(w*h))),dict(op='selection_sample',method=dict(type='edge',radius=3,tolerance=0))])
            self.assertEqual(self.values(full),bytes([v])*(w*h))

    def test_sessions_mcp_channels_selection_spot_undo_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            args=dict(session_root=str(Path(temp)/'sessions'),session_id='channel-session')
            d=self.document(8,6,[(x*30,y*40,20,255) for y in range(6) for x in range(8)])
            before=self.png(d);role=dict(type='spot',ink_id='highlight',alternate_srgb=[255,220,30])
            ops=[dict(op='selection_sample',method=dict(type='color_range',colors=[[60,80,20,255]],tolerance=40,feather=40)),calc('highlight',dict(type='selection'),role=role),dict(op='selection_fill',selected=False),dict(op='channel_load',id='highlight')]
            c=Client()
            try:
                c.initialize();c.success('session.create',**args,request_id='create',document=d)
                result=c.success('session.apply',**args,expected_revision=0,request_id='isolate',action=dict(type='edit',operations=ops))
                saved=result['document'];self.assertEqual(self.values(saved),self.values(saved,'highlight'));self.assertEqual(saved['channels']['highlight']['role'],role)
                exported=c.tool('channel.export',document=saved,id='highlight',display='ink')
                self.assertTrue(any(v['type']=='image' for v in exported['content']))
                error=c.tool('session.apply',**args,expected_revision=1,request_id='bad',action=dict(type='edit',operations=[dict(op='channel_remove',id='highlight'),dict(op='channel_load',id='missing')]))
                self.assertTrue(error['isError']);self.assertEqual(c.success('session.read',**args)['document'],saved)
            finally:c.close()
            c=Client()
            try:
                c.initialize();self.assertEqual(c.success('session.read',**args)['document'],saved)
                undo=c.success('session.apply',**args,expected_revision=1,request_id='undo',action=dict(type='undo'))['document']
                self.assertNotIn('channels',undo);self.assertNotIn('selection',undo);self.assertEqual(self.png(undo),before)
                redo=c.success('session.apply',**args,expected_revision=2,request_id='redo',action=dict(type='redo'))['document']
                self.assertEqual(redo['channels'],saved['channels']);self.assertEqual(redo['selection'],saved['selection']);c.success('session.verify',**args)
            finally:c.close()

    def test_invalid_inputs_budgets_schema_and_absent_selection_fail_explicitly(self):
        d=self.document();saved=copy.deepcopy(d)
        for op in [calc('missing',dict(type='selection')),dict(op='channel_load',id='missing'),dict(op='channel_remove',id='missing'),dict(op='selection_sample',method=dict(type='edge',radius=1,tolerance=0))]:
            self.edit(d,[op],1)
        for method in [dict(type='color_range',colors=[],tolerance=0),dict(type='color_range',colors=[[0,0,0,255]]*33,tolerance=0),dict(type='connected',seeds=[],tolerance=0),dict(type='connected',seeds=[[8,0]],tolerance=0),dict(type='edge',radius=9,tolerance=0),dict(type='edge',radius=1,tolerance=0,black=80,white=80),dict(type='color_range',colors=[[0,0,0,255]],tolerance=256)]:
            self.edit(d,[dict(op='selection_sample',method=method)],1)
        for channel in [dict(name='wrong',plane=plane(1,1,[0])),dict(name='wrong',plane=dict(width=8,height=6,gray_hex='zz'*48)),dict(name='wrong\x01',plane=plane(8,6,[0]*48)),dict(name='wrong',role=dict(type='unknown'),plane=plane(8,6,[0]*48))]:
            self.edit(d,[dict(op='channel_put',id='bad',channel=channel)],1)
        active=self.edit(d,[calc('a',dict(type='constant',value=80))])
        self.assertEqual(self.edit(active,[dict(op='channel_load',id='a',combine='add')],1)['code'],'INVALID_OPERATION')
        for w,h,count in ((128,128,17),(256,256,5)):
            big=self.document(w,h)
            result=self.edit(big,[calc('c'+str(i),dict(type='constant',value=0)) for i in range(count)],1)
            self.assertEqual(result['code'],'RESOURCE_LIMIT')
        large=self.document(512,512)
        large=self.edit(large,[dict(op='selection_fill',selected=True)])
        self.assertEqual(self.edit(large,[dict(op='selection_sample',method=dict(type='edge',radius=8,tolerance=0))],1)['code'],'RESOURCE_LIMIT')
        v1=copy.deepcopy(active);v1['schema_version']=1
        self.invoke(dict(command='document.validate',document=v1),1)
        self.assertEqual(d,saved)

    def test_document_coordinate_channels_mask_pixels_and_artboard_views(self):
        d=self.document(8,6,[(20,80,150,128)]*48)
        values=bytes(255 if 2<=x<6 and 1<=y<5 else 0 for y in range(6) for x in range(8))
        d=self.edit(d,[dict(op='selection_set',selection=plane(8,6,values)),calc('region',dict(type='selection'))])
        d=self.edit(d,[dict(op='transform',id='pixels',matrix=[1,0,0,1,1,0]),dict(op='selection_set',selection=None),dict(op='channel_load',id='region'),dict(op='mask_from_selection',id='pixels',linked=False)])
        actual=editing.png_pixels(self.png(d))[2]
        self.assertEqual(actual,bytes(c for v in values for c in ((20,80,150,128) if v else (0,0,0,0))))
        from test_boards_cli import BoardCliTests
        for kind in ('raster','vector'):
            b=BoardCliTests().fixture(kind)
            before=self.invoke(dict(command='artboard.export',document=b,format='png',include_bleed=True))
            b=self.edit(b,[calc('plate',dict(type='constant',value=173),role=dict(type='spot',ink_id='proof',alternate_srgb=[40,90,120]))])
            saved=copy.deepcopy(b)
            after=self.invoke(dict(command='artboard.export',document=b,format='png',include_bleed=True))
            self.assertEqual(after['artifacts'],before['artifacts'])
            if kind=='vector':
                svg=self.invoke(dict(command='document.export',document=b,format='svg'))
                self.assertTrue(any('named-ink channels' in v for v in svg['losses']))
            self.assertEqual(b,saved)


if __name__=='__main__':unittest.main()
