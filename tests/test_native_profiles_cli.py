"""Native color continuity, public PCS encodings and independent stage equations."""
import copy
from fractions import Fraction as F
import itertools
import struct
import unittest
from cmyk_fixtures import cmyk_profile, separation
from test_profiles_cli import embedded, linear_profile
from test_sample_profiles_cli import tags_of, repack
from test_samples_cli import layer
import test_native_images_cli as images
from test_native_images_cli import MATRIX
from native_profile_fixtures import modern, eight, source_profile, output_profile, curve
from test_proof_cli import lab


class NativeProfileTests(unittest.TestCase):
    invoke=images.NativeImageTests.invoke
    document=images.NativeImageTests.document
    planes=images.NativeImageTests.planes
    samples=images.NativeImageTests.samples
    assertColors=images.NativeImageTests.assertColors

    def test_adjacent_native_codes_survive_both_pcs_families_without_integer_intermediates(self):
        for depth,source,pcs,modern in itertools.product(['u16','f32'],[None,linear_profile(gamma=2)],['XYZ ','Lab '],[False,True]):
            values=[v for k in range(32) for v in ([20000+k,20000,20000,65535] if depth=='u16' else [.3+k*2**-24,.4,.5,1])]
            d=self.document(32,1);d['items']=[layer(values,depth=depth,w=32)]
            if source:d['items'][0]['content']['grid'].update(encoding='profiled_rgb',profile=embedded(source))
            c=[p[0] for p in self.samples(d,profile=embedded(cmyk_profile(pcs=pcs,modern=modern)))]
            self.assertTrue(all(b>a for a,b in zip(c,c[1:])),(depth,pcs,modern,c))
            self.assertLess(max(b-a for a,b in zip(c,c[1:])),min(b-a for a,b in zip(c,c[1:]))*1.02)

    def test_directional_lab_codes_decode_by_table_type_and_preserve_sample_source(self):
        for kind,version in [('legacy',2),('legacy',4),('modern',4),('eight',4)]:
            source=bytearray(source_profile(kind=kind));source[8]=version;source=bytes(source)
            d=self.document(3,1);d['items']=[layer([.2,.4,.6,1,.7,.3,.8,.5,1,0,1,1],depth='f32',w=3)]
            d['items'][0]['content']['grid'].update(encoding='profiled_rgb',profile=embedded(source))
            before=copy.deepcopy(d);p=self.samples(d,profile=embedded(cmyk_profile(pcs='Lab ',modern=True)))
            maximum=255 if kind=='eight' else 65535;scale=65280/65535 if kind=='legacy' else 1
            # Each table axis is independent and affine. Interpolate its exact
            # quantized endpoints, undo legacy encoding, then separate Lab.
            for actual,q in zip(p,[(.2,.4,.6,1),(.7,.3,.8,.5),(1,0,1,1)]):
                encoded=[((1-v)*round(lo*scale*maximum)+v*round(hi*scale*maximum))/maximum/scale for v,lo,hi in zip(q,(.2,.45,.45),(.8,.55,.55))]
                self.assertColors(actual,[v*q[3] for v in separation(encoded)],.00002)
            self.assertEqual(d,before)

    def test_nonseparable_lookup_uses_declared_tensor_interpolation_at_continuous_coordinates(self):
        fn=lambda q:[q[0]*q[1],q[1]*q[2],q[0]*q[2],q[0]*q[1]*q[2]]
        for precision in [1,2]:
            # Product corner samples are exactly 0 or 1 in either precision.
            target=output_profile(modern(fn,4,False,precision=precision))
            source=source_profile(pcs='XYZ ',kind='modern')
            d=self.document(5,1);values=[v for k in range(5) for v in [k/4,.25,.75,1]]
            d['items']=[layer(values,depth='f32',w=5)];d['items'][0]['content']['grid'].update(encoding='profiled_rgb',profile=embedded(source))
            for actual,k in zip(self.samples(d,profile=embedded(target)),range(5)):
                q=[float((1-F(v))*F(round(.1*65535),65535)+F(v)*F(round(.4*65535),65535)) for v in [F(k,4),F(1,4),F(3,4)]]
                self.assertColors(actual,fn(q),1e-12)

    def test_full_modern_stage_order_and_parametric_branches_match_direct_equations(self):
        matrix=[.75,.125,0,0,.75,.125,.125,0,.75,.0625,.03125,.015625]
        inputs=[curve(params=[2]),curve(params=[1,.75,-.125]),curve(params=[1,.5,-.25,.125])]
        middle=[curve(params=[2,1,0,.5,.25]),curve(params=[2,1,0,.5,.25,.125,.0625]),curve(values=[0,32768,65535])]
        fn=lambda q:[.125+.25*q[0],.25+.25*q[1],.0625+.5*q[2],.125+.125*sum(q)]
        target=output_profile(modern(fn,4,False,inputs=inputs,matrix=matrix,middle=middle,ending=[curve(params=[2])]*4))
        source=source_profile(pcs='XYZ ',kind='modern')
        d=self.document(4,1);d['items']=[layer([v for k in range(4) for v in [k/3,.2,.9,1]],depth='f32',w=4)]
        d['items'][0]['content']['grid'].update(encoding='profiled_rgb',profile=embedded(source))
        native=struct.unpack('<16f',bytes.fromhex(d['items'][0]['content']['grid']['data_hex']))
        for p,k in zip(self.samples(d,profile=embedded(target)),range(4)):
            q=[((1-v)*round(.1*65535)+v*round(.4*65535))/65535 for v in native[4*k:4*k+3]]
            q=[q[0]**2,max(0,.75*q[1]-.125),max(0,.5*q[2]-.25)+.125]
            q=[sum(matrix[3*r+c]*q[c] for c in range(3))+matrix[9+r] for r in range(3)]
            q=[q[0]**2 if q[0]>=.25 else .5*q[0],q[1]**2+.125 if q[1]>=.25 else .5*q[1]+.0625,2*q[2]*32768/65535 if q[2]<=.5 else (32768+(2*q[2]-1)*32767)/65535]
            self.assertColors(p,[v*v for v in fn(q)],.000015)
        # The forward table reverses the stage positions: input -> CLUT -> M -> matrix -> output.
        forward=source_profile(pcs='XYZ ',table=modern(lambda q:q,3,True,inputs=[curve(params=[2])]*3,matrix=matrix,middle=[curve(params=[2])]*3,ending=[curve(params=[2])]*3))
        d['items'][0]['content']['grid']['profile']=embedded(forward)
        for p,k in zip(self.samples(d),range(4)):
            q=[v**4 for v in native[4*k:4*k+3]]
            q=[(sum(matrix[3*r+c]*q[c] for c in range(3))+matrix[9+r])**2 for r in range(3)]
            self.assertColors(p,separation(q),.000015)

    def test_source_matrix_table_transfer_and_classic_eight_bit_lab_destination(self):
        source=linear_profile();tags=tags_of(source)
        for channel in [b'r',b'g',b'b']:tags[channel+b'TRC']=curve(values=[0,10000,50000,65535])
        source=repack(source,tags)
        d=self.document(4,1);d['items']=[layer([v for p in [.1,.4,.7,.9] for v in [p,p,p,1]],depth='f32',w=4)]
        d['items'][0]['content']['grid'].update(encoding='profiled_rgb',profile=embedded(source))
        for actual,p in zip(self.samples(d),[.1,.4,.7,.9]):
            t=p*3;i=min(int(t),2);v=((1-(t-i))*[0,10000,50000][i]+(t-i)*[10000,50000,65535][i])/65535
            xyz=[sum(row)*v*32768/65535 for row in MATRIX]
            self.assertColors(actual,separation(xyz),.00001)
        # A Lab8 identity corner table must use the full code range, unlike Lab16.
        target=output_profile(eight(lambda q:[q[0],q[1],q[2],0],4),pcs='Lab ')
        source=source_profile(kind='eight');d['items'][0]['content']['grid']['profile']=embedded(source)
        for actual,p in zip(self.samples(d,profile=embedded(target)),[.1,.4,.7,.9]):
            self.assertColors(actual,[.2+.6*p,(round(.45*255)*(1-p)+round(.55*255)*p)/255,(round(.45*255)*(1-p)+round(.55*255)*p)/255,0],.000001)

    def test_invalid_lookup_stage_ranges_and_ambiguous_pcs_are_explicit(self):
        source=source_profile(pcs='XYZ ',kind='modern');tags=tags_of(source);original=tags[b'A2B1']
        d=self.document(1,1);d['items']=[layer([.3,.4,.5,1],depth='f32',w=1)]
        malformed=[]
        for at,value in [(12,1),(24,0),(28,0),(16,32)]:
            b=bytearray(original);struct.pack_into('>I',b,at,value);malformed.append(bytes(b))
        for table in malformed:
            tags[b'A2B1']=table;d['items'][0]['content']['grid'].update(encoding='profiled_rgb',profile=embedded(repack(source,tags)))
            self.assertIn(self.planes(d,1)['code'],['INVALID_PROFILE','UNSUPPORTED'])
        source=source_profile(pcs='XYZ ',kind='eight');d['items'][0]['content']['grid']['profile']=embedded(source)
        self.assertEqual(self.planes(d,1)['code'],'UNSUPPORTED')

    def test_lab_encoding_boundary_is_clamped_before_declared_input_curves(self):
        # An original, intentionally extreme XYZ chart puts a* above its code
        # range. Clipping must happen before nonlinear profile input curves.
        source=source_profile(pcs='XYZ ',table=modern(lambda q:[.75,.0625,.75],3,True))
        target=output_profile(modern(lambda q:[q[0],q[1],q[2],0],4,False,inputs=[curve(params=[2])]*3),pcs='Lab ')
        d=self.document(1,1);d['items']=[layer([.2,.3,.4,1],depth='f32',w=1)]
        d['items'][0]['content']['grid'].update(encoding='profiled_rgb',profile=embedded(source))
        xyz=[round(v*65535)/32768 for v in [.75,.0625,.75]];l,a,b=lab(xyz)
        self.assertGreater(a,127);q=[l/100,(a+128)/255,(b+128)/255]
        self.assertColors(self.samples(d,profile=embedded(target))[0],[max(0,min(1,v))**2 for v in q]+[0],1e-12)

    def test_classic_xyz_matrix_precedes_input_tables_and_default_source_intent_is_used(self):
        source=source_profile(pcs='XYZ ',kind='modern');tags=tags_of(source);tags.pop(b'A2B1');source=repack(source,tags)
        target=cmyk_profile();tags=tags_of(target);table=bytearray(tags[b'B2A1'])
        matrix=[.75,.125,0,0,.75,.125,.125,0,.75]
        for i,v in enumerate(matrix):struct.pack_into('>i',table,12+4*i,round(v*65536))
        tags[b'B2A1']=bytes(table);target=repack(target,tags)
        d=self.document(1,1);d['items']=[layer([.25,.5,.75,1],depth='f32',w=1)]
        d['items'][0]['content']['grid'].update(encoding='profiled_rgb',profile=embedded(source))
        q=[((1-v)*round(.1*65535)+v*round(.4*65535))/65535 for v in [.25,.5,.75]]
        q=[sum(matrix[3*r+c]*q[c] for c in range(3)) for r in range(3)]
        self.assertColors(self.samples(d,profile=embedded(target))[0],separation(q),.000015)


if __name__=='__main__':unittest.main()
