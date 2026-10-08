"""Independent affine algebra, constant document widths and placed-outline checks."""
import base64
import copy
from fractions import Fraction as F
import json
import math
import tempfile
import unittest
import test_editing_cli as editing
from test_mcp import Client
from test_stroke_outlines_cli import polygons,area


def matrix_product(a,b):
    a=list(map(F,a));b=list(map(F,b))
    return [a[0]*b[0]+a[2]*b[1],a[1]*b[0]+a[3]*b[1],a[0]*b[2]+a[2]*b[3],a[1]*b[2]+a[3]*b[3],a[0]*b[4]+a[2]*b[5]+a[4],a[1]*b[4]+a[3]*b[5]+a[5]]
def inverse(m):
    a,b,c,d,x,y=map(F,m);det=a*d-b*c
    return [d/det,-b/det,-c/det,a/det,(c*y-d*x)/det,(b*x-a*y)/det]
def point(m,p):return [float(m[0]*F(p[0])+m[2]*F(p[1])+m[4]),float(m[1]*F(p[0])+m[3]*F(p[1])+m[5])]
def pivot(m,p):return matrix_product([1,0,0,1,*p],matrix_product(m,[1,0,0,1,-p[0],-p[1]]))
def path(points):return dict(shape='path',commands=[dict(verb='move' if i==0 else 'line',to=p) for i,p in enumerate(points)])
def byid(d,id):return next(i for i in d['items'] if i['id']==id)


class TransformPolicyTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def edit(self,d,*ops,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=list(ops)),expected)
        return r if expected else r['document']
    def document(self,scaling='document',matrix=None,geometry=None,**stroke):
        d=self.invoke(dict(command='document.create',id='transform-policies',kind='vector',width=64,height=40))
        item=dict(id='line',transform=matrix or [1,0,0,1,0,0],content=dict(type='vector',geometry=geometry or path([[2,4],[10,4]]),stroke=dict(color=[40,100,220,255],width=2,scaling=scaling,**stroke)))
        return self.edit(d,dict(op='add',item=item))
    def pixels(self,d,scale=1):
        p=self.invoke(dict(command='document.export',document=d,format='png',scale=scale))
        return editing.png_pixels(base64.b64decode(p['data']))[:3]
    def expand(self,d,id='line'):
        return self.edit(d,dict(op='stroke_expand',id=id,fill_id=id+'-fill',stroke_id=id+'-outline'))
    def svg_roundtrip(self,d,scale=2):
        result=self.invoke(dict(command='document.export',document=d,format='svg'))
        imported=self.invoke(dict(command='svg.import',id='transform-import',source=dict(kind='text',text=result['data'])))['document']
        self.assertEqual(self.pixels(imported,scale),self.pixels(d,scale));return result

    def test_nested_composition_inverse_shear_reflection_and_pivots_match_rational_algebra(self):
        d=self.document(geometry=dict(shape='rect',x=1,y=2,width=4,height=3));geometry=copy.deepcopy(byid(d,'line')['content']['geometry'])
        parent=[2,.5,-1,1,20,4];local=[1,0,.5,1,1,2]
        d=self.edit(d,dict(op='group',ids=['line'],new_id='group'),dict(op='transform',id='group',matrix=parent),dict(op='transform',id='line',matrix=local))
        expected=matrix_product(parent,local)
        for space,m,p in [('local',[1,0,.5,1,0,0],[2,3]),('world',[0,1,-1,0,0,0],[24,12]),('world',[-1,0,0,1,0,0],[25,0])]:
            before=expected;anchored=pivot(m,p);expected=matrix_product(expected,anchored) if space=='local' else matrix_product(anchored,expected)
            d=self.edit(d,dict(op='transform',id='line',space=space,matrix=m,anchor=p))
            item=next(i for i in self.invoke(dict(command='document.inspect',document=d))['items'] if i['id']=='line')
            for actual,wanted in zip(item['world_transform'],expected):self.assertAlmostEqual(actual,float(wanted),places=11)
            corners=[point(expected,p) for p in [(1,2),(5,2),(5,5),(1,5)]];bounds=[min(p[0] for p in corners),min(p[1] for p in corners),max(p[0] for p in corners),max(p[1] for p in corners)]
            for actual,wanted in zip(item['geometry_bounds'],bounds):self.assertAlmostEqual(actual,wanted,places=10)
            restored=self.edit(d,dict(op='transform',id='line',space=space,matrix=list(map(float,inverse(anchored)))))
            actual=next(i for i in self.invoke(dict(command='document.inspect',document=restored))['items'] if i['id']=='line')['world_transform']
            for a,b in zip(actual,before):self.assertAlmostEqual(a,float(b),places=10)
        self.assertEqual(byid(d,'line')['content']['geometry'],geometry)
        replaced=self.edit(d,dict(op='transform',id='line',space='replace',matrix=[2,0,0,3,0,0],anchor=[2,3]));actual=next(i for i in self.invoke(dict(command='document.inspect',document=replaced))['items'] if i['id']=='line')['world_transform']
        self.assertEqual(actual,list(map(float,matrix_product(parent,pivot([2,0,0,3,0,0],[2,3])))))

    def test_document_width_and_object_width_have_independent_exact_pixels_at_all_scales(self):
        for scaling,radius in [('object',2),('document',1)]:
            d=self.document(scaling,matrix=[3,0,0,2,2,2])
            for scale in (1,2,4):
                w,h,p=self.pixels(d,scale);expected=bytes(v for y in range(h) for x in range(w) for v in ([40,100,220,255] if 8<=(x+.5)/scale<32 and 10-radius<=(y+.5)/scale<10+radius else [0]*4))
                self.assertEqual(p,expected,(scaling,scale))
            self.assertEqual(self.pixels(d,3),self.pixels(self.expand(d),3))

    def test_sheared_reflected_document_outline_matches_segment_normal_and_area(self):
        for matrix in ([2,1,.5,2,4,5],[-2,1,.5,2,38,5],[1,-.5,1,2,8,10]):
            d=self.document(matrix=matrix,geometry=path([[0,0],[10,0]]));expanded=self.expand(d)
            p=[point(matrix,v) for v in polygons(byid(expanded,'line-outline')['content']['geometry'])[0]]
            a,b=point(matrix,[0,0]),point(matrix,[10,0]);dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy);n=[-dy/length,dx/length]
            wanted=[[a[0]+n[0],a[1]+n[1]],[b[0]+n[0],b[1]+n[1]],[b[0]-n[0],b[1]-n[1]],[a[0]-n[0],a[1]-n[1]]]
            self.assertAlmostEqual(area(p),2*length,places=10)
            for q in wanted:self.assertTrue(any(math.dist(q,r)<1e-10 for r in p))
            w,h,pixels=self.pixels(d,3)
            for y in range(h):
                for x in range(w):
                    v=[(x+.5)/3-a[0],(y+.5)/3-a[1]];along=(v[0]*dx+v[1]*dy)/length;across=abs(v[0]*n[0]+v[1]*n[1]);alpha=pixels[(y*w+x)*4+3]
                    if 1<along<length-1 and across<.6:self.assertEqual(alpha,255)
                    if across>1.4 or along < -.4 or along>length+.4:self.assertEqual(alpha,0)
            self.assertEqual(self.pixels(d,2),self.pixels(expanded,2))

    def test_document_dashes_phase_profiles_and_arrow_dimensions_are_fixed(self):
        d=self.document(matrix=[3,0,0,2,2,12],geometry=path([[0,0],[8,0]]),dash=dict(array=[4,2],offset=1))
        w,h,p=self.pixels(d)
        expected=bytes(v for y in range(h) for x in range(w) for v in ([40,100,220,255] if 2<=x<26 and 11<=y<13 and ((x+.5-2)+1)%6<4 else [0]*4));self.assertEqual(p,expected)
        d=self.document(matrix=[3,0,0,2,2,12],geometry=path([[0,0],[8,0]]),width_profile=[[0,.5],[1,2]],end_arrow=dict(kind='triangle',length=6,width=8))
        expanded=self.expand(d);p=[point([3,0,0,2,2,12],v) for v in polygons(byid(expanded,'line-outline')['content']['geometry'])[-1]]
        self.assertEqual(len(p),3)
        for wanted in [(26,12),(20,8),(20,16)]:self.assertTrue(any(math.dist(wanted,actual)<1e-10 for actual in p))
        self.assertEqual(self.pixels(d,4),self.pixels(expanded,4));self.svg_roundtrip(d,3)

    def test_curves_gradient_paint_and_affine_hierarchy_match_independent_world_controls(self):
        m=[2,.5,-.25,1,8,8];g=dict(shape='path',commands=[dict(verb='move',to=[0,0]),dict(verb='cubic',control1=[4,-4],control2=[8,8],to=[16,4])])
        gradient=dict(type='linear',start=[0,0],end=[16,0],stops=[dict(offset=0,color=[20,100,220,255]),dict(offset=1,color=[220,80,20,128])])
        d=self.document(matrix=m,geometry=g,cap='round',join='round',dash=dict(array=[5,2],offset=-1),width_profile=[[0,.5],[.5,2],[1,1]])
        byid(d,'line')['content']['stroke']['color']=gradient
        independent=copy.deepcopy(d);item=byid(independent,'line');item['transform']=[1,0,0,1,0,0];item['content']['stroke']['scaling']='object';item['content']['stroke']['color']['transform']=m
        for command in item['content']['geometry']['commands']:
            for key in ('to','control1','control2'):
                if key in command:command[key]=point(m,command[key])
        for scale in (1,3):self.assertEqual(self.pixels(d,scale),self.pixels(independent,scale))
        self.assertEqual(self.pixels(d,3),self.pixels(self.expand(d),3));self.svg_roundtrip(d,3)

    def test_shared_mask_references_resolve_document_width_per_placement(self):
        d=self.document(geometry=path([[1,4],[7,4]]));line=byid(d,'line');line['parent']='mask';line['content']['stroke']['color']=[255]*4
        d['items']=[dict(id='mask',content=dict(type='mask_source')),line]
        for id,m in [('large',[2,0,0,3,2,2]),('small',[1,0,0,1,30,2])]:
            d['items'].append(dict(id=id,transform=m,content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=8,height=8),fill=[30,180,100,255]),artwork_mask=dict(source='mask',region=[0,0,8,8],mode='alpha')))
        w,h,p=self.pixels(d);expected=bytes(v for y in range(h) for x in range(w) for v in ([30,180,100,255] if (4<=x<16 and 13<=y<15) or (31<=x<37 and 5<=y<7) else [0]*4));self.assertEqual(p,expected)
        self.svg_roundtrip(d,3)
        self.assertEqual(self.edit(d,dict(op='stroke_expand',id='line',fill_id='f',stroke_id='s'),expected=1)['code'],'UNSUPPORTED')

    def test_components_and_variants_keep_document_width_after_nested_placement(self):
        d=self.document(geometry=path([[0,0],[8,0]]));line=byid(d,'line');line['parent']='source'
        d['items']=[dict(id='source',content=dict(type='component_source')),line,dict(id='copy',transform=[3,0,0,2,4,10],content=dict(type='instance',instance=dict(source='source')))]
        self.assertEqual(self.edit(d,dict(op='stroke_expand',id='line',fill_id='f',stroke_id='s'),expected=1)['code'],'UNSUPPORTED')
        detached=self.edit(d,dict(op='instance_unlink',id='copy'));child=next(i['id'] for i in detached['items'] if i['id']!='line' and i['content']['type']=='vector')
        self.assertEqual(self.pixels(d,3),self.pixels(self.expand(detached,child),3))
        definition=dict(bindings=[dict(key='placement',item_id='copy',property='transform')],datasets=dict(wide=dict(values=dict(placement=dict(type='transform',value=[5,0,0,4,4,10])))))
        active=self.edit(d,dict(op='variants_set',definition=definition),dict(op='variant_select',dataset='wide'));w,h,p=self.pixels(active)
        self.assertEqual(p,bytes(v for y in range(h) for x in range(w) for v in ([40,100,220,255] if 4<=x<44 and 9<=y<11 else [0]*4)));self.svg_roundtrip(active)

    def test_artboard_exports_remove_board_placement_but_keep_fixed_width(self):
        d=self.document(matrix=[3,0,0,2,4,10],geometry=path([[0,0],[8,0]]));line=byid(d,'line');line['parent']='board'
        d['items']=[dict(id='board',transform=[.5,0,0,.5,20,2],content=dict(type='frame',frame=dict(role='artboard',width=40,height=24))),line]
        for scale in (1,3):
            result=self.invoke(dict(command='artboard.export',document=d,format='png',scale=scale))['artifacts'][0]['artifact'];w,h,p=editing.png_pixels(base64.b64decode(result['data']))[:3]
            expected=bytes(v for y in range(h) for x in range(w) for v in ([40,100,220,255] if 4<=(x+.5)/scale<28 and 9<=(y+.5)/scale<11 else [0]*4));self.assertEqual(p,expected)
        svg=self.invoke(dict(command='artboard.export',document=d,format='svg'))['artifacts'][0]['artifact'];imported=self.invoke(dict(command='svg.import',id='board-import',source=dict(kind='text',text=svg['data'])))['document'];self.assertEqual(self.pixels(imported,3),(w,h,p))

    def test_hidden_document_space_dashes_and_mask_copies_cannot_bypass_work_limits(self):
        d=self.document('object',matrix=[30000,0,0,1,0,16],geometry=path([[0,0],[1,0]]),dash=dict(array=[.5,.5]));bad=copy.deepcopy(d);byid(bad,'line')['content']['stroke']['scaling']='document';byid(bad,'line')['visible']=False
        self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'LIMIT_EXCEEDED')
        d=self.document(geometry=path([[0,.5],[1,.5]]),dash=dict(array=[.5,.5]));line=byid(d,'line');line['parent']='mask';line['content']['stroke']['width']=.2
        d['items']=[dict(id='mask',content=dict(type='mask_source')),line,dict(id='owner',transform=[30000,0,0,1,0,0],content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=1,height=1),fill=[255]*4),artwork_mask=dict(source='mask',region=[0,0,1,1],mode='alpha'))]
        self.invoke(dict(command='document.validate',document=d))
        for fmt in ('png','svg'):self.assertEqual(self.invoke(dict(command='document.export',document=d,format=fmt),1)['code'],'LIMIT_EXCEEDED')

    def test_artboard_preflight_uses_export_coordinates_before_any_output(self):
        d=self.document(geometry=path([[0,0],[1,0]]),dash=dict(array=[.01,.01]));line=byid(d,'line');line['parent']='board';line['transform']=[1000,0,0,1,0,10]
        d['items']=[dict(id='board',transform=[.01,0,0,.01,0,0],content=dict(type='frame',frame=dict(role='artboard',width=40,height=24))),line]
        self.invoke(dict(command='document.validate',document=d))
        for fmt in ('png','svg'):
            self.assertEqual(self.invoke(dict(command='artboard.export',document=d,format=fmt),1)['code'],'LIMIT_EXCEEDED')
        byid(d,'line')['content']['stroke']['scaling']='object'
        for fmt in ('png','svg'):self.invoke(dict(command='artboard.export',document=d,format=fmt))

    def test_default_object_policy_and_expansion_freezes_future_width_behavior(self):
        old=self.document('object');self.assertNotIn('scaling',byid(old,'line')['content']['stroke'])
        explicit=copy.deepcopy(old);byid(explicit,'line')['content']['stroke']['scaling']='object'
        self.assertEqual(self.pixels(old,3),self.pixels(explicit,3))
        d=self.document(matrix=[3,0,0,2,2,2]);expanded=self.expand(d)
        self.assertEqual(self.pixels(d),self.pixels(expanded))
        op=dict(op='transform',id='line',space='world',matrix=[1,0,0,2,0,0],anchor=[0,10])
        for source,radius in [(d,1),(expanded,2)]:
            w,h,p=self.pixels(self.edit(source,op),2)
            self.assertEqual(p,bytes(v for y in range(h) for x in range(w) for v in ([40,100,220,255] if 8<=(x+.5)/2<32 and 10-radius<=(y+.5)/2<10+radius else [0]*4)))

    def test_closed_compound_profiles_match_independently_mapped_control_geometry(self):
        m=[-2,.5,.25,1,36,6]
        g=dict(shape='path',commands=[dict(verb='move',to=[0,0]),dict(verb='cubic',control1=[4,-2],control2=[12,2],to=[12,8]),dict(verb='line',to=[0,8]),dict(verb='close'),dict(verb='move',to=[3,3]),dict(verb='line',to=[3,5]),dict(verb='line',to=[8,5]),dict(verb='close')])
        d=self.document(matrix=m,geometry=g,join='round',width_profile=[[0,.5],[.5,1],[1,.5]])
        independent=copy.deepcopy(d);item=byid(independent,'line');item['transform']=[1,0,0,1,0,0];item['content']['stroke']['scaling']='object'
        for command in item['content']['geometry']['commands']:
            for key in ('to','control1','control2'):
                if key in command:command[key]=point(m,command[key])
        for scale in (1,4):self.assertEqual(self.pixels(d,scale),self.pixels(independent,scale))
        self.assertEqual(self.pixels(d,3),self.pixels(self.expand(d),3));self.svg_roundtrip(d,3)

    def test_invalid_matrices_unknown_policies_locks_and_expansion_storage_fail_atomically(self):
        d=self.document();before=copy.deepcopy(d)
        for matrix in ([0]*6,[1e-6,0,0,1e-6,0,0],[1,0,0,1,1e30,0]):self.edit(d,dict(op='transform',id='line',matrix=matrix),expected=1)
        bad=copy.deepcopy(d);byid(bad,'line')['content']['stroke']['scaling']='automatic';self.invoke(dict(command='document.validate',document=bad),1)
        locked=self.edit(d,dict(op='properties',id='line',locked=True));self.assertEqual(self.edit(locked,dict(op='transform',id='line',matrix=[2,0,0,2,0,0]),expected=1)['code'],'LOCKED')
        tiny=self.edit(d,dict(op='transform',id='line',matrix=[.0002,0,0,.0002,0,0]));byid(tiny,'line')['content']['stroke']['width']=100
        self.invoke(dict(command='document.validate',document=tiny));self.edit(tiny,dict(op='stroke_expand',id='line',fill_id='f',stroke_id='s'),expected=1)
        self.assertEqual(d,before)

    def test_mcp_policy_transforms_and_expansion_survive_sessions_undo_redo_and_retry(self):
        d=self.document(matrix=[3,0,0,2,2,2]);c=Client();self.addCleanup(c.close);c.initialize()
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='transform-policies');c.success('session.create',**session,request_id='create',document=d)
            ops=[dict(op='transform',id='line',space='world',matrix=[1,0,0,2,0,0],anchor=[0,10]),dict(op='stroke_expand',id='line',fill_id='fill',stroke_id='outline')]
            args=dict(**session,request_id='expand',expected_revision=0,action=dict(type='edit',operations=ops));result=c.success('session.apply',**args)
            self.assertTrue(c.success('session.apply',**args)['replayed']);self.assertEqual(self.pixels(result['document']),self.pixels(d))
            undo=c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(undo['items'],d['items']);self.assertEqual(byid(undo,'line')['content']['stroke']['scaling'],'document')
            redo=c.success('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'))['document'];self.assertEqual(redo['items'],result['document']['items']);c.success('session.verify',**session)
            snapshot=c.success('document.export',document=undo,format='snapshot');self.assertEqual(json.loads(snapshot['data']),undo)


if __name__=='__main__':unittest.main()
