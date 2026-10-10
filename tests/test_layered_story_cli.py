"""Original story-source conflicts, typed strings and strict bounded references."""
import copy, hashlib, json, tempfile, unittest
from pathlib import Path
import layered_fixtures as f
import layered_text_fixtures as t
import test_layered_metadata_cli as m
import test_layered_cli as core
from test_mcp import Client


class Name(str): pass


def encode(v):
    if isinstance(v, Name): return b'/'+v.encode('ascii')
    if isinstance(v, bytes): return b'('+v.replace(b'\\',b'\\\\').replace(b'(',b'\\(').replace(b')',b'\\)')+b')'
    if isinstance(v, dict): return b'<< '+entries(v)+b' >>'
    if isinstance(v, list): return b'[ '+b' '.join(map(encode,v))+b' ]'
    return t.data(v)


def entries(v): return b' '.join(b'/'+k.encode('ascii')+b' '+encode(x) for k,x in v.items())


def story(text, lengths=None, fonts=None):
    n=len(text.encode('utf-16-be'))//2+1
    lengths=[n] if lengths is None else lengths
    fonts=[0]*len(lengths) if fonts is None else fonts
    return {'0':{'0':text+'\r','5':{'0':[{'0':{},'1':n}]},
                 '6':{'0':[{'0':{'0':{'6':{'0':font}}},'1':length} for length,font in zip(lengths,fonts)]}}}


def global_data(text='A\U0001f600B'):
    return {'98':{'0':14},'0':{'1':{'0':[{'0':{'0':{'0':'OriginalStory-Regular'}}},
                                       {'0':{'0':{'0':'OriginalStory-Second'}}}]}},'1':{'1':[story(text)]}}


def tag(raw, key=b'Txt2', signature=b'8BIM', wide=False):
    return signature+key+(f.U64(len(raw)) if wide else f.U32(len(raw)))+raw+bytes(-len(raw)%4)


def source(global_=None, raw=None, index=0, text='A\U0001f600B', version=1, extra=b'', layers=None):
    if layers is None:
        layers=[dict(name='Original label',id=29,width=1,height=1,rgba=[3,7,11,255],
                     extra=f.tag(b'TySh',t.record(text,changes={'TextIndex':m.integer(index)})))]
    raw=entries(global_data() if global_ is None else global_) if raw is None else raw
    return f.make(layers,version=version,global_extra=extra+tag(raw))


