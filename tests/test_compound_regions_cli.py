"""Original retained-region fixtures; independent vertical integrals and analytic lobes."""
import base64
import copy
from contextlib import closing
import json
import math
import tempfile
import unittest
import test_work_paths_cli as work
import test_paths_cli as paths
from test_mcp import Client


def operand(g,rule='nonzero',transform=None):return dict(geometry=g,fill_rule=rule,transform=transform or [1,0,0,1,0,0])
def compound(mode,*parts):return dict(shape='compound',mode=mode,operands=list(parts))
def truth(values,mode):
    return {'union':lambda:any(values),'intersection':lambda:all(values),'difference':lambda:values[0] and not any(values[1:]),'xor':lambda:sum(values)%2==1}[mode]()
def graphs():
    def g(points):return work.path([dict(verb='move',to=points[0]),dict(verb='cubic',control1=points[1],control2=points[2],to=points[3]),dict(verb='line',to=[14,14]),dict(verb='line',to=[2,14]),dict(verb='close')])
    return g([[2,2],[6,2],[10,5],[14,11]]),g([[2,7.5],[6,4.5],[10,3],[14,3]])
def integrate(f,a,b,tolerance=1e-8):
    def area(a,b,fa,fm,fb):return (b-a)*(fa+4*fm+fb)/6
    def recurse(a,b,fa,fm,fb,whole,tol,depth):
        m=(a+b)/2;l=(a+m)/2;r=(m+b)/2;fl=f(l);fr=f(r)
        left=area(a,m,fa,fl,fm);right=area(m,b,fm,fr,fb);delta=left+right-whole
        if depth==0 or abs(delta)<=15*tol:return left+right+delta/15
        return recurse(a,m,fa,fl,fm,left,tol/2,depth-1)+recurse(m,b,fm,fr,fb,right,tol/2,depth-1)
    fa,fm,fb=f(a),f((a+b)/2),f(b)
    return recurse(a,b,fa,fm,fb,area(a,b,fa,fm,fb),tolerance,22)


