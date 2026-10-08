"""Independent world geometry, winding, pixel area and persistent region workflows."""
import base64
import copy
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
import test_paths_cli as paths
import test_booleans_cli as booleans
from test_selections_cli import polygon_area_in_pixel, rect
from test_mcp import Client


def work(g, id='region', **kw):
    return dict(id=id, content=dict(type='work_path', geometry=g, fill_rule='nonzero'), **kw)


def path(commands):return dict(shape='path', commands=commands)
def region(x,y,w,h):return path(paths.rectangle_path(x,y,w,h))
def mapped(m,p):return [m[0]*p[0]+m[2]*p[1]+m[4],m[1]*p[0]+m[3]*p[1]+m[5]]


def parabola_pixel_area(x,y):
    # Independently integrate in x; the implementation samples horizontal rows.
    lo,hi=max(2,x),min(14,x+1);bottom,top=max(2,y),min(14,y+1)
    if hi<=lo or top<=bottom:return 0
    a=2+(12*(bottom-2))**.5;b=2+(12*(top-2))**.5
    full=max(0,min(hi,a)-lo)*(top-bottom)
    left,right=max(lo,a),min(hi,b)
    primitive=lambda v:(top-2)*v-(v-2)**3/36
    return full+(primitive(right)-primitive(left) if right>left else 0)


class WorkPathTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,w=24,h=20,kind='raster'):
        return self.invoke(dict(command='document.create',id='work-path-fixture',kind=kind,width=w,height=h))
    def edit(self,d,ops,expected=0):
        result=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops),expected)
        return result if expected else result['document']
    def add(self,d,items):return self.edit(d,[dict(op='add',item=i) for i in items])
    def select(self,d,id='region',**kw):return self.edit(d,[dict(op='selection_path',id=id,**kw)])
    def values(self,d):return bytes.fromhex(d['selection']['gray_hex'])
    def pixels(self,d):
        output=self.invoke(dict(command='document.export',document=d,format='png'))
        return editing.png_pixels(base64.b64decode(output['data']))[2]
    def fill(self,id='fill',**kw):
        return dict(id=id,content=dict(type='fill',width=24,height=20,paint=[30,100,210,255]),**kw)

    def test_closed_path_selection_geometry_and_filled_pixels(self):
        d=self.add(self.document(),[work(region(2,3,8,6)),self.fill()]);original=copy.deepcopy(d)
        selected=self.select(d)
        expected=bytes(255 if 2<=x<10 and 3<=y<9 else 0 for y in range(20) for x in range(24))
        self.assertEqual(self.values(selected),expected)
        self.assertEqual(self.pixels(d),self.pixels(selected))
        filled=self.edit(selected,[dict(op='mask_from_selection',id='fill')])
        self.assertEqual(self.pixels(filled),b''.join(bytes([30,100,210,255]) if v else bytes(4) for v in expected))
        self.assertEqual(d,original)
        q=self.invoke(dict(command='document.query',document=d,query=dict(types=['work_path'],shapes=['path'],include_anchors=True)))
        self.assertEqual(q['ids'],['region']);self.assertEqual(q['items'][0]['geometry_bounds'],[2,3,10,9])
        self.assertEqual(len(q['items'][0]['anchors']),4)
        self.assertEqual(q['items'][0]['geometry'],region(2,3,8,6))

    def test_nonprinting_visibility_svg_persistence_and_duplicate_identity(self):
        for kind in ('vector','raster'):
            blank=self.document(kind=kind);d=self.add(blank,[work(rect(1,2,8,6),name='same')])
            d=self.edit(d,[dict(op='duplicate',id='region',new_id='copy')])
            self.assertEqual(self.pixels(blank),self.pixels(d))
            saved=self.invoke(dict(command='document.export',document=d,format='snapshot'))
            restored=self.invoke(dict(command='document.validate',document=json.loads(saved['data'])))
            self.assertEqual(restored,d)
            self.assertEqual([i['name'] for i in d['items']],['same','same'])
            hidden=self.edit(d,[dict(op='properties',id='region',visible=False,locked=True)])
            self.assertEqual(self.values(self.select(d)),self.values(self.select(hidden)))
            if kind=='vector':
                svg=self.invoke(dict(command='document.export',document=d,format='svg'))
                self.assertFalse(ET.fromstring(svg['data']).findall('.//*[@id="region"]'))
                self.assertTrue(any('Nonprinting work paths' in loss for loss in svg['losses']))

    def test_transformed_parent_fractional_area_and_source_appearance(self):
        m=[1,.25,-.5,1,8,2];g=region(0,0,8,6)
        group=dict(id='parent',transform=m,opacity=.3,visible=False,locked=True,content=dict(type='group'))
        # Build before locking the parent: read-only region use ignores appearance/locks.
        group.update(locked=False)
        d=self.add(self.document(),[group,work(g,parent='parent')])
        d=self.edit(d,[dict(op='properties',id='parent',locked=True)])
        selected=self.select(d);points=[mapped(m,p) for p in ([0,0],[8,0],[8,6],[0,6])]
        expected=[round(255*polygon_area_in_pixel(points,x,y)) for y in range(20) for x in range(24)]
        self.assertLessEqual(max(abs(a-b) for a,b in zip(self.values(selected),expected)),2)
        self.assertAlmostEqual(sum(self.values(selected))/255,54,delta=.2)
        self.assertEqual(self.pixels(selected),bytes(24*20*4))
        self.assertEqual(self.edit(d,[dict(op='path',id='region',action=dict(type='reverse'))],1)['code'],'LOCKED')

    def test_cubic_area_handles_world_anchors_and_exact_split(self):
        # x=2+12t, y=2+12t^2; integral between the curve and y=14 is 96.
        points=[[2,2],[6,2],[10,6],[14,14]]
        g=path([dict(verb='move',to=points[0]),dict(verb='cubic',control1=points[1],control2=points[2],to=points[3]),dict(verb='line',to=[2,14]),dict(verb='close')])
        d=self.add(self.document(),[work(g)]);selected=self.select(d)
        self.assertAlmostEqual(sum(self.values(selected))/255,96,delta=.1)
        expected=[round(255*parabola_pixel_area(x,y)) for y in range(20) for x in range(24)]
        self.assertLessEqual(max(abs(a-b) for a,b in zip(self.values(selected),expected)),1)
        hard=self.values(self.select(d,antialias=False))
        for y in range(20):
            for x in range(24):
                xx,yy=x+.5,y+.5;edge=2+(xx-2)**2/12
                if abs(yy-edge)>.2:
                    self.assertEqual(hard[y*24+x],255 if 2<xx<14 and edge<yy<14 else 0)
        split=self.edit(d,[dict(op='path',id='region',action=dict(type='split',command_index=1,t=.375))])
        commands=split['items'][0]['content']['geometry']['commands']
        for t in (.125,.25,.5,.75,.875):
            if t<=.375:segment=[points[0],commands[1]['control1'],commands[1]['control2'],commands[1]['to']];u=t/.375
            else:segment=[commands[1]['to'],commands[2]['control1'],commands[2]['control2'],commands[2]['to']];u=(t-.375)/.625
            for a,b in zip(paths.cubic(segment,u),paths.cubic(points,t)):self.assertAlmostEqual(a,b,places=12)
        transformed=self.edit(d,[dict(op='transform',id='region',matrix=[2,0,0,1,1,3]),dict(op='path',id='region',action=dict(type='handles',command_index=1,control1=[13,4],space='world'))])
        self.assertEqual(transformed['items'][0]['content']['geometry']['commands'][1]['control1'],[6,1])
        anchored=self.edit(transformed,[dict(op='path',id='region',action=dict(type='anchors',points=[dict(command_index=1,to=[31,18])],space='world'))])
        self.assertEqual(anchored['items'][0]['content']['geometry']['commands'][1]['to'],[15,15])
        self.assertEqual(anchored['items'][0]['content']['geometry']['commands'][1]['control2'],[11,7])

    def test_compound_winding_reversal_and_implicit_closure(self):
        g=path(paths.rectangle_path(2,2,16,14)+paths.rectangle_path(6,5,7,6))
        d=self.add(self.document(),[work(g)])
        nonzero=self.values(self.select(d));self.assertEqual(sum(nonzero),16*14*255)
        even=self.edit(d,[dict(op='work_path',id='region',geometry=g,fill_rule='even_odd')])
        reversed_d=self.edit(d,[dict(op='path',id='region',action=dict(type='reverse',contours=[1]))])
        expected=bytes(255 if 2<=x<18 and 2<=y<16 and not(6<=x<13 and 5<=y<11) else 0 for y in range(20) for x in range(24))
        self.assertEqual(self.values(self.select(even)),expected)
        self.assertEqual(self.values(self.select(reversed_d)),expected)
        triangle=path([dict(verb='move',to=[2,2]),dict(verb='line',to=[10,2]),dict(verb='line',to=[2,10])])
        open_d=self.edit(d,[dict(op='work_path',id='region',geometry=triangle)])
        self.assertAlmostEqual(sum(self.values(self.select(open_d)))/255,32,delta=.1)
        converted=self.add(self.document(),[work(rect(2,2,8,6))])
        converted=self.edit(converted,[dict(op='path',id='region',action=dict(type='convert'))])
        self.assertEqual(converted['items'][0]['content']['geometry'],region(2,2,8,6))

    def test_partial_coverage_selection_algebra(self):
        d=self.add(self.document(8,6),[work(region(1.25,1.5,3.5,3.25))])
        operand=self.values(self.select(d))
        expected=[round(255*max(0,min(x+1,4.75)-max(x,1.25))*max(0,min(y+1,4.75)-max(y,1.5))) for y in range(6) for x in range(8)]
        self.assertLessEqual(max(abs(a-b) for a,b in zip(operand,expected)),1)
        old=bytes((i*41)%256 for i in range(48))
        before=self.edit(d,[dict(op='selection_set',selection=dict(width=8,height=6,gray_hex=old.hex()))])
        for mode,fn in [('add',max),('subtract',lambda a,b:max(0,a-b)),('intersect',min),('replace',lambda a,b:b)]:
            actual=self.values(self.select(before,combine=mode))
            self.assertEqual(actual,bytes(fn(a,b) for a,b in zip(old,operand)))

    def test_turning_cubic_roots_reversal_and_zero_area_traces(self):
        # x=2+12t; y=8+96t(t-1/2)(t-1). Two lobes enclose total area 36.
        commands=[dict(verb='move',to=[2,8]),dict(verb='cubic',control1=[6,24],control2=[10,-8],to=[14,8]),dict(verb='close')]
        d=self.add(self.document(),[work(path(commands))])
        selected=self.select(d);self.assertAlmostEqual(sum(self.values(selected))/255,36,delta=.1)
        binary=self.values(self.select(d,antialias=False))
        for y in range(20):
            for x in range(24):
                t=(x+.5-2)/12;edge=8+96*t*(t-.5)*(t-1)
                if abs(y+.5-edge)>.05:
                    inside=0<t<1 and min(8,edge)<y+.5<max(8,edge)
                    self.assertEqual(binary[y*24+x],255 if inside else 0)
        reversed_d=self.edit(d,[dict(op='path',id='region',action=dict(type='reverse'))])
        self.assertEqual(self.values(self.select(reversed_d)),self.values(selected))
        empty=self.edit(d,[dict(op='work_path',id='region',geometry=path([dict(verb='move',to=[1,2]),dict(verb='line',to=[12,9])]))])
        self.assertEqual(self.values(self.select(empty)),bytes(24*20))
        off_canvas=self.edit(d,[dict(op='transform',id='region',matrix=[1,0,0,1,50,50])])
        self.assertEqual(self.values(self.select(off_canvas)),bytes(24*20))

    def test_compound_vector_mask_rule_and_pixel_mask_composition(self):
        g=path(paths.rectangle_path(2,2,16,14)+paths.rectangle_path(6,5,7,6))
        item=work(g);item['content']['fill_rule']='even_odd'
        d=self.add(self.document(),[item,self.fill(mask=dict(width=24,height=20,gray_hex='80'*(24*20)))])
        masked=self.edit(d,[dict(op='clip_from_path',id='fill',path_id='region')])
        expected=b''.join(bytes([30,100,210,128]) if 2<=x<18 and 2<=y<16 and not(6<=x<13 and 5<=y<11) else bytes(4) for y in range(20) for x in range(24))
        self.assertEqual(self.pixels(masked),expected)
        self.assertEqual(masked['items'][1]['clip']['fill_rule'],'even_odd')

    def test_geometry_combinations_preserve_sources_and_reuse_results(self):
        a,b=rect(2,3,10,8),rect(8,6,12,10)
        d=self.add(self.document(),[work(a,'a'),work(b,'b')]);original=copy.deepcopy(d)
        for mode,area in [('union',180),('intersection',20),('difference',60),('xor',160)]:
            result=self.invoke(dict(command='document.boolean',document=d,ids=['a','b'],mode=mode))
            self.assertEqual(result['area_exact'],str(area))
            added=self.add(d,[work(result['geometry'],'output')]);actual=self.values(self.select(added,'output',antialias=False))
            expected=bytes(255 if booleans.truth([booleans.contains(a,x+.5,y+.5),booleans.contains(b,x+.5,y+.5)],mode) else 0 for y in range(20) for x in range(24))
            self.assertEqual(actual,expected)
        self.assertEqual(d,original)

    def test_vector_mask_copy_preserves_world_placement_then_edits_independently(self):
        d=self.add(self.document(),[
            dict(id='group',transform=[1,0,0,1,3,2],content=dict(type='group')),
            self.fill(parent='group',transform=[2,0,0,1,1,1]),
            work(region(0,0,4,6),transform=[2,0,0,1,8,5])])
        masked=self.edit(d,[dict(op='clip_from_path',id='fill',path_id='region')])
        layer=next(i for i in masked['items'] if i['id']=='fill')
        self.assertEqual(layer['clip']['transform'],[1,0,0,1,2,2])
        expected=b''.join(bytes([30,100,210,255]) if 8<=x<16 and 5<=y<11 else bytes(4) for y in range(20) for x in range(24))
        self.assertEqual(self.pixels(masked),expected)
        moved=self.edit(masked,[dict(op='transform',id='region',matrix=[1,0,0,1,1,0],space='world')])
        self.assertEqual(self.pixels(moved),expected)
        self.assertEqual(self.edit(moved,[dict(op='clip_from_path',id='fill',path_id='region')],1)['code'],'INVALID_OPERATION')
        replaced=self.edit(moved,[dict(op='clip_from_path',id='fill',path_id='region',replace_existing=True),dict(op='remove',id='region')])
        self.assertNotEqual(self.pixels(replaced),expected)
        disabled=copy.deepcopy(layer['clip']);disabled['enabled']=False
        unclipped=self.edit(masked,[dict(op='clip',id='fill',clip=disabled)])
        self.assertEqual(self.pixels(unclipped),self.pixels(d))

    def test_work_paths_do_not_interrupt_clipped_adjustment_chains(self):
        base=self.add(self.document(),[self.fill()])
        adjustment=dict(id='adjust',content=dict(type='adjustment',adjustment=dict(operators=[dict(type='invert')],clip_to='fill')))
        plain=self.add(base,[adjustment]);interleaved=self.add(base,[work(region(2,3,6,4)),adjustment])
        self.assertEqual(self.pixels(plain),self.pixels(interleaved))
        bad=copy.deepcopy(adjustment);bad['content']['adjustment']['clip_to']='region'
        self.assertEqual(self.edit(self.add(base,[work(region(2,3,6,4))]),[dict(op='add',item=bad)],1)['code'],'INVALID_DOCUMENT')

    def test_mcp_sessions_reopen_undo_retry_diff_and_snapshot(self):
        c=Client();self.addCleanup(c.close);c.initialize()
        d=self.add(self.document(),[self.fill()])
        ops=[dict(op='add',item=work(region(2,3,8,6))),dict(op='selection_path',id='region'),dict(op='clip_from_path',id='fill',path_id='region')]
        with tempfile.TemporaryDirectory() as root:
            args=dict(session_root=root,session_id='paths')
            c.success('session.create',**args,request_id='create',document=d)
            action=dict(type='edit',operations=ops)
            changed=c.success('session.apply',**args,request_id='make-path',expected_revision=0,action=action)['document']
            self.assertEqual(self.invoke(dict(command='session.read',**args))['document'],changed)
            c.success('session.apply',**args,request_id='save',expected_revision=1,action=dict(type='snapshot',name='region'))
            undone=c.success('session.apply',**args,request_id='undo',expected_revision=2,action=dict(type='undo'))['document']
            self.assertEqual(undone['items'],d['items']);self.assertNotIn('selection',undone)
            redo=c.success('session.apply',**args,request_id='redo',expected_revision=3,action=dict(type='redo'))['document']
            self.assertEqual(redo['items'],changed['items']);self.assertEqual(redo['selection'],changed['selection'])
            self.assertEqual(c.success('session.read',**args,snapshot='region')['document']['items'],changed['items'])
            replay=c.success('session.apply',**args,request_id='make-path',expected_revision=0,action=action)
            self.assertEqual(replay['document'],changed);self.assertEqual(replay['current_revision'],4)
            diff=c.success('session.diff',**args,from_revision=0,to_revision=1,compare_pixels=True)
            self.assertEqual(diff['rendered_pixels']['changed_pixels'],24*20-8*6)
            c.success('session.verify',**args)

    def test_invalid_semantics_limits_and_atomic_failures(self):
        d=self.add(self.document(),[work(region(1,2,8,6)),self.fill()]);original=copy.deepcopy(d)
        invalid=[dict(op='selection_path',id='fill'),dict(op='work_path',id='fill',geometry=rect(0,0,1,1)),dict(op='selection_path',id='region',combine='add')]
        for op in invalid:self.assertEqual(self.edit(d,[op],1)['code'],'INVALID_OPERATION')
        for fields in [dict(opacity=.5),dict(blend='multiply'),dict(clip=dict(geometry=rect(0,0,2,2))),dict(mask=dict(width=1,height=1,gray_hex='ff'))]:
            item=work(rect(0,0,2,2),'invalid',**fields)
            error=self.edit(d,[dict(op='properties',id='fill',name='pending'),dict(op='add',item=item)],1)
            self.assertEqual(error['code'],'UNSUPPORTED');self.assertEqual(error['operation_index'],1)
        locked=self.edit(d,[dict(op='properties',id='fill',locked=True)])
        self.assertEqual(self.edit(locked,[dict(op='clip_from_path',id='fill',path_id='region')],1)['code'],'LOCKED')
        self.assertEqual(d,original)
        large=self.add(self.document(1024,1024),[work(rect(0,0,2,2))])
        self.assertEqual(self.edit(large,[dict(op='selection_path',id='region')],1)['code'],'RESOURCE_LIMIT')
        many=self.add(self.document(512,512),[work(path(paths.rectangle_path(0,0,512,512)*60))])
        self.assertEqual(self.edit(many,[dict(op='selection_path',id='region')],1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.edit(d,[dict(op='clip_from_path',id='region',path_id='region')],1)['code'],'UNSUPPORTED')


if __name__=='__main__':unittest.main()
