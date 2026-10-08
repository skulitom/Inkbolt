"""Original retained device colours, independent PDF operands and ink equations."""
import copy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import pdf_reader
import test_swatches_cli as swatches
import test_ink_delivery_cli as inks
import test_vector_plates_cli as plates
from test_profiles_cli import embedded, linear_profile
from test_sample_profiles_cli import tags_of
from test_device_color_cli import endpoint, gray_profile, independent_table
from cmyk_fixtures import cmyk_profile
from test_mcp import Client


def managed(space, values, profile=None, intent='relative_colorimetric', spot=False, **kw):
    color=dict(space='device', encoding=endpoint(space, profile, **kw), components=values, intent=intent)
    return dict(name='Original managed ink', definition=dict(type='spot', alternate=color) if spot else dict(type='process',color=color))


class SwatchProfileTests(unittest.TestCase):
    invoke=swatches.SwatchTests.invoke
    document=swatches.SwatchTests.document
    edit=swatches.SwatchTests.edit
    export=swatches.SwatchTests.export
    pixels=swatches.SwatchTests.pixels
    inspect=swatches.SwatchTests.inspect
    pdf=inks.InkDeliveryTests.pdf
    plates=plates.VectorPlateTests.plates

    def profile(self,d,action,expected=0,id='ink'):
        return self.edit(d,[dict(op='swatch_profile',id=id,action=action)],expected)

    def test_all_device_spaces_retain_exact_declarations_profiles_and_source_tints(self):
        for space,values,raw in [('rgb',[.2,.4,.6],linear_profile(gamma=2)),('gray',[.5],gray_profile()),('cmyk',[.1,.2,.3,.4],cmyk_profile()),('lab',[50,0,0],None)]:
            encoded=embedded(raw) if raw else None
            s=managed(space,values,encoded)
            d=self.document({'ink':s,'t':swatches.tint('ink',.5)},[swatches.rectangle(fill=swatches.paint('t',.5))])
            before=copy.deepcopy(d);saved=json.loads(self.export(d)['data']);self.assertEqual(saved,d)
            white={'rgb':[1,1,1],'gray':[1],'cmyk':[0]*4,'lab':[100,0,0]}[space]
            tinted=[float(F(w)+F(1,4)*(F(v)-F(w))) for w,v in zip(white,values)]
            converted=self.invoke(dict(command='color.convert',source=endpoint(space,encoded),destination=endpoint('rgb',untagged='assume_srgb'),values=[tinted]))['samples'][0]['values']
            expected=bytes(swatches.byte(v) for v in converted)+b'\xff'
            self.assertEqual(self.pixels(d)[1][:4],expected)
            self.assertIsNotNone(self.inspect(d)['swatches'][0]['preview_rgba']);self.assertEqual(d,before)

    def test_assignment_preserves_numbers_conversion_changes_them_and_history_receipt_retains_original(self):
        numbers=[.125,.5,.875];d=self.document({'ink':swatches.process(components=numbers)})
        assigned=self.profile(d,dict(type='assign',encoding=endpoint('rgb',embedded(linear_profile(gamma=2)))))
        self.assertEqual(assigned['swatches']['ink']['definition']['color']['components'],numbers)
        self.assertNotEqual(self.pixels(d)[1],self.pixels(assigned)[1]);self.assertEqual(assigned['items'],d['items'])
        action=dict(type='convert',destination=endpoint('rgb',embedded(linear_profile())))
        request=dict(command='document.edit',document=assigned,expected_revision=assigned['revision'],operations=[dict(op='swatch_profile',id='ink',action=action)])
        response=self.invoke(request);converted=response['document'];values=converted['swatches']['ink']['definition']['color']['components']
        for got,want in zip(values,[x*x for x in numbers]):self.assertAlmostEqual(got,want,places=14)
        self.assertEqual(self.pixels(assigned)[1],self.pixels(converted)[1]);self.assertEqual(d['swatches']['ink']['definition']['color']['components'],numbers)
        self.assertIn('original_declaration',json.dumps(response));self.assertIn('source_pcs_xyz',json.dumps(response))

    def test_gray_assignment_is_one_channel_and_conversion_respects_legacy_encoded_neutral(self):
        d=self.document({'ink':swatches.process(space='gray',component=.5)})
        assigned=self.profile(d,dict(type='assign',encoding=endpoint('gray',embedded(gray_profile()))))
        self.assertEqual(assigned['swatches']['ink']['definition']['color']['components'],[.5])
        converted=self.profile(d,dict(type='convert',destination=endpoint('rgb',untagged='assume_srgb')))
        for v in converted['swatches']['ink']['definition']['color']['components']:self.assertAlmostEqual(v,.5,places=13)
        self.assertNotEqual(self.pixels(assigned)[1],self.pixels(d)[1])

    def test_pdf_embeds_exact_deduplicated_profiles_tints_and_each_rendering_intent(self):
        intents={'relative_colorimetric':'RelativeColorimetric','absolute_colorimetric':'AbsoluteColorimetric','perceptual':'Perceptual','saturation':'Saturation'}
        for space,values,raw in [('rgb',[.25,.5,.75],linear_profile()),('gray',[.375],gray_profile()),('cmyk',[.125,.25,.5,.75],cmyk_profile())]:
            for intent,pdf_intent in intents.items():
                s=managed(space,values,embedded(raw),intent)
                d=self.document({'ink':s,'spot':managed(space,values,embedded(raw),intent,spot=True)},[swatches.rectangle(fill=swatches.paint(tint=.5)),swatches.rectangle('s',swatches.paint('spot',.25),x=5)])
                reader=pdf_reader.Pdf(self.pdf(d));records=inks.painted(reader);first,second=records
                profile_ref=first['space'][1];self.assertEqual(first['space'][0],'ICCBased');self.assertEqual(reader.streams[profile_ref],raw)
                self.assertEqual(reader.get(profile_ref)['N'],len(values));self.assertEqual(sum(v==raw for v in reader.streams.values()),1)
                self.assertEqual(first['state']['RI'],pdf_intent);self.assertEqual(second['state']['RI'],pdf_intent)
                white=[0]*4 if space=='cmyk' else [1]*len(values)
                self.assertEqual(first['values'],[w+.5*(v-w) for w,v in zip(white,values)])
                self.assertEqual(second['space'][0],'Separation');self.assertEqual(second['space'][2],['ICCBased',profile_ref]);self.assertEqual(second['values'],[.25])
                function=reader.get(second['space'][3]);self.assertEqual(function['C0'],white);self.assertEqual(function['C1'],values)

    def test_native_plate_conversion_uses_retained_source_profile_and_tints_before_conversion(self):
        raw=cmyk_profile();tags=tags_of(raw);values=[.125,.25,.5,.75]
        d=self.document({'ink':managed('cmyk',values,embedded(raw))},[swatches.rectangle(fill=swatches.paint(tint=.5))],w=8,h=8)
        actual=self.plates(d,samples=[[1,1]])['samples'][0]['ink_fractions']
        pcs=independent_table(tags[b'A2B1'],[F(x)/2 for x in values]);expected=independent_table(tags[b'B2A1'],pcs)
        for a,b in zip(actual,expected):self.assertAlmostEqual(a,float(b),places=14)
        self.assertNotEqual(actual,[x*.5 for x in values])
        self.assertEqual(json.loads(self.export(d)['data']),d)

    def test_profile_errors_locks_strict_fields_and_failed_batch_leave_original_unchanged(self):
        d=self.document({'ink':swatches.process(components=[.2,.4,.6])});before=copy.deepcopy(d)
        for encoding in [endpoint('rgb'),endpoint('gray',embedded(gray_profile())),endpoint('rgb',embedded(gray_profile())),endpoint('lab',embedded(linear_profile()))]:
            self.profile(d,dict(type='assign',encoding=encoding),1)
        locked=self.edit(d,[dict(op='properties',id='art',locked=True)])
        self.assertEqual(self.profile(locked,dict(type='assign',encoding=endpoint('rgb',untagged='assume_srgb')),1)['code'],'LOCKED')
        raw=self.document({'ink':swatches.process(space='cmyk',components=[.1,.2,.3,.4])})
        self.assertEqual(self.profile(raw,dict(type='convert',destination=endpoint('lab')),1)['code'],'UNTAGGED_COLOR')
        operation=dict(op='swatch_profile',id='ink',action=dict(type='assign',encoding=endpoint('rgb',untagged='assume_srgb')))
        self.edit(d,[operation,dict(op='remove',id='missing')],1);self.assertEqual(d,before)

    def test_tint_aliases_spot_identity_baking_transfer_and_explicit_delivery_boundaries(self):
        d=self.document({'ink':managed('gray',[.5],embedded(gray_profile()),spot=True),'t':swatches.tint('ink',.5)},[swatches.rectangle(fill=swatches.paint('t'))])
        converted=self.profile(d,dict(type='convert',destination=endpoint('rgb',untagged='assume_srgb')))
        self.assertEqual(converted['swatches']['ink']['definition']['type'],'spot');self.assertEqual(converted['swatches']['t'],d['swatches']['t'])
        self.profile(d,dict(type='assign',encoding=endpoint('rgb',untagged='assume_srgb')),1,id='t')
        for fmt in ['svg','pdf']:self.export(d,fmt,1)
        baked=self.edit(d,[dict(op='swatch_bake',ids=['art'])]);self.export(baked,'svg');self.assertEqual(self.pixels(d)[1],self.pixels(baked)[1]);self.assertEqual(baked['swatches'],d['swatches'])
        dest=self.invoke(dict(command='document.create',id='target',kind='vector',width=16,height=8))
        transferred=self.edit(dest,[dict(op='transfer',transfer=dict(source=d,ids=['art'],prefix='copy'))])
        self.assertEqual(transferred['swatches']['copy-ink'],d['swatches']['ink']);self.assertEqual(self.pixels(transferred)[1],self.pixels(d)[1])

    def test_mcp_durable_assignment_conversion_restart_undo_and_redo(self):
        d=self.document({'ink':swatches.process(components=[.25,.5,.75])})
        with tempfile.TemporaryDirectory(prefix='inkbolt-managed-') as td:
            c=Client();c.initialize();session=dict(session_root=td,session_id='managed');c.success('session.create',**session,request_id='create',document=d)
            assign=dict(op='swatch_profile',id='ink',action=dict(type='assign',encoding=endpoint('rgb',embedded(linear_profile(gamma=2)))))
            first=c.success('session.apply',**session,expected_revision=0,request_id='profile-assign',action=dict(type='edit',operations=[assign]));c.close()
            c=Client();self.addCleanup(c.close);c.initialize()
            current=c.success('session.read',**session)['document'];self.assertEqual(current,first['document']);self.assertEqual(current['swatches']['ink']['definition']['color']['components'],[.25,.5,.75])
            convert=dict(op='swatch_profile',id='ink',action=dict(type='convert',destination=endpoint('rgb',embedded(linear_profile()))))
            final=c.success('session.apply',**session,expected_revision=current['revision'],request_id='profile-convert',action=dict(type='edit',operations=[convert]))['document'];self.assertNotEqual(final['swatches'],current['swatches'])
            undone=c.success('session.apply',**session,expected_revision=final['revision'],request_id='undo',action=dict(type='undo'))['document'];self.assertEqual(undone['swatches'],current['swatches'])
            redone=c.success('session.apply',**session,expected_revision=undone['revision'],request_id='redo',action=dict(type='redo'))['document'];self.assertEqual(redone['swatches'],final['swatches'])
            self.assertTrue(c.success('session.verify',**session)['valid'])


if __name__=='__main__':unittest.main()
