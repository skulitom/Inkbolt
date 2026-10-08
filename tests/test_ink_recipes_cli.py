"""Original scalar recipes, exact rational curves and independent DeviceN framing."""
import base64
import copy
from fractions import Fraction as F
import hashlib
import itertools
import json
import math
import re
from pathlib import Path
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
from test_profiles_cli import builtin, png_profile, decode_srgb, encode_srgb
from test_proof_cli import scalar
from test_mcp import Client
import pdf_reader


def channel(values,width,height,role=None):
    return dict(name='Original scalar',role=role or dict(type='alpha'),plane=dict(width=width,height=height,gray_hex=bytes(values).hex()))


def recipe(n=2,masked=False):
    colors=[[30,100,200],[180,60,20],[55,170,85],[160,40,190],[190,140,20],[80,30,130],[210,210,210],[10,10,10]]
    return dict(inks=[dict(id='ink'+str(i),name='Repeated label',channel='gray',alternate_srgb=colors[i],curve=[[0,1],[1,0]],**(dict(mask_channel='mask') if masked else {})) for i in range(n)],preview=dict(type='transmittance',paper_srgb=[245,250,255]))


def tone(knots,value,alpha=255):
    x=F(value,255);points=[(F(a),F(b)) for a,b in knots]
    for a,b in zip(points,points[1:]):
        if a[0]<=x<=b[0]:
            v=a[1]+(x-a[0])/(b[0]-a[0])*(b[1]-a[1]);q=v*alpha+F(1,2)
            return q.numerator//q.denominator
    raise AssertionError((knots,value))


def calculator(program,inputs,outputs=3,max_stack=22):
    """Independent interpreter for the deliberately small delivered operator set."""
    tokens=iter(re.findall(r'\{|\}|[^\s{}]+',program.decode()))
    def parse():
        out=[]
        for token in tokens:
            if token=='}':return out
            out.append(parse() if token=='{' else token)
        return out
    root=parse();assert len(root)==1 and isinstance(root[0],list)
    stack=list(inputs);peak=len(stack)
    def run(ops):
        nonlocal peak
        for op in ops:
            if isinstance(op,list):stack.append(op)
            elif op=='dup':stack.append(stack[-1])
            elif op=='index':at=int(stack.pop());stack.append(stack[-1-at])
            elif op=='exch':stack[-2],stack[-1]=stack[-1],stack[-2]
            elif op=='pop':stack.pop()
            elif op=='roll':
                shift=int(stack.pop());n=int(stack.pop());shift%=n;v=stack[-n:];stack[-n:]=v[-shift:]+v[:-shift] if shift else v
            elif op=='ifelse':no=stack.pop();yes=stack.pop();condition=stack.pop();run(yes if condition else no)
            elif op in ['add','sub','mul','div','exp','le']:
                b=stack.pop();a=stack.pop()
                stack.append({'add':lambda:a+b,'sub':lambda:a-b,'mul':lambda:a*b,'div':lambda:a/b,'exp':lambda:a**b,'le':lambda:a<=b}[op]())
            else:stack.append(float(op))
            peak=max(peak,len(stack))
    run(root[0]);assert len(stack)==outputs and peak<=max_stack
    return stack


class InkRecipeTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,n=2,masked=False):
        d=self.invoke(dict(command='document.create',id='recipes',kind='raster',width=16,height=16,resolution_ppi=300))
        d['channels']={'gray':channel(range(256),16,16),'mask':channel(((i*73+41)%256 for i in range(256)),16,16)}
        d['ink_recipe']=recipe(n,masked)
        return self.invoke(dict(command='document.validate',document=d))
    def separate(self,d,expected=0,**kw):return self.invoke(dict(command='document.separations',document=d,**kw),expected)
    def edit(self,d,ops,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops),expected)
        return r if expected else r['document']
    def pdf(self,d,expected=0,**kw):return self.invoke(dict(command='document.export',document=d,format='pdf',pdf_options=dict(ink_recipe={},**kw)),expected)

    def test_duotone_curves_and_masks_have_one_exact_rational_projection(self):
        d=self.document(masked=True);original=copy.deepcopy(d)
        d['ink_recipe']['inks'][0]['curve']=[[0,1],[.125,.25],[.625,.875],[1,0]]
        d['ink_recipe']['inks'][1]['curve']=[[0,0],[.25,.75],[.75,.125],[1,1]]
        r=self.separate(d)
        for ink,plane in zip(d['ink_recipe']['inks'],r['plates']):
            self.assertEqual(scalar(plane)[2],bytes(tone(ink['curve'],i,(i*73+41)%256) for i in range(256)))
        self.assertEqual(d['channels'],original['channels'])
        self.assertEqual(self.separate(d),r)

    def test_half_ties_and_narrow_binary64_knots_use_exact_stored_values(self):
        d=self.document();q=128/255
        d['ink_recipe']['inks'][0]['curve']=[[0,.5],[math.nextafter(q,0),.5],[math.nextafter(q,1),.75],[1,1]]
        d['ink_recipe']['inks'][1]['curve']=[[0,.5],[1,.5]]
        r=self.separate(d)
        for ink,plane in zip(d['ink_recipe']['inks'],r['plates']):self.assertEqual(scalar(plane)[2],bytes(tone(ink['curve'],i) for i in range(256)))
        self.assertEqual(set(scalar(r['plates'][1])[2]),{128})

    def test_explicit_multidimensional_corners_have_exact_order_and_independent_mix(self):
        for n in [1,2,3,5,8]:
            d=self.document(n);d['width']=8;d['height']=1
            d['channels']={str(i):channel([(x*37+i*29)%256 for x in range(8)],8,1) for i in range(n)}
            for i,ink in enumerate(d['ink_recipe']['inks']):ink.update(channel=str(i),curve=[[0,0],[1,1]])
            corners=[[((b*701+c*139+17)%65536)/65535 for c in range(3)] for b in range(1<<n)]
            d['ink_recipe']['preview']=dict(type='corners',linear_rgb=corners)
            r=self.separate(d);_,_,actual,_=editing.png_pixels(base64.b64decode(r['preview']['data']))
            quantized=[[round(v*65535) for v in row] for row in corners]
            self.assertEqual(r['inks']['preview_corners_linear_rgb16'],quantized)
            for x in range(8):
                q=[F((x*37+i*29)%256,255) for i in range(n)]
                for c in range(3):
                    linear=sum(F(v[c],65535)*math.prod(q[i] if b&(1<<i) else 1-q[i] for i in range(n)) for b,v in enumerate(quantized))
                    self.assertEqual(actual[x*4+c],math.floor(encode_srgb(float(linear))*255+.5))
                self.assertEqual(actual[x*4+3],255)

    def test_transmittance_corner_model_uses_linear_rgb_and_embeds_display_profile(self):
        d=self.document();r=self.separate(d)
        for b,corner in enumerate(r['inks']['preview_corners_linear_rgb16']):
            for c,v in enumerate(corner):
                linear=decode_srgb(d['ink_recipe']['preview']['paper_srgb'][c]/255)
                for i,ink in enumerate(d['ink_recipe']['inks']):
                    if b&(1<<i):linear*=decode_srgb(ink['alternate_srgb'][c]/255)
                self.assertEqual(v,math.floor(linear*65535+.5))
        raw=base64.b64decode(r['preview']['data']);self.assertEqual(hashlib.sha256(png_profile(raw)).hexdigest(),r['preview']['icc_sha256'])

    def test_source_channel_edits_update_both_inks_without_changing_recipe_or_artwork(self):
        d=self.document();original=copy.deepcopy(d)
        before=self.invoke(dict(command='document.render',document=d))
        changed=self.edit(d,[dict(op='channel_put',id='gray',channel=channel([127]*256,16,16),replace_existing=True)])
        self.assertEqual(changed['ink_recipe'],d['ink_recipe']);r=self.separate(changed)
        self.assertTrue(all(set(scalar(p)[2])=={128} for p in r['plates']))
        self.assertEqual(self.invoke(dict(command='document.render',document=changed)),before)
        self.assertEqual(d,original)

    def test_missing_sources_masks_and_removal_fail_atomically(self):
        d=self.document(masked=True)
        for source in ['gray','mask']:
            self.assertEqual(self.edit(d,[dict(op='channel_remove',id=source)],1)['code'],'CHANNEL_IN_USE')
            bad=copy.deepcopy(d);del bad['channels'][source]
            self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'NOT_FOUND')
        result=self.edit(d,[dict(op='ink_recipe',recipe=None),dict(op='channel_remove',id='gray')]);self.assertNotIn('ink_recipe',result)
        self.assertEqual(self.separate(result,1)['code'],'INVALID_REQUEST')

    def test_invalid_ink_ids_curves_corners_and_legacy_schema_fail(self):
        d=self.document();invalid=[]
        a=copy.deepcopy(d);a['ink_recipe']['inks'][1]['id']='ink0';invalid.append(a)
        for curve in [[],[[0,0]],[[.1,0],[1,1]],[[0,0],[.8,1],[.8,0],[1,1]],[[0,0],[1,2]]]:
            a=copy.deepcopy(d);a['ink_recipe']['inks'][0]['curve']=curve;invalid.append(a)
        a=copy.deepcopy(d);a['ink_recipe']['preview']=dict(type='corners',linear_rgb=[[0,0,0]]);invalid.append(a)
        a=copy.deepcopy(d);a['ink_recipe']['inks'][0]['name']='';invalid.append(a)
        a=copy.deepcopy(d);a['schema_version']=1;invalid.append(a)
        for a in invalid:self.assertEqual(self.invoke(dict(command='document.validate',document=a),1)['code'],'INVALID_DOCUMENT')
        # The whole batch rolls back when a later recipe references a missing source.
        bad=copy.deepcopy(d['ink_recipe']);bad['inks'][0]['channel']='missing'
        self.assertEqual(self.edit(d,[dict(op='channel_put',id='extra',channel=channel([3]*256,16,16)),dict(op='ink_recipe',recipe=bad)],1)['code'],'NOT_FOUND')
        self.assertNotIn('extra',d['channels'])

    def test_scale_replicates_exact_plates_and_preserves_physical_density(self):
        d=self.document();base=self.separate(d)
        for scale in [2,4]:
            result=self.separate(d,scale=scale);self.assertEqual(result['inks']['resolution_ppi'],300*scale)
            for a,b in zip(base['plates'],result['plates']):
                raw=scalar(a)[2];w,h,scaled,chunks=scalar(b);self.assertEqual((w,h),(16*scale,16*scale))
                self.assertEqual(scaled,bytes(raw[(y//scale)*16+x//scale] for y in range(h) for x in range(w)))
                self.assertEqual(struct.unpack('>IIB',chunks[b'pHYs']),(round(300*scale/.0254),round(300*scale/.0254),1))

    def test_pdf_retains_devicen_planes_colorants_profile_and_bounded_calculator(self):
        d=self.document(3,masked=True);r=self.separate(d);a=self.pdf(d);p=pdf_reader.Pdf(a)
        image=next(v for v in p.objects.values() if isinstance(v,dict) and v.get('Subtype')=='Image')
        image_id=next(k for k,v in p.objects.items() if v is image);space=p.get(image['ColorSpace'])
        self.assertEqual(space[:2],['DeviceN',['Inkbolt.ink0','Inkbolt.ink1','Inkbolt.ink2']])
        self.assertEqual((image['Width'],image['Height'],image['BitsPerComponent']),(16,16,8));self.assertNotIn('SMask',image)
        interleaved=bytes(v for q in zip(*(scalar(x)[2] for x in r['plates'])) for v in q)
        self.assertEqual(p.streams[image_id],interleaved);self.assertEqual(a['inks'],r['inks'])
        f=p.get(space[3]);self.assertEqual(f['FunctionType'],4);self.assertEqual(f['Domain'],[0,1]*3);self.assertEqual(f['Range'],[0,1]*3)
        for offset in range(256):
            rgb=calculator(p.streams[space[3]],[v/255 for v in interleaved[offset*3:offset*3+3]])
            actual=editing.png_pixels(base64.b64decode(r['preview']['data']))[2][offset*4:offset*4+3]
            self.assertEqual(bytes(math.floor(v*255+.5) for v in rgb),actual)
        profile=p.streams[space[2][1]];self.assertEqual(hashlib.sha256(profile).hexdigest(),a['color_profile']['icc_sha256'])
        self.assertEqual(p.pages[0]['MediaBox'],[0,0,3.84,3.84]);self.assertEqual(a['pages'][0]['physical_points'],[3.84,3.84])
        self.assertEqual(self.pdf(d),a)

    def test_pdf_calculator_matches_independent_tensor_weights_for_eight_inks(self):
        for n in [1,2,5,8]:
            d=self.document(n);d['ink_recipe']['preview']=dict(type='corners',linear_rgb=[[((b*3307+c*157+17)%65536)/65535 for c in range(3)] for b in range(1<<n)])
            p=pdf_reader.Pdf(self.pdf(d));image=next(v for v in p.objects.values() if isinstance(v,dict) and v.get('Subtype')=='Image');space=p.get(image['ColorSpace']);program=p.streams[space[3]]
            for step in range(10):
                q=[F((step*37+i*83)%256,255) for i in range(n)]
                corners=[[round(v*65535) for v in row] for row in d['ink_recipe']['preview']['linear_rgb']]
                expected=[encode_srgb(float(sum(F(row[c],65535)*math.prod(q[i] if b&(1<<i) else 1-q[i] for i in range(n)) for b,row in enumerate(corners)))) for c in range(3)]
                actual=calculator(program,list(map(float,q)))
                for a,b in zip(actual,expected):self.assertAlmostEqual(a,b,places=13)

    def test_pdf_snapshot_privacy_and_create_only_publication(self):
        d=self.document();d['metadata']=dict(title='Original ink chart',private={'secret':'hidden-marker'})
        a=self.pdf(d);p=pdf_reader.Pdf(a);raw=base64.b64decode(a['data'])
        self.assertNotIn(b'hidden-marker',raw);self.assertIn(b'Original ink chart',raw)
        meta=p.streams[p.catalog['Metadata']];ET.fromstring(meta)
        snapshot=self.invoke(dict(command='document.export',document=d,format='snapshot'));self.assertEqual(json.loads(snapshot['data']),d)
        with tempfile.TemporaryDirectory() as root:
            output=dict(output_root=root,file_name='inks.pdf',format='pdf',pdf_options=dict(ink_recipe={}))
            result=self.invoke(dict(command='document.publish',document=d,output=output));before=(Path(root)/'inks.pdf').read_bytes()
            self.assertEqual(result['inks'],a['inks']);self.assertEqual(before,raw)
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output),1)['code'],'OUTPUT_EXISTS')
            self.assertEqual((Path(root)/'inks.pdf').read_bytes(),before)
        stripped=self.invoke(dict(command='document.export',document=d,format='pdf',pdf_options=dict(ink_recipe={}),metadata_policy=dict(mode='strip')))
        self.assertNotIn('Metadata',pdf_reader.Pdf(stripped).catalog)

    def test_delivery_option_conflicts_and_missing_recipe_fail_explicitly(self):
        d=self.document()
        for kw in [dict(color='native_inks'),dict(include_bleed=True),dict(artboards=dict(type='ids',ids=['missing']))]:
            self.assertEqual(self.pdf(d,1,**kw)['code'],'INVALID_REQUEST')
        d['output_profile']=builtin('srgb');self.assertEqual(self.pdf(d,1)['code'],'PROFILE_CONFLICT');del d['output_profile']
        del d['ink_recipe'];self.assertEqual(self.pdf(d,1)['code'],'INVALID_REQUEST')
        d=self.document()
        for scale in [0,5]:self.assertEqual(self.separate(d,1,scale=scale)['code'],'INVALID_REQUEST')

    def test_resource_and_cancellation_limits_return_no_artifact(self):
        d=self.document(8);d['width']=256;d['height']=128;d['channels']={'gray':channel([128]*32768,256,128)}
        self.assertEqual(self.separate(d,1)['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.pdf(d,1)['code'],'RESOURCE_LIMIT')
        d=self.document()
        self.assertEqual(self.separate(d,1,control=dict(timeout_ms=0))['code'],'TIMEOUT')
        with tempfile.TemporaryDirectory() as root:
            marker=Path(root)/'cancel';marker.write_text('')
            self.assertEqual(self.separate(d,1,control=dict(cancel_file=str(marker)))['code'],'CANCELLED')
            output=dict(output_root=root,file_name='inks.pdf',format='pdf',pdf_options=dict(ink_recipe={}))
            for control,code in [(dict(timeout_ms=0),'TIMEOUT'),(dict(cancel_file=str(marker)),'CANCELLED')]:
                self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output,control=control),1)['code'],code)
            self.assertEqual(list(Path(root).iterdir()),[marker])

    def test_inspection_diff_and_canvas_extent_retain_source_recipe(self):
        d=self.document(masked=True);info=self.invoke(dict(command='document.inspect',document=d))
        self.assertEqual(info['ink_recipe']['recipe'],d['ink_recipe'])
        for ink,receipt in zip(d['ink_recipe']['inks'],self.separate(d)['inks']['channels']):
            for field,source in [('source','gray'),('mask','mask')]:
                h=hashlib.sha256(bytes.fromhex(d['channels'][source]['plane']['gray_hex'])).hexdigest()
                self.assertEqual(receipt[field+'_sha256'],h)
                self.assertEqual(info['ink_recipe']['source_hashes' if field=='source' else 'mask_source_hashes'][ink['id']],h)
            self.assertEqual(receipt['mask_channel'],'mask')
        r=copy.deepcopy(d['ink_recipe']);r['inks'][0]['curve']=[[0,0],[1,1]]
        updated=self.edit(d,[dict(op='ink_recipe',recipe=r)])
        diff=self.invoke(dict(command='document.diff',before=d,after=updated))
        self.assertTrue(any(x['field']=='ink_recipe' for x in diff['metadata']))
        grown=self.edit(d,[dict(op='canvas',action=dict(type='extent',width=18,height=18,anchor='top_left'))])
        self.assertEqual(grown['ink_recipe'],d['ink_recipe'])
        for plate in self.separate(grown)['plates']:
            w,h,values,_=scalar(plate)
            self.assertTrue(all(values[y*w+x]==0 for y in range(h) for x in range(w) if x>=16 or y>=16))

    def test_unmasked_extent_is_zero_source_then_curve_not_implicit_zero_ink(self):
        d=self.document();grown=self.edit(d,[dict(op='canvas',action=dict(type='extent',width=18,height=18,anchor='top_left'))])
        for plate in self.separate(grown)['plates']:
            w,h,values,_=scalar(plate)
            self.assertTrue(all(values[y*w+x]==255 for y in range(h) for x in range(w) if x>=16 or y>=16))

    def test_transfer_and_board_views_keep_document_recipe_scope_explicit(self):
        d=self.document();source=self.document();source['id']='source'
        source['items']=[dict(id='shape',content=dict(type='raster',width=1,height=1,rgba_hex='204080ff'))]
        source['ink_recipe']['inks'][0]['curve']=[[0,0],[1,1]]
        result=self.edit(d,[dict(op='transfer',transfer=dict(source=source,ids=['shape'],prefix='copy'))])
        self.assertEqual(result['ink_recipe'],d['ink_recipe']);self.assertEqual(result['channels'],d['channels'])
        result=self.edit(result,[dict(op='add',item=dict(id='board',content=dict(type='frame',frame=dict(role='artboard',width=8,height=8))))])
        boards=self.invoke(dict(command='artboard.export',document=result,format='png'))
        w,h,pixels,_=editing.png_pixels(base64.b64decode(boards['artifacts'][0]['artifact']['data']))
        self.assertEqual((w,h),(8,8));self.assertEqual(pixels,bytes(8*8*4))
        self.assertEqual(self.separate(result)['inks'],self.separate(d)['inks'])

    def test_capabilities_declare_limits_and_unsupported_combinations(self):
        c=self.invoke(dict(command='capabilities'))['ink_recipes']
        self.assertEqual(c['inks'],[1,8]);self.assertEqual(c['curve_knots'],[2,64])
        self.assertIn('NChannel',c['combined_process'])
        self.assertFalse(c['source_mutation'])

    def test_mcp_recipe_edits_history_retry_and_pdf_publication(self):
        d=self.document();r=copy.deepcopy(d['ink_recipe']);del d['ink_recipe']
        c=Client();self.addCleanup(c.close);c.initialize()
        with tempfile.TemporaryDirectory() as root:
            s=dict(session_root=root,session_id='inks');c.success('session.create',**s,request_id='create',document=d)
            action=dict(type='edit',operations=[dict(op='ink_recipe',recipe=r)])
            applied=c.success('session.apply',**s,request_id='recipe',expected_revision=0,action=action)
            expected=self.separate(applied['document']);self.assertEqual(c.success('document.separations',document=applied['document']),expected)
            undo=c.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'));self.assertNotIn('ink_recipe',undo['document'])
            redo=c.success('session.apply',**s,request_id='redo',expected_revision=2,action=dict(type='redo'));self.assertEqual(redo['document']['ink_recipe'],r)
            self.assertTrue(c.success('session.apply',**s,request_id='recipe',expected_revision=0,action=action)['replayed'])
            out=dict(output_root=root,file_name='inks.pdf',format='pdf',pdf_options=dict(ink_recipe={}))
            delivered=c.success('session.publish',**s,expected_revision=3,output=out);self.assertEqual(delivered['inks'],expected['inks'])
            self.assertTrue(c.success('session.verify',**s)['valid'])
        self.assertIn('document.separations',c.success('capabilities')['commands'])


if __name__=='__main__':unittest.main()
