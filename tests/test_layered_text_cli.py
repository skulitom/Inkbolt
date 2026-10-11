"""Structured text diagnostics without opting into editable reconstruction."""
import hashlib,json,struct,tempfile,unittest
from advertised_limits import capabilities
from pathlib import Path
import layered_text_fixtures as t
import test_layered_metadata_cli as m
import test_layered_cli as core
from test_mcp import Client


class LayeredTextTests(unittest.TestCase):
    invoke=core.LayeredTests.invoke
    read=core.LayeredTests.read

    def load(self,raw=None,**kwargs):
        return self.read(t.source(**kwargs) if raw is None else raw,1,color_policy='assume_srgb')

    def test_valid_text_has_bounded_structured_requirements_without_claiming_import(self):
        raw=t.data(t.payload());error=self.load(engine=raw);d=error['details']
        self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        self.assertEqual(d['kind'],'native_text_requirements')
        self.assertEqual(d['text_characters'],3);self.assertEqual(d['text_utf16_units'],4)
        self.assertEqual(d['font_face_names'],['OriginalFixture-Regular'])
        self.assertEqual(d['text_data_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(d['style_runs'],1);self.assertEqual(d['paragraph_runs'],1)
        for k in ['editable_import_supported','whole_file_validated','layout_semantics_validated','cached_pixels_used','font_file_identity_declared']:
            self.assertFalse(d[k])
        self.assertNotIn('document',error);self.assertLess(len(json.dumps(error).encode()),8192)
        capability=self.invoke(dict(command='capabilities'))['layered_interchange']['text_diagnostics']
        self.assertTrue(capability['editable_text_import']);self.assertEqual(capability['editable_text_import_scope'],'explicit_point_subset;see_text_import');self.assertTrue(capability['editable_text_export'])
        self.assertEqual(capability['limits']['runs'],65)

    def test_font_references_and_unicode_run_units_are_checked(self):
        p=t.payload(lengths=[1,2,2],font_indices=[1,0,1]);d=self.load(engine=t.data(p))['details']
        self.assertEqual(d['font_face_names'],['OriginalFixture-Regular','OriginalFixture-Second'])
        self.assertEqual(d['style_runs'],3)
        for lengths in [[2,3],[1,1,3],[1,2,1],[1,2,3],[0,5],[-1,6],[1.0,4],[],[2**63,1]]:
            with self.subTest(lengths=lengths):
                self.assertEqual(self.load(engine=t.data(t.payload(lengths=lengths)))['code'],'INVALID_LAYERED_FILE')
        for index in [-1,2,2**40]:
            p=t.payload(font_indices=[index]);error=self.load(engine=t.data(p))
            self.assertNotIn('details',error)
        p=t.payload();p['EngineDict']['StyleRun']['RunArray'].append({})
        self.assertEqual(self.load(engine=t.data(p))['code'],'INVALID_LAYERED_FILE')

    def test_text_strings_escape_roundtrip_and_descriptor_consistency(self):
        for text in ['', 'A(B)\\C', 'A\rB', '\u00e9\U0001f600', 'AB'*700]:
            d=self.load(text=text)['details'];self.assertEqual(d['text_characters'],len(text))
        p=t.payload();p['EngineDict']['Editor']['Text']='changed\r'
        self.assertEqual(self.load(engine=t.data(p))['code'],'INVALID_LAYERED_FILE')
        p=t.payload();p['EngineDict']['Editor']['Text']='A\U0001f600B'
        self.assertEqual(self.load(engine=t.data(p))['code'],'INVALID_LAYERED_FILE')
        for raw in [b'(abc)',b'(\xfe\xff\x00)',b'(\xfe\xff\xd8\x00)',b'(\xfe\xff\x00A',b'(\xfe\xff\x00\\x)']:
            error=self.load(engine=b'<< /X '+raw+b' >>');self.assertNotIn('details',error)

    def test_dictionary_number_container_and_framing_corruption(self):
        valid=t.data(t.payload())
        malformed=[valid+b'false',valid[:-1],b'[]',b'<< /X 1 /X 2 >>',b'<< /X >>',
                   b'<< /X [1 2 >>',b'<< /X NaN >>',b'<< /X inf >>',b'<< /X 1.2.3 >>',
                   b'<< /X . >>',b'<< /X + >>',b'<< /X --1 >>',b'<< /X 1e999 >>',
                   b'<< /X 999999999999999999999999999999 >>',valid+b'\0']
        for raw in malformed:
            with self.subTest(raw=raw[:60]):
                self.assertEqual(self.load(engine=raw)['code'],'INVALID_LAYERED_FILE')
        for end in [b'',bytes(15),bytes(20),bytes(16)+b'\1']:
            self.assertEqual(self.load(tail=end)['code'],'INVALID_LAYERED_FILE')
        self.assertEqual(self.load(transform=(1,0,0,float('nan'),0,0))['code'],'INVALID_LAYERED_FILE')
        for kw in [dict(version=2),dict(text_version=51),dict(warp_version=2),dict(changes={'unknown':m.integer(1)})]:
            error=self.load(**kw);self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS');self.assertNotIn('details',error)

    def test_limits_reject_before_large_allocations_or_receipts(self):
        cap = capabilities()['layered_interchange']
        limits = cap['text_diagnostics']['limits']
        entries = limits['container_entries']
        depth = limits['data_depth'] + 2
        for raw in [b' '*(limits['record_bytes']+1),
                    b'<< /X '+b'['*depth+b'0'+b']'*depth+b' >>',
                    b'<< /X ['+b'0 '*(entries+1)+b'] >>',
                    b'<< '+b' '.join(b'/K'+str(i).encode()+b' 1' for i in range(entries+1))+b' >>',
                    b'<< /X '+t.data('A'*(limits['string_bytes']//2))+b' >>']:
            self.assertEqual(self.load(engine=raw)['code'],'RESOURCE_LIMIT')
        tree={f'K{i}':[0]*entries for i in range(limits['data_values']//entries)}
        self.assertEqual(self.load(engine=t.data(tree))['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.load(text='A'*(cap['text_delivery']['limits']['characters']+1))['code'],'RESOURCE_LIMIT')
        runs = limits['runs']
        p=t.payload('A'*runs,lengths=[1]*(runs+1))
        self.assertEqual(self.load(text='A'*runs,engine=t.data(p))['code'],'RESOURCE_LIMIT')
        faces = limits['referenced_fonts']
        p=t.payload('A'*faces,lengths=[1]*(faces+1),font_indices=list(range(faces+1)))
        p['ResourceDict']['FontSet']=[dict(Name=f'Original-{i}') for i in range(faces+1)]
        self.assertEqual(self.load(text='A'*faces,engine=t.data(p))['code'],'RESOURCE_LIMIT')

    def test_optional_bounds_descriptors_require_matching_class_and_finite_values(self):
        fields=[(k,b'UntF#Pnt'+struct.pack('>d',v)) for k,v in [('Left',0),('Top ',-3),('Rght',15),('Btom',4)]]
        changes={k:m.obj(k,fields) for k in ['bounds','boundingBox']}
        self.assertFalse(self.load(changes=changes)['details']['layout_semantics_validated'])
        for key in ['bounds','boundingBox']:
            error=self.load(changes={key:m.obj('unknown',fields)})
            self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS');self.assertNotIn('details',error)
            self.assertEqual(self.load(changes={key:m.obj(key,[('Left',m.number(float('inf')))]+fields[1:])})['code'],'INVALID_LAYERED_FILE')

    def test_unused_layout_fields_do_not_grant_semantic_acceptance(self):
        p=t.payload();p['EngineDict']['UnknownLayout']={'X':[-.5,True,False]}
        d=self.load(engine=t.data(p))['details'];self.assertFalse(d['layout_semantics_validated'])
        p['ResourceDict']['FontSet'][0]['Name']='A'*129
        self.assertEqual(self.load(engine=t.data(p))['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        p=t.payload();del p['EngineDict']['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']['Font']
        error=self.load(engine=t.data(p));self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS');self.assertNotIn('details',error)

    def test_geometry_owner_labels_are_bounded_untrusted_diagnostic_data(self):
        p=t.payload();p['EngineDict']['Rendered']={'Shapes':{'Children':[{'Cookie':{f'Owner{i}':{} for i in range(10)}}]}}
        d=self.load(engine=t.data(p))['details'];self.assertEqual(d['shape_owner_labels'],[f'Owner{i}' for i in range(8)])
        self.assertTrue(d['shape_owner_labels_truncated']);self.assertFalse(d['shape_owner_labels_trusted']);self.assertFalse(d['layout_semantics_validated'])

    def test_cli_mcp_parity_source_hash_cancellation_and_no_output(self):
        raw=t.source()
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'source.psd';path.write_bytes(raw)
            args=dict(source_path=str(path),id='imported',color_policy='assume_srgb')
            expected=self.invoke(dict(command='layered.import',**args),1)
            c=Client()
            try:
                c.initialize()
                response=c.tool('layered.import',**args)
                self.assertTrue(response['isError']);self.assertEqual(response['structuredContent']['error'],expected)
                error=c.tool('layered.import',**args,control=dict(timeout_ms=0))['structuredContent']['error']
                self.assertEqual(error['code'],'TIMEOUT');self.assertNotIn('details',error)
            finally:c.close()
            error=self.invoke(dict(command='layered.import',**args,expected_sha256='0'*64),1)
            self.assertEqual(error['code'],'SOURCE_MISMATCH');self.assertNotIn('details',error)
            self.assertEqual(path.read_bytes(),raw);self.assertEqual(list(Path(root).iterdir()),[path])


if __name__=='__main__':unittest.main()
