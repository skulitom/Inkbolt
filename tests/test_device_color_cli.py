"""Original device profile connections, independent equations and strict policies."""
import copy
from fractions import Fraction as F
import hashlib
import itertools
import math
import struct
import unittest
import test_editing_cli as editing
from test_profiles_cli import builtin, embedded, linear_profile
from test_sample_profiles_cli import repack, tags_of, intent_profile, solve3
from cmyk_fixtures import lookup, cmyk_profile
from test_proof_cli import xyz as lab_xyz
from test_mcp import Client

INTENTS={'perceptual':0,'relative_colorimetric':1,'absolute_colorimetric':1,'saturation':2}
WHITE=[.9642,1,.8249]
def endpoint(space,profile=None,**kw):return dict(space=space,**(dict(profile=profile) if profile else {}),**kw)
def gray_profile(pcs='XYZ ',curve=None):
    base=linear_profile();header=bytearray(base[:128]);header[16:24]=b'GRAY'+pcs.encode();tags={k:v for k,v in tags_of(base).items() if k in [b'desc',b'cprt',b'wtpt']}
    tags[b'kTRC']=curve or b'curv'+bytes(4)+struct.pack('>IH',1,512)
    return repack(header,tags)
def independent_table(tag,point):
    n,m,g=tag[8:11];assert tag[:4]==b'mft2' and len(point)==n;ni,no=struct.unpack_from('>HH',tag,48);assert ni==no==2
    start=52+ni*n*2;values=struct.unpack_from('>'+str(g**n*m)+'H',tag,start);lo=[min(int(F(v)*(g-1)),g-2) for v in point];t=[F(v)*(g-1)-a for v,a in zip(point,lo)];out=[F(0)]*m
    for corner in itertools.product([0,1],repeat=n):
        at=0;weight=F(1)
        for i,c in enumerate(corner):at=at*g+lo[i]+c;weight*=t[i] if c else 1-t[i]
        for c in range(m):out[c]+=F(values[at*m+c],65535)*weight
    return out

class DeviceColorTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def convert(self,source,destination,values,expected=0,**kw):return self.invoke(dict(command='color.convert',source=source,destination=destination,values=values,**kw),expected)
    def test_clipping_reports_actual_destination_curve_range(self):
        curve=b'curv'+bytes(4)+struct.pack('>IHH',2,16384,49152)
        raw=gray_profile('Lab ',curve)
        result=self.convert(endpoint('lab'),endpoint('gray',embedded(raw)),[[0,0,0],[50,0,0],[100,0,0]])
        self.assertEqual([s['clipped_components'] for s in result['samples']],[1,0,1])
        self.assertEqual(result['samples'][0]['values'],[0]);self.assertEqual(result['samples'][2]['values'],[1])
        self.assertAlmostEqual(result['samples'][1]['values'][0],float((F(1,2)-F(16384,65535))/F(32768,65535)),places=14)
    def test_rgb_matrix_source_and_destination_match_exact_rational_algebra(self):
        a=linear_profile(gamma=2);b=linear_profile();tags=tags_of(a);columns=[[F(struct.unpack_from('>i',tags[k],8+i*4)[0],65536) for i in range(3)] for k in [b'rXYZ',b'gXYZ',b'bXYZ']];rows=list(map(list,zip(*columns)))
        points=[[0,0,0],[1,1,1],[.125,.5,.875],[.9,.4,.03]]
        for intent in INTENTS:
            r=self.convert(endpoint('rgb',embedded(a)),endpoint('rgb',embedded(b)),points,intent=intent)
            for sample,p in zip(r['samples'],points):
                xyz=[sum(columns[c][i]*F(p[c])**2 for c in range(3)) for i in range(3)];expected=solve3(rows,xyz)
                for x,y in zip(sample['source_pcs_xyz'],xyz):self.assertAlmostEqual(x,float(y),places=14)
                for x,y in zip(sample['values'],expected):self.assertAlmostEqual(x,float(y),places=14)
            self.assertEqual(r['source']['profile_sha256'],hashlib.sha256(a).hexdigest())
    def test_cmyk_four_dimensional_tables_and_intents_match_rational_tensor(self):
        raw=cmyk_profile(intents=True);tags=tags_of(raw);points=[[.1,.2,.3,.4],[0,0,0,0],[1,1,1,1],[.875,.375,.625,.125]]
        for intent,index in INTENTS.items():
            r=self.convert(endpoint('cmyk',embedded(raw)),endpoint('cmyk',embedded(raw)),points,intent=intent)
            self.assertEqual(r['source']['selected_table'],'A2B'+str(index));self.assertEqual(r['destination']['selected_table'],'B2A'+str(index))
            for sample,p in zip(r['samples'],points):
                pcs=independent_table(tags[b'A2B'+str(index).encode()],p);wanted=independent_table(tags[b'B2A'+str(index).encode()],pcs)
                for x,y in zip(sample['source_pcs_xyz'],pcs):self.assertAlmostEqual(x,float(y*F(65535,32768)),places=14)
                for x,y in zip(sample['values'],wanted):self.assertAlmostEqual(x,float(y),places=14)
    def test_modern_four_input_and_three_to_gray_tables_preserve_all_dimensions(self):
        raw=cmyk_profile(modern=True);tags=tags_of(raw);model=lambda q:[.1+.1*q[0]+.2*q[1]+.1*q[2]*q[3],.3+.2*q[3],.15+.1*q[1]*q[2]]
        for i in range(3):tags[b'A2B'+str(i).encode()]=lookup(4,3,model,modern=True,forward=True,grid=3)
        modern=repack(raw[:128],tags);classic_tags=dict(tags)
        for i in range(3):classic_tags[b'A2B'+str(i).encode()]=lookup(4,3,model,grid=3)
        classic=repack(raw[:128],classic_tags);points=[[.125,.375,.625,.875],[.8,.1,.9,.25]]
        a=self.convert(endpoint('cmyk',embedded(modern)),endpoint('lab'),points);b=self.convert(endpoint('cmyk',embedded(classic)),endpoint('lab'),points);self.assertEqual(a['samples'],b['samples'])
        gray=gray_profile();t=tags_of(gray)
        for i in range(3):t[b'B2A'+str(i).encode()]=lookup(3,1,lambda q:[.2+.2*q[0]+.3*q[1]+.1*q[2]],modern=True)
        target=repack(gray[:128],t);r=self.convert(endpoint('cmyk',embedded(modern)),endpoint('gray',embedded(target)),points);self.assertEqual(r['destination']['selected_table'],'B2A1')
        for s in r['samples']:
            q=[F(v)*F(32768,65535) for v in s['source_pcs_xyz']];ref=independent_table(lookup(3,1,lambda q:[.2+.2*q[0]+.3*q[1]+.1*q[2]]),q);self.assertAlmostEqual(s['values'][0],float(ref[0]),places=14)
    def test_gray_xyz_and_lab_curves_are_distinct_and_roundtrip(self):
        values=[[0],[.125],[.5],[1]]
        for pcs in ['XYZ ','Lab ']:
            raw=gray_profile(pcs);r=self.convert(endpoint('gray',embedded(raw)),endpoint('lab'),values)
            for s,v in zip(r['samples'],values):
                wanted=lab_xyz([v[0]**2*100,0,0]) if pcs=='Lab ' else [x*v[0]**2 for x in WHITE]
                for a,b in zip(s['source_pcs_xyz'],wanted):self.assertAlmostEqual(a,b,places=12)
            back=self.convert(endpoint('lab'),endpoint('gray',embedded(raw)),[s['values'] for s in r['samples']])
            for s,v in zip(back['samples'],values):self.assertAlmostEqual(s['values'][0],v[0],places=11)
    def test_curve_inverse_plateaus_and_descending_tables_have_defined_endpoints(self):
        for curve,targets,expected in [([0,32768,32768,65535],[[50,0,0],[100,0,0]],[2/3,1]),([0,65535,65535],[[100,0,0],[0,0,0]],[.5,0]),([65535,32768,0],[[100,0,0],[0,0,0]],[0,1])]:
            raw=gray_profile('Lab ',b'curv'+bytes(4)+struct.pack('>I',len(curve))+struct.pack('>'+str(len(curve))+'H',*curve))
            if len(curve)==4:targets[0][0]=32768/65535*100
            r=self.convert(endpoint('lab'),endpoint('gray',embedded(raw)),targets)
            for s,v in zip(r['samples'],expected):self.assertAlmostEqual(s['values'][0],v,places=12)
    def test_absolute_media_white_scaling_table_selection_and_fallback(self):
        raw=intent_profile(white=(.75,.5,.25));tag=tags_of(raw);tag.pop(b'A2B1');fallback=repack(raw[:128],tag)
        for intent in ['relative_colorimetric','absolute_colorimetric']:
            r=self.convert(endpoint('rgb',embedded(fallback)),endpoint('lab'),[[.2,.4,.6]],intent=intent);s=r['samples'][0];self.assertEqual(r['source']['selected_table'],'A2B0')
            factor=[F(x)/F(str(w)) for x,w in zip([.75,.5,.25],WHITE)] if intent=='absolute_colorimetric' else [1]*3
            for x,y,f in zip(s['destination_pcs_xyz'],s['source_pcs_xyz'],factor):self.assertAlmostEqual(x,y*float(f),places=14)
        tag.pop(b'A2B0');broken=repack(raw[:128],tag);self.assertEqual(self.convert(endpoint('rgb',embedded(broken)),endpoint('lab'),[[0,0,0]],1)['code'],'UNSUPPORTED_PROFILE_INTENT')
    def test_untagged_mismatched_profiles_and_invalid_curves_fail_explicitly(self):
        for space,values in [('rgb',[[0,0,0]]),('gray',[[.5]]),('cmyk',[[0,0,0,0]])]:self.assertEqual(self.convert(endpoint(space),endpoint('lab'),values,1)['code'],'UNTAGGED_COLOR')
        assumed=self.convert(endpoint('rgb',untagged='assume_srgb'),endpoint('lab'),[[.3,.4,.5]]);explicit=self.convert(endpoint('rgb',builtin('srgb')),endpoint('lab'),[[.3,.4,.5]]);self.assertEqual(assumed['samples'],explicit['samples']);self.assertEqual(assumed['source']['untagged_assumption'],'srgb')
        for space in ['gray','cmyk']:self.convert(endpoint(space,builtin('srgb')),endpoint('lab'),[[0]*({'gray':1,'cmyk':4}[space])],1)
        for curve in [[0,65535,0],[1200,1200]]:
            raw=gray_profile(curve=b'curv'+bytes(4)+struct.pack('>I',len(curve))+struct.pack('>'+str(len(curve))+'H',*curve));self.assertEqual(self.convert(endpoint('lab'),endpoint('gray',embedded(raw)),[[50,0,0]],1)['code'],'UNSUPPORTED_PROFILE_CURVE')
    def test_bounded_samples_components_clipping_and_agent_controls(self):
        source=endpoint('lab');target=endpoint('rgb',builtin('srgb'));before=copy.deepcopy([source,target]);r=self.convert(source,target,[[50,120,-100]]);self.assertGreater(r['samples'][0]['clipped_components'],0);self.assertTrue(all(0<=v<=1 for v in r['samples'][0]['values']));self.assertEqual([source,target],before)
        for rows in [[[101,0,0]],[[50,128,0]],[[50,0]],[[50,0,0,0]]]:self.assertEqual(self.convert(source,target,rows,1)['code'],'INVALID_COLOR')
        self.assertEqual(self.convert(source,target,[[50,0,0]]*4097,1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.convert(source,target,[[50,0,0]],1,control=dict(timeout_ms=0))['code'],'TIMEOUT')
        c=Client();c.initialize();self.addCleanup(c.close);self.assertEqual(c.success('color.convert',source=source,destination=target,values=[[50,120,-100]]),r)

if __name__=='__main__':unittest.main()
