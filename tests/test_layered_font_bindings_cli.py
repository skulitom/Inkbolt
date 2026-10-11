"""Pinned native face selection, stale caches and immutable licensed resources."""
import copy, hashlib, json, subprocess, tempfile, unittest
from pathlib import Path
import layered_fixtures as f
import layered_text_fixtures as t
import layered_text_delivery_reader as font_fixture
import test_layered_style_cli as styles
import test_layered_cli as core
from test_cli import EXE
from test_mcp import Client


class LayeredFontBindingTests(unittest.TestCase):
    invoke=core.LayeredTests.invoke

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=self.root/'.inkbolt/fonts';self.license=self.root/'LICENSE.txt'
        self.license.write_text('Original test font. MIT license retained by this fixture.')
        self.name='OriginalFixture-Regular';self.font=self.add_font('original',font_fixture.named_font(self.name))
        self.source=self.root/'original.psd';self.source.write_bytes(t.source())

    def add_font(self,label,data):
        p=self.root/(label+'.ttf');p.write_bytes(data)
        return self.invoke(dict(command='font.import',source_path=str(p),license_path=str(self.license),store_root=str(self.store)))

    def bindings(self,name=None,font=None,root=True):
        result=dict(bindings=[dict(face_name=name or self.name,font=font or self.font)])
        if root:result['font_root']=str(self.store)
        return result

    def args(self,bindings=None):
        return dict(command='layered.import',source_path=str(self.source),expected_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(),id='incoming',color_policy='assume_srgb',text_fonts=self.bindings() if bindings is None else bindings)

    def read(self,bindings=None,**kw):
        args=self.args(bindings);args.update(kw);return self.invoke(args,1)

    def owned_files(self):
        # Exact fixture inventory also catches unexpected empty directories.
        sources={self.source,self.license,self.root/'original.ttf'}
        stored={self.store/(self.font['sha256']+'.font'),self.store/(self.font['license_sha256']+'.license')}
        self.assertEqual(set(self.root.iterdir()),sources|{self.store.parent})
        self.assertEqual(set(self.store.parent.iterdir()),{self.store})
        self.assertEqual(set(self.store.iterdir()),stored)
        return {str(p):p.read_bytes() for p in sources|stored}

    def test_local_selection_is_pinned_without_claiming_source_font_identity(self):
        before=self.owned_files()
        error=self.read();self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        d=error['details'];r=d['font_bindings']
        expected=hashlib.sha256(json.dumps({self.name:self.font},sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(r,dict(text_source='local_record',checked_faces=1,unused_bindings=0,chosen_bindings_sha256=expected,chosen_resources_validated=True,source_font_files_identified=False))
        self.assertFalse(d['editable_import_supported']);self.assertFalse(d['font_file_identity_declared']);self.assertFalse(d['cached_pixels_used'])
        self.assertEqual(before,self.owned_files())

    def test_authoritative_global_faces_do_not_use_a_stale_local_binding(self):
        g,local=styles.inputs();g['0']['1']['0'][0]['0']['0']['0']=self.name
        self.source.write_bytes(styles.source(g,local))
        r=self.read()['details']['font_bindings'];self.assertEqual(r['text_source'],'global_story')
        self.assertEqual(r['checked_faces'],1)
        error=self.read(self.bindings(name='OriginalFixture-Second'))
        self.assertEqual(error['code'],'FONT_BINDING_REQUIRED');self.assertEqual(error['details']['missing_face_names'],[self.name])
        self.assertEqual(error['details']['text_source'],'global_story')

    def test_same_name_different_files_remain_explicit_distinct_choices(self):
        other=self.add_font('other',font_fixture.named_font(self.name,advance=900))
        a=self.read()['details']['font_bindings'];b=self.read(self.bindings(font=other))['details']['font_bindings']
        self.assertNotEqual(self.font['sha256'],other['sha256']);self.assertNotEqual(a['chosen_bindings_sha256'],b['chosen_bindings_sha256'])
        self.assertFalse(a['source_font_files_identified']);self.assertFalse(b['source_font_files_identified'])
        # The retained license is part of the selected identity as well.
        self.license.write_text('Original second permitted license statement.')
        alternate_license=self.invoke(dict(command='font.import',source_path=str(self.root/'original.ttf'),license_path=str(self.license),store_root=str(self.store)))
        c=self.read(self.bindings(font=alternate_license))['details']['font_bindings']
        self.assertNotEqual(a['chosen_bindings_sha256'],c['chosen_bindings_sha256'])

    def test_font_name_mismatch_never_falls_back_to_an_installed_font(self):
        other=self.add_font('other',font_fixture.named_font('OriginalDifferent-Regular'))
        error=self.read(self.bindings(font=other));self.assertEqual(error['code'],'FONT_FACE_MISMATCH')
        self.assertEqual(error['details']['face_name'],self.name)
        for name in ['originalfixture-Regular','OriginalFixture-RegularX']:
            error=self.read(self.bindings(name=name));self.assertEqual(error['code'],'FONT_BINDING_REQUIRED')

    def test_missing_corrupt_font_and_license_resources_fail_without_writes(self):
        self.assertEqual(self.read(self.bindings(root=False))['code'],'FONT_ROOT_REQUIRED')
        for path in [self.store/(self.font['sha256']+'.font'),self.store/(self.font['license_sha256']+'.license')]:
            original=path.read_bytes();path.unlink()
            self.assertEqual(self.read()['code'],'FONT_MISSING');self.assertFalse(path.exists())
            path.write_bytes(b'x'*len(original));self.assertEqual(self.read()['code'],'FONT_CORRUPT')
            self.assertEqual(path.read_bytes(),b'x'*len(original));path.write_bytes(original)
        wrong=copy.deepcopy(self.font);wrong['bytes']+=1
        self.assertEqual(self.read(self.bindings(font=wrong))['code'],'FONT_CORRUPT')
        wrong=copy.deepcopy(self.font);wrong['face_index']=1
        self.assertEqual(self.read(self.bindings(font=wrong))['code'],'INVALID_FONT')

    def test_invalid_names_duplicates_descriptor_bounds_and_missing_names(self):
        for name in ['', 'contains space', 'NonAscii\u00e9', 'x'*129]:
            value=self.bindings();value['bindings'][0]['face_name']=name
            self.assertEqual(self.read(value)['code'],'INVALID_REQUEST')
        value=self.bindings();value['bindings']*=2
        self.assertEqual(self.read(value)['code'],'INVALID_REQUEST')
        for bindings in [[],[dict(face_name='Original'+str(i),font=self.font) for i in range(9)]]:
            self.assertEqual(self.read(dict(bindings=bindings))['code'],'RESOURCE_LIMIT')
        for names in [[],['OriginalFixture-Regular','OriginalConflicting-Regular']]:
            font=self.add_font('unnamed'+str(len(names)),font_fixture.named_font(names=names))
            self.assertEqual(self.read(self.bindings(font=font))['code'],'UNSUPPORTED_LAYERED_SEMANTICS')

    def test_unused_bindings_are_not_read_and_order_does_not_change_identity(self):
        value=self.bindings();unused=copy.deepcopy(self.font);unused['sha256']='0'*64
        value['bindings'].append(dict(face_name='OriginalUnused-Regular',font=unused))
        a=self.read(value)['details']['font_bindings'];self.assertEqual(a['unused_bindings'],1)
        value['bindings'].reverse();b=self.read(value)['details']['font_bindings'];self.assertEqual(a,b)
        self.source.write_bytes(f.make([dict(name='Original pixels',width=1,height=1,rgba=[7,11,13,255])]))
        value['font_root']=str(self.root/'absent')
        result=self.invoke(self.args(value));self.assertNotIn('font_bindings',result);self.assertFalse((self.root/'absent').exists())

    def test_first_record_scope_does_not_claim_other_layers_have_bound_fonts(self):
        a=t.payload('A');b=t.payload('B');b['ResourceDict']['FontSet'][0]['Name']='OriginalOtherLayer-Regular'
        layers=[dict(name='First',width=1,height=1,rgba=[1,2,3,255],extra=f.tag(b'TySh',t.record('A',engine=t.data(a)))),dict(name='Second',width=1,height=1,rgba=[2,3,4,255],extra=f.tag(b'TySh',t.record('B',engine=t.data(b))))]
        self.source.write_bytes(f.make(layers));r=self.read()['details']
        self.assertFalse(r['whole_file_validated']);self.assertEqual(r['font_bindings']['checked_faces'],1)

    def test_source_identity_and_cancellation_precede_missing_font_resources(self):
        value=self.bindings(root=False)
        self.assertEqual(self.read(value,expected_sha256='0'*64)['code'],'SOURCE_MISMATCH')
        self.assertEqual(self.read(value,control=dict(timeout_ms=0))['code'],'TIMEOUT')
        args=self.args();args.pop('text_fonts');original=self.invoke(args,1)
        self.assertNotIn('font_bindings',original['details'])

    def test_cli_mcp_workspace_defaults_and_read_only_parity(self):
        args=self.args(self.bindings(root=False));args['source_path']='original.psd'
        before=self.owned_files()
        raw=subprocess.run([str(EXE),'--workspace',str(self.root)],input=json.dumps(args).encode(),capture_output=True,timeout=20)
        self.assertEqual(raw.returncode,1);error=json.loads(raw.stdout)['error'];self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        self.assertTrue(error['details']['font_bindings']['chosen_resources_validated'])
        client=Client(workspace=self.root)
        try:
            client.initialize();args.pop('command');reply=client.tool('layered.import',**args)
            self.assertTrue(reply['isError']);self.assertEqual(reply['structuredContent']['error'],error)
            schema=client.success('schema.lookup',name='layered.import',full=True)
            self.assertIn('TextFonts',schema['schema']['$defs'])
        finally:client.close()
        self.assertEqual(before,self.owned_files())


if __name__=='__main__':unittest.main()
