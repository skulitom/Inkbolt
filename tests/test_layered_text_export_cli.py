"""Editable text bytes, explicit reconstruction and durable font-bound delivery."""
import base64,copy,hashlib,json,tempfile,time,unittest
from pathlib import Path
import layered_fixtures as f
import layered_delivery_reader as objects
import layered_text_delivery_reader as reader
import test_layered_cli as core
from test_mcp import Client
from platform_support import requires_capability

POLICY=dict(text=dict(reconstruction='native_layout',shape_owner='OriginalFixture'))


class LayeredTextExportTests(unittest.TestCase):
    invoke=core.LayeredTests.invoke
    document=core.LayeredTests.document
    read=core.LayeredTests.read

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=self.root/'fonts'
        self.license=self.root/'LICENSE.txt';self.license.write_bytes((Path(__file__).resolve().parents[1]/'LICENSE').read_bytes())
        self.font=self.add_font('original',reader.named_font())
    def add_font(self,name,data):
        path=self.root/(name+'.ttf');path.write_bytes(data)
        return self.invoke(dict(command='font.import',source_path=str(path),license_path=str(self.license),store_root=str(self.store)))
    def scene(self,text='AB A',**options):
        d=self.document(160,96);d['resolution_ppi']=96;d['fonts']={'original':self.font}
        frame=dict(text=text,width=140,height=72,wrap=False,style=dict(font_id='original',size=24,fill=[20,80,160,255]))
        frame.update(options)
        d['items']=[dict(id='text',name='Editable text',transform=[1,0,0,1,8,10],content=dict(type='text',frame=frame))]
        return d
    def export(self,d,expected=0,format='layered',**kw):
        return self.invoke(dict(command='document.export',document=d,format=format,**dict(dict(font_root=str(self.store),layered_options=POLICY),**kw)),expected)
    def parse(self,d,**kw):
        artifact=self.export(d,**kw);p=f.parse(base64.b64decode(artifact['data']))
        return artifact,p,reader.record(next(l['tags'][b'TySh'] for l in p['layers'] if b'TySh' in l['tags']))
    def test_point_source_fonts_decimal_units_geometry_and_determinism(self):
        d=self.scene();before=copy.deepcopy(d)
        for format in ['layered','layered_large']:
            a,p,r=self.parse(d,format=format);data=r['data'];style=data['EngineDict']['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']
            self.assertEqual(r['fields']['Txt '],'AB A');self.assertEqual(data['EngineDict']['Editor']['Text'],'AB A\r')
            self.assertEqual(data['EngineDict']['StyleRun']['RunLengthArray'],[5])
            self.assertIs(type(style['FontSize']),float);self.assertEqual(style['FontSize'],24.0)
            self.assertEqual(style['FillColor']['Values'],[1.0,20/255,80/255,160/255]);self.assertEqual(style['Leading'],24.0)
            self.assertEqual(data['ResourceDict']['FontSet'][0]['Name'],'InkboltDeliveryFixture-Regular')
            self.assertEqual(r['matrix'],[1,0,0,1,8,29.2]);self.assertEqual(p['layers'][0]['name'],'Editable text')
            receipt=a['layered']['text'][0];self.assertFalse(receipt['native_layout_equality']);self.assertFalse(receipt['cached_pixels_are_source'])
            self.assertEqual(receipt['source_fonts'][0]['font'],self.font);self.assertFalse(receipt['source_fonts'][0]['recipient_file_identity_pinned'])
            self.assertEqual(receipt['text_sha256'],hashlib.sha256(b'AB A').hexdigest());self.assertIn('Font binaries',a['losses'][-1])
            self.assertEqual(self.export(d,format=format)['data'],a['data'])
            error=self.read(base64.b64decode(a['data']),1);self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
            self.assertEqual(error['details']['shape_owner_labels'],['OriginalFixture']);self.assertFalse(error['details']['editable_import_supported'])
        self.assertEqual(d,before);self.assertEqual((self.root/'original.ttf').read_bytes(),reader.named_font())
    def test_unicode_gaps_multiline_ranges_tracking_and_explicit_leading(self):
        d=self.scene('A😀B\nAéB',wrap=True,leading=30);frame=d['items'][0]['content']['frame']
        frame['ranges']=[dict(start=1,end=3,style=dict(frame['style'],size=18,tracking=2,features={'kern':0,'liga':0,'dlig':0})),dict(start=5,end=6,style=dict(frame['style'],size=20))]
        a,p,r=self.parse(d);e=r['data']['EngineDict'];self.assertEqual(e['Editor']['Text'],'A😀B\rAéB\r')
        self.assertEqual(e['StyleRun']['RunLengthArray'],[1,3,2,1,2]);self.assertEqual(e['ParagraphRun']['RunLengthArray'],[5,4])
        styles=[v['StyleSheet']['StyleSheetData'] for v in e['StyleRun']['RunArray']]
        self.assertEqual([s['FontSize'] for s in styles],[24,18,24,20,24]);self.assertTrue(all(s['Leading']==30 for s in styles))
        self.assertEqual(styles[1]['Tracking'],111);self.assertIs(type(styles[1]['Tracking']),int);self.assertFalse(styles[1]['AutoKerning']);self.assertFalse(styles[1]['Ligatures']);self.assertFalse(styles[1]['DLigatures'])
        self.assertEqual(a['layered']['text'][0]['tracking_quantization'],[dict(style_index=1,source_pixels=2,native_thousandths_em=111,delivered_pixels=1.998)])
        shape=e['Rendered']['Shapes']['Children'][0];self.assertEqual(shape['ShapeType'],1);self.assertEqual(shape['Cookie']['OriginalFixture']['BoxBounds'],[0,0,140,72])
        self.assertEqual(r['matrix'],[1,0,0,1,8,10]);self.assertEqual(a['layered']['text'][0]['utf16_units'],8)
    def test_empty_escaped_strings_and_automatic_tracking_feature(self):
        for text in ['', 'A(B)\\A', 'A\n', 'é😀']:
            with self.subTest(text=text):
                d=self.scene(text);d['items'][0]['content']['frame']['style']['tracking']=.25
                a,p,r=self.parse(d);self.assertEqual(r['fields']['Txt '],text.replace('\n','\r'))
                self.assertEqual(r['data']['EngineDict']['Editor']['Text'],text.replace('\n','\r')+'\r')
                self.assertFalse(r['data']['EngineDict']['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']['Ligatures'])
    def test_signed_tracking_rounds_native_units_with_explicit_receipt(self):
        for pixels,units in [(3,125),(.252,11),(-.252,-11),(2,83),(-2,-83)]:
            d=self.scene('AB');d['items'][0]['content']['frame']['style']['tracking']=pixels
            a,p,r=self.parse(d);style=r['data']['EngineDict']['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']
            self.assertEqual(style['Tracking'],units);self.assertIs(type(style['Tracking']),int)
            quantization=a['layered']['text'][0]['tracking_quantization']
            if pixels==3:self.assertEqual(quantization,[])
            else:self.assertEqual(quantization,[dict(style_index=0,source_pixels=pixels,native_thousandths_em=units,delivered_pixels=units*24/1000)])
    def test_affine_parent_and_cache_keeps_opacity_masks_separate(self):
        d=self.scene('AB');plain,p,r=self.parse(d);pixels=p['layers'][0]['rgba']
        d['items'][0].update(opacity=128/255,fill_opacity=192/255,visible=False,locked=True,mask=dict(width=2,height=1,gray_hex='40ff',linked=True))
        a,p,r=self.parse(d);self.assertEqual(p['layers'][0]['rgba'],pixels);self.assertEqual(p['layers'][0]['opacity'],128);self.assertFalse(p['layers'][0]['visible']);self.assertEqual(p['layers'][0]['mask_gray'],bytes([64,255]))
        d=self.scene('AB');d['items'][0]['parent']='folder';d['items'].insert(0,dict(id='folder',transform=[0,1,-1,0,90,1],content=dict(type='group',isolated=True)))
        a,p,r=self.parse(d);self.assertEqual(r['matrix'],[0,1,-1,0,60.8,9]);self.assertEqual(len(p['layers']),3)
    def test_source_preview_hash_and_native_cache_match_independent_source_render(self):
        d=self.scene('AB');a,p,r=self.parse(d)
        rgba=bytes.fromhex(self.invoke(dict(command='document.render',document=d,font_root=str(self.store)))['data'])
        self.assertEqual(a['layered']['source_composite_rgba_sha256'],hashlib.sha256(rgba).hexdigest())
        layer=p['layers'][0];top,left,bottom,right=layer['bounds'];crop=b''.join(rgba[(y*160+left)*4:(y*160+right)*4] for y in range(top,bottom))
        self.assertEqual(layer['rgba'],crop);self.assertNotEqual(crop,bytes(len(crop)))
    def test_nested_text_source_is_editable_and_font_names_are_global(self):
        source=self.scene('AB');obj=self.invoke(dict(command='object.import',snapshot=json.dumps(source)))['object']
        d=self.document(160,96);d['items']=[dict(id='placed',content=dict(type='object',object=obj))]
        options=dict(POLICY,embedded_objects='native_reconstruction');a=self.export(d,layered_options=options)
        native=objects.sources(f.parse(base64.b64decode(a['data']))['global_tags'][b'lnk2'])[0]
        nested=f.parse(native['data']);self.assertEqual(reader.record(nested['layers'][0]['tags'][b'TySh'])['fields']['Txt '],'AB')
        other=self.add_font('different',reader.named_font(advance=700));d['fonts']={'original':other};d['items'].append(copy.deepcopy(source['items'][0]))
        self.assertEqual(self.export(d,1,layered_options=options)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
    def test_policy_missing_font_names_collisions_and_invalid_identifiers(self):
        for options in [None,{},dict(text=dict(reconstruction='native_layout',shape_owner='')),dict(text=dict(reconstruction='native_layout',shape_owner='A B')),dict(text=dict(reconstruction='native_layout',shape_owner='A'*129))]:
            self.assertEqual(self.export(self.scene(),1,layered_options=options)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for options in [dict(text=dict(reconstruction='exact',shape_owner='OriginalFixture')),dict(text=dict(reconstruction='native_layout')),dict(text=dict(POLICY['text'],unknown=True))]:
            self.assertEqual(self.export(self.scene(),1,layered_options=options)['code'],'INVALID_REQUEST')
        for names in [[],['First','Second'],['Has Space'],['é'],['A'*129]]:
            d=self.scene();d['fonts']['original']=self.add_font('badname',reader.named_font(names=names))
            self.assertEqual(self.export(d,1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        d=self.scene();d['fonts']['second']=self.add_font('collision',reader.named_font(advance=700));second=copy.deepcopy(d['items'][0]);second['id']='second';second['content']['frame']['style']['font_id']='second';d['items'].append(second)
        self.assertIn('same native face name',self.export(d,1)['message'])
    def test_unsupported_style_layout_controls_and_cancellation(self):
        for change in [dict(align='center'),dict(direction='rtl'),dict(bidi='unicode'),dict(wrap=False,overflow='clip'),dict(wrap=True,overflow='visible')]:
            self.assertEqual(self.export(self.scene(**change),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for change in [dict(language='en'),dict(features={'calt':0}),dict(features={'liga':2}),dict(fill=[20,80,160,128])]:
            d=self.scene();d['items'][0]['content']['frame']['style'].update(change)
            self.assertEqual(self.export(d,1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for change in [dict(blend='multiply'),dict(opacity=.5)]:
            d=self.scene();d['items'][0].update(change);self.assertEqual(self.export(d,1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        self.assertEqual(self.export(self.scene(),1,control=dict(timeout_ms=0))['code'],'TIMEOUT')
        for format in ['png','snapshot','svg']:self.assertEqual(self.export(self.scene(),1,format=format)['code'],'INVALID_REQUEST')
        d=self.scene();d['fonts']['second']=self.font;d['items'][0]['content']['frame']['style']['fallback_fonts']=['second']
        self.assertEqual(self.export(d,1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
    def test_fonts_license_mutation_and_no_font_root_never_fall_back(self):
        d=self.scene();self.assertEqual(self.export(d,1,font_root=None)['code'],'FONT_ROOT_REQUIRED')
        fontpath=self.store/(self.font['sha256']+'.font');original=fontpath.read_bytes();fontpath.write_bytes(original[:-1]+bytes([original[-1]^1]))
        self.assertEqual(self.export(d,1)['code'],'FONT_CORRUPT');fontpath.write_bytes(original)
        licensepath=self.store/(self.font['license_sha256']+'.license');licensepath.write_bytes(b'changed')
        self.assertEqual(self.export(d,1)['code'],'FONT_CORRUPT')
    def test_variable_and_missing_outlines_fail_before_delivery(self):
        from synthetic_variable_font import variable_font, tables
        from synthetic_unicode_font import sfnt
        plain=tables(reader.named_font());plain.pop(b'glyf');plain.pop(b'loca')
        d=self.scene('AB');d['fonts']['original']=self.add_font('variable',reader.named_font(source=variable_font()))
        self.assertEqual(self.export(d,1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        path=self.root/'nooutlines.ttf';path.write_bytes(sfnt(plain))
        self.assertEqual(self.invoke(dict(command='font.import',source_path=str(path),license_path=str(self.license),store_root=str(self.store)),1)['code'],'UNSUPPORTED')
    def test_resource_limits_no_partial_publication(self):
        d=self.scene('A\n'*65,style=dict(font_id='original',size=.1,fill=[0,0,0,255]))
        self.assertEqual(self.export(d,1)['code'],'RESOURCE_LIMIT')
        d=self.scene('A'*80,style=dict(font_id='original',size=.1,fill=[0,0,0,255]));frame=d['items'][0]['content']['frame']
        frame['ranges']=[dict(start=i,end=i+1,style=frame['style']) for i in range(1,80,2)]
        self.assertEqual(self.export(d,1)['code'],'RESOURCE_LIMIT')
        path=self.root/'failed.psd';output=dict(output_root=str(self.root),file_name=path.name,format='layered',layered_options=POLICY)
        r=self.invoke(dict(command='document.preflight',document=d,resources=dict(font_root=str(self.store)),output=output))
        self.assertFalse(r['ready']);self.assertFalse(path.exists())
    def test_mcp_session_preflight_restart_history_and_create_only_without_job(self):
        self.delivery_workflow(False)

    @requires_capability('jobs')
    def test_mcp_session_preflight_restart_job_history_and_create_only(self):
        self.delivery_workflow(True)

    def delivery_workflow(self, with_job):
        d=self.scene('Aé😀B');before=copy.deepcopy(d);resources=dict(font_root=str(self.store))
        session=dict(session_root=str(self.root/'sessions'),session_id='textdelivery');output=dict(output_root=str(self.root),file_name='editable.psd',format='layered',layered_options=POLICY)
        c=Client();c.initialize()
        try:
            direct=self.export(d);remote=c.success('document.export',document=d,format='layered',layered_options=POLICY,font_root=str(self.store));self.assertEqual(direct,remote)
            c.success('session.create',**session,request_id='create',document=d,resources=resources)
            self.assertTrue(c.success('document.preflight',document=d,resources=resources,output=output)['ready']);self.assertFalse((self.root/'editable.psd').exists())
            published=c.success('session.publish',**session,expected_revision=0,output=output)
            raw=(self.root/'editable.psd').read_bytes();self.assertEqual(raw,base64.b64decode(direct['data']))
            self.assertEqual(c.tool('session.publish',**session,expected_revision=0,output=output)['structuredContent']['error']['code'],'OUTPUT_EXISTS')
            edit=dict(request_id='hide',expected_revision=0,action=dict(type='edit',operations=[dict(op='properties',id='text',visible=False)]))
            c.success('session.apply',**session,**edit);c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))
            job=dict(job_root=str(self.root/'jobs'),request_id='delivery',document=d,resources=resources,output=dict(output,file_name='background.psd'))
            if with_job: c.success('job.start',**job)
        finally:c.close()
        c=Client();c.initialize()
        try:
            self.assertTrue(c.success('session.apply',**session,**edit)['replayed']);self.assertTrue(c.success('session.verify',**session)['valid'])
            if with_job:
                deadline=time.monotonic()+20
                while True:
                    state=c.success('job.wait',job_root=job['job_root'],request_id='delivery',wait_ms=1000)
                    if state['state'] not in ['queued','running']:break
                    self.assertLess(time.monotonic(),deadline)
                self.assertEqual(state['state'],'completed',state);self.assertEqual((self.root/'background.psd').read_bytes(),raw)
                self.assertEqual(c.success('job.result',job_root=job['job_root'],request_id='delivery')['sha256'],published['sha256']);self.assertTrue(c.success('job.start',**job)['replayed'])
        finally:c.close()
        self.assertEqual(d,before)


if __name__=='__main__':unittest.main()
