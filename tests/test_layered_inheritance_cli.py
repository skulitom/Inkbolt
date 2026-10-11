"""Original source-defined style graphs; no native tables or default values."""
import base64,copy,json,unittest
import layered_editable_text_fixtures as p
import layered_object_fixtures as objects
import layered_fixtures as f
import test_layered_editable_text_cli as editable
import test_layered_story_cli as story
from test_mcp import Client


def graph(text='AA'):
    g=p.global_data((text,));a=g['1']['1'][0]['0']
    root=copy.deepcopy(a['6']['0'][0]['0']['0']['6']);root['1']=10.0
    para={'0':0,'9':False}
    g['1'].update({'2':copy.deepcopy(root),'3':copy.deepcopy(para)})
    # Deliberately put each declared root at a different, nonzero table index.
    g['0']['5']={'0':[{'0':{'0':'Size choice','5':1,'6':{'1':30.0}}},{'0':{'0':'Root','6':root}}]}
    g['0']['6']={'0':[{'0':{'0':'Paragraph choice','6':1,'5':{'32':{'1':20.0,'53':{'99':story.Name('SimplePaint'),'0':{'0':1,'1':[1.0,0.0,1.0,0.0]}}}}}},
                         {'0':{'0':'Paragraph root','5':para}}]}
    a['6']['0'][0]['0']={'0':0};a['5']['0'][0]['0']={'0':0}
    return g


def sparse(text='AA'):
    local=p.local(text);local['EngineDict']['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']={}
    return local