class LayeredStoryTests(unittest.TestCase):
    invoke=core.LayeredTests.invoke
    read=core.LayeredTests.read

    def load(self, data=None, **kwargs):
        return self.read(source(**kwargs) if data is None else data,1,color_policy='assume_srgb')

    def test_global_source_is_selected_by_index_not_local_text_order_or_layer_id(self):
        g=global_data();g['1']['1']=[story('unselected'),story('B\U0001f600A',fonts=[1])]
        raw=entries(g)
        for version in [1,2]:
            d=self.load(global_=g,index=1,version=version)['details'];s=d['global_story']
            self.assertEqual(d['reported_text_source'],'local_record');self.assertEqual(d['native_story_index'],1)
            self.assertEqual(d['font_face_names'],['OriginalFixture-Regular'])
            self.assertEqual(s['font_face_names'],['OriginalStory-Second'])
            self.assertEqual((s['story_index'],s['story_count'],s['text_characters'],s['text_utf16_units']),(1,2,3,4))
            self.assertEqual(s['text_source'],'global_story');self.assertFalse(s['local_text_matches'])
            self.assertEqual(s['text_sha256'],hashlib.sha256('B\U0001f600A'.encode()).hexdigest())
            self.assertEqual(s['global_data_sha256'],hashlib.sha256(raw).hexdigest())
            for k in ['other_stories_validated','other_layer_references_validated','layout_semantics_validated','style_semantics_validated','local_style_consistency_validated','font_file_identity_declared']:
                self.assertFalse(s[k])
            self.assertFalse(d['whole_file_validated']);self.assertNotIn('document',d)
            self.assertLess(len(json.dumps(d).encode()),8192)

    def test_equal_text_and_missing_global_are_distinct_from_layout_acceptance(self):
        s=self.load()['details']['global_story'];self.assertTrue(s['local_text_matches'])
        self.assertTrue(s['global_tag_framing_validated']);self.assertTrue(s['selected_story_run_references_validated'])
        for index in [0,-1]:
            d=self.load(t.source(changes={'TextIndex':m.integer(index)}))['details']
            self.assertEqual(d['native_story_index'],index);self.assertFalse(d['global_story']['present'])
            self.assertEqual(d['global_story']['text_source'],'local_record')
        c=self.invoke(dict(command='capabilities'))['layered_interchange']['text_diagnostics']
        self.assertEqual(c['global_story']['versions'],[14]);self.assertFalse(c['editable_text_import'])

    def test_utf16_run_coverage_and_font_indices_are_independently_checked(self):
        g=global_data();g['1']['1']=[story('A\U0001f600B',[1,2,2],[1,0,1])]
        s=self.load(global_=g)['details']['global_story']
        self.assertEqual(s['font_face_names'],['OriginalStory-Regular','OriginalStory-Second']);self.assertEqual(s['style_runs'],3)
        for lengths in [[2,3],[1,1,3],[1,2,1],[1,2,3],[0,5],[-1,6],[1.0,4],[],[2**63,1]]:
            g['1']['1']=[story('A\U0001f600B',lengths)]
            with self.subTest(lengths=lengths):self.assertEqual(self.load(global_=g)['code'],'INVALID_LAYERED_FILE')
        for font in [-1,2,1.0,True,Name('nil'),'0']:
            g['1']['1']=[story('A\U0001f600B',fonts=[font])]
            self.assertEqual(self.load(global_=g)['code'],'INVALID_LAYERED_FILE')
        g=global_data();g['1']['1'][0]['0']['5']['0'][0]['1']=4
        self.assertEqual(self.load(global_=g)['code'],'INVALID_LAYERED_FILE')

    def test_missing_or_incorrect_story_reference_never_falls_back_to_local(self):
        for index in [-2,-1,1,2147483647]:
            error=self.load(index=index);self.assertEqual(error['code'],'INVALID_LAYERED_FILE');self.assertNotIn('details',error)
        for key in ['0','5','6']:
            g=global_data();del g['1']['1'][0]['0'][key]
            self.assertEqual(self.load(global_=g)['code'],'INVALID_LAYERED_FILE')
        for version in [0,13,15]:
            g=global_data();g['98']['0']=version
            self.assertEqual(self.load(global_=g)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')

    def test_named_and_byte_values_do_not_impersonate_unicode_text(self):
        g=global_data();g['unknown']=[Name('nil'),Name('OriginalType'),b'01(\\)\0\xff',{},False,-.5]
        self.assertTrue(self.load(global_=g)['details']['global_story']['local_text_matches'])
        for value in [Name('nil'),b'A\r','A','',42,True]:
            bad=copy.deepcopy(g);bad['1']['1'][0]['0']['0']=value
            self.assertEqual(self.load(global_=bad)['code'],'INVALID_LAYERED_FILE')
        for value in [Name('Face'),b'Face',None]:
            bad=copy.deepcopy(g)
            if value is None:del bad['0']['1']['0'][0]['0']['0']['0']
            else:bad['0']['1']['0'][0]['0']['0']['0']=value
            self.assertEqual(self.load(global_=bad)['code'],'INVALID_LAYERED_FILE')
        for value in ['', 'A'*129, 'has space', '\u00e9']:
            bad=copy.deepcopy(g);bad['0']['1']['0'][0]['0']['0']['0']=value
            self.assertEqual(self.load(global_=bad)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        # Global grammar additions do not relax local text data.
        local=t.payload();local['Unknown']=Name('nil')
        self.assertEqual(self.load(t.source(engine=encode(local)))['code'],'INVALID_LAYERED_FILE')

    def test_global_duplicate_keys_tokens_escapes_and_tag_framing_fail(self):
        valid=entries(global_data())
        for raw in [b'<< '+valid+b' >>',valid+b' /98 << /0 14 >>',valid+b' null',valid+b'\0',
                    valid+b' /X [1 2 >>',valid+b' /X << /A 0 /A 1 >>',valid+b' /X NaN',valid+b' /X 1e2',
                    valid+b' /X (\xfe\xff\x00)',valid+b' /X (\xfe\xff\xd8\x00)',valid+b' /X (abc',
                    valid+b' /X /',valid+b' /X /'+b'A'*129]:
            self.assertEqual(self.load(raw=raw)['code'],'INVALID_LAYERED_FILE',raw[-50:])
        self.assertEqual(self.load(raw=valid+b' /X (\x00\\q)')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for extra in [tag(valid),b'8BIMnoop'+f.U32(99999999),b'bad!noop'+f.U32(0),tag(b'a',b'noop')[:-1]+b'\1']:
            error=self.load(extra=extra);self.assertNotIn('details',error)
        self.assertEqual(self.load(extra=tag(b'',b'noop',b'8B64',True))['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        # Correctly framed unrelated records are not silently declared supported.
        self.assertFalse(self.load(extra=tag(b'opaque',b'noop'))['details']['whole_file_validated'])
        wide=tag(b'opaque',b'lnk2',b'8B64',True)
        self.assertTrue(self.load(extra=wide,version=2)['details']['global_story']['present'])

    def test_global_budgets_are_separate_from_local_and_receipts_remain_bounded(self):
        valid=entries(global_data())
        for raw in [valid+b' '*262144, valid+b' /X '+b'['*33+b'0'+b']'*33,
                    valid+b' /X ['+b'0 '*4097+b']',
                    valid+b' /X '+encode({str(i):[0]*4096 for i in range(8)}),
                    valid+b' /X '+encode(b'a'*16389)]:
            self.assertEqual(self.load(raw=raw)['code'],'RESOURCE_LIMIT')
        g=global_data();g['1']['1']=[story('A')]*257
        self.assertEqual(self.load(global_=g)['code'],'RESOURCE_LIMIT')
        g=global_data();g['1']['1']=[story('A'*4097)]
        self.assertEqual(self.load(global_=g)['code'],'RESOURCE_LIMIT')
        g=global_data();g['1']['1']=[story('A'*65,[1]*66)]
        self.assertEqual(self.load(global_=g)['code'],'RESOURCE_LIMIT')
        g=global_data();g['1']['1']=[story('A'*8,[1]*9,list(range(9)))];g['0']['1']['0']=[{'0':{'0':{'0':f'Original{i}'}}} for i in range(9)]
        self.assertEqual(self.load(global_=g)['code'],'RESOURCE_LIMIT')

    def test_unused_stories_and_later_layers_are_explicitly_not_validated(self):
        g=global_data();g['1']['1'].append({'unknown':True})
        layers=[dict(name='First',width=1,height=1,rgba=[1,2,3,255],extra=f.tag(b'TySh',t.record())),
                dict(name='Later',width=1,height=1,rgba=[1,2,3,255],extra=f.tag(b'TySh',b'broken'))]
        d=self.load(global_=g,layers=layers)['details']
        self.assertFalse(d['global_story']['other_stories_validated']);self.assertFalse(d['whole_file_validated'])

    def test_compatibility_markers_are_typed_untrusted_data_only(self):
        raw=t.record(changes={'oldText':m.boolean(True),'oldTextAge':m.enum('OriginalAge','OriginalState')})
        d=self.load(t.source(raw=raw))['details'];c=d['compatibility_markers']
        self.assertTrue(c['present']);self.assertTrue(c['old_text'])
        self.assertEqual(c['age'],dict(kind='OriginalAge',value='OriginalState'))
        self.assertFalse(c['semantics_validated']);self.assertFalse(c['trusted'])
        for changes in [{'oldText':m.integer(1)},{'oldTextAge':m.txt('age')}]:
            self.assertEqual(self.load(t.source(changes=changes))['code'],'INVALID_LAYERED_FILE')
        self.assertFalse(self.load()['details']['compatibility_markers']['present'])

    def test_empty_and_maximum_unicode_story_counts_and_remaining_container_limits(self):
        for text in ['', 'A(B)\\C', '\U0001f600'*4096]:
            g=global_data(text);s=self.load(global_=g)['details']['global_story']
            self.assertEqual(s['text_characters'],len(text));self.assertEqual(s['text_utf16_units'],len(text.encode('utf-16-be'))//2)
        valid=entries(global_data());raw=valid+b' /X '+encode({str(i):0 for i in range(4097)})
        self.assertEqual(self.load(raw=raw)['code'],'RESOURCE_LIMIT')
        extra=b''.join(tag(b'',f'{i:04}'.encode()) for i in range(512))
        self.assertEqual(self.load(extra=extra)['code'],'RESOURCE_LIMIT')
        for value in [[],[{'0':{},'1':0}],[{'0':{},'1':True}],[{'0':[], '1':5}]]:
            g=global_data();g['1']['1'][0]['0']['5']['0']=value
            self.assertEqual(self.load(global_=g)['code'],'INVALID_LAYERED_FILE')

    def test_cli_mcp_parity_source_pin_cancellation_and_no_writes(self):
        data=source(index=1,global_={**global_data(),'1':{'1':[story('unused'),story('B\U0001f600A')]}})
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'source.psd';p.write_bytes(data)
            args=dict(source_path=str(p),expected_sha256=hashlib.sha256(data).hexdigest(),id='incoming',color_policy='assume_srgb')
            expected=self.invoke(dict(command='layered.import',**args),1)
            c=Client()
            try:
                c.initialize();got=c.tool('layered.import',**args)
                self.assertTrue(got['isError']);self.assertEqual(got['structuredContent']['error'],expected)
                self.assertEqual(c.tool('layered.import',**args,control=dict(timeout_ms=0))['structuredContent']['error']['code'],'TIMEOUT')
            finally:c.close()
            args['expected_sha256']='0'*64
            self.assertEqual(self.invoke(dict(command='layered.import',**args),1)['code'],'SOURCE_MISMATCH')
            self.assertEqual(p.read_bytes(),data);self.assertEqual(list(Path(root).iterdir()),[p])


if __name__=='__main__':unittest.main()
