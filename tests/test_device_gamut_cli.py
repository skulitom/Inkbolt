"""Profile-supplied gamut classification from actual retained source coordinates."""
import copy
from fractions import Fraction as F
import json
import struct
import unittest
import gamut_fixtures as fixtures
import test_editing_cli as editing
import test_swatch_profiles_cli as swatches
from test_device_color_cli import endpoint,gray_profile
from test_profiles_cli import embedded,linear_profile
from test_sample_profiles_cli import tags_of,repack,intent_profile
from test_proof_cli import xyz as lab_xyz
from test_mcp import Client


class DeviceGamutTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def convert(self,source,destination,values,expected=0,**kw):
        return self.invoke(dict(command='color.convert',source=source,destination=destination,values=values,gamut=kw.pop('gamut','required'),**kw),expected)

    def test_lab_points_have_independent_classification_and_overflow_without_clamping(self):
        target=endpoint('cmyk',embedded(fixtures.profile(pcs='XYZ ')))
        points=[[50,0,0],[100,100,0],[100,127,-128]]
        result=self.convert(endpoint('lab'),target,points)
        self.assertEqual([s['gamut']['classification'] for s in result['samples']],['in_gamut','out_of_gamut','outside_pcs_encoding'])
        for p,s in zip(points,result['samples']):
            xyz=lab_xyz(p);q=[v*32768/65535 for v in xyz]
            for actual,wanted in zip(s['gamut']['encoded_pcs'],q):self.assertAlmostEqual(actual,wanted,places=13)
            if max(q)<=1:self.assertAlmostEqual(s['gamut']['gamut_value'],max(0,q[0]-.5)*2*32768/65535,places=13)
        self.assertGreater(result['samples'][-1]['clipped_components'],0);self.assertIsNone(result['samples'][-1]['gamut']['gamut_value'])
        self.assertFalse(result['source_changed'])

    def test_perceptual_and_saturation_diagnostics_use_separate_colourimetric_source_tables(self):
        raw=intent_profile();target=fixtures.profile(pcs='XYZ ',table=fixtures.modern_table(lambda q:q[0]))
        for intent,table in [('relative_colorimetric','A2B1'),('perceptual','A2B0'),('saturation','A2B2')]:
            result=self.convert(endpoint('rgb',embedded(raw)),endpoint('cmyk',embedded(target)),[[.2,.4,.6]],intent=intent)
            self.assertEqual(result['source']['selected_table'],table);self.assertEqual(result['gamut']['source']['selected_table'],'A2B1');self.assertEqual(result['gamut']['intent'],'relative_colorimetric')
            # Constant original A2B1 fixture stores X directly as an ICC u1.15 number.
            stored=round(.9642*.4*32768);wanted=F(stored,65535)
            self.assertAlmostEqual(result['samples'][0]['gamut']['gamut_value'],float(wanted),places=14)
            if intent!='relative_colorimetric':self.assertNotEqual(result['samples'][0]['source_pcs_xyz'],result['samples'][0]['gamut']['destination_relative_pcs_xyz'])

    def test_absolute_gamut_coordinates_apply_each_declared_media_white_once(self):
        source=intent_profile(white=(.75,.5,.25));target=fixtures.profile(pcs='XYZ ',white=(.5,.75,.5),table=fixtures.modern_table(lambda q:q[0]))
        result=self.convert(endpoint('rgb',embedded(source)),endpoint('cmyk',embedded(target)),[[.2,.4,.6]],intent='absolute_colorimetric')
        s=result['samples'][0];expected=[F(round(v*.4*32768),32768)*F(a)/F(b) for v,a,b in zip([.9642,1,.8249],[.75,.5,.25],[.5,.75,.5])]
        for got,want in zip(s['gamut']['destination_relative_pcs_xyz'],expected):self.assertAlmostEqual(got,float(want),places=14)
        self.assertAlmostEqual(s['gamut']['gamut_value'],float(expected[0]*F(32768,65535)),places=14)
        self.assertEqual(result['gamut']['profile']['source_to_profile_relative_scale'],[1,1,1])

    def test_rgb_gray_missing_and_off_policies_never_invent_gamut_membership(self):
        points=[[50,0,0]]
        for space,base in [('rgb',linear_profile()),('gray',gray_profile())]:
            for mode in ['if_available','off']:
                r=self.convert(endpoint('lab'),endpoint(space,embedded(base)),points,gamut=mode)
                self.assertEqual(r['gamut']['status'],'off' if mode=='off' else 'unavailable');self.assertNotIn('gamut',r['samples'][0])
            self.assertEqual(self.convert(endpoint('lab'),endpoint(space,embedded(base)),points,1)['code'],'GAMUT_UNAVAILABLE')
            tags=tags_of(base);tags[b'gamt']=fixtures.modern_table(lambda q:0)
            r=self.convert(endpoint('lab'),endpoint(space,embedded(repack(base[:128],tags))),points)
            self.assertEqual(r['samples'][0]['gamut']['classification'],'in_gamut')
        self.assertEqual(self.convert(endpoint('lab'),endpoint('lab'),points,1)['code'],'GAMUT_UNAVAILABLE')

    def test_swatch_conversion_receipts_and_mcp_keep_gamut_evidence_with_original_values(self):
        helper=swatches.SwatchProfileTests();d=helper.document({'ink':swatches.managed('lab',[50,0,0])});before=copy.deepcopy(d)
        operation=dict(op='swatch_profile',id='ink',action=dict(type='convert',destination=endpoint('cmyk',embedded(fixtures.profile())),gamut='required'))
        response=self.invoke(dict(command='document.edit',document=d,expected_revision=0,operations=[operation]))
        self.assertIn('in_gamut',json.dumps(response));self.assertEqual(d,before)
        c=Client();self.addCleanup(c.close);c.initialize()
        kwargs=dict(source=endpoint('lab'),destination=endpoint('cmyk',embedded(fixtures.profile())),values=[[50,0,0]],gamut='required')
        self.assertEqual(c.success('color.convert',**kwargs),self.invoke(dict(command='color.convert',**kwargs)))
        self.assertEqual(self.invoke(dict(command='color.convert',**kwargs,control=dict(timeout_ms=0)),1)['code'],'TIMEOUT')


if __name__=='__main__':unittest.main()