class LayeredInheritanceTests(unittest.TestCase):
    invoke=editable.EditableLayeredTextTests.invoke
    setUp=editable.EditableLayeredTextTests.setUp
    add_font=editable.EditableLayeredTextTests.add_font
    bindings=editable.EditableLayeredTextTests.bindings
    args=editable.EditableLayeredTextTests.args
    load=editable.EditableLayeredTextTests.load
    pixels=editable.EditableLayeredTextTests.pixels

    def raw(self,g=None,local=None,version=1):
        g=graph() if g is None else g;text=g['1']['1'][0]['0']['0'][:-1]
        return p.source([p.layer(text,payload=sparse(text) if local is None else local)],g,version)

    def test_source_precedence_and_clear_override_have_analytic_pixels(self):
        for version in [1,2]:
            for level,size in [('root',10),('paragraph',20),('character',30),('local',40)]:
                g=graph();a=g['1']['1'][0]['0']
                if level=='root':a['5']['0'][0]['0']={'0':1};a['6']['0'][0]['0']={'0':1}
                elif level=='paragraph':g['0']['5']['0'][0]['0']['6']={}
                elif level=='local':a['6']['0'][0]['0']={'0':{'0':'','5':0,'6':{'1':40.0}}}
                r=self.load(self.raw(g,version=version));d=r['document'];frame=d['items'][0]['content']['frame']
                self.assertEqual(frame['style']['size'],size);self.assertEqual(frame['text'],'AA')
                self.assertEqual(frame['style']['fill'],[255,0,0,255] if level=='root' else [0,255,0,255])
                h=r['text'][0]['inheritance'];self.assertTrue(h['source_defined_inheritance']);self.assertFalse(h['source_defaults_invented'])
                self.assertFalse(h['named_style_links_retained']);self.assertTrue(r['text'][0]['missing_values_inherited'])
                # Integral glyph edges for size20/40; others still check structure.
                if size in [20,40]:
                    expected=bytes(v for y in range(48) for x in range(64) for v in
                        ([0,255,0,255] if 30-.7*size<=y<30 and any(8+size*(.05+.6*k)<=x<8+size*(.45+.6*k) for k in [0,1]) else [0,0,0,0]))
                    self.assertEqual(self.pixels(d),expected)

    def test_sparse_stale_local_values_never_override_source_styles(self):
        g=graph();expected=self.load(self.raw(g))['document']
        local=p.local(styles=[p.style(FontSize=7,FillColor=dict(Type=1,Values=[1,0,0,1]))])
        self.assertEqual(self.load(self.raw(g,local))['document'],expected)
        args=self.args(self.raw(g));del args['text_fonts']
        details=self.invoke(args,1)['details']
        self.assertEqual(details['local_font_reference_runs_missing'],1)
        self.assertEqual(details['font_face_names'],[])
        self.assertEqual(details['global_story']['font_face_names'],[p.NAME])
        self.assertIn('font_face_name',details['global_story']['character_styles']['comparison']['missing_local_controls'])
        self.assertEqual(self.load(p.source([p.layer(payload=sparse())]),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')

    def test_source_root_values_are_not_guessed_and_unknown_controls_stay_visible(self):
        for family,default,property_key in [('5','2','6'),('6','3','5')]:
            for change in ['missing','different','unknown']:
                g=graph()
                if change=='missing':del g['1'][default]
                elif change=='different':g['1'][default]['OriginalUnknown']=False
                else:
                    g['1'][default]['OriginalUnknown']=False
                    g['0'][family]['0'][1]['0'][property_key]['OriginalUnknown']=False
                self.assertEqual(self.load(self.raw(g),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        g=graph();g['0']['5']['0'][0]['0']['6']['1']=True
        self.assertEqual(self.load(self.raw(g),1)['code'],'INVALID_LAYERED_FILE')
        g=graph();g['0']['5']['1']=[{'0':0},{'0':1}]
        self.assertEqual(self.load(self.raw(g),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')

    def test_broken_cyclic_typed_and_deeper_references_fail_explicitly(self):
        for value in [-1,2,True,0.0,'0',story.Name('nil')]:
            g=graph();g['1']['1'][0]['0']['6']['0'][0]['0']={'0':value}
            self.assertEqual(self.load(self.raw(g),1)['code'],'INVALID_LAYERED_FILE')
        for family,parent,field in [('5','5','6'),('6','6','5')]:
            for fault in ['missing','self','cycle','bad_parent','bad_properties','unknown_wrapper']:
                g=graph();sheet=g['0'][family]['0'][0]['0']
                if fault=='missing':del g['0'][family]
                elif fault=='self':sheet[parent]=0
                elif fault=='cycle':g['0'][family]['0'][1]['0'][parent]=0
                elif fault=='bad_parent':sheet[parent]=True
                elif fault=='bad_properties':sheet[field]=[]
                else:sheet['unmapped']=False
                code=self.load(self.raw(g),1)['code']
                self.assertEqual(code,'UNSUPPORTED_LAYERED_SEMANTICS' if fault=='unknown_wrapper' else 'INVALID_LAYERED_FILE',(family,fault))
            g=graph();g['0'][family]['0'].insert(0,{'0':{'0':'Extra','5':{} if field=='5' else 1,'6':{} if field=='6' else 1}})
            g['0'][family]['0'][1]['0'][parent]=2
            self.assertEqual(self.load(self.raw(g),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')

    def test_paragraph_boundaries_split_character_properties_without_losing_utf16(self):
        text='A\r😀';g=graph(text);a=g['1']['1'][0]['0']
        g['0']['5']['0'][0]['0']['6']={}
        a['5']['0']=[{'0':{'0':0},'1':2},{'0':{'0':{'6':0,'5':{'32':{'1':35.0}}}},'1':3}]
        local=p.local(text,styles=[p.style(FontSize=20),p.style(FontSize=35)],lengths=[2,3])
        args=self.args(self.raw(g,local));del args['text_fonts']
        h=self.invoke(args,1)['details']['global_story']
        self.assertEqual(h['inheritance']['resolved_character_runs'],2)
        self.assertNotIn('size',h['character_styles']['comparison']['different_controls'])
        self.assertEqual(self.load(self.raw(g,local),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')

    def test_resolution_has_span_and_property_budgets(self):
        g=graph('A'*64);a=g['1']['1'][0]['0'];a['6']['0']=[{'0':{'0':0},'1':1} for _ in range(65)]
        for i in range(120):
            g['1']['2']['Original'+str(i)]=False;g['0']['5']['0'][1]['0']['6']['Original'+str(i)]=False
        error=self.load(self.raw(g),1);self.assertEqual(error['code'],'RESOURCE_LIMIT');self.assertIn('Resolved text exceeds',error['message'])
        g=graph('A'*128);a=g['1']['1'][0]['0']
        a['6']['0']=[{'0':{'0':0},'1':n} for n in [2]*64+[1]]
        a['5']['0']=[{'0':{'0':0},'1':n} for n in [1]+[2]*64]
        error=self.load(self.raw(g),1);self.assertEqual(error['code'],'RESOURCE_LIMIT');self.assertIn('Resolved text exceeds',error['message'])

    def test_nested_mcp_and_delivery_keep_resolved_editable_styles(self):
        raw=self.raw();r=self.load(raw);d=r['document']
        client=Client()
        try:
            client.initialize();args=self.args(raw)
            cap=client.success('capabilities')['layered_interchange']['text_import']['inheritance']
            self.assertEqual((cap['max_reference_depth'],cap['max_resolved_character_runs'],cap['max_property_references']),(2,65,8192))
            self.assertEqual(client.success('layered.import',**{k:v for k,v in args.items() if k!='command'}),r)
        finally:client.close()
        nested=f.make([dict(name='Placed',width=1,height=1,rgba=[0,0,0,255],extra=objects.placement(size=(64,48),matrix=(1,0,0,1,0,0)))],w=64,h=48,global_extra=objects.global_sources([objects.entry(raw)]))
        n=self.load(nested,embedded_objects=objects.POLICY)
        self.assertEqual(self.pixels(n['document']),self.pixels(d))
        self.assertEqual(n['embedded_sources'][0]['text'][0]['inheritance'],r['text'][0]['inheritance'])
        artifact=self.invoke(dict(command='document.export',document=d,format='layered_large',font_root=str(self.store),layered_options=dict(text=dict(reconstruction='native_layout',shape_owner='OriginalGeometry'))))
        reopened=self.load(base64.b64decode(artifact['data']))['document']
        self.assertEqual(reopened['items'][0]['content']['frame'],d['items'][0]['content']['frame'])
        self.assertEqual(self.pixels(reopened),self.pixels(d))


if __name__=='__main__':unittest.main()
