"""Independent rational conversions, delivered masks, and durable transfers."""
import base64
import copy
from fractions import Fraction as F
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
from test_affine_inverse_cli import ABOVE,document
from test_relative_transforms_cli import IDENTITY,item,source
from test_transform_policies_cli import matrix_product,inverse
from test_mcp import Client
from test_sessions_cli import invoke


def chain(*matrices):
    result=list(map(F,IDENTITY))
    for matrix in matrices:result=matrix_product(result,matrix)
    return result


def shift(x,y):return [1,0,0,1,x,y]


def board(matrix,masked=False,visible=False):
    d=document(matrix);size=2 if visible else .001
    d['items']=[dict(id='board',transform=matrix,content=dict(type='frame',frame=dict(
        role='artboard',width=2 if visible else 1,height=2 if visible else 1,logical_size=[size,size],
        bleed=dict(left=1,top=1,right=0,bottom=0))))]
    if masked:
        content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=size,height=size),fill=[20,80,150,255])
        d['items'] += [dict(id='thin',parent='board',content=content,artwork_mask=dict(
            source='mask-source',region=[0,0,size,size],linked=False,transform=matrix)),
            dict(id='mask-source',content=dict(type='mask_source')),
            dict(id='mask-content',parent='mask-source',content=copy.deepcopy(content))]
    return d


class CoordinateConversionTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke

    def valid(self,d):return self.invoke(dict(command='document.validate',document=d))
    def edit(self,d,*operations):
        return self.invoke(dict(command='document.edit',document=d,expected_revision=d.get('revision',0),
                                operations=list(operations)))['document']

    def test_transfer_into_matching_parent_preserves_world_placement_and_source(self):
        for matrix in ABOVE:
            original=self.valid(document(matrix));before=copy.deepcopy(original)
            destination=self.valid(dict(document(IDENTITY),items=[dict(id='parent',transform=matrix,content=dict(type='group'))]))
            result=self.edit(destination,dict(op='transfer',transfer=dict(source=original,ids=['thin'],prefix='copy',parent='parent')))
            self.assertEqual(item(result,'copy-thin')['transform'],IDENTITY)
            self.assertEqual(item(result,'copy-thin')['content'],item(original)['content'])
            info=self.invoke(dict(command='document.inspect',document=result))
            self.assertEqual(next(i for i in info['items'] if i['id']=='copy-thin')['world_transform'],matrix)
            self.assertEqual(original,before)
            self.assertEqual(item(destination,'parent'),item(result,'parent'))

    def test_copied_work_path_clip_preserves_exact_local_coordinates(self):
        for matrix in ABOVE:
            d=document(matrix)
            geometry=dict(shape='path',commands=[dict(verb='move',to=[0,0]),dict(verb='line',to=[.001,0]),
                dict(verb='line',to=[.001,.001]),dict(verb='line',to=[0,.001]),dict(verb='close')])
            d['items'].append(dict(id='path',transform=matrix,content=dict(type='work_path',geometry=geometry,fill_rule='nonzero')))
            d=self.valid(d);before=copy.deepcopy(d)
            result=self.edit(d,dict(op='clip_from_path',id='thin',path_id='path'))
            self.assertEqual(item(result)['clip']['transform'],IDENTITY)
            self.assertEqual(item(result)['clip']['geometry'],geometry)
            self.assertEqual(item(result,'path'),item(d,'path'))
            self.assertEqual(item(result)['content'],item(d)['content']);self.assertEqual(d,before)

    def test_masked_artboard_svg_and_visible_pixels_match_independent_local_source(self):
        for matrix,visible in [(m,False) for m in ABOVE]+[([1000,1000,1000,1000.00390625,0,0],True)]:
            d=self.valid(board(matrix,True,visible));before=copy.deepcopy(d)
            reference=self.valid(board(IDENTITY,True,visible))
            for bleed in (False,True):
                def export(source,format):
                    return self.invoke(dict(command='artboard.export',document=source,format=format,
                        include_bleed=bleed))['artifacts'][0]['artifact']
                actual=export(d,'svg')['data'];expected=export(reference,'svg')['data']
                ET.fromstring(actual)
                self.assertEqual(actual,expected)
                if visible:
                    _,_,pixels,_=editing.png_pixels(base64.b64decode(export(d,'png')['data']))
                    self.assertGreater(sum(pixels[3::4]),0)
                    self.assertEqual(pixels,editing.png_pixels(base64.b64decode(export(reference,'png')['data']))[2])
            self.assertEqual(d,before)

    def test_focused_artboard_mappings_round_complete_fraction_expressions(self):
        for matrix in ABOVE:
            d=self.valid(board(matrix));before=copy.deepcopy(d)
            for scale in (1,3,4):
                s=[scale,0,0,scale,0,0]
                for bleed in (False,True):
                    origin=[-1,-1] if bleed else [0,0]
                    result=self.invoke(dict(command='document.preview',document=d,options=dict(
                        focus=dict(type='artboard',id='board',include_bleed=bleed),scale=scale)))
                    expected=chain(s,shift(-origin[0],-origin[1]),inverse(matrix))
                    reverse=chain(matrix,shift(*origin),inverse(s))
                    self.assertEqual(result['mapping']['world_to_pixel'],list(map(float,expected)))
                    self.assertEqual(result['mapping']['pixel_to_world'],list(map(float,reverse)))
                    self.assertFalse(result['source_changed'])
            self.assertEqual(d,before)

    def test_dimension_noop_under_cancelling_parent_keeps_local_identity(self):
        for matrix in ABOVE:
            d=self.valid(source(matrix,True))
            metric=self.invoke(dict(command='geometry.measure',document=d,
                options=dict(ids=['thin'],bounds_only=True)))['items'][0]
            result=self.edit(d,dict(op='dimensions',id='thin',dimensions=dict(width=metric['width'],height=metric['height'])))
            self.assertEqual(item(result)['transform'],IDENTITY)
            self.assertEqual(item(result)['content'],item(d)['content'])

    def test_world_path_anchor_and_handles_use_exact_inverse_points(self):
        for matrix in ABOVE:
            d=document(matrix)
            item(d)['content']['geometry']=dict(shape='path',commands=[dict(verb='move',to=[.0001,.0001]),
                dict(verb='cubic',control1=[.0002,0],control2=[.0004,.001],to=[.001,.001]),
                dict(verb='line',to=[0,.001]),dict(verb='close')])
            d=self.valid(d);point=matrix[4:]
            result=self.edit(d,dict(op='path',id='thin',action=dict(type='anchors',space='world',
                points=[dict(command_index=0,to=point)])),dict(op='path',id='thin',action=dict(
                type='handles',command_index=1,space='world',control1=point,control2=point)))
            commands=item(result)['content']['geometry']['commands']
            self.assertEqual(commands[0]['to'],[0,0]);self.assertEqual(commands[1]['control1'],[0,0])
            self.assertEqual(commands[1]['control2'],[0,0]);self.assertEqual(commands[1]['to'],[.001,.001])
            self.assertEqual(item(result)['transform'],matrix)

    def test_alignment_snap_and_assisted_moves_match_rational_parent_conversion(self):
        parent=[7000,7000,7000,7000.00390625,0,0];local=[1,0,0,1,.125,-.125]
        d=source(parent,True);item(d)['transform']=local;d=self.valid(d)
        info=self.invoke(dict(command='document.inspect',document=d));bounds=next(i for i in info['items'] if i['id']=='thin')['geometry_bounds']
        delta=2**-10;target=[bounds[0]+delta,bounds[1]+delta]
        aligned=self.edit(d,dict(op='align',ids=['thin'],axis='x',anchor='min',reference=dict(type='bounds',bounds=[target[0],0,target[0],1])))
        snapped=self.edit(d,dict(op='snap',ids=['thin'],snap=dict(anchor=dict(x='min',y='min'),targets=[dict(type='point',point=target)],max_distance=1)))
        options=dict(ids=['thin'],bounds=[target[0],target[1],target[0]+20,target[1]+20])
        plan=self.invoke(dict(command='assist.layout',document=d,options=options))
        assisted=self.edit(d,dict(op='assist_layout',options=options))
        for result,motion in ((aligned,[delta,0]),(snapped,[delta,delta]),(assisted,[delta,delta])):
            expected=chain(inverse(parent),shift(*motion),parent,local)
            self.assertEqual(item(result)['transform'],list(map(float,expected)))
            self.assertEqual(item(result)['transform'][:4],local[:4])
            self.assertEqual(item(result)['content'],item(d)['content'])
        self.assertLessEqual(plan['maximum_geometry_error'],1e-6)

    def test_cli_and_mcp_transfer_retry_undo_and_conflict_preserve_history(self):
        client=Client();self.addCleanup(client.close);client.initialize()
        for transport in ('cli','mcp'):
            with tempfile.TemporaryDirectory() as root:
                session=dict(session_root=root,session_id='conversion')
                def call(command,**kw):
                    args=dict(**session,**kw)
                    return invoke(dict(command=command,**args)) if transport=='cli' else client.tool(command,**args)['structuredContent']
                matrix=ABOVE[0];d=dict(document(IDENTITY),items=[dict(id='parent',transform=matrix,content=dict(type='group'))])
                created=call('session.create',request_id='create',document=d);self.assertTrue(created['ok'],created)
                args=dict(request_id='transfer',expected_revision=0,action=dict(type='edit',operations=[
                    dict(op='transfer',transfer=dict(source=document(matrix),ids=['thin'],prefix='copy',parent='parent'))]))
                edited=call('session.apply',**args);self.assertTrue(edited['ok'],edited)
                self.assertEqual(item(edited['result']['document'],'copy-thin')['transform'],IDENTITY)
                self.assertTrue(call('session.apply',**args)['result']['replayed'])
                history=call('session.history',limit=128)
                stale=call('session.apply',**dict(args,request_id='stale'))
                self.assertFalse(stale['ok']);self.assertEqual(call('session.history',limit=128),history)
                undo=call('session.apply',request_id='undo',expected_revision=1,action=dict(type='undo'))
                self.assertEqual(undo['result']['document']['items'],created['result']['document']['items'])
                self.assertTrue(call('session.verify')['result']['valid'])

    def test_capabilities_identify_expression_limits_and_separate_sampling(self):
        info=self.invoke(dict(command='capabilities'))['coordinate_precision']['coordinate_conversions']
        self.assertEqual(info['maximum_expression_factors'],9)
        self.assertEqual(info['factor_types'],['forward','inverse'])
        self.assertEqual(info['fast_coefficient_point_error'],1e-9)
        self.assertEqual(info['point_coordinate_absolute_limit'],65536)
        self.assertIn('raster_sampling',info['error_scope'])


if __name__=='__main__':unittest.main()
