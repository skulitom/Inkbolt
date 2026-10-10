"""Independent Fraction expressions for cancelling parent-space edits."""
import copy
from fractions import Fraction as F
import tempfile
import unittest
import test_editing_cli as editing
from test_affine_inverse_cli import ABOVE, BELOW, document
from test_transform_policies_cli import matrix_product, inverse, pivot
from test_mcp import Client
from test_sessions_cli import invoke

IDENTITY=[1,0,0,1,0,0]


def source(matrix, parented=False):
    d=document(matrix)
    d['items'].append(dict(id='parent',transform=matrix,content=dict(type='group')))
    if parented:d['items'][0].update(parent='parent',transform=IDENTITY.copy())
    return d


def item(d, name='thin'):
    return next(i for i in d['items'] if i['id']==name)


class RelativeTransformTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke

    def edit(self,d,*operations):
        return self.invoke(dict(command='document.edit',document=d,
            expected_revision=d.get('revision',0),operations=list(operations)))['document']

    def test_reparent_and_identity_world_edits_preserve_exact_local_identity(self):
        for matrix in ABOVE:
            for parented in (False,True):
                d=self.invoke(dict(command='document.validate',document=source(matrix,parented)));before=copy.deepcopy(d)
                op=(dict(op='transform',id='thin',space='world',matrix=IDENTITY)
                    if parented else dict(op='reparent',id='thin',parent='parent'))
                result=self.edit(d,op)
                self.assertEqual(item(result)['transform'],IDENTITY)
                info=self.invoke(dict(command='document.inspect',document=result))
                self.assertEqual(next(i for i in info['items'] if i['id']=='thin')['world_transform'],matrix)
                self.assertEqual(item(result)['content'],item(d)['content'])
                self.assertEqual(d,before)

    def test_world_translation_and_anchored_reflection_match_complete_rational_expression(self):
        for matrix in ABOVE:
            for old in (IDENTITY,[-1,0,0,-1,0,0]):
                d=self.invoke(dict(command='document.validate',document=source(matrix,True)));item(d)['transform']=old
                moves=[([1,0,0,1,matrix[0]/2**20,matrix[1]/2**20],None),
                       ([-1,0,0,-1,0,0],matrix[4:])]
                for change,anchor in moves:
                    world_change=pivot(change,anchor) if anchor is not None else change
                    expected=matrix_product(inverse(matrix),matrix_product(world_change,matrix_product(matrix,old)))
                    op=dict(op='transform',id='thin',space='world',matrix=change)
                    if anchor is not None:op['anchor']=anchor
                    result=self.edit(d,op)
                    self.assertEqual(item(result)['transform'],list(map(float,expected)))
                    self.assertEqual(item(result)['content'],item(d)['content'])

    def test_moderate_transform_expressions_preserve_bounded_exact_control_error(self):
        for parent in ([1.1,.03,-.04,.9,12.25,-23.5],[2,.5,-1,1,20,4],[-1,0,0,1,40,30]):
            d=source(parent,True);old=[.9,.1,-.2,1.2,3.125,-2.5];item(d)['transform']=old
            change=[1.01,.02,-.01,.99,.125,-.25];anchor=[13.25,9.5]
            for space in ('local','world','replace'):
                anchored=pivot(change,anchor)
                expected=(anchored if space=='replace' else matrix_product(old,anchored) if space=='local' else
                    matrix_product(inverse(parent),matrix_product(anchored,matrix_product(parent,old))))
                result=self.edit(d,dict(op='transform',id='thin',space=space,matrix=change,anchor=anchor))
                actual=list(map(F,item(result)['transform']))
                for x in (-65536,65536):
                    for y in (-65536,65536):
                        for axis in (0,1):
                            error=(actual[axis]-expected[axis])*x+(actual[axis+2]-expected[axis+2])*y+actual[axis+4]-expected[axis+4]
                            self.assertLessEqual(abs(error),F('1e-9'))

    def test_scalar_and_artwork_mask_linking_preserve_cancelling_world_placement(self):
        for matrix in ([1000,1000,1000,1000.00390625,12.25,-23.5],
                       [7000,7000,7000,7000.00390625,0,0],
                       [8191,8191,8191,8191.00390625,0,0]):
            for field,prefix in (('mask','mask'),('artwork_mask','artwork_mask')):
                d=document(matrix)
                if field=='mask':
                    item(d)[field]=dict(width=1,height=1,gray_hex='a7',linked=False,transform=matrix)
                else:
                    d['items'].append(dict(id='mask-source',content=dict(type='mask_source')))
                    d['items'].append(dict(id='mask-pixels',parent='mask-source',content=dict(
                        type='vector',geometry=dict(shape='rect',x=0,y=0,width=1,height=1),fill=[255,255,255,167])))
                    item(d)[field]=dict(source='mask-source',region=[0,0,1,1],linked=False,transform=matrix)
                d=self.invoke(dict(command='document.validate',document=d))
                before=copy.deepcopy(item(d)[field])
                linked=self.edit(d,dict(op=prefix+'_link',id='thin',linked=True))
                self.assertEqual(item(linked)[field]['transform'],IDENTITY)
                self.assertTrue(item(linked)[field]['linked'])
                for key,value in before.items():
                    if key not in ('transform','linked'):self.assertEqual(item(linked)[field][key],value)
                stable=self.edit(linked,dict(op=prefix+'_transform',id='thin',space='world',matrix=IDENTITY))
                self.assertEqual(item(stable)[field],item(linked)[field])
                moved=self.edit(linked,dict(op=prefix+'_transform',id='thin',space='world',
                    matrix=[1,0,0,1,matrix[0]/2**20,matrix[1]/2**20]))
                self.assertEqual(item(moved)[field]['transform'],[1,0,0,1,2**-20,0])
                unlinked=self.edit(linked,dict(op=prefix+'_link',id='thin',linked=False))
                self.assertEqual(item(unlinked)[field],before)

    def test_visible_parented_artwork_keeps_pixels_and_controls_across_no_op_edits(self):
        import base64
        for parent in ([10000,10000,10000,10000.03125,4,4],
                       [-8192,8192,-8192,8191.96875,35,4]):
            d=source(parent);inv=inverse(parent)
            points=[[float(inv[0]*x+inv[2]*y+inv[4]),float(inv[1]*x+inv[3]*y+inv[5])]
                    for x,y in [(4,4),(20,4),(20,20),(4,20)]]
            item(d)['content']['geometry']=dict(shape='path',commands=[dict(
                verb='move' if i==0 else 'line',to=p) for i,p in enumerate(points)]+[dict(verb='close')])
            d=self.invoke(dict(command='document.validate',document=d))
            def pixels(document):
                p=self.invoke(dict(command='document.export',document=document,format='png',
                    render_options=dict(antialias='supersample4')))
                return editing.png_pixels(base64.b64decode(p['data']))[:3]
            before=pixels(d)
            # The inverse-placed source covers a visible 16-by-16 square.
            self.assertGreater(sum(before[2][3::4]),200*255)
            linked=self.edit(d,dict(op='reparent',id='thin',parent='parent'))
            stable=self.edit(linked,dict(op='transform',id='thin',space='world',matrix=IDENTITY))
            detached=self.edit(stable,dict(op='reparent',id='thin',parent=None))
            self.assertEqual(item(linked)['transform'],IDENTITY)
            self.assertEqual(item(detached)['transform'],parent)
            for result in (linked,stable,detached):
                self.assertEqual(pixels(result),before)
                self.assertEqual(item(result)['content'],item(d)['content'])

    def test_cli_and_mcp_reparent_retry_undo_and_failed_edit_preserve_history(self):
        client=Client();self.addCleanup(client.close);client.initialize()
        for transport in ('cli','mcp'):
            with tempfile.TemporaryDirectory() as root:
                session=dict(session_root=root,session_id='relative')
                def call(command,**kw):
                    args=dict(**session,**kw)
                    return (invoke(dict(command=command,**args)) if transport=='cli' else
                            client.tool(command,**args)['structuredContent'])
                created=call('session.create',request_id='create',document=source(ABOVE[0]))
                self.assertTrue(created['ok'],created)
                args=dict(request_id='reparent',expected_revision=0,
                    action=dict(type='edit',operations=[dict(op='reparent',id='thin',parent='parent')]))
                edited=call('session.apply',**args);self.assertTrue(edited['ok'],edited)
                self.assertEqual(item(edited['result']['document'])['transform'],IDENTITY)
                self.assertTrue(call('session.apply',**args)['result']['replayed'])
                history=call('session.history',limit=128)
                failure=call('session.apply',request_id='bad',expected_revision=1,
                    action=dict(type='edit',operations=[dict(op='transform',id='thin',space='replace',matrix=BELOW[0])]))
                self.assertFalse(failure['ok']);self.assertEqual(failure['error']['code'],'UNSUPPORTED')
                self.assertEqual(call('session.history',limit=128),history)
                self.assertEqual(call('session.read')['result']['document'],edited['result']['document'])
                undo=call('session.apply',request_id='undo',expected_revision=1,action=dict(type='undo'))
                self.assertEqual(undo['result']['document']['items'],created['result']['document']['items'])
                self.assertTrue(call('session.verify')['result']['valid'])

    def test_capabilities_identify_relative_edit_scope_and_rounding_contract(self):
        info=self.invoke(dict(command='capabilities'))['coordinate_precision']['relative_edits']
        self.assertEqual(set(info['operations']),{'reparent','transform','mask_link','mask_transform',
                                               'artwork_mask_link','artwork_mask_transform'})
        self.assertEqual(info['maximum_factors'],8)
        self.assertEqual(info['fast_coefficient_point_error'],1e-9)
        self.assertEqual(info['point_coordinate_absolute_limit'],65536)
        self.assertFalse(info['source_geometry_changed'])
        self.assertIn('world_recomposition_point_arithmetic_and_sampling_are_separate',info['error_scope'])


if __name__=='__main__':unittest.main()
