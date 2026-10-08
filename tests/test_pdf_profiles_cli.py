"""Calibrated page blending, retained paint profiles and explicit source policy."""
import copy
import hashlib
import json
import tempfile
import unittest
import pdf_reader
import test_swatches_cli as swatches
import test_ink_delivery_cli as inks
import test_boards_cli as boards
from test_profiles_cli import builtin,embedded,linear_profile
from test_device_color_cli import gray_profile
from test_swatch_profiles_cli import managed
from cmyk_fixtures import cmyk_profile
from test_mcp import Client


class PdfProfileTests(unittest.TestCase):
    invoke=swatches.SwatchTests.invoke
    document=swatches.SwatchTests.document
    edit=swatches.SwatchTests.edit
    export=swatches.SwatchTests.export
    pdf=inks.InkDeliveryTests.pdf

    def set_profile(self,d,p):return self.edit(d,[dict(op='output_profile',profile=p)])
    def source_profile(self,reader,space):
        self.assertEqual(space[0],'ICCBased');return reader.streams[space[1]]

    def test_exact_page_profile_and_explicit_source_rgb_in_every_form_scope(self):
        raw=linear_profile();d=self.document({'ink':swatches.process(components=[.25,.5,.75])},[dict(id='group',opacity=.5,content=dict(type='group',isolated=True)),swatches.rectangle(parent='group')])
        original=copy.deepcopy(d);d=self.set_profile(d,embedded(raw));artifact=self.pdf(d);reader=pdf_reader.Pdf(artifact)
        self.assertTrue(reader.data.startswith(b'%PDF-2.0\n'))
        self.assertTrue(any(isinstance(o,dict) and o.get('UseBlackPtComp')=='OFF' and o.get('RI')=='RelativeColorimetric' for o in reader.objects.values()))
        profile_spaces=[page['Group']['CS'] for page in reader.pages]
        defaults=[]
        for obj in reader.objects.values():
            if isinstance(obj,dict) and 'Resources' in obj:
                defaults.append(reader.get(obj['Resources']['ColorSpace']['DefaultRGB']))
                if obj.get('Group',{}).get('I'):profile_spaces.append(obj['Group']['CS'])
        self.assertGreater(len(defaults),1)
        self.assertTrue(all(self.source_profile(reader,space)==raw for space in profile_spaces))
        self.assertTrue(all(space==defaults[0] for space in defaults))
        source=self.source_profile(reader,defaults[0]);self.assertNotEqual(source,raw)
        self.assertEqual(sum(stream==raw for stream in reader.streams.values()),1)
        self.assertEqual(artifact['color_profile']['icc_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(inks.painted(reader)[0]['values'],[.25,.5,.75])
        self.assertEqual(d['items'],original['items']);self.assertEqual(json.loads(self.export(d)['data']),d)

    def test_all_source_spaces_and_per_paint_intents_survive_calibrated_page_embedding(self):
        target=linear_profile();raws={'rgb':linear_profile(gamma=2),'gray':gray_profile(),'cmyk':cmyk_profile(intents=True)}
        for space,values in [('rgb',[.2,.4,.6]),('gray',[.5]),('cmyk',[.1,.2,.3,.4]),('lab',[50,0,0])]:
            for intent in ['relative_colorimetric','absolute_colorimetric','perceptual','saturation']:
                source=embedded(raws[space]) if space in raws else None
                d=self.document({'ink':managed(space,values,source,intent),'spot':managed(space,values,source,intent,spot=True)},[swatches.rectangle(),swatches.rectangle('s',swatches.paint('spot',.5),x=6)])
                d=self.set_profile(d,embedded(target));reader=pdf_reader.Pdf(self.pdf(d));records=inks.painted(reader)
                self.assertEqual(self.source_profile(reader,reader.pages[0]['Group']['CS']),target)
                self.assertEqual(records[0]['values'],values);self.assertEqual(records[1]['values'],[.5])
                self.assertEqual(records[0]['state']['RI'],dict(relative_colorimetric='RelativeColorimetric',absolute_colorimetric='AbsoluteColorimetric',perceptual='Perceptual',saturation='Saturation')[intent])
                self.assertEqual(records[0]['state']['UseBlackPtComp'],'OFF')
                self.assertEqual(records[1]['state']['UseBlackPtComp'],'OFF')
                if source:self.assertEqual(self.source_profile(reader,records[0]['space']),raws[space])
                else:self.assertEqual(records[0]['space'][0],'Lab')

    def test_legacy_native_mode_retains_cmyk_and_calibrated_rgb_rejects_untagged_inks(self):
        for is_spot in [False,True]:
            d=self.document({'ink':inks.cmyk([.2,.3,.4,.5],spot=is_spot)})
            native=self.pdf(d);self.assertEqual(pdf_reader.Pdf(native).pages[0]['Group']['CS'],'DeviceCMYK')
            assigned=self.set_profile(d,builtin('srgb'))
            error=self.export(assigned,'pdf',1,pdf_options=dict(color='native_inks'));self.assertEqual(error['code'],'UNTAGGED_COLOR')
            cleared=self.set_profile(assigned,None);self.assertEqual(self.pdf(cleared)['data'],native['data'])
        d=self.document({'ink':managed('rgb',[.2,.4,.6],untagged='assume_srgb')})
        d['vector_canvas']=dict(origin_px=[0,0],size_px=[16,8],unit='px',process_space='cmyk');d=self.set_profile(d,builtin('srgb'))
        self.assertEqual(self.export(d,'pdf',1,pdf_options=dict(color='native_inks'))['code'],'COLOR_POLICY_REQUIRED')

    def test_display_paths_and_images_keep_working_numbers_under_profiled_blending(self):
        d=self.invoke(dict(command='document.create',id='image-page',kind='raster',width=16,height=8))
        d['items']=[dict(id='pixels',content=dict(type='raster',width=2,height=1,rgba_hex='4080c0ff20406080'))]
        d=self.set_profile(d,embedded(linear_profile()));artifact=self.export(d,'pdf');reader=pdf_reader.Pdf(artifact)
        images=[(ref,obj) for ref,obj in reader.objects.items() if isinstance(obj,dict) and obj.get('Subtype')=='Image' and obj.get('ColorSpace')=='DeviceRGB']
        self.assertEqual(len(images),1);self.assertEqual(reader.streams[images[0][0]],bytes.fromhex('4080c0204060'))
        self.assertIn('color_profile',artifact)
        d=self.document(items=[swatches.rectangle(fill=[64,128,192,255])]);d=self.set_profile(d,embedded(linear_profile()))
        reader=pdf_reader.Pdf(self.export(d,'pdf'));self.assertEqual(inks.painted(reader)[0]['values'],[64/255,128/255,192/255])

    def test_selected_pages_retain_order_and_exact_calibration_without_source_changes(self):
        d=self.document(items=[boards.BoardCliTests().board('a',8,6),boards.BoardCliTests().board('b',12,8),swatches.rectangle(parent='a'),swatches.rectangle('second',parent='b')])
        d=self.set_profile(d,builtin('srgb'));before=copy.deepcopy(d)
        artifact=self.pdf(d,artboards=dict(type='ids',ids=['b','a']),include_bleed=True);reader=pdf_reader.Pdf(artifact)
        self.assertEqual([p['artboard_id'] for p in artifact['pages']],['b','a'])
        self.assertEqual(reader.pages[0]['Group']['CS'],reader.pages[1]['Group']['CS']);self.assertEqual(d,before)
        self.assertEqual(self.pdf(d,artboards=dict(type='ids',ids=['b','a']),include_bleed=True)['data'],artifact['data'])

    def test_durable_output_association_publication_undo_and_original_profiles(self):
        c=Client();self.addCleanup(c.close);c.initialize()
        d=self.document({'ink':managed('gray',[.5],embedded(gray_profile()),'absolute_colorimetric')})
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='pdf-color');c.success('session.create',**session,request_id='create',document=d)
            changed=c.success('session.apply',**session,expected_revision=0,request_id='profile',action=dict(type='edit',operations=[dict(op='output_profile',profile=builtin('srgb'))]))['document']
            output=dict(output_root=root,file_name='calibrated.pdf',format='pdf',pdf_options=dict(color='native_inks'))
            published=c.success('session.publish',**session,expected_revision=1,output=output);self.assertIn('color_profile',published)
            undone=c.success('session.apply',**session,expected_revision=1,request_id='undo',action=dict(type='undo'))['document'];self.assertEqual(undone,dict(d,revision=2));self.assertEqual(changed['swatches'],d['swatches']);self.assertTrue(c.success('session.verify',**session)['valid'])


if __name__=='__main__':unittest.main()
