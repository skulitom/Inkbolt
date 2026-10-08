"""Independent color equations and exact delivered ink planes from original charts."""
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
import zlib
from cmyk_fixtures import cmyk_profile, proof_profile, lookup, fixed
import test_print_cmyk_cli as print_tests
from test_print_cmyk_cli import images
from test_profiles_cli import embedded, builtin, decode_srgb, png_profile
from test_sample_profiles_cli import tags_of, repack
from test_mcp import Client
import test_editing_cli as editing

WHITE=(.9642,1,.8249)


def lab(xyz):
    f=lambda x:x**(1/3) if x>(6/29)**3 else x/(3*(6/29)**2)+4/29
    x,y,z=[f(v/w) for v,w in zip(xyz,WHITE)]
    return [116*y-16,500*(x-y),200*(y-z)]


def xyz(values):
    l,a,b=values;y=(l+16)/116;f=[y+a/500,y,y-b/200]
    return [w*(v**3 if v>6/29 else 3*(6/29)**2*(v-4/29)) for v,w in zip(f,WHITE)]


def scalar(artifact):
    raw=base64.b64decode(artifact['data']);assert hashlib.sha256(raw).hexdigest()==artifact['sha256']
    at=8;compressed=b'';chunks={}
    while at<len(raw):
        n=int.from_bytes(raw[at:at+4],'big');kind=raw[at+4:at+8];value=raw[at+8:at+8+n]
        assert zlib.crc32(kind+value)==int.from_bytes(raw[at+8+n:at+12+n],'big')
        chunks[kind]=value
        if kind==b'IDAT':compressed+=value
        at+=n+12
    w,h,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',chunks[b'IHDR'])
    assert (depth,color,compression,filtering,interlace)==(8,0,0,0,0)
    assert not ({b'iCCP',b'sRGB',b'gAMA',b'cHRM'} & chunks.keys())
    filtered=zlib.decompress(compressed);assert len(filtered)==(w+1)*h
    out=bytearray();previous=bytes(w)
    for y in range(h):
        mode=filtered[y*(w+1)];row=bytearray(filtered[y*(w+1)+1:(y+1)*(w+1)])
        for x in range(w):
            a=row[x-1] if x else 0;b=previous[x];c=previous[x-1] if x else 0
            if mode==0:predict=0
            elif mode==1:predict=a
            elif mode==2:predict=b
            elif mode==3:predict=(a+b)//2
            else:
                assert mode==4;p=a+b-c;predict=min((a,b,c),key=lambda v:abs(p-v))
            row[x]=(row[x]+predict)%256
        out.extend(row);previous=row
    assert hashlib.sha256(out).hexdigest()==artifact['sample_sha256']
    return w,h,bytes(out),chunks


def inks(result):
    planes=[scalar(result['plates'][n])[2] for n in ['cyan','magenta','yellow','black']]
    return bytes(v for q in zip(*planes) for v in q)


class ProofTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    document=print_tests.CmykPrintTests.document
    board=print_tests.CmykPrintTests.board

    def proof(self,d,profile=None,expected=0,**kw):
        options=dict(print=dict(profile=embedded(profile or proof_profile()),matte=[237,243,251]),delta_e76_threshold=20)
        options.update(kw)
        return self.invoke(dict(command='document.proof',document=d,options=options),expected)

    def test_exact_pdf_ink_identity_scalar_plates_density_and_source_preservation(self):
        d,_=self.document();original=copy.deepcopy(d);profile=proof_profile();d['resolution_ppi']=300
        options=dict(profile=embedded(profile),matte=[237,243,251],raster_scale=2)
        result=self.proof(d,print=options)
        pdf=self.invoke(dict(command='document.export',document=d,format='pdf',pdf_options=dict(print=options)))
        ink=inks(result);self.assertEqual(ink,images(pdf)[1][0]['stream'])
        self.assertEqual(result['cmyk_sha256'],pdf['pages'][0]['cmyk_sha256'])
        self.assertEqual((result['width'],result['height'],result['resolution_ppi']),(32,8,600))
        self.assertEqual(result['print_profile']['icc_sha256'],hashlib.sha256(profile).hexdigest())
        for c,name in enumerate(['cyan','magenta','yellow','black']):
            plane=result['plates'][name];w,h,values,chunks=scalar(plane)
            self.assertEqual((w,h),(32,8));self.assertEqual(values,ink[c::4])
            self.assertEqual((plane['minimum'],plane['maximum']),(min(values),max(values)))
            self.assertAlmostEqual(plane['mean_fraction'],sum(values)/(255*len(values)),places=13)
            self.assertEqual(struct.unpack('>IIB',chunks[b'pHYs']),(round(600/.0254),round(600/.0254),1))
        self.assertEqual(self.proof(d,print=options),result)
        d['resolution_ppi']=original['resolution_ppi'];self.assertEqual(d,original)

    def test_source_matte_xyz_and_d50_lab_are_independent_of_proof_profile(self):
        d,raw=self.document();result=self.proof(d,samples=[[x,y] for y in range(4) for x in range(16)])
        profile=png_profile(base64.b64decode(result['preview']['data']));tags=tags_of(profile)
        columns=[struct.unpack('>3i',tags[k][8:20]) for k in [b'rXYZ',b'gXYZ',b'bXYZ']]
        for i,s in enumerate(result['samples']):
            p=raw[i*4:i*4+4];rgb=[decode_srgb((p[c]*p[3]+[237,243,251][c]*(255-p[3]))/65025) for c in range(3)]
            expected=[sum(columns[c][r]*rgb[c]/65536 for c in range(3)) for r in range(3)]
            for a,b in zip(s['source_xyz_d50'],expected):self.assertAlmostEqual(a,b,delta=.00004)
            for a,b in zip(s['source_lab_d50'],lab(expected)):self.assertAlmostEqual(a,b,delta=.015)
        self.assertEqual(hashlib.sha256(profile).hexdigest(),result['preview_profile_sha256'])

    def test_affine_xyz_and_lab_tables_versions_and_absolute_white_scale(self):
        d,_=self.document()
        for pcs in ['XYZ ','Lab ']:
            for version,modern in [(2,False),(4,False),(4,True)]:
                profile=proof_profile(pcs=pcs,version=version,modern=modern,white=(.8,.9,.7))
                for absolute in [False,True]:
                    result=self.proof(d,profile,samples=[[x,y] for y in range(4) for x in range(16)],view_intent='absolute_colorimetric' if absolute else 'relative_colorimetric')
                    for s in result['samples']:
                        c,m,y,k=[v/255 for v in s['cmyk8']]
                        if pcs=='XYZ ':
                            q=[.40-.10*c-.05*m-.10*k,.42-.05*c-.10*m-.10*k,.35-.10*y-.10*k]
                            expected=[v*(2 if modern else 65535/32768) for v in q]
                        else:
                            q=[.85-.05*c-.05*m-.10*k,.5+.1*m-.1*c,.5+.1*y-.1*m]
                            if not modern:q=[v*65535/65280 for v in q]
                            expected=xyz([q[0]*100,q[1]*255-128,q[2]*255-128])
                        if absolute:expected=[v*(round(w*65536)/65536)/(round(d50*65536)/65536) for v,w,d50 in zip(expected,[.8,.9,.7],WHITE)]
                        for a,b in zip(s['proof_xyz_d50'],expected):self.assertAlmostEqual(a,b,delta=.00012,msg=(pcs,version,modern,absolute,s))
                        for a,b in zip(s['proof_lab_d50'],lab(expected)):self.assertAlmostEqual(a,b,delta=.018)

    def test_nonlinear_four_dimensional_tables_follow_multilinear_contract(self):
        d,_=self.document();result=self.proof(d,cmyk_profile(),samples=[[x,3] for x in range(16)])
        for s in result['samples']:
            c,m,y,k=[v/255 for v in s['cmyk8']]
            expected=[.9642*(1-c)*(1-k), (1-m)*(1-k),.8249*(1-y)*(1-k)]
            for a,b in zip(s['proof_xyz_d50'],expected):self.assertAlmostEqual(a,b,delta=.00008)

    def test_eight_bit_lab_table_encoding_is_independent_of_profile_version(self):
        # A constant original 8-bit Lab table has no interpolation uncertainty.
        table=(b'mft1'+bytes(4)+bytes([4,3,2,0])
               +b''.join(fixed(v) for v in [1,0,0,0,1,0,0,0,1])
               +bytes(range(256))*4+bytes([180,155,97])*16+bytes(range(256))*3)
        d,_=self.document();expected=xyz([180/255*100,155-128,97-128])
        for version in [2,4]:
            p=proof_profile(pcs='Lab ',version=version);tags=tags_of(p);tags[b'A2B1']=table
            result=self.proof(d,repack(p[:128],tags),samples=[[0,0],[15,3]])
            for s in result['samples']:
                for a,b in zip(s['proof_xyz_d50'],expected):self.assertAlmostEqual(a,b,delta=.00002)
            p=proof_profile(pcs='XYZ ',version=version);tags=tags_of(p);tags[b'A2B1']=table
            self.assertEqual(self.proof(d,repack(p[:128],tags),expected=1)['code'],'UNSUPPORTED')

    def test_requested_colorimetric_table_and_fallback_control_observation(self):
        d,_=self.document();p=proof_profile();tags=tags_of(p)
        # Viewing stays colorimetric even if the profile's other intent tables differ.
        changed=dict(tags);changed[b'A2B0']=lookup(4,3,lambda q:[.1,.2,.3]);changed[b'A2B2']=lookup(4,3,lambda q:[.3,.2,.1])
        a=self.proof(d,p);b=self.proof(d,repack(p[:128],changed))
        self.assertEqual(a['preview'],b['preview']);self.assertEqual(a['difference'],b['difference'])
        del changed[b'A2B1'];fallback=self.proof(d,repack(p[:128],changed),samples=[[0,0]])
        for x,y in zip(fallback['samples'][0]['proof_xyz_d50'],[.2,.4,.6]):self.assertAlmostEqual(x,y,delta=.00004)
        self.assertNotEqual(a['preview'],fallback['preview'])

    def test_pixel_limit_and_cancel_marker_fail_without_output_or_source_edits(self):
        d,_=self.document();d['width']=1025;d['height']=1024
        self.assertEqual(self.proof(d,expected=1)['code'],'RESOURCE_LIMIT')
        d,_=self.document()
        with tempfile.TemporaryDirectory() as root:
            marker=Path(root)/'cancel';marker.write_text('')
            options=dict(print=dict(profile=embedded(proof_profile()),matte=[255]*3),delta_e76_threshold=2)
            self.assertEqual(self.invoke(dict(command='document.proof',document=d,options=options,control=dict(cancel_file=str(marker))),1)['code'],'CANCELLED')
            self.assertEqual(list(Path(root).iterdir()),[marker])

    def test_difference_statistics_mask_and_total_ink_use_actual_samples(self):
        d,_=self.document();result=self.proof(d,samples=[[x,y] for y in range(4) for x in range(16)])
        values=[math.dist(s['source_lab_d50'],s['proof_lab_d50']) for s in result['samples']]
        for s,v in zip(result['samples'],values):self.assertAlmostEqual(s['delta_e76'],v,places=10)
        difference=result['difference'];self.assertAlmostEqual(difference['maximum'],max(values),places=10)
        self.assertAlmostEqual(difference['mean'],sum(values)/len(values),places=10)
        self.assertEqual(scalar(difference['mask'])[2],bytes(255 if v>20 else 0 for v in values))
        self.assertEqual(difference['pixels_above_threshold'],sum(v>20 for v in values))
        sums=[sum(s['cmyk8']) for s in result['samples']]
        self.assertAlmostEqual(result['total_ink']['maximum_fraction'],max(sums)/255,places=13)
        self.assertAlmostEqual(result['total_ink']['mean_fraction'],sum(sums)/(255*len(sums)),places=13)
        # Equal threshold is excluded; the caller controls the interpretation.
        equal=self.proof(d,delta_e76_threshold=values[0],samples=[[0,0],[0,0]])
        self.assertEqual(scalar(equal['difference']['mask'])[2][0],0)
        self.assertEqual(equal['samples'][0],equal['samples'][1])

    def test_display_clipping_is_separate_from_pcs_difference_and_alpha_is_opaque(self):
        d,_=self.document();p=proof_profile();tags=tags_of(p)
        tags[b'A2B1']=lookup(4,3,lambda q:[.5,.1,.1])
        result=self.proof(d,repack(p[:128],tags),samples=[[0,0]])
        sample=result['samples'][0];self.assertGreater(sample['linear_srgb'][0],1)
        self.assertLess(sample['linear_srgb'][1],0)
        self.assertEqual(result['display_clipping']['pixels'],64)
        self.assertEqual(result['display_clipping']['channels'],[64,64,0])
        raw=base64.b64decode(result['preview']['data']);_,_,pixels,_=editing.png_pixels(raw)
        self.assertEqual(pixels[3::4],bytes([255]*64));self.assertEqual(pixels[:3],bytes(sample['preview_rgb8']))
        self.assertEqual(sample['preview_rgb8'][0:2],[255,0])
        self.assertGreater(sample['delta_e76'],50)

    def test_artboard_bleed_and_scale_match_delivery_without_world_placement(self):
        d,_=self.document();d['kind']='vector';d['items']=[self.board('board',16,4,x=80,y=-30,bleed=dict(left=1,right=2,top=3,bottom=4)),dict(id='rect',parent='board',content=dict(type='vector',geometry=dict(shape='rect',x=-1,y=-3,width=19,height=11),fill=[150,30,80,255]))]
        r=self.proof(d,artboard_id='board',include_bleed=True)
        self.assertEqual((r['width'],r['height']),(19,11))
        d['items'][0]['transform']=[0,2,-3,0,-600,200]
        self.assertEqual(self.proof(d,artboard_id='board',include_bleed=True),r)

    def test_invalid_options_profiles_and_controls_fail_without_mutation(self):
        d,_=self.document();original=copy.deepcopy(d)
        for kw in [dict(delta_e76_threshold=-1),dict(delta_e76_threshold=1001),dict(samples=[[16,0]]),dict(samples=[[0,0]]*65),dict(include_bleed=True)]:
            self.assertEqual(self.proof(d,expected=1,**kw)['code'],'INVALID_REQUEST')
        for intent in ['perceptual','saturation']:
            self.assertEqual(self.proof(d,expected=1,view_intent=intent)['code'],'UNSUPPORTED_PROFILE_INTENT')
        d['output_profile']=builtin('srgb');self.assertEqual(self.proof(d,expected=1)['code'],'PROFILE_CONFLICT');del d['output_profile']
        options=dict(print=dict(profile=embedded(proof_profile()),matte=[255]*3),delta_e76_threshold=2)
        self.assertEqual(self.invoke(dict(command='document.proof',document=d,options=options,control=dict(timeout_ms=0)),1)['code'],'TIMEOUT')
        self.assertEqual(d,original)

    def test_hash_pinned_large_profile_file_is_preserved_and_not_disclosed(self):
        d,_=self.document();profile=proof_profile(grid=17)
        self.assertGreater(len(profile),1024*1024)
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'press.icc';path.write_bytes(profile)
            ref=dict(type='file',source_path=str(path),sha256=hashlib.sha256(profile).hexdigest())
            result=self.proof(d,print=dict(profile=ref,matte=[255]*3))
            self.assertNotIn(root,json.dumps(result));self.assertEqual(path.read_bytes(),profile)
            ref['sha256']='0'*64
            self.assertEqual(self.proof(d,expected=1,print=dict(profile=ref,matte=[255]*3))['code'],'PROFILE_MISMATCH')

    def test_mcp_discovery_call_and_durable_session_remain_readonly(self):
        c=Client();self.addCleanup(c.close);c.initialize();d,_=self.document()
        tools=[];cursor=None
        while True:
            page=c.rpc('tools/list',{} if cursor is None else dict(cursor=cursor))['result'];tools.extend(page['tools']);cursor=page.get('nextCursor')
            if cursor is None:break
        t=next(t for t in tools if t['name']=='inkbolt_document_proof');self.assertTrue(t['annotations']['readOnlyHint'])
        self.assertFalse(t['inputSchema']['additionalProperties'])
        options=dict(print=dict(profile=embedded(proof_profile()),matte=[237,243,251]),delta_e76_threshold=20)
        with tempfile.TemporaryDirectory() as root:
            c.success('session.create',session_root=root,session_id='proof',request_id='create',document=d)
            before=c.success('session.read',session_root=root,session_id='proof')
            result=c.success('document.proof',document=before['document'],options=options)
            self.assertEqual(result,self.proof(before['document']))
            self.assertEqual(c.success('session.read',session_root=root,session_id='proof'),before)
            self.assertEqual(c.success('document.proof',document=before['document'],options=options),result)
        self.assertIn('document.proof',c.success('capabilities')['commands'])


if __name__=='__main__':unittest.main()
