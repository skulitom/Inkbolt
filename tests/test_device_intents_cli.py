"""Original reference-medium equations and actual four-intent agent delivery."""
from fractions import Fraction as F
import copy
import struct
import unittest
import test_editing_cli as editing
import test_swatches_cli as swatches
import test_swatch_profiles_cli as managed
import test_vector_plates_cli as plates
import test_print_cmyk_cli as printing
import test_proof_cli as proof
from test_device_color_cli import endpoint,independent_table,gray_profile
from test_profiles_cli import embedded,linear_profile
from test_sample_profiles_cli import tags_of,repack
from cmyk_fixtures import cmyk_profile
import gamut_fixtures
import test_native_images_cli as images
import test_native_adjustments_cli as adjustments
from test_samples_cli import layer

WHITE=list(map(F,['.9642','1','.8249']));BLACK=list(map(F,['.003357','.003479','.002869']))
INTENTS={'perceptual':0,'relative_colorimetric':1,'absolute_colorimetric':1,'saturation':2}


class DeviceIntentTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    document=swatches.SwatchTests.document
    plates=plates.VectorPlateTests.plates
    def convert(self,source,destination,points,intent):return self.invoke(dict(command='color.convert',source=source,destination=destination,values=points,intent=intent))
    def close(self,actual,expected):
        for a,b in zip(actual,expected):self.assertAlmostEqual(a,float(b),places=13)

    def test_v4_reference_medium_bridge_preserves_white_with_exact_xyz_affine_equations(self):
        raw=cmyk_profile(intents=True);tags=tags_of(raw);target=endpoint('cmyk',embedded(raw))
        points=[[0,0,0],[50,0,0],[100,0,0]]
        for intent in ['perceptual','saturation']:
            result=self.convert(endpoint('lab'),target,points,intent)
            self.assertEqual(result['pcs_adjustment']['model'],'colourimetric_to_v4_reference_medium')
            for point,s in zip(points,result['samples']):
                xyz=list(map(F,proof.xyz(point)));mapped=[v*(1-b/w)+b for v,b,w in zip(xyz,BLACK,WHITE)]
                self.close(s['destination_pcs_xyz'],mapped)
                expected=independent_table(tags[b'B2A'+str(INTENTS[intent]).encode()],[v*F(32768,65535) for v in mapped]);self.close(s['values'],expected)
            self.close(result['samples'][-1]['destination_pcs_xyz'],WHITE)
            reverse=self.convert(target,endpoint('lab'),[[.125,.25,.5,.75]],intent)
            self.assertEqual(reverse['pcs_adjustment']['model'],'v4_reference_medium_to_colourimetric')
            s=reverse['samples'][0];self.close(s['destination_pcs_xyz'],[(F(v)-b)/(1-b/w) for v,b,w in zip(s['source_pcs_xyz'],BLACK,WHITE)])

    def test_matrix_gray_and_legacy_connections_report_their_domains_without_unrequested_adjustment(self):
        for space,raw,values in [('rgb',linear_profile(),[.25,.5,.75]),('gray',gray_profile(),[.5])]:
            for intent in ['perceptual','saturation']:
                result=self.convert(endpoint(space,embedded(raw)),endpoint(space,embedded(raw)),[values],intent)
                self.assertEqual(result['pcs_adjustment']['model'],'identity');self.close(result['samples'][0]['values'],values)
        source=linear_profile(lut=True);destination=linear_profile()
        for sv,dv in [(2,2),(2,4),(4,2)]:
            a=bytearray(source);b=bytearray(destination);a[8]=sv;b[8]=dv
            result=self.convert(endpoint('rgb',embedded(a)),endpoint('rgb',embedded(b)),[[.25,.5,.75]],'perceptual')
            self.assertEqual(result['pcs_adjustment']['model'],'legacy_v2_direct_PCS_no_black_rescaling')
            self.assertEqual(result['samples'][0]['destination_pcs_xyz'],result['samples'][0]['source_pcs_xyz'])

    def test_native_rgb_profile_tints_select_each_print_table_and_reference_connection(self):
        source=linear_profile(gamma=2);target=cmyk_profile(intents=True);src=tags_of(source);dst=tags_of(target)
        components=[.125,.5,.875];d=self.document({'ink':managed.managed('rgb',components,embedded(source))},[swatches.rectangle(fill=swatches.paint(tint=.5))],w=8,h=8)
        tinted=[(F(1)+F(v))/2 for v in components];columns=[[F(struct.unpack_from('>i',src[k],8+i*4)[0],65536) for i in range(3)] for k in [b'rXYZ',b'gXYZ',b'bXYZ']]
        xyz=[sum(columns[c][i]*tinted[c]**2 for c in range(3)) for i in range(3)]
        outputs={}
        for intent,index in INTENTS.items():
            result=self.plates(d,profile=embedded(target),intent=intent,samples=[[1,1]])
            actual=result['samples'][0]['ink_fractions'];mapped=[v*(1-b/w)+b for v,b,w in zip(xyz,BLACK,WHITE)] if intent in ['perceptual','saturation'] else xyz
            self.close(actual,independent_table(dst[b'B2A'+str(index).encode()],[v*F(32768,65535) for v in mapped]));outputs[intent]=actual
        self.assertNotEqual(outputs['perceptual'],outputs['saturation']);self.assertNotEqual(outputs['perceptual'],outputs['relative_colorimetric'])

    def test_flattened_pdf_intents_and_colourimetric_proof_use_actual_delivered_inks(self):
        raw=gamut_fixtures.profile(pcs='XYZ ');tags=tags_of(raw)
        d=self.document(items=[swatches.rectangle(fill=[0,0,0,255],w=4,h=4)],w=4,h=4)
        for intent in INTENTS:
            options=dict(profile=embedded(raw),matte=[255,255,255],intent=intent)
            artifact=self.invoke(dict(command='document.export',document=d,format='pdf',pdf_options=dict(print=options)))
            pdf,images=printing.images(artifact);actual=images[0]['stream'];xyz=BLACK if intent in ['perceptual','saturation'] else [F(0)]*3
            wanted=independent_table(tags[b'B2A'+str(INTENTS[intent]).encode()],[v*F(32768,65535) for v in xyz]);expected=bytes(int(v*255+F(1,2)) for v in wanted)
            self.assertEqual(actual,expected*16)
            observed=self.invoke(dict(command='document.proof',document=d,options=dict(print=options,view_intent='relative_colorimetric',delta_e76_threshold=10,gamut='required',samples=[[0,0]])))
            self.assertEqual(bytes(observed['samples'][0]['cmyk8']),expected);self.assertEqual(observed['gamut']['status'],'available')
            self.assertEqual(artifact['color_profile']['intent'],intent)

    def test_native_profiled_image_precision_and_alpha_survive_all_separation_intents(self):
        source=linear_profile(gamma=2);target=cmyk_profile(intents=True);src=tags_of(source);dst=tags_of(target)
        columns=[[F(struct.unpack_from('>i',src[k],8+i*4)[0],65536) for i in range(3)] for k in [b'rXYZ',b'gXYZ',b'bXYZ']]
        for depth,maximum,fmt in [('u8',255,'B'),('u16',65535,'H'),('f32',1,'f')]:
            values=[.125,.5,.875,.625];stored=[round(v*maximum) for v in values] if maximum!=1 else values
            d=images.NativeImageTests.document(self,1,1);d['items']=[layer(stored,depth=depth,w=1)];grid=d['items'][0]['content']['grid'];grid.update(encoding='profiled_rgb',profile=embedded(source));before=copy.deepcopy(d)
            rgb=struct.unpack('<'+fmt*4,bytes.fromhex(grid['data_hex']));rgb=[F(v)/maximum for v in rgb]
            xyz=[sum(columns[c][i]*rgb[c]**2 for c in range(3)) for i in range(3)]
            for intent,index in INTENTS.items():
                result=images.NativeImageTests.planes(self,d,profile=embedded(target),intent=intent,samples=[[0,0]])
                mapped=[v*(1-b/w)+b for v,b,w in zip(xyz,BLACK,WHITE)] if intent in ['perceptual','saturation'] else xyz
                expected=independent_table(dst[b'B2A'+str(index).encode()],[v*F(32768,65535) for v in mapped])
                for a,b in zip(result['samples'][0]['ink_fractions'],expected):self.assertAlmostEqual(a,float(b*rgb[3]),delta=3e-6)
                self.assertEqual(d,before)

    def test_adjustments_observe_colourimetric_ink_but_reseparate_with_selected_intent(self):
        target=cmyk_profile(intents=True);tags=tags_of(target)
        d=images.NativeImageTests.document(self,1,1);d['items']=[images.fill('p',plates.named('process'),box=(0,0,1,1)),adjustments.adjustment(operators=[dict(type='threshold',level=1)])]
        for intent,index in INTENTS.items():
            result=images.NativeImageTests.planes(self,d,profile=embedded(target),intent=intent,samples=[[0,0]],adjustment_policy=adjustments.POLICY)
            xyz=BLACK if intent in ['perceptual','saturation'] else [F(0)]*3
            expected=independent_table(tags[b'B2A'+str(index).encode()],[v*F(32768,65535) for v in xyz]);self.close(result['samples'][0]['ink_fractions'],expected)
            receipt=result['coverage_sources']['adjustments'];self.assertEqual(receipt['separation_intent'],intent);self.assertEqual(receipt['observation_intent'],'absolute_colorimetric' if intent=='absolute_colorimetric' else 'relative_colorimetric')


if __name__=='__main__':unittest.main()
