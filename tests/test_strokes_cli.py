"""Original dash fixtures: periodic interval arithmetic, geometry and transport."""
import base64
import copy
from fractions import Fraction as F
import json
import math
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
from test_mcp import Client


def line(points):
    return dict(shape='path',commands=[dict(verb='move' if i==0 else 'line',to=p) for i,p in enumerate(points)])


def intervals(array,offset,length):
    # Independently enumerate translated periodic intervals, then clip to the line.
    values=[F(str(v)) for v in array]
    if len(values)%2:values*=2
    if not any(values):return [(F(0),F(length))]
    period=sum(values);offset=F(str(offset));out=[];prefix=F(0)
    for i,value in enumerate(values):
        if i%2==0:
            for k in range(math.floor((offset-prefix)/period)-1,math.ceil((length+offset-prefix)/period)+1):
                a,b=k*period+prefix-offset,k*period+prefix+value-offset
                if b>=0 and a<=length:out.append((max(F(0),a),min(F(length),b)))
        prefix+=value
    return sorted(out)


class StrokeCliTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke

    def document(self,geometry=None,array=None,offset=0,**style):
        d=self.invoke(dict(command='document.create',id='dash-fixture',kind='vector',width=40,height=24))
        stroke=dict(color=[30,100,210,255],width=2,**style)
        if array is not None:stroke['dash']=dict(array=array,offset=offset)
        item=dict(id='path',content=dict(type='vector',geometry=geometry or line([[4,8],[36,8]]),stroke=stroke))
        return self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=item)]))['document']

    def pixels(self,d,scale=1):
        r=self.invoke(dict(command='document.export',document=d,format='png',scale=scale))
        w,h,p,_=editing.png_pixels(base64.b64decode(r['data']));return w,h,p

    def test_periodic_dash_pixels_positive_negative_odd_and_wrapped_phase(self):
        for array in ([6,4],[3],[2,3,4],[0,3,4,2],[3,0,2,4]):
            for offset in (-32,-11,0,1,7,32):
                with self.subTest(array=array,offset=offset):
                    d=self.document(array=array,offset=offset)
                    w,h,p=self.pixels(d);on=intervals(array,offset,32)
                    wanted=bytes(v for y in range(h) for x in range(w) for v in (
                        [30,100,210,255] if 7<=y<9 and any(a<=F(2*x+1,2)-4<b for a,b in on) else [0]*4))
                    self.assertEqual(p,wanted)

    def test_empty_zero_patterns_and_entire_gap_are_explicitly_transparent_or_solid(self):
        solid=self.pixels(self.document())
        for array in ([],[0],[0,0],[0,0,0]):
            self.assertEqual(self.pixels(self.document(array=array,offset=-7)),solid)
        for array,offset in (([0,8],0),([2,100],3),([1,100],50)):
            self.assertFalse(any(self.pixels(self.document(array=array,offset=offset))[2]))
        # A curved contour whose entire control polygon fits within the first gap.
        curve=dict(shape='path',commands=[dict(verb='move',to=[4,8]),dict(verb='cubic',control1=[6,3],control2=[8,13],to=[10,8])])
        self.assertFalse(any(self.pixels(self.document(curve,array=[2,100],offset=3))[2]))

    def test_round_and_square_zero_length_dashes_have_caps(self):
        for cap in ('round','square','butt'):
            d=self.document(array=[0,8],cap=cap)
            w,h,p=self.pixels(d,4)
            # A gap reaching the terminal point does not start another zero dash.
            centers=[4,12,20,28]
            for y in range(h):
                for x in range(w):
                    xx,yy=(x+.5)/4,(y+.5)/4
                    distance=min(math.hypot(xx-c,yy-8) for c in centers)
                    square=min(max(abs(xx-c),abs(yy-8)) for c in centers)
                    metric=distance if cap=='round' else square
                    a=p[(y*w+x)*4+3]
                    if cap=='butt' or metric>1.2:self.assertEqual(a,0,(cap,x,y))
                    if cap!='butt' and metric<.8:self.assertEqual(a,255,(cap,x,y))

    def test_closed_seam_is_joined_and_subpath_phase_resets(self):
        d=self.document(dict(shape='rect',x=4,y=4,width=8,height=8),array=[6,4],offset=2)
        w,h,p=self.pixels(d)
        self.assertEqual(p[(3*w+3)*4:(3*w+3)*4+4],bytes([30,100,210,255]))
        g=line([[4,6],[36,6]]);g['commands']+=line([[4,16],[36,16]])['commands']
        d=self.document(g,array=[3,2,1],offset=-5);w,h,p=self.pixels(d)
        self.assertEqual(p[5*w*4:7*w*4],p[15*w*4:17*w*4])

    def test_caps_and_join_miter_limit_on_continuous_dash(self):
        g=line([[4,16],[4,8],[12,8]])
        for cap in ('butt','round','square'):
            for join in ('miter','round','bevel'):
                for limit in (1,4,16):
                    a=self.document(g,cap=cap,join=join,miter_limit=limit)
                    b=self.document(g,array=[40,3],cap=cap,join=join,miter_limit=limit)
                    self.assertEqual(self.pixels(a,2),self.pixels(b,2))
        full=self.pixels(self.document(g,array=[40,3],miter_limit=4))[2]
        short=self.pixels(self.document(g,array=[40,3],miter_limit=1))[2]
        self.assertGreater(sum(full[3::4]),sum(short[3::4]))

    def test_svg_dash_properties_inheritance_units_and_source_preservation(self):
        text='<svg xmlns="http://www.w3.org/2000/svg" width="40" height="24"><g fill="none" stroke="#1e64d2" stroke-width="2" stroke-dasharray="4px, 3pt 2" stroke-dashoffset="-2px"><path id="a" d="M4 8H36"/><path id="b" d="M4 16H36" style="stroke-dasharray: 6 4; stroke-dashoffset:1"/></g></svg>'
        with tempfile.TemporaryDirectory() as root:
            from pathlib import Path
            source=Path(root)/'original.svg';source.write_text(text)
            imported=self.invoke(dict(command='svg.import',id='import-dash',source=dict(kind='file',source_path=str(source))))
            self.assertEqual(source.read_text(),text)
        d=imported['document'];strokes=[i['content']['stroke'] for i in d['items'] if i['content']['type']=='vector']
        self.assertEqual([s['dash'] for s in strokes],[dict(array=[4,4,2],offset=-2),dict(array=[6,4],offset=1)])
        output=self.invoke(dict(command='document.export',document=d,format='svg'))['data']
        nodes=ET.fromstring(output).findall('.//{*}path')
        self.assertEqual([n.get('stroke-dasharray') for n in nodes],['4 4 2','6 4'])
        self.assertEqual([n.get('stroke-dashoffset') for n in nodes],['-2','1'])
        again=self.invoke(dict(command='svg.import',id='reimport-dash',source=dict(kind='text',text=output)))['document']
        self.assertEqual(self.pixels(d,3),self.pixels(again,3))

    def test_invalid_dash_json_svg_and_aggregate_work_limits(self):
        d=self.document();original=copy.deepcopy(d)
        for dash in (dict(array=[-1,2]),dict(array=[.0001,2]),dict(array=[32769,2]),dict(array=[1]*65),dict(array=[1,2],offset=32769),dict(array=[1,2],phase=0)):
            item=copy.deepcopy(d['items'][0]);item['id']='bad';item['content']['stroke']['dash']=dash
            self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='add',item=item)]),1)
        dense=copy.deepcopy(d);dense['items'][0]['content']['stroke']['dash']=dict(array=[.001,.001])
        self.assertEqual(self.invoke(dict(command='document.validate',document=dense),1)['code'],'LIMIT_EXCEEDED')
        for value in ('-1 2','1,,2',',2','1,','1% 2','1 2 nonsense',''):
            text=f'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="24"><g stroke="none" stroke-dasharray="{value}"><rect width="3" height="3"/></g></svg>'
            self.invoke(dict(command='svg.import',id='bad',source=dict(kind='text',text=text)),1)
        self.assertEqual(d,original)

    def test_curves_transforms_gradients_snapshot_and_scale_are_repeatable(self):
        g=dict(shape='path',commands=[dict(verb='move',to=[4,14]),dict(verb='cubic',control1=[8,2],control2=[26,2],to=[32,14])])
        d=self.document(g,array=[3,2],offset=-1,cap='round')
        d['items'][0]['transform']=[-1,0,0,1,40,1]
        d['items'][0]['content']['stroke']['color']=dict(type='linear',start=[4,0],end=[32,0],stops=[dict(offset=0,color=[255,0,0,128]),dict(offset=1,color=[0,0,255,255])])
        before=copy.deepcopy(d)
        snap=json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data'])
        svg=self.invoke(dict(command='document.export',document=d,format='svg'))['data']
        again=self.invoke(dict(command='svg.import',id='curves',source=dict(kind='text',text=svg)))['document']
        for scale in (1,2,4):
            pixels=self.pixels(d,scale);self.assertTrue(any(pixels[2]));self.assertEqual(pixels,self.pixels(snap,scale));self.assertEqual(pixels,self.pixels(again,scale))
        self.assertEqual(d,before)

    def test_mcp_strict_schema_sessions_undo_redo_and_retry_keep_dash_controls(self):
        d=self.document(array=[6,4],offset=-2);changed=copy.deepcopy(d['items'][0]['content']);changed['stroke']['dash']=dict(array=[0,8],offset=2);changed['stroke']['cap']='round'
        client=Client();self.addCleanup(client.close);client.initialize()
        self.assertEqual(client.success('document.render',document=d),self.invoke(dict(command='document.render',document=d)))
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='dash')
            client.success('session.create',**session,request_id='create',document=d)
            args=dict(**session,expected_revision=0,request_id='phase',action=dict(type='edit',operations=[dict(op='vector',id='path',**{k:v for k,v in changed.items() if k!='type'})]))
            edited=client.success('session.apply',**args)
            self.assertTrue(client.success('session.apply',**args)['replayed'])
            state=client.success('session.read',**session)['document']
            self.assertEqual(state,edited['document'])
            self.assertEqual(state['items'][0]['content']['stroke']['dash'],changed['stroke']['dash'])
            undone=client.success('session.apply',**session,expected_revision=state['revision'],request_id='undo',action=dict(type='undo'))['document']
            self.assertEqual(undone['items'][0]['content'],d['items'][0]['content'])
            redone=client.success('session.apply',**session,expected_revision=undone['revision'],request_id='redo',action=dict(type='redo'))['document']
            self.assertEqual(redone['items'][0]['content'],state['items'][0]['content'])
            client.success('session.verify',**session)
        bad=copy.deepcopy(d);bad['items'][0]['content']['stroke']['dash']['phase']=0
        self.assertTrue(client.tool('document.render',document=bad)['isError'])

    def test_document_mask_instances_and_artboard_range_dash_budgets(self):
        d=self.document(array=[.003,.003]);path=d['items'][0]
        many=copy.deepcopy(d);many['items']=[dict(copy.deepcopy(path),id=f'p{i}',visible=False) for i in range(10)]
        error=self.invoke(dict(command='document.validate',document=many),1)
        self.assertEqual(error['code'],'LIMIT_EXCEEDED');self.assertIn('dashing',error['message'])
        source=dict(id='source',content=dict(type='mask_source'));path=copy.deepcopy(path);path['parent']='source'
        def owner(id,parent=None):return dict(id=id,parent=parent,artwork_mask=dict(source='source',region=[0,0,40,24],mode='alpha'),content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=2,height=2),fill=[255]*4))
        masks=copy.deepcopy(d);masks['items']=[source,path]+[owner(f'o{i}') for i in range(12)]
        self.invoke(dict(command='document.validate',document=masks))
        error=self.invoke(dict(command='document.render',document=masks),1)
        self.assertEqual(error['code'],'LIMIT_EXCEEDED');self.assertIn('dashing',error['message'])
        boards=copy.deepcopy(d);boards['items']=[source,path]
        for i in range(24):
            boards['items'] += [dict(id=f'b{i}',content=dict(type='frame',frame=dict(role='artboard',width=2,height=2))),owner(f'o{i}',f'b{i}')]
        self.invoke(dict(command='document.validate',document=boards))
        error=self.invoke(dict(command='artboard.export',document=boards,format='png'),1)
        self.assertEqual(error['code'],'LIMIT_EXCEEDED');self.assertIn('dashing',error['message'])

    def test_mask_artboards_and_overlapping_caps_preserve_single_paint_alpha(self):
        d=self.document(array=[0,1],cap='round');d['items'][0]['content']['stroke']['color']=[30,100,210,128]
        d['items'][0]['opacity']=.5
        w,h,p=self.pixels(d,2)
        self.assertEqual(max(p[3::4]),64)
        source=copy.deepcopy(d['items'][0]);source['id']='dots';source['parent']='source'
        d['items']=[dict(id='source',content=dict(type='mask_source')),source,dict(id='board',content=dict(type='frame',frame=dict(role='artboard',width=40,height=24))),dict(id='ink',parent='board',artwork_mask=dict(source='source',region=[0,0,40,24],mode='alpha'),content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=40,height=24),fill=[30,100,210,255]))]
        self.assertEqual(self.pixels(d,2)[2],p)
        r=self.invoke(dict(command='artboard.export',document=d,format='png',scale=2))
        self.assertEqual(editing.png_pixels(base64.b64decode(r['artifacts'][0]['artifact']['data']))[:3],(w,h,p))

    def test_quadratic_curve_dash_interiors_match_analytic_arc_length(self):
        # x=4+28t, y=8+32t(1-t), expressed as one cubic.
        g=dict(shape='path',commands=[dict(verb='move',to=[4,8]),dict(verb='cubic',control1=[4+28/3,8+32/3],control2=[4+56/3,8+32/3],to=[32,8])])
        d=self.document(g,array=[5,4],offset=-1);w,h,p=self.pixels(d,4)
        primitive=lambda u:(u*math.hypot(28,u)+28**2*math.asinh(u/28))/2
        def point(t):return 4+28*t,8+32*t*(1-t)
        checked=[0,0]
        for y in range(h):
            for x in range(w):
                xx,yy=(x+.5)/4,(y+.5)/4
                lo,hi=0.,1.
                def distance(t):
                    a,b=point(t);return (a-xx)**2+(b-yy)**2
                for _ in range(32):
                    a,b=(2*lo+hi)/3,(lo+2*hi)/3
                    if distance(a)<distance(b):hi=b
                    else:lo=a
                t=(lo+hi)/2
                if not .05<t<.95 or distance(t)>.5**2:continue
                length=(primitive(32)-primitive(32-64*t))/64
                phase=(length-1)%9
                if 1<phase<4:
                    self.assertEqual(p[(y*w+x)*4+3],255,(x,y,length));checked[0]+=1
                if 6<phase<8:
                    self.assertEqual(p[(y*w+x)*4+3],0,(x,y,length));checked[1]+=1
        self.assertTrue(all(n>30 for n in checked),checked)

    def test_zero_length_contours_and_initial_dash_boundary_caps(self):
        for cap in ('butt','round','square'):
            for offset in (0,4,5):
                d=self.document(line([[12,8],[12,8]]),array=[4,4],offset=offset,cap=cap)
                w,h,p=self.pixels(d,2)
                if offset==5 or cap=='butt':self.assertFalse(any(p))
                else:self.assertEqual(p[(16*w+24)*4+3],255)
            # At phase four the first painted interval terminates at the origin.
            d=self.document(array=[4,4],offset=4,cap=cap)
            w,h,p=self.pixels(d,2)
            self.assertEqual(p[(16*w+7)*4+3],0 if cap=='butt' else 255)

    def test_diagonal_boundary_square_cap_inspection_diff_and_locks(self):
        for cap in ('round','square'):
            d=self.document(line([[12,12],[18,18]]),array=[4,4],offset=4,cap=cap)
            d['items'][0]['content']['stroke']['width']=4
            w,h,p=self.pixels(d,4)
            # This whole pixel is inside the tangent-oriented square and outside
            # the circular cap; the first nonzero dash is still four units away.
            self.assertEqual(p[(38*w+48)*4+3],255 if cap=='square' else 0)
        info=self.invoke(dict(command='document.inspect',document=d))
        self.assertEqual(info['items'][0]['stroke'],d['items'][0]['content']['stroke'])
        changed=copy.deepcopy(d);changed['items'][0]['content']['stroke']['dash']['offset']=0
        diff=self.invoke(dict(command='document.diff',before=d,after=changed,compare_pixels=True))
        self.assertIn('content.stroke',diff['items'][0]['fields']);self.assertTrue(diff['changed'])
        d['items'][0]['locked']=True
        operation=dict(op='vector',id='path',**{k:v for k,v in changed['items'][0]['content'].items() if k!='type'})
        error=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[operation]),1)
        self.assertEqual(error['code'],'LOCKED')


if __name__=='__main__':unittest.main()