class CompoundRegionTests(unittest.TestCase):
    invoke=work.WorkPathTests.invoke
    document=work.WorkPathTests.document
    edit=work.WorkPathTests.edit
    add=work.WorkPathTests.add
    values=work.WorkPathTests.values
    def combine(self,d,mode='union',ids=None,new_id='combined'):
        return self.edit(d,[dict(op='work_path_combine',ids=ids or ['a','b'],new_id=new_id,mode=mode)])
    def selection(self,d,id='combined',antialias=True):return self.values(self.edit(d,[dict(op='selection_path',id=id,antialias=antialias)]))
    def pixels(self,d,scale=1,**kw):
        r=self.invoke(dict(command='document.render',document=d,scale=scale,**kw));return r,bytes.fromhex(r['data'])

    def test_subpixel_operations_combine_regions_before_coverage_integration(self):
        # Disjoint halves occupy the same output pixel: max/min mask algebra is wrong.
        for ax,bx in [(.0,.5),(.125,.375)]:
            a=work.rect(ax,0,.5,1);b=work.rect(bx,0,.5,1)
            d=self.add(self.document(2,2),[work.work(a,'a'),work.work(b,'b')]);before=copy.deepcopy(d)
            intersection=max(0,min(ax+.5,bx+.5)-max(ax,bx))
            areas=dict(union=1-intersection,intersection=intersection,difference=.5-intersection,xor=1-2*intersection)
            for mode,area in areas.items():
                combined=self.combine(d,mode);coverage=self.selection(combined)
                self.assertLessEqual(abs(coverage[0]-round(area*255)),1);self.assertEqual(coverage[1:],bytes(3))
                self.assertEqual(combined['items'][:2],d['items']);self.assertEqual(d,before)

    def test_irrational_curve_crossings_against_independent_vertical_area_integrals(self):
        a,b=graphs();d=self.add(self.document(16,16),[work.work(a,'a'),work.work(b,'b')])
        crossing=-10+8*math.sqrt(5);self.assertNotEqual(crossing,round(crossing))
        for mode in ['union','intersection','difference','xor']:
            values=self.selection(self.combine(d,mode));expected=[]
            for y in range(16):
                for x in range(16):
                    def height(u):
                        if not 2<=u<=14:return 0
                        aa=2+(u-2)**2/16;bb=3+(14-u)**2/32
                        def span(lo,hi):return max(0,min(y+1,hi,14)-max(y,lo))
                        return {'union':lambda:span(min(aa,bb),14),'intersection':lambda:span(max(aa,bb),14),'difference':lambda:span(aa,bb),'xor':lambda:span(min(aa,bb),max(aa,bb))}[mode]()
                    lo,hi=max(x,2),min(x+1,14)
                    expected.append(round(255*integrate(height,lo,hi)) if lo<hi else 0)
            self.assertLessEqual(max(abs(v-e) for v,e in zip(values,expected)),1,mode)

    def test_self_intersecting_nodal_curve_and_corner_contact_against_analytic_lobes(self):
        # x=12+48s^2, y=24+96s^3-12s, s=t-1/2. The node is (18,24).
        g=work.path([dict(verb='move',to=[24,18]),dict(verb='cubic',control1=[8,38],control2=[8,10],to=[24,30]),dict(verb='close')])
        d=self.add(self.document(32,48),[work.work(g,'a'),work.work(work.rect(18,24,10,12),'b')])
        for mode in ['union','intersection','difference','xor']:
            values=self.selection(self.combine(d,mode),antialias=False);expected=[]
            for y in range(48):
                for x in range(32):
                    xx,yy=x+.5,y+.5;bound=abs((2*xx-36)*math.sqrt(max(0,(xx-12)/48)))
                    inside=12<xx<24 and abs(yy-24)<bound
                    expected.append(255 if truth([inside,18<xx<28 and 24<yy<36],mode) else 0)
            self.assertEqual(values,bytes(expected),mode)

    def test_nested_modes_operand_winding_duplicate_curves_and_empty_regions(self):
        ring=work.region(1,1,12,12);ring['commands']+=paths.rectangle_path(4,4,6,6)
        a=work.work(ring,'a');a['content']['fill_rule']='even_odd';b=work.work(work.rect(7,0,3,16),'b')
        d=self.add(self.document(16,16),[a,b,work.work(work.rect(0,8,16,8),'cut')]);d=self.combine(d,'xor');d=self.combine(d,'difference',['combined','cut'],'nested')
        actual=self.selection(d,'nested',False)
        expected=bytes(255 if ((1<=x<13 and 1<=y<13 and not(4<=x<10 and 4<=y<10)) != (7<=x<10)) and y<8 else 0 for y in range(16) for x in range(16))
        self.assertEqual(actual,expected)
        reverse=self.edit(d,[dict(op='path_component',id='nested',component=[0,0],action=dict(type='reverse',contours=[0,1]))])
        self.assertEqual(self.selection(reverse,'nested'),self.selection(d,'nested'))
        empty=self.combine(d,'xor',['a','nested'],'duplicate');empty=self.edit(empty,[dict(op='work_path',id='duplicate',geometry=compound('xor',operand(ring,'even_odd'),operand(copy.deepcopy(ring),'even_odd')))])
        self.assertEqual(self.selection(empty,'duplicate'),bytes(256))

    def test_world_coordinates_frozen_sources_query_and_component_handles(self):
        a,b=graphs();parent=dict(id='parent',transform=[2,0,0,1,4,2],content=dict(type='group'))
        d=self.add(self.document(40,24),[parent,work.work(a,'a',parent='parent'),work.work(b,'b')]);d=self.edit(d,[dict(op='properties',id='a',locked=True,visible=False)])
        combined=self.combine(d);original=copy.deepcopy(combined)
        self.assertEqual(next(i for i in combined['items'] if i['id']=='combined')['content']['geometry']['operands'][0]['transform'],[2,0,0,1,4,2])
        edited=self.edit(combined,[dict(op='path_component',id='combined',component=[0],action=dict(type='handles',command_index=1,control1=[18,6],space='world'))])
        operands=next(i for i in edited['items'] if i['id']=='combined')['content']['geometry']['operands'];self.assertEqual(operands[0]['geometry']['commands'][1]['control1'],[7,4]);self.assertEqual(operands[1],next(i for i in combined['items'] if i['id']=='combined')['content']['geometry']['operands'][1])
        query=self.invoke(dict(command='document.query',document=edited,query=dict(shapes=['compound'],include_anchors=True)))
        self.assertEqual(query['ids'],['combined']);anchor=next(v for v in query['items'][0]['anchors'] if v['component']==[0] and v['command_index']==1)
        self.assertEqual(anchor['incoming_segment_handles']['world_control1'],[18,6]);self.assertEqual(combined,original)
        moved=self.edit(combined,[dict(op='properties',id='a',locked=False),dict(op='transform',id='a',matrix=[1,0,0,1,1,1])])
        self.assertEqual(self.selection(moved),self.selection(combined))

    def test_copied_compound_vector_masks_scale_and_edit_independently(self):
        d=self.add(self.document(16,12),[work.work(work.region(1.25,1.5,8.5,8),'a'),work.work(work.region(4,3,3,4),'b'),dict(id='paint',content=dict(type='fill',width=16,height=12,paint=[30,100,210,255]),mask=dict(width=16,height=12,gray_hex='80'*192))]);d=self.combine(d,'difference')
        masked=self.edit(d,[dict(op='clip_from_path',id='paint',path_id='combined')])
        for scale in [1,2,4]:
            result,pixels=self.pixels(masked,scale)
            for y in range(result['height']):
                for x in range(result['width']):
                    overlap=lambda a,b,c:max(0,min(b,c+1)-max(a,c))
                    area=overlap(1.25*scale,9.75*scale,x)*overlap(1.5*scale,9.5*scale,y)-overlap(4*scale,7*scale,x)*overlap(3*scale,7*scale,y)
                    self.assertLessEqual(abs(pixels[(y*result['width']+x)*4+3]-round(area*128)),1)
        modified=self.edit(masked,[dict(op='path_component',id='paint',clip=True,component=[1],action=dict(type='anchors',points=[dict(command_index=1,to=[8,3])],move_handles=False))])
        self.assertNotEqual(self.pixels(modified)[1],self.pixels(masked)[1]);self.assertEqual(modified['items'][-1],masked['items'][-1])
        removed=self.edit(masked,[dict(op='remove',id='combined'),dict(op='remove',id='a'),dict(op='remove',id='b')]);self.assertEqual(self.pixels(removed)[1],self.pixels(masked)[1])

    def test_snapshot_mcp_history_retry_and_reopen_preserve_compound_paths(self):
        a,b=graphs();d=self.add(self.document(16,16),[work.work(a,'a'),work.work(b,'b')]);action=dict(type='edit',operations=[dict(op='work_path_combine',ids=['a','b'],new_id='combined',mode='intersection')])
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='regions')
            with closing(Client()) as client:
                client.initialize();client.success('session.create',**session,request_id='create',document=d)
                made=client.success('session.apply',**session,request_id='combine',expected_revision=0,action=action);document=made['document']
                saved=json.loads(client.success('document.export',document=document,format='snapshot')['data']);self.assertEqual(saved,document)
                undo=client.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'));self.assertEqual(undo['document'],dict(d,revision=2))
                redo=client.success('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'))
            with closing(Client()) as client:
                client.initialize();self.assertEqual(client.success('session.read',**session)['document'],redo['document'])
                self.assertEqual(self.selection(redo['document']),self.selection(document));self.assertTrue(client.success('session.apply',**session,request_id='combine',expected_revision=0,action=action)['replayed'])

    def test_invalid_contexts_locks_limits_and_atomic_failures(self):
        a,b=graphs();d=self.add(self.document(16,16),[work.work(a,'a'),work.work(b,'b')]);combined=self.combine(d);before=copy.deepcopy(combined)
        locked=self.edit(combined,[dict(op='properties',id='combined',locked=True)])
        self.assertEqual(self.edit(locked,[dict(op='path_component',id='combined',component=[0],action=dict(type='reverse'))],1)['code'],'LOCKED')
        for address in [[],[2],[0,0]]:self.assertEqual(self.edit(combined,[dict(op='path_component',id='combined',component=address,action=dict(type='reverse'))],1)['code'],'INVALID_OPERATION')
        self.edit(d,[dict(op='work_path_combine',ids=['a','a'],new_id='x',mode='union')],1)
        self.edit(d,[dict(op='work_path_combine',ids=['a','b'],new_id='x',mode='union'),dict(op='remove',id='missing')],1)
        self.assertEqual(self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='work_path_combine',ids=['a','b'],new_id='x',mode='union')],control=dict(timeout_ms=0)),1)['code'],'TIMEOUT')
        g=compound('union',operand(a),operand(b));self.edit(combined,[dict(op='work_path',id='combined',geometry=g,fill_rule='even_odd')],1)
        for _ in range(8):g=compound('union',operand(g),operand(a))
        self.assertEqual(self.edit(combined,[dict(op='work_path',id='combined',geometry=g)],1)['code'],'RESOURCE_LIMIT')
        g=compound('union',*[operand(compound('union',*[operand(a) for _ in range(16)])) for _ in range(5)])
        self.assertEqual(self.edit(combined,[dict(op='work_path',id='combined',geometry=g)],1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.invoke(dict(command='document.boolean',document=combined,ids=['a','combined'],mode='union'),1)['code'],'UNSUPPORTED')
        self.assertEqual(combined,before)

    def test_vector_page_delivery_rejects_implicit_compound_clip_flattening(self):
        d=self.add(self.document(16,16,'vector'),[work.work(work.rect(1,1,12,12),'a'),work.work(work.rect(4,4,4,4),'b'),dict(id='paint',content=dict(type='vector',geometry=work.rect(0,0,16,16),fill=[30,100,210,255]))]);d=self.combine(d,'difference');masked=self.edit(d,[dict(op='clip_from_path',id='paint',path_id='combined')])
        for fmt in ['svg','pdf']:
            self.assertEqual(self.invoke(dict(command='document.export',document=masked,format=fmt),1)['code'],'UNSUPPORTED')
        snapshot=self.invoke(dict(command='document.export',document=masked,format='snapshot'));self.assertEqual(json.loads(snapshot['data']),masked)
        clip=copy.deepcopy(masked['items'][2]['clip']);clip['enabled']=False;disabled=self.edit(masked,[dict(op='clip',id='paint',clip=clip)])
        self.invoke(dict(command='document.export',document=disabled,format='svg'))

    def test_nested_reflected_sheared_regions_and_component_split_preserve_world_geometry(self):
        a,b=graphs();m=[-1,.25,.5,1,20.125,2.0625];d=self.add(self.document(40,32),[dict(id='parent',transform=m,content=dict(type='group')),work.work(a,'a',parent='parent'),work.work(b,'b',parent='parent'),work.work(work.rect(0,0,40,32),'canvas')])
        d=self.combine(d,'union');d=self.combine(d,'intersection',['combined','canvas'],'nested');before=self.selection(d,'nested')
        split=self.edit(d,[dict(op='path_component',id='nested',component=[0,0],action=dict(type='split',command_index=1,t=.375))])
        self.assertEqual(self.selection(split,'nested'),before)
        values=self.selection(d,'nested',False);expected=[];det=m[0]*m[3]-m[1]*m[2]
        for y in range(32):
            for x in range(40):
                dx,dy=x+.5-m[4],y+.5-m[5];u=(m[3]*dx-m[2]*dy)/det;v=(-m[1]*dx+m[0]*dy)/det
                inside=2<u<14 and min(2+(u-2)**2/16,3+(14-u)**2/32)<v<14
                expected.append(255 if inside else 0)
        self.assertEqual(values,bytes(expected))
        self.assertEqual(next(i for i in split['items'] if i['id']=='combined'),next(i for i in d['items'] if i['id']=='combined'))

    def test_nodal_antialiasing_against_independent_vertical_lobe_area(self):
        g=work.path([dict(verb='move',to=[24,18]),dict(verb='cubic',control1=[8,38],control2=[8,10],to=[24,30]),dict(verb='close')])
        d=self.add(self.document(32,40),[work.work(g,'a'),work.work(work.rect(18,24,10,12),'b')])
        for mode in ['union','intersection','difference','xor']:
            got=self.selection(self.combine(d,mode));expected=[]
            for y in range(40):
                for x in range(32):
                    def length(u):
                        bound=abs((2*u-36)*math.sqrt(max(0,(u-12)/48)))
                        lo,hi=max(y,24-bound),min(y+1,24+bound)
                        aa=max(0,hi-lo) if 12<=u<=24 else 0
                        bb=1 if 18<=u<=28 and 24<=y<36 else 0
                        both=aa if bb else 0
                        return {'union':aa+bb-both,'intersection':both,'difference':aa-both,'xor':aa+bb-2*both}[mode]
                    expected.append(round(255*integrate(length,x,x+1)))
            self.assertLessEqual(max(abs(a-b) for a,b in zip(got,expected)),1,mode)


if __name__=='__main__':unittest.main()
