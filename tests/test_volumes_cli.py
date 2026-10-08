"""Retained dimensional artwork with independent inverse-ray visibility and lighting."""
import base64
import copy
import json
import tempfile
import unittest
import test_editing_cli as editing
import test_variants_cli as variants
from test_mcp import Client
import volume_reference as reference


def geometry(loops):
    commands=[]
    for p in loops:
        commands.append(dict(verb='move',to=p[0]));commands.extend(dict(verb='line',to=q) for q in p[1:]);commands.append(dict(verb='close'))
    return dict(shape='path',commands=commands)
def original(loops=None):
    if loops is None:loops=[[[6,7],[25,7],[25,24],[6,24]]]
    spec=dict(geometry=geometry(loops),depth=8,rotation=[22,35,12],pivot=[16,16,-4],material=dict(type='diffuse',color=[190,100,60],ambient=[.12,.15,.2],lights=[dict(direction=[-.3,-.4,1],color=[1,.8,.6],intensity=1)]))
    return dict(schema_version=2,id='dimensional-icon',kind='vector',width=36,height=36,color_space='srgb',items=[dict(id='solid',content=dict(type='volume',volume=spec))]),loops


class VolumeTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    edit=variants.VariantTests.edit
    def valid(self,d):return self.invoke(dict(command='document.validate',document=d))
    def image(self,d):return editing.png_pixels(base64.b64decode(self.invoke(dict(command='document.export',document=d,format='png',render_options=dict(antialias='none')))['data']))[2]
    def check_rays(self,d,loops):
        spec=d['items'][0]['content']['volume'];expected=reference.pixels(spec,loops,d['width'],d['height'])
        report=self.invoke(dict(command='volume.inspect',document=d,id='solid'));projected,distances=reference.projected(report['faces'],d['width'],d['height'])
        self.assertLessEqual(max(abs(a-b) for a,b in zip(projected,expected)),1)
        actual=self.image(d)
        # Existing binary preview edges use 26.6 vertex quantization. Two subpixel
        # quanta bound the excluded boundary band for these small original fixtures;
        # all ideal geometry samples above remain checked, including this band.
        interior=[abs(a-b) for i,(a,b) in enumerate(zip(actual,expected)) if distances[i//4]>1/32]
        self.assertGreater(len(interior),len(actual)*.85);self.assertLessEqual(max(interior),1)
        return report
    def test_box_rotation_visibility_and_linear_lighting_against_inverse_rays(self):
        d,loops=original();d=self.valid(d);spec=d['items'][0]['content']['volume']
        result=self.check_rays(d,loops);self.assertGreaterEqual(len(result['faces']),3);self.assertEqual(result['source'],spec)
    def test_concave_hole_disjoint_and_perspective_occlusion_against_rays(self):
        fixtures=[[[[4,4],[28,4],[28,10],[11,10],[11,23],[28,23],[28,29],[4,29]]],
                  [[[4,4],[28,4],[28,29],[4,29]],[[10,10],[10,23],[22,23],[22,10]]],
                  [[[4,4],[12,4],[12,29],[4,29]],[[21,4],[29,4],[29,29],[21,29]]]]
        for loops in fixtures:
            for camera in [dict(type='orthographic'),dict(type='perspective',principal=[18,18],distance=90,near=10,far=150)]:
                with self.subTest(loops=loops,camera=camera):
                    d,_=original(loops);s=d['items'][0]['content']['volume'];s.update(rotation=[35,-48,16],camera=camera);d=self.valid(d)
                    self.check_rays(d,loops)
    def test_expansion_delivery_and_snapshot_preserve_editable_source(self):
        d,_=original();d=self.valid(d);source=copy.deepcopy(d);expanded=self.edit(d,dict(op='volume_expand',id='solid'))
        self.assertEqual(self.image(d),self.image(expanded));self.assertEqual(expanded['items'][0]['content']['type'],'group')
        self.assertTrue(all(i['content']['type']=='vector' for i in expanded['items'][1:]));self.assertGreater(len(expanded['items']),1)
        svg=self.invoke(dict(command='document.export',document=d,format='svg'));self.assertIn('Dimensional artwork',' '.join(svg['losses']));self.assertIn('<path',svg['data'])
        self.assertEqual(self.invoke(dict(command='document.export',document=d,format='pdf'))['media_type'],'application/pdf')
        self.assertEqual(json.loads(self.invoke(dict(command='document.export',document=d,format='snapshot'))['data']),source)
    def test_zero_depth_two_sided_rotation_and_exact_quarter_turn(self):
        d,loops=original();s=d['items'][0]['content']['volume'];s.update(depth=0,rotation=[0,180,0],material=dict(type='unlit',color=[15,100,230]));d=self.valid(d)
        self.assertEqual(self.image(d),reference.pixels(s,loops,36,36));result=self.invoke(dict(command='volume.inspect',document=d,id='solid'));self.assertEqual(len(result['faces']),1);self.assertEqual(result['faces'][0]['part'],'back')
        s=copy.deepcopy(d['items'][0]['content']['volume']);s['rotation']=[0,90,0];edge=self.edit(d,dict(op='volume',id='solid',volume=s));self.assertFalse(any(self.image(edge)))
    def test_invalid_topology_camera_depth_and_unknown_fields_fail_without_changes(self):
        d,_=original();d=self.valid(d);before=copy.deepcopy(d)
        for change in [dict(depth=-1),dict(camera=dict(type='perspective',principal=[18,18],distance=8,near=1,far=20)),dict(camera=dict(type='perspective',principal=[18,18],distance=100,near=.01,far=200)),dict(geometry=geometry([[[3,3],[25,25],[3,25],[25,3]]]))]:
            s=copy.deepcopy(d['items'][0]['content']['volume']);s.update(change);self.edit(d,dict(op='volume',id='solid',volume=s),expected=1)
        bad=copy.deepcopy(d);bad['items'][0]['content']['volume']['network_material']=True;self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'INVALID_REQUEST');self.assertEqual(d,before)
    def test_mcp_atomic_camera_edit_expand_undo_retry_and_lock(self):
        d,_=original();d=self.valid(d);client=Client();self.addCleanup(client.close);client.initialize()
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='volume');client.success('session.create',**session,request_id='create',document=d)
            s=copy.deepcopy(d['items'][0]['content']['volume']);s['rotation']=[-25,30,45];action=dict(type='edit',operations=[dict(op='volume',id='solid',volume=s)])
            changed=client.success('session.apply',**session,request_id='rotate',expected_revision=0,action=action)['document'];self.assertNotEqual(self.image(changed),self.image(d))
            expanded=client.success('session.apply',**session,request_id='expand',expected_revision=1,action=dict(type='edit',operations=[dict(op='volume_expand',id='solid')]))['document'];self.assertEqual(self.image(changed),self.image(expanded))
            restored=client.success('session.apply',**session,request_id='undo',expected_revision=2,action=dict(type='undo'))['document'];self.assertEqual(restored['items'],changed['items'])
            self.assertTrue(client.success('session.apply',**session,request_id='rotate',expected_revision=0,action=action)['replayed']);self.assertTrue(client.success('session.verify',**session)['valid'])
            self.assertEqual(client.success('volume.inspect',document=restored,id='solid')['source']['rotation'],s['rotation'])
        locked=self.edit(d,dict(op='properties',id='solid',locked=True));self.assertEqual(self.edit(locked,dict(op='volume_expand',id='solid'),expected=1)['code'],'LOCKED')

    def test_evenodd_holes_and_redundant_nonzero_contours_have_correct_walls(self):
        outer=[[4,4],[28,4],[28,29],[4,29]];inner=[[10,10],[22,10],[22,23],[10,23]]
        d,_=original([outer,inner]);s=d['items'][0]['content']['volume'];s['fill_rule']='even_odd';d=self.valid(d)
        self.check_rays(d,[outer,list(reversed(inner))])
        redundant=copy.deepcopy(d);redundant['items'][0]['content']['volume']['fill_rule']='nonzero';redundant=self.valid(redundant)
        single,_=original([outer]);single=self.valid(single);self.assertEqual(self.image(redundant),self.image(single))
        self.assertEqual(len(self.invoke(dict(command='volume.inspect',document=redundant,id='solid'))['faces']),len(self.invoke(dict(command='volume.inspect',document=single,id='solid'))['faces']))

    def test_curved_profile_certificate_material_edit_and_resource_rejection(self):
        d,_=original();s=d['items'][0]['content']['volume'];s['geometry']=dict(shape='ellipse',cx=18,cy=18,rx=10,ry=8);d=self.valid(d)
        report=self.invoke(dict(command='volume.inspect',document=d,id='solid'));self.assertLessEqual(report['source_curve_error_bound'],.1);self.assertGreater(report['profile_edges'],8);self.assertTrue(any(self.image(d)))
        s=copy.deepcopy(d['items'][0]['content']['volume']);s['material']=dict(type='unlit',color=[1,120,220]);changed=self.edit(d,dict(op='volume',id='solid',volume=s))
        self.assertNotEqual(self.image(changed),self.image(d));self.assertEqual(self.image(changed)[3::4],self.image(d)[3::4])
        s['tolerance']=.000001;self.assertEqual(self.edit(d,dict(op='volume',id='solid',volume=s),expected=1)['code'],'RESOURCE_LIMIT')
        s=copy.deepcopy(d['items'][0]['content']['volume']);s['material']['lights']*=9;self.assertEqual(self.edit(d,dict(op='volume',id='solid',volume=s),expected=1)['code'],'INVALID_VOLUME')

    def test_parent_transform_components_masks_and_artboard_export_match_expansion(self):
        d,_=original();d['items'][0].update(transform=[1,.1,.2,1,-2,-1],opacity=.6,clip=dict(geometry=dict(shape='rect',x=5,y=5,width=22,height=22)));d=self.valid(d)
        self.assertEqual(self.image(d),self.image(self.edit(d,dict(op='volume_expand',id='solid'))))
        component=copy.deepcopy(d);component['items'][0]['parent']='definition';component['items'].insert(0,dict(id='definition',content=dict(type='component_source')));component['items'].append(dict(id='copy',content=dict(type='instance',instance=dict(source='definition'))));component=self.valid(component)
        self.assertEqual(self.image(component),self.image(d))
        board=copy.deepcopy(d);board['items'][0]['parent']='page';board['items'].insert(0,dict(id='page',transform=[1,0,0,1,4,3],content=dict(type='frame',frame=dict(role='artboard',width=36,height=36))));board['width']=42;board['height']=42;board=self.valid(board)
        export=self.invoke(dict(command='artboard.export',document=board,format='png',render_options=dict(antialias='none')))['artifacts'][0]['artifact']
        self.assertEqual(editing.png_pixels(base64.b64decode(export['data']))[2],self.image(d))


if __name__=='__main__':unittest.main()
