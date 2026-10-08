"""Exact delivery, original analytic gamut fixtures and failure boundaries."""
import base64
import copy
import hashlib
import itertools
import math
from pathlib import Path
import struct
import tempfile
import unittest
import gamut_fixtures as fixtures
from cmyk_fixtures import proof_profile, lookup
from test_profiles_cli import embedded
from test_sample_profiles_cli import tags_of, repack
from test_ink_recipes_cli import recipe, channel, calculator
from test_proof_cli import scalar, inks, xyz
from test_print_cmyk_cli import images
import test_print_cmyk_cli as print_tests
from test_mcp import Client
import test_editing_cli as editing


def attach_recipe(d,n=2):
    w,h=d['width'],d['height'];d['ink_recipe']=recipe(n,True)
    d['channels']={'gray':channel(((i*37)%256 for i in range(w*h)),w,h),
                   'mask':channel(((i*73+41)%256 for i in range(w*h)),w,h)}
    return d


def mix(n):
    return dict(model='multiplicative_cmyk',alternate_cmyk={f'ink{i}':[(i*13+c*17)%31/31 for c in range(4)] for i in range(n)})


class ExtendedPrepressTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    document=print_tests.CmykPrintTests.document

    def proof(self,d,print_options=None,expected=0,**kw):
        return self.invoke(dict(command='document.proof',document=d,options=dict(
            print=print_options or dict(profile=embedded(fixtures.profile()),matte=[237,243,251]),delta_e76_threshold=20,**kw)),expected)

    def gamut(self,p,points,expected=0,**kw):
        return self.invoke(dict(command='profile.gamut',profile=embedded(p),xyz_d50=points,**kw),expected)

    def test_combined_pdf_and_proof_retain_exact_independent_plates(self):
        for n,scale in [(1,1),(2,2),(5,1),(8,4)]:
            d,_=self.document();attach_recipe(d,n);original=copy.deepcopy(d)
            options=dict(profile=embedded(proof_profile()),matte=[237,243,251],named_inks=mix(n),raster_scale=scale)
            result=self.proof(d,options,samples=[[0,0],[15*scale,3*scale]])
            pdf,ims=images(self.invoke(dict(command='document.export',document=d,format='pdf',pdf_options=dict(print=options))))
            space=pdf.get(ims[0]['ColorSpace']);self.assertEqual(space[:2],['DeviceN',['Cyan','Magenta','Yellow','Black']+[f'Inkbolt.ink{i}' for i in range(n)]])
            attrs=space[4];self.assertEqual(attrs['Subtype'],'NChannel');self.assertEqual(attrs['Process']['Components'],space[1][:4])
            process=inks(self.proof(d,{k:v for k,v in options.items() if k!='named_inks'}))
            self.assertEqual(inks(result),process)
            named=self.invoke(dict(command='document.separations',document=d,scale=scale))
            plates=[process[c::4] for c in range(4)]+[scalar(p)[2] for p in named['plates']]
            interleaved=bytes(v for pixel in zip(*plates) for v in pixel)
            self.assertEqual(ims[0]['stream'],interleaved)
            self.assertEqual([scalar(p)[2] for p in result['named_plates']],plates[4:])
            self.assertEqual(result['inks']['interleaved_sha256'],hashlib.sha256(interleaved).hexdigest())
            program=pdf.streams[space[3]]
            for s in result['samples']:
                q=[x/255 for x in s['cmyk8']+s['named8']]
                expected=[1-(1-q[c])*math.prod(1-q[4+i]*options['named_inks']['alternate_cmyk'][f'ink{i}'][c] for i in range(n)) for c in range(4)]
                for actual in [s['fallback_cmyk'],calculator(program,q,4,32)]:
                    for a,b in zip(actual,expected):self.assertAlmostEqual(a,b,places=12)
            self.assertEqual(d,original)

    def test_combined_continuous_preview_has_no_extra_byte_projection(self):
        d,_=self.document();attach_recipe(d)
        options=dict(profile=embedded(proof_profile()),matte=[255]*3,named_inks=mix(2))
        result=self.proof(d,options,samples=[[x,y] for y in range(4) for x in range(16)])
        noninteger=False
        for sample in result['samples']:
            c,m,y,k=sample['fallback_cmyk'];expected=[.40-.10*c-.05*m-.10*k,.42-.05*c-.10*m-.10*k,.35-.10*y-.10*k]
            for a,b in zip(sample['proof_xyz_d50'],expected):self.assertAlmostEqual(a,b*65535/32768,delta=.00006)
            noninteger|=any(abs(v*255-round(v*255))>.01 for v in sample['fallback_cmyk'])
        self.assertTrue(noninteger)

    def test_combined_model_requires_exact_ink_set_and_explicit_scope(self):
        d,_=self.document();attach_recipe(d);options=dict(profile=embedded(proof_profile()),matte=[255]*3,named_inks=mix(2))
        for key,value in [('missing',None),('extra',[0]*4),('range',[2]*4)]:
            bad=copy.deepcopy(options)
            if key=='missing':del bad['named_inks']['alternate_cmyk']['ink0']
            else:bad['named_inks']['alternate_cmyk']['extra' if key=='extra' else 'ink0']=value
            self.assertEqual(self.proof(d,bad,expected=1)['code'],'INVALID_REQUEST')
        self.assertEqual(self.proof(d,options,expected=1,include_bleed=True)['code'],'INVALID_REQUEST')
        del d['ink_recipe'];self.assertEqual(self.proof(d,options,expected=1)['code'],'INVALID_REQUEST')

    def test_combined_publication_metadata_history_and_failed_retry_preserve_source(self):
        d,_=self.document();attach_recipe(d)
        d['metadata']={'title':'Public original chart','private':{'note':'private-proof-secret'}}
        options=dict(profile=embedded(proof_profile()),matte=[255]*3,named_inks=mix(2))
        c=Client();self.addCleanup(c.close);c.initialize()
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='combined')
            c.success('session.create',**session,request_id='create',document=d)
            before=c.success('session.read',**session)
            output=dict(output_root=root,file_name='print.pdf',format='pdf',pdf_options=dict(print=options),metadata_policy=dict(mode='public'))
            published=c.success('session.publish',**session,expected_revision=0,output=output)
            raw=(Path(root)/'print.pdf').read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),published['sha256']);self.assertNotIn(b'private-proof-secret',raw)
            error=c.tool('session.publish',**session,expected_revision=0,output=output)['structuredContent']['error'];self.assertEqual(error['code'],'OUTPUT_EXISTS')
            self.assertEqual(c.success('session.read',**session),before);self.assertEqual((Path(root)/'print.pdf').read_bytes(),raw)
            failed=dict(output, file_name='failed.pdf',pdf_options=dict(print=dict(options,named_inks=mix(3))))
            self.assertEqual(c.tool('session.publish',**session,expected_revision=0,output=failed)['structuredContent']['error']['code'],'INVALID_REQUEST')
            self.assertFalse((Path(root)/'failed.pdf').exists())

    def test_gamut_input_and_output_curve_tables_gamma_and_negative_branches(self):
        cases=[(fixtures.curve(values=[512]),lambda x:x*x),
               (fixtures.curve(params=[2,1,-.25]),lambda x:max(0,x-.25)**2),
               (fixtures.curve(params=[2,1,-.25,.125]),lambda x:max(0,x-.25)**2+.125),
               (fixtures.curve(values=[0,16384,65535]),lambda x:x*32768/65535 if x<=.5 else 16384/65535+(x-.5)*98302/65535)]
        for curve,fn in cases:
            for output in [False,True]:
                kw=dict(output=curve) if output else dict(inputs=[curve,fixtures.IDENTITY,fixtures.IDENTITY])
                p=fixtures.profile(fixtures.modern_table(lambda q:q[0],**kw),pcs='XYZ ')
                xs=[0,.125,.25,.5,.875,1]
                for x,s in zip(xs,self.gamut(p,[[x*65535/32768,.2,.3] for x in xs])['samples']):self.assertAlmostEqual(s['gamut_value'],fn(x),places=13)

    def test_gamut_encoding_overflow_proof_mask_does_not_silently_clamp(self):
        d,_=self.document();p=fixtures.profile(pcs='XYZ ',white=(.01,.01,.01))
        options=dict(profile=embedded(p),matte=[255]*3,intent='absolute_colorimetric')
        result=self.proof(d,options,gamut='required')
        mask=scalar(result['gamut']['unclassified_mask'])[2]
        self.assertGreater(mask.count(255),0);self.assertEqual(result['gamut']['unclassified_pixels'],mask.count(255))

    def test_direct_gamut_exact_zero_and_quantized_nonzero_are_separate_from_delta(self):
        for version,modern in [(2,False),(4,False),(4,True)]:
            p=fixtures.profile(version=version,modern=modern)
            points=[xyz([l,0,0]) for l in [0,25,50,75,100]]
            r=self.gamut(p,points)
            for sample in r['samples']:
                expected=max(0,sample['encoded_pcs'][0]-.5)*2*32768/65535
                self.assertAlmostEqual(sample['gamut_value'],expected,places=13)
                self.assertEqual(sample['classification'],'in_gamut' if expected==0 else 'out_of_gamut')
            self.assertEqual(r['profile']['profile_sha256'],hashlib.sha256(p).hexdigest())

    def test_xyz_encoding_and_absolute_media_white_are_explicit(self):
        for modern in [False,True]:
            p=fixtures.profile(pcs='XYZ ',modern=modern,white=(.8,.9,.7))
            for intent in ['relative_colorimetric','absolute_colorimetric']:
                r=self.gamut(p,[[.5,.4,.3]],intent=intent);s=r['samples'][0]
                for a,b,scale in zip(s['encoded_pcs'],[.5,.4,.3],r['profile']['source_to_profile_relative_scale']):
                    self.assertAlmostEqual(a,b*scale*32768/65535,places=14)
                self.assertEqual(s['classification'],'in_gamut')

    def test_tetrahedral_nonlinear_cube_uses_all_axis_orders_and_ties(self):
        p=fixtures.profile(fixtures.modern_table(lambda q:math.prod(q)),pcs='XYZ ')
        codes=list(itertools.permutations([.2,.4,.7]))+[[.5]*3,[0]*3,[1]*3]
        result=self.gamut(p,[[v*65535/32768 for v in q] for q in codes])
        for q,s in zip(codes,result['samples']):self.assertAlmostEqual(s['gamut_value'],min(q),places=14)

    def test_modern_curve_matrix_middle_output_order_is_analytic(self):
        p=fixtures.profile(fixtures.modern_table(lambda q:q[0],
            inputs=[fixtures.curve(params=[2])]*3,
            matrix=[.5,.25,0,0,1,0,0,0,1,.125,0,0],
            middle=[fixtures.curve(params=[2])]*3,output=fixtures.curve(params=[2])),pcs='XYZ ')
        codes=[[.2,.4,.7],[.7,.2,.4],[.5,.5,.5]]
        for q,s in zip(codes,self.gamut(p,[[v*65535/32768 for v in q] for q in codes])['samples']):
            self.assertAlmostEqual(s['gamut_value'],(.5*q[0]**2+.25*q[1]**2+.125)**4,places=13)

    def test_all_five_parametric_curve_types_preserve_fixed_parameters(self):
        params=[[2],[2,.75,.125],[2,.75,.125,.0625],[2,1,0,.5,.25],[2,1,0,.5,.25,.125,.0625]]
        expected=[lambda x:x*x,lambda x:(.75*x+.125)**2,lambda x:(.75*x+.125)**2+.0625,
                  lambda x:x*x if x>=.25 else .5*x,lambda x:x*x+.125 if x>=.25 else .5*x+.0625]
        for values,fn in zip(params,expected):
            p=fixtures.profile(fixtures.modern_table(lambda q:q[0],inputs=[fixtures.curve(params=values),fixtures.IDENTITY,fixtures.IDENTITY]),pcs='XYZ ')
            xs=[.1,.25,.5,.75]
            for x,s in zip(xs,self.gamut(p,[[x*65535/32768,.3,.2] for x in xs])['samples']):self.assertAlmostEqual(s['gamut_value'],fn(x),places=13)

    def test_eight_bit_lab_tables_and_modern_eight_bit_clut(self):
        for version in [2,4]:
            p=fixtures.profile(fixtures.eight_table(lambda q:q[0]),version=version)
            result=self.gamut(p,[xyz([v,0,0]) for v in [0,25,50,75,100]])
            for s in result['samples']:
                x=s['encoded_pcs'][0];expected=x*256/255 if x<=.5 else 128/255+(x-.5)*254/255
                self.assertAlmostEqual(s['gamut_value'],expected,places=13)
        p=fixtures.profile(fixtures.modern_table(lambda q:q[0]*q[1]*q[2],precision=1),pcs='XYZ ')
        self.assertAlmostEqual(self.gamut(p,[[.4,.8,1.4]])['samples'][0]['gamut_value'],.4*32768/65535,places=14)

    def test_missing_disabled_required_and_outside_encoding_are_distinct(self):
        d,_=self.document();options=dict(profile=embedded(proof_profile()),matte=[255]*3)
        self.assertEqual(self.proof(d,options)['gamut']['status'],'unavailable')
        self.assertEqual(self.proof(d,options,gamut='off')['gamut']['status'],'disabled')
        self.assertEqual(self.proof(d,options,expected=1,gamut='required')['code'],'GAMUT_UNAVAILABLE')
        self.assertEqual(self.gamut(proof_profile(),[],expected=1)['code'],'GAMUT_UNAVAILABLE')
        r=self.gamut(fixtures.profile(pcs='XYZ '),[[-.1,.5,.5],[2.5,.5,.5]])
        self.assertTrue(all(s['classification']=='outside_pcs_encoding' and s['gamut_value'] is None for s in r['samples']))

    def test_proof_masks_correspond_to_direct_gamut_samples_and_preserve_source(self):
        d,_=self.document();before=copy.deepcopy(d);p=fixtures.profile()
        result=self.proof(d,samples=[[x,y] for y in range(4) for x in range(16)],gamut='required')
        direct=self.gamut(p,[s['source_xyz_d50'] for s in result['samples']])
        for a,b in zip(result['samples'],direct['samples']):
            self.assertEqual(a['gamut'],{k:v for k,v in b.items() if k!='xyz_d50'})
        expected=bytes(255 if s['classification']=='out_of_gamut' else 0 for s in direct['samples'])
        self.assertEqual(scalar(result['gamut']['mask'])[2],expected)
        self.assertEqual(result['gamut']['out_of_gamut_pixels'],expected.count(255))
        self.assertEqual(d,before)

    def test_malformed_table_bounds_channels_offsets_curves_and_overlap_fail(self):
        base=fixtures.profile(fixtures.modern_table(lambda q:q[0]));tags=tags_of(base);table=tags[b'gamt'];bad=[]
        for at,raw in [(8,b'\x04'),(12,struct.pack('>I',0)),(24,struct.pack('>I',0xfffffff0)),(36,b'\x01'),(10,b'\x01')]:
            q=bytearray(table);q[at:at+len(raw)]=raw;bad.append(bytes(q))
        q=bytearray(table);q[28:32]=q[24:28];bad.append(bytes(q))
        bad.extend([table[:20],table[:-5]])
        for value in bad:
            changed=dict(tags);changed[b'gamt']=value
            result=self.gamut(repack(base[:128],changed),[[.3,.3,.3]],expected=1)
            self.assertIn(result['code'],['INVALID_PROFILE','UNSUPPORTED'])

    def test_gamut_limits_controls_hash_pinned_files_and_strict_agent_schema(self):
        p=fixtures.profile();self.assertEqual(self.gamut(p,[[.2]*3]*4097,expected=1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.gamut(p,[],expected=1,control=dict(timeout_ms=0))['code'],'TIMEOUT')
        self.assertEqual(self.gamut(p,[],expected=1,intent='perceptual')['code'],'UNSUPPORTED_PROFILE_INTENT')
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'profile.icc';path.write_bytes(p);marker=Path(root)/'cancel';marker.touch()
            ref=dict(type='file',source_path=str(path),sha256=hashlib.sha256(p).hexdigest())
            args=dict(command='profile.gamut',profile=ref,xyz_d50=[[.2]*3])
            self.assertEqual(self.invoke(args)['samples'],self.gamut(p,[[.2]*3])['samples'])
            self.assertEqual(self.invoke(dict(args,control=dict(cancel_file=str(marker))),1)['code'],'CANCELLED')
            path.write_bytes(p+b'x');self.assertEqual(self.invoke(args,1)['code'],'PROFILE_MISMATCH')
        c=Client();self.addCleanup(c.close);c.initialize()
        tools=[];cursor=None
        while True:
            page=c.rpc('tools/list',{} if cursor is None else dict(cursor=cursor))['result'];tools.extend(page['tools']);cursor=page.get('nextCursor')
            if cursor is None:break
        tool=next(t for t in tools if t['name']=='inkbolt_profile_gamut')
        self.assertTrue(tool['annotations']['readOnlyHint'])
        self.assertEqual(c.success('profile.gamut',profile=embedded(p),xyz_d50=[[.2]*3]),self.gamut(p,[[.2]*3]))


if __name__=='__main__':unittest.main()
