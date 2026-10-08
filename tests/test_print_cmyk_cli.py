"""Original calibrated page fixtures with independent profile/geometry equations."""
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
import pdf_reader
from cmyk_fixtures import cmyk_profile, separation
from test_profiles_cli import embedded, builtin, decode_srgb, linear_profile
from test_sample_profiles_cli import tags_of, repack
import test_editing_cli as editing
import test_boards_cli as boards
import test_hdr_cli as hdr
from test_mcp import Client


def images(artifact):
    pdf = pdf_reader.Pdf(artifact)
    return pdf, [dict(v, stream=pdf.streams[k]) for k,v in pdf.objects.items() if isinstance(v, dict) and v.get('Subtype') == 'Image']


class CmykPrintTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke
    board = boards.BoardCliTests.board

    def document(self):
        d = self.invoke(dict(command='document.create', id='print', kind='raster', width=16, height=4))
        pixels = bytes(v for y in range(4) for x in range(16) for v in (x*17, (15-x)*17, (x*73)%256, [0, 64, 128, 255][y]))
        d['items'] = [dict(id='pixels', content=dict(type='raster', width=16, height=4, rgba_hex=pixels.hex()))]
        return self.invoke(dict(command='document.validate',document=d)), pixels

    def options(self, profile=None, **kw):
        return dict(profile=embedded(profile or cmyk_profile()), matte=[237, 243, 251], **kw)

    def export(self, d, expected=0, print_options=None, **kw):
        return self.invoke(dict(command='document.export', document=d, format='pdf',
                                pdf_options=dict(print=print_options or self.options(), **kw)), expected)

    def test_four_channels_follow_independent_xyz_and_matte_equations(self):
        d, pixels = self.document()
        original = copy.deepcopy(d)
        # The source matrix is the public quantized D50-adapted sRGB definition.
        matrix = [[.4360747,.3850649,.1430804], [.2225045,.7168786,.0606169], [.0139322,.0971045,.7141733]]
        for modern in (False, True):
            profile = cmyk_profile(modern=modern)
            a = self.export(d, print_options=self.options(profile))
            p, ims = images(a)
            self.assertEqual(len(ims), 1)
            image = ims[0]
            self.assertEqual((image['Width'],image['Height'],image['BitsPerComponent']), (16,4,8))
            self.assertEqual(image['ColorSpace'][0], 'ICCBased')
            icc = p.get(image['ColorSpace'][1])
            self.assertEqual(icc['N'], 4)
            self.assertEqual(p.streams[image['ColorSpace'][1]], profile)
            actual = image['stream']
            expected = []
            for at in range(0,len(pixels),4):
                rgb = [decode_srgb((pixels[at+c]*pixels[at+3]+[237,243,251][c]*(255-pixels[at+3]))/65025) for c in range(3)]
                xyz = [sum(row[c]*rgb[c] for c in range(3)) for row in matrix]
                # mft2 XYZ input covers [0, 65535/32768], mBA covers [0, 2).
                q = [v*(.5 if modern else 32768/65535) for v in xyz]
                expected.extend(round(v*255) for v in separation(q))
            self.assertLessEqual(max(abs(x-y) for x,y in zip(actual,expected)),1)
            self.assertEqual(a['color_profile']['icc_sha256'],hashlib.sha256(profile).hexdigest())
            self.assertEqual(a['pages'][0]['cmyk_sha256'],hashlib.sha256(actual).hexdigest())
            self.assertNotIn('SMask',image)
            self.assertEqual(self.export(d,print_options=self.options(profile)),a)
        self.assertEqual(d,original)

    def test_intents_select_directional_tables_and_absolute_white_scaling(self):
        d,_ = self.document()
        profile = cmyk_profile(intents=True)
        values = {}
        for intent in ['relative_colorimetric','absolute_colorimetric']:
            a = self.export(d,print_options=self.options(profile,intent=intent))
            values[intent] = images(a)[1][0]['stream']
            self.assertEqual(a['color_profile']['intent'],intent)
        self.assertEqual(values['relative_colorimetric'],values['absolute_colorimetric'])
        for intent in ['perceptual','saturation']:
            artifact=self.export(d,print_options=self.options(profile,intent=intent))
            values[intent]=images(artifact)[1][0]['stream'];self.assertEqual(artifact['color_profile']['intent'],intent)
        self.assertNotEqual(values['perceptual'],values['saturation'])
        base=images(self.export(d))[1][0]['stream']
        self.assertTrue(all(9 <= y-x <= 11 for x,y in zip(base,values['relative_colorimetric'])))
        adjusted = cmyk_profile(white=(.8,.9,.7))
        a = self.export(d,print_options=self.options(adjusted,intent='relative_colorimetric'))
        b = self.export(d,print_options=self.options(adjusted,intent='absolute_colorimetric'))
        self.assertNotEqual(images(a)[1][0]['stream'],images(b)[1][0]['stream'])

    def test_density_changes_physical_size_and_scale_changes_only_samples(self):
        d,_ = self.document()
        for ppi in [1,72,96,300,254.5]:
            d['resolution_ppi']=ppi
            for scale in [1,2,4]:
                a=self.export(d,print_options=self.options(raster_scale=scale))
                p,ims=images(a)
                self.assertEqual((ims[0]['Width'],ims[0]['Height']),(16*scale,4*scale))
                self.assertEqual(a['pages'][0]['raster_ppi'],ppi*scale)
                self.assertEqual(a['pages'][0]['physical_points'],[16*72/ppi,4*72/ppi])
                self.assertEqual(p.pages[0]['MediaBox'],[0,0,16*72/ppi,4*72/ppi])

    def test_page_selection_bleed_user_unit_and_source_placement(self):
        d,_=self.document();d['kind']='vector';d['width']=30000;d['height']=128;d['items']=[];d['resolution_ppi']=1
        for i in range(2):
            d['items'].append(self.board('page'+str(i),256,64,x=i*300,y=20,bleed=dict(left=2,right=3,top=4,bottom=5)))
            d['items'].append(dict(id='ink'+str(i),parent='page'+str(i),content=dict(type='vector',geometry=dict(shape='rect',x=-2,y=-4,width=261,height=73),fill=[i*200,30,80,255])))
        options=dict(artboards=dict(type='ids',ids=['page1','page0']),include_bleed=True)
        a=self.export(d,**options);p,ims=images(a)
        self.assertEqual([x['artboard_id'] for x in a['pages']],['page1','page0'])
        for page,r in zip(p.pages,a['pages']):
            self.assertEqual(r['logical_size'],[261,73]);self.assertEqual(page['UserUnit'],2)
            self.assertEqual(page['TrimBox'],[72,180,9288,2484])
        for item in d['items']:
            if item['content']['type']=='frame':item['transform']=[0,-2,3,0,1000,20]
        self.assertEqual(self.export(d,**options),a)

    def test_missing_direction_malformed_tables_wrong_models_and_override_tags(self):
        d,_=self.document();profile=cmyk_profile();tags=tags_of(profile)
        bad=[(linear_profile(),'UNSUPPORTED'),(profile[:-1],'INVALID_PROFILE')]
        for signature in [b'A2B0',b'B2A0']:
            bad.append((repack(profile[:128],{k:v for k,v in tags.items() if k!=signature}),'UNSUPPORTED'))
        bad.append((repack(profile[:128],tags|{b'B2D1':b'mpet'+bytes(16)}),'UNSUPPORTED'))
        for key in [b'A2B0',b'B2A0']:
            damaged=bytearray(tags[key]);damaged[8]=5
            bad.append((repack(profile[:128],tags|{key:bytes(damaged)}),'INVALID_PROFILE'))
        for raw,code in bad:
            self.assertEqual(self.export(d,1,print_options=self.options(raw))['code'],code)
        self.assertEqual(self.export(d,1,print_options=dict(profile=builtin('srgb'),matte=[255]*3))['code'],'UNSUPPORTED')
        # Directional fallback is explicit: relative may use B2A0 when B2A1 is absent.
        fallback=repack(profile[:128],{k:v for k,v in tags.items() if k!=b'B2A1'})
        self.assertEqual(images(self.export(d,print_options=self.options(fallback)))[1][0]['stream'],images(self.export(d))[1][0]['stream'])

    def test_strict_options_profile_conflicts_and_no_partial_publication(self):
        d,_=self.document()
        for options in [dict(profile=embedded(cmyk_profile())),self.options(raster_scale=0),self.options(render_options=dict(crop_to_canvas=False)),dict(profile=embedded(cmyk_profile()),matte=[255]*3,proof=True)]:
            self.assertEqual(self.export(d,1,print_options=options)['code'],'INVALID_REQUEST')
        self.assertEqual(self.export(d,1,color='native_inks')['code'],'INVALID_REQUEST')
        d['output_profile']=builtin('srgb')
        self.assertEqual(self.export(d,1)['code'],'PROFILE_CONFLICT')
        del d['output_profile']
        with tempfile.TemporaryDirectory() as root:
            output=dict(output_root=root,file_name='print.pdf',format='pdf',pdf_options=dict(print=self.options()))
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output,control=dict(timeout_ms=0)),1)['code'],'TIMEOUT')
            self.assertFalse((Path(root)/'print.pdf').exists())
            receipt=self.invoke(dict(command='document.publish',document=d,output=output));original=(Path(root)/'print.pdf').read_bytes()
            self.assertEqual(receipt['pdf']['color'],'ICCBased_CMYK8');self.assertEqual(receipt['color_profile']['samples'],'cmyk8')
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output),1)['code'],'OUTPUT_EXISTS')
            self.assertEqual((Path(root)/'print.pdf').read_bytes(),original)

    def test_lab_connection_matches_independent_lab_equations(self):
        d,pixels=self.document()
        matrix=[[.4360747,.3850649,.1430804],[.2225045,.7168786,.0606169],[.0139322,.0971045,.7141733]]
        for modern in [False,True]:
            a=self.export(d,print_options=self.options(cmyk_profile(pcs='Lab ',modern=modern)))
            expected=[]
            for at in range(0,len(pixels),4):
                rgb=[decode_srgb((pixels[at+c]*pixels[at+3]+[237,243,251][c]*(255-pixels[at+3]))/65025) for c in range(3)]
                xyz=[sum(row[c]*rgb[c] for c in range(3))/white for row,white in zip(matrix,[.9642,1,.8249])]
                f=lambda v:v**(1/3) if v>(6/29)**3 else v/(3*(6/29)**2)+4/29
                x,y,z=map(f,xyz);q=[(116*y-16)/100,(500*(x-y)+128)/255,(200*(y-z)+128)/255]
                if not modern:q=[v*256/257 for v in q]
                expected.extend(round(v*255) for v in separation(q))
            self.assertLessEqual(max(abs(x-y) for x,y in zip(images(a)[1][0]['stream'],expected)),1)

    def test_version_two_profiles_retain_declared_bytes_and_relative_numbers(self):
        d,_=self.document()
        for pcs in ['XYZ ','Lab ']:
            profile=cmyk_profile(pcs=pcs,version=2)
            a=self.export(d,print_options=self.options(profile));p,ims=images(a)
            b=self.export(d,print_options=self.options(cmyk_profile(pcs=pcs)))
            self.assertLessEqual(max(abs(x-y) for x,y in zip(ims[0]['stream'],images(b)[1][0]['stream'])),1)
            self.assertEqual(p.streams[ims[0]['ColorSpace'][1]],profile)

    def test_dense_four_dimensional_profiles_have_a_separate_bounded_allowance(self):
        d,_=self.document();profile=cmyk_profile(grid=17)
        self.assertGreater(len(profile),1024*1024)
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'output.icc';path.write_bytes(profile)
            source=dict(type='file',source_path=str(path),sha256=hashlib.sha256(profile).hexdigest())
            a=self.export(d,print_options=dict(profile=source,matte=[237,243,251]));p,ims=images(a)
            self.assertEqual(p.streams[ims[0]['ColorSpace'][1]],profile)
            simple=images(self.export(d))[1][0]['stream']
            self.assertLessEqual(max(abs(x-y) for x,y in zip(ims[0]['stream'],simple)),1)
            self.assertEqual(path.read_bytes(),profile)
            path.write_bytes(bytes(4*1024*1024+1))
            self.assertEqual(self.export(d,1,print_options=dict(profile=source,matte=[255]*3))['code'],'RESOURCE_LIMIT')

    def test_file_profiles_pin_source_identity_and_fail_before_publication(self):
        d,_=self.document();profile=cmyk_profile()
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'profile.icc';path.write_bytes(profile)
            source=dict(type='file',source_path=str(path),sha256=hashlib.sha256(profile).hexdigest())
            options=dict(profile=source,matte=[237,243,251])
            self.assertEqual(self.export(d,print_options=options),self.export(d))
            self.assertEqual(self.export(d,1,print_options=dict(options,profile=dict(source,source_path='relative.icc')))['code'],'INVALID_REQUEST')
            self.assertEqual(self.export(d,1,print_options=dict(options,profile=dict(source,sha256='invalid')))['code'],'INVALID_REQUEST')
            self.assertEqual(self.export(d,1,print_options=dict(options,profile=dict(source,source_path=str(Path(root)/'missing.icc'))))['code'],'PROFILE_IO')
            path.write_bytes(profile+b'changed')
            output=dict(output_root=root,file_name='output.pdf',format='pdf',pdf_options=dict(print=options))
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output),1)['code'],'PROFILE_MISMATCH')
            self.assertEqual(path.read_bytes(),profile+b'changed');self.assertFalse((Path(root)/'output.pdf').exists())

    def test_public_metadata_profile_density_and_strip_preserve_source(self):
        d,_=self.document();d['metadata']=dict(title='Print proof',private={'path':'private-print-location'})
        options=self.options(raster_scale=2);before=copy.deepcopy(d)
        a=self.export(d,print_options=options);p,_=images(a)
        raw=base64.b64decode(a['data']);self.assertNotIn(b'private-print-location',raw);self.assertIn(b'Print proof',raw)
        xml=next(p.streams[k] for k,v in p.objects.items() if isinstance(v,dict) and v.get('Type')=='Metadata')
        envelope=json.loads(next(n.text for n in ET.fromstring(xml).iter() if n.tag.endswith('}packet')));self.assertEqual(envelope['pages'][0]['packet']['delivery']['profile']['samples'],'cmyk8')
        self.assertEqual(envelope['pages'][0]['packet']['delivery']['resolution_ppi'],192)
        stripped=self.invoke(dict(command='document.export',document=d,format='pdf',pdf_options=dict(print=options),metadata_policy=dict(mode='strip')))
        self.assertNotIn(b'Print proof',base64.b64decode(stripped['data']))
        self.assertEqual(images(stripped)[1][0]['stream'],images(a)[1][0]['stream']);self.assertEqual(d,before)

    def test_linear_surface_requires_explicit_view_and_retains_native_source(self):
        d=hdr.HdrTests().document([hdr.layer([2,.25,-.5,.5])]);before=copy.deepcopy(d)
        self.assertEqual(self.export(d,1)['code'],'HDR_VIEW_REQUIRED')
        view=dict(exposure=0,tone_map='clip')
        # Use the existing declared display projection before the printing boundary.
        render=dict(view=view)
        display=self.invoke(dict(command='document.render',document=d,render_options=render))
        ordinary=copy.deepcopy(d);ordinary['color_space']='srgb';ordinary['items']=[dict(id='view',content=dict(type='raster',width=1,height=1,rgba_hex=display['data']))]
        a=self.export(d,print_options=self.options(render_options=render));b=self.export(ordinary)
        self.assertEqual(images(a)[1][0]['stream'],images(b)[1][0]['stream']);self.assertEqual(d,before)

    def test_flattened_print_reuses_effect_mask_blend_and_sampling_semantics(self):
        d,_=self.document()
        d['items'][0]['mask']=dict(width=2,height=1,gray_hex='80ff',clip=False)
        d['items'][0]['effects']=[dict(id='shadow',operator=dict(type='shadow',offset=[1,1],sigma=1),color=[20,40,80,180])]
        d['items'].append(dict(id='top',blend='multiply',opacity=.6,content=dict(type='raster',width=1,height=1,rgba_hex='c82840ff')))
        render=dict(antialias='supersample2',padding=2)
        before=copy.deepcopy(d);display=self.invoke(dict(command='document.render',document=d,render_options=render))
        flat=copy.deepcopy(d);flat['items']=[dict(id='flat',content=dict(type='raster',width=16,height=4,rgba_hex=display['data']))]
        a=self.export(d,print_options=self.options(render_options=render));b=self.export(flat)
        self.assertEqual(images(a)[1][0]['stream'],images(b)[1][0]['stream']);self.assertEqual(d,before)

    def test_resource_limits_reject_before_publication(self):
        d,_=self.document();d['width']=2048;d['height']=2048
        with tempfile.TemporaryDirectory() as root:
            output=dict(output_root=root,file_name='large.pdf',format='pdf',pdf_options=dict(print=self.options()))
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output),1)['code'],'RESOURCE_LIMIT')
            self.assertFalse((Path(root)/'large.pdf').exists())
        # Aggregate page pixel limit is independent of each bounded render.
        d['kind']='vector';d['items']=[self.board('p'+str(i),1024,1024) for i in range(5)]
        self.assertEqual(self.export(d,1,artboards=dict(type='all'))['code'],'RESOURCE_LIMIT')

    def test_agent_undo_retry_reopen_and_print_publication_preserve_source(self):
        d,_=self.document();client=Client();self.addCleanup(client.close);client.initialize()
        with tempfile.TemporaryDirectory() as root:
            s=dict(session_root=root,session_id='print')
            client.success('session.create',**s,request_id='create',document=d)
            action=dict(type='edit',operations=[dict(op='canvas',action=dict(type='resolution',ppi=300))])
            changed=client.success('session.apply',**s,request_id='density',expected_revision=0,action=action)['document']
            output=dict(output_root=root,file_name='print.pdf',format='pdf',pdf_options=dict(print=self.options()))
            receipt=client.success('session.publish',**s,expected_revision=1,output=output)
            self.assertEqual(receipt['pages'][0]['raster_ppi'],300)
            self.assertEqual(client.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'],dict(d,revision=2))
            self.assertEqual(client.success('session.apply',**s,request_id='redo',expected_revision=2,action=dict(type='redo'))['document'],dict(changed,revision=3))
            self.assertTrue(client.success('session.apply',**s,request_id='density',expected_revision=0,action=action)['replayed'])
            self.assertTrue(client.success('session.verify',**s)['valid'])
            self.assertEqual(changed['items'],d['items'])


if __name__=='__main__':unittest.main()
