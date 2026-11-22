"""Original folder grammar, independent records, pixels and durable workflows."""
from advertised_limits import capabilities
import base64,copy,hashlib,tempfile,unittest
from fractions import Fraction
from pathlib import Path
import layered_fixtures as f
import test_blending_cli as reference
import test_layered_cli as core
from test_editing_cli import png_pixels
from test_mcp import Client

def marker(kind,name='folder',mode=b'norm',**kw):
    data=f.U32(kind)+(b'8BIM'+mode if kind in [1,2] else b'')
    return dict(name=name,width=0,height=0,rgba=[],extra=f.tag(b'lsct',data),**kw)
def pixel(name='pixels',**kw):return dict(name=name,width=2,height=1,rgba=[17,221,103,0,190,31,79,128],**kw)
def tree(d):
    def children(parent):
        return [(i['name'],i['content']['type'],i['visible'],i['opacity'],children(i['id'])) for i in d['items'] if i.get('parent')==parent]
    return children(None)


BLENDS = {
    'multiply': b'mul ', 'screen': b'scrn', 'darken': b'dark', 'lighten': b'lite',
    'overlay': b'over', 'hard_light': b'hLit', 'soft_light': b'sLit', 'exclusion': b'smud',
    'pin_light': b'pLit', 'subtract': b'fsub', 'hue': b'hue ', 'saturation': b'sat ',
    'color': b'colr', 'luminosity': b'lum ',
}
BACK = bytes.fromhex('265abaff 962b8e79 943a791f 54403100')
FIRST = bytes.fromhex('cd6523ff 63959b89 a0ae6fdb fc6bb895')
SECOND = bytes.fromhex('1676b960 f7a264c0 588cf100 ab1948b2')


def blended_sheet(mode, grouped):
    def strip(name, samples, **controls):
        return dict(name=name, width=4, height=1, rgba=samples, **controls)
    back = strip('paper', BACK)
    key = BLENDS[mode]
    if grouped:
        return [back, marker(3), strip('lower', FIRST), strip('upper', SECOND, blend=b'scrn'),
                marker(1, 'folder', mode=key, opacity=173)]
    return [back, strip('ink', FIRST, blend=key, opacity=173, extra=f.tag(b'iOpa',bytes([191,0,0,0])))]


def expected_strip(mode, grouped, fill=255, upper_mode='screen'):
    result = bytearray()
    for offset in range(0,len(BACK),4):
        back, first, second = (reference.premul(raw[offset:offset+4]) for raw in (BACK,FIRST,SECOND))
        if grouped:
            folder = reference.over(first, second, mode=upper_mode)
            color = reference.over(back, folder, Fraction(173*fill,255**2), mode)
        else:
            color = reference.over(back, first, Fraction(173*191,255**2), mode)
        result.extend(round(v) for v in reference.encoded(color))
    return bytes(result)

class GroupLayeredTests(unittest.TestCase):
    invoke=core.LayeredTests.invoke
    document=core.LayeredTests.document
    read=core.LayeredTests.read
    pixels=core.LayeredTests.pixels
    def export(self,d,version=1,expected=0):return self.invoke(dict(command='document.export',document=d,format='layered' if version==1 else 'layered_large'),expected)
    def scene(self):
        d=self.document(12,8)
        d['items']=[dict(id='back',content=dict(type='raster',width=2,height=1,rgba_hex='2864a0ff'*2)),dict(id='outer',name='folder Δ 🎨',opacity=153/255,transform=[1,0,0,1,2,1],content=dict(type='group',isolated=False)),dict(id='p',parent='inner',name='original',transform=[1,0,0,1,1,0],content=dict(type='raster',width=2,height=1,rgba_hex='11dd6700be1f4f80')),dict(id='inner',parent='outer',name='inner',opacity=128/255,content=dict(type='group',isolated=True)),dict(id='empty',parent='outer',name='empty',visible=False,locked=True,content=dict(type='group')),dict(id='above',name='original',transform=[1,0,0,1,3,2],content=dict(type='raster',width=1,height=1,rgba_hex='f08a3380'))]
        return self.invoke(dict(command='document.validate',document=d))
    def test_export_nested_folders_preserves_tree_original_pixels_and_absolute_placement(self):
        d=self.scene();before=copy.deepcopy(d)
        for version in [1,2]:
            artifact=self.export(d,version);raw=base64.b64decode(artifact['data']);native=f.parse(raw);records=native['layers'];self.assertEqual(len(records),9)
            self.assertEqual(artifact['layered']['empty_name_source_ids'],['back']);self.assertTrue(any('Empty names' in loss for loss in artifact['losses']))
            self.assertEqual([r['name'] for r in records],['','<group end>','<group end>','original','inner','<group end>','empty','folder Δ 🎨','original'])
            self.assertEqual(records[3]['bounds'],[1,3,2,5]);self.assertEqual(records[3]['rgba'].hex(),'11dd6700be1f4f80');self.assertEqual(records[7]['tags'][b'lsct'],f.U32(1)+b'8BIMpass')
            reopened=self.read(raw);self.assertEqual(reopened['layers'],6);self.assertEqual(reopened['groups'],3);self.assertEqual(reopened['serialized_records'],9)
            self.assertEqual(tree(reopened['document']),tree(d));self.assertEqual(self.pixels(reopened['document']),self.pixels(d));self.assertEqual(d,before)
            for item in reopened['document']['items']:
                if item['content']['type']=='group':self.assertEqual(item['transform'],[1,0,0,1,0,0])
    def test_original_nested_import_all_compressions_versions_and_folder_modes(self):
        records=[pixel('below'),marker(3),marker(3),pixel('same',xy=(2,1)),marker(2,'same',visible=False),pixel('second',xy=(1,2)),marker(1,'folder Δ 🎨',mode=b'pass',opacity=153),pixel('above',xy=(4,3))]
        outputs=[]
        for version in [1,2]:
            for compression in range(4):
                r=self.read(f.make(records,compression=compression,version=version),color_policy='assume_srgb');d=r['document'];self.assertEqual(r['groups'],2);self.assertEqual(len(d['items']),6)
                outer=next(i for i in d['items'] if i['name']=='folder Δ 🎨');self.assertFalse(outer['content']['isolated']);self.assertEqual(outer['opacity'],153/255)
                inner=next(i for i in d['items'] if i['content']['type']=='group' and i['name']=='same');self.assertEqual(inner['parent'],outer['id']);self.assertFalse(inner['visible'])
                child=next(i for i in d['items'] if i['content']['type']=='raster' and i['name']=='same');self.assertEqual(child['parent'],inner['id']);self.assertEqual(child['content']['rgba_hex'],'11dd6700be1f4f80');outputs.append(self.pixels(d))
        self.assertEqual(len(set(outputs)),1)
    def test_empty_folders_decode_zero_sample_channels_without_panics(self):
        for compression in range(4):
            for version in [1,2]:
                for channels in [[],[-1,0,1,2],[0,1,2]]:
                    records=[marker(3,channel_ids=channels),marker(1,'empty',channel_ids=channels)]
                    r=self.read(f.make(records,compression=compression,version=version),color_policy='assume_srgb');self.assertEqual(len(r['document']['items']),1);self.assertEqual(self.pixels(r['document']),'00000000'*48)

    def test_pixel_and_isolated_group_blends_preserve_channels_structure_and_composition(self):
        capability = capabilities()['layered_interchange']
        self.assertEqual(capability['pixel_blend_modes'], ['normal', *BLENDS])
        self.assertEqual(capability['groups']['modes'], ['normal_isolated','normal_pass_through',
                                                       *(mode+'_isolated' for mode in BLENDS)])
        for version in (1, 2):
            for mode, key in BLENDS.items():
                for grouped in (False, True):
                    with self.subTest(version=version, mode=mode, grouped=grouped):
                        layers = blended_sheet(mode, grouped)
                        if grouped:
                            layers[-1]['extra'] += f.tag(b'iOpa',bytes([63,0,0,0]))
                        raw = f.make(layers, w=4, h=1, version=version)
                        doc = self.read(raw, color_policy='assume_srgb')['document']
                        target = doc['items'][-1]
                        self.assertEqual(target['blend'], mode)
                        if grouped:
                            self.assertTrue(target['content']['isolated'])
                            self.assertEqual(doc['items'][2]['parent'], target['id'])
                            self.assertEqual(doc['items'][2]['blend'], 'screen')
                        pixels = bytes.fromhex(self.pixels(doc))
                        oracle = expected_strip(mode, grouped, fill=63)
                        self.assertLessEqual(max(abs(a-b) for a,b in zip(pixels, oracle, strict=True)), 1)
                        encoded = base64.b64decode(self.export(doc,version)['data'])
                        parsed = f.parse(encoded)
                        self.assertEqual(parsed['layers'][-1]['blend'], key)
                        if grouped:
                            self.assertEqual(parsed['layers'][-1]['tags'][b'lsct'], f.U32(1)+b'8BIM'+key)
                            self.assertEqual(parsed['layers'][1]['blend'], b'norm')
                            self.assertEqual(parsed['layers'][1]['tags'][b'iOpa'][0], 255)
                            self.assertEqual(parsed['layers'][-1]['tags'][b'iOpa'][0], 63)
                            self.assertEqual(parsed['layers'][-1]['opacity'], 173)
                        self.assertEqual([r['rgba'] for r in parsed['layers'] if r['rgba']],
                                         [BACK,FIRST,SECOND] if grouped else [BACK,FIRST])
                        again = self.read(encoded)['document']
                        self.assertEqual(self.pixels(again), pixels.hex())
                        self.assertEqual(again['items'][-1]['blend'], mode)

    def test_pass_through_folder_fill_preserves_pixels_and_editable_controls(self):
        for version in (1, 2):
            for fill, upper_mode in [(128,'normal'), (0,'screen'), (128,'screen')]:
                with self.subTest(version=version, fill=fill, upper_mode=upper_mode):
                    layers = blended_sheet('multiply', True)
                    layers[-2]['blend'] = b'norm' if upper_mode == 'normal' else b'scrn'
                    folder = marker(1, 'folder', mode=b'pass', opacity=173)
                    folder['extra'] += f.tag(b'iOpa', bytes([fill,0,0,0]))
                    layers[-1] = folder
                    # Non-normal children can blend against their own isolated
                    # group while the outer pass-through group stays editable.
                    if fill and upper_mode == 'screen':
                        layers.insert(2, marker(3))
                        layers.insert(-1, marker(1, 'inner'))
                    source = f.make(layers, w=4, h=1, version=version)
                    doc = self.read(source, color_policy='assume_srgb')['document']
                    expected = expected_strip('normal', True, fill, upper_mode)
                    actual = bytes.fromhex(self.pixels(doc))
                    self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,expected,strict=True)), 1)
                    encoded = base64.b64decode(self.export(doc, version)['data'])
                    records = f.parse(encoded)['layers']
                    self.assertEqual([layer['rgba'] for layer in records if layer['rgba']], [BACK,FIRST,SECOND])
                    outer = self.read(encoded)['document']['items'][-1]
                    self.assertFalse(outer['content']['isolated'])
                    self.assertEqual((outer['opacity'],outer['fill_opacity']), (173/255,fill/255))

    def test_intermediate_pass_through_fill_rejects_backdrop_blend_in_file_and_edit(self):
        layers = blended_sheet('multiply', True)
        layers[-1] = marker(1, 'outer', mode=b'pass')
        full = self.read(f.make(layers,w=4,h=1), color_policy='assume_srgb')['document']
        group = full['items'][-1]
        operation = dict(op='properties', id=group['id'], fill_opacity=128/255)
        error = self.invoke(dict(command='document.edit', document=full, expected_revision=full['revision'], operations=[operation]),1)
        self.assertEqual(error['code'],'UNSUPPORTED')
        self.assertIn('backdrop', error['message'])
        layers[-1]['extra'] += f.tag(b'iOpa', bytes([128,0,0,0]))
        error = self.read(f.make(layers,w=4,h=1),1,color_policy='assume_srgb')
        self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        self.assertIn('backdrop', error['message'])

    def test_folder_blend_header_fallback_and_conflicting_or_unknown_modes(self):
        for header, divider in [(b'mul ', f.U32(2)), (b'norm',f.U32(2)+b'8BIMmul '),
                                (b'mul ',f.U32(2)+b'8BIMmul ')]:
            folder = marker(2, blend=header)
            folder['extra'] = f.tag(b'lsct',divider)
            doc = self.read(f.make([marker(3),pixel(),folder]),color_policy='assume_srgb')['document']
            self.assertEqual(doc['items'][-1]['blend'],'multiply')
        for folder in [marker(1,blend=b'scrn',mode=b'mul '),marker(1,blend=b'pass',mode=b'mul ')]:
            error = self.read(f.make([marker(3),folder]),1,color_policy='assume_srgb')
            self.assertEqual(error['code'],'INVALID_LAYERED_FILE')

    def test_shallow_and_deep_pixel_knockout_survive_nested_folders(self):
        def strip(name,color):
            return dict(name=name,width=3,height=1,rgba=bytes(color)*3)
        paper = strip('paper',[220,87,13,255])
        lower = strip('outside inner folder',[183,61,141,255])
        inner = strip('inside',[31,58,191,255])
        cut = dict(name='cut',width=3,height=1,rgba=bytes.fromhex('80000000 80000080 800000ff'))
        following = dict(name='following',width=3,height=1,rgba=bytes.fromhex('00ff0000 00ff0000 00ff00ff'))
        capability = capabilities()['layered_interchange']['pixel_knockout']
        self.assertEqual(capability['targets'],['none','shallow','deep'])
        for version in (1,2):
            for target,byte in [('shallow',1),('deep',2)]:
                flagged = dict(cut,extra=f.tag(b'knko',bytes([byte,0,0,0]))+f.tag(b'iOpa',bytes(4)))
                records = [paper,marker(3),lower,marker(3),inner,flagged,following,
                           marker(1,'inner',mode=b'pass'),marker(1,'outer')]
                doc = self.read(f.make(records,w=3,h=1,version=version),color_policy='assume_srgb')['document']
                items = {i['name']:i for i in doc['items']}
                self.assertEqual(items['cut']['knockout_target'],target)
                self.assertNotIn('knockout_target',items['following'])
                revealed = lower if target=='shallow' else paper
                half = [round((127*x+128*y)/255) for x,y in zip(inner['rgba'][:4],revealed['rgba'][:4])]
                self.assertEqual(bytes.fromhex(self.pixels(doc)),inner['rgba'][:4]+bytes(half)+bytes([0,255,0,255]))
                raw = base64.b64decode(self.export(doc,version)['data'])
                parsed = {i['name']:i for i in f.parse(raw)['layers']}
                self.assertEqual(parsed['cut']['tags'][b'knko'],bytes([byte,0,0,0]))
                self.assertEqual(parsed['cut']['rgba'],cut['rgba'])
                self.assertNotIn(b'knko',parsed['following']['tags'])
                again = self.read(raw)['document']
                self.assertEqual(self.pixels(again),self.pixels(doc))
                self.assertEqual(next(i for i in again['items'] if i['name']=='cut')['knockout_target'],target)

    def test_layer_knockout_opacity_and_document_background(self):
        doc=self.document(1,1)
        def pixel_item(name,color,**controls):
            return dict(id=name,content=dict(type='raster',width=1,height=1,rgba_hex=color),**controls)
        doc['items']=[pixel_item('paper','d5322aff'),pixel_item('ink','1e3cb4ff'),
                      pixel_item('cut','e24612ff',fill_opacity=0,opacity=128/255,knockout_target='deep')]
        self.assertEqual(self.pixels(doc),'1e3cb47f')
        doc['background']=dict(item_id='paper',matte=[255,255,255])
        expected=bytes([round((a*127+b*128)/255) for a,b in zip(bytes.fromhex('1e3cb4'),bytes.fromhex('d5322a'))])+b'\xff'
        self.assertEqual(bytes.fromhex(self.pixels(doc)),expected)
        cover = pixel_item('paint-on-paper','00ff00ff',clip_to='paper')
        doc['items'].insert(1,cover)
        self.assertEqual(bytes.fromhex(self.pixels(doc)),expected)
        doc['items'][-1]['opacity']=0
        self.assertEqual(self.pixels(doc),'1e3cb4ff')
        doc['items'][-1]['opacity']=1
        edit=dict(op='properties',id='cut',knockout_target='none')
        changed=self.invoke(dict(command='document.edit',expected_revision=0,document=doc,operations=[edit]))['document']
        self.assertEqual(self.pixels(changed),'1e3cb4ff')
        self.assertNotIn('knockout_target',changed['items'][-1])
        difference=self.invoke(dict(command='document.diff',before=doc,after=changed))
        self.assertIn('knockout_target',next(i for i in difference['items'] if i['id']=='cut')['fields'])

    def test_knockout_marks_on_folders_and_clipped_members_fail_explicitly(self):
        tag=f.tag(b'knko',bytes([1,0,0,0]))
        folder=marker(1)
        folder['extra']+=tag
        for records in ([marker(3),pixel(),folder],[pixel('base'),pixel('cut',clipping=1,extra=tag)]):
            error=self.read(f.make(records),1,color_policy='assume_srgb')
            self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
            self.assertIn('knockout',error['message'])

    def test_fixed_background_roundtrip_paint_visibility_and_protection(self):
        paper = dict(name='paper',width=1,height=1,xy=(1,0),rgba=bytes.fromhex('c2497fff'),
                     channel_ids=[0,1,2],flags=9,extra=f.tag(b'lspf',f.U32(13)))
        ink = dict(name='ink',width=3,height=1,rgba=bytes.fromhex('63819cff')*3)
        cut = dict(ink,name='cut',extra=f.tag(b'knko',bytes([2,0,0,0]))+f.tag(b'iOpa',bytes(4)))
        for version in (1,2):
            source = f.make([paper,ink,cut],w=3,h=1,version=version)
            doc = self.read(source,color_policy='assume_srgb')['document']
            bg = doc['items'][0]['id']
            self.assertEqual(doc['background'],dict(item_id=bg,matte=[255]*3,fixed_pixel_bounds=[1,0,1,1]))
            self.assertFalse(doc['items'][0]['locked'])
            self.assertEqual(self.pixels(doc),'ffffffffc2497fffffffffff')
            def edit(d,operation,expected=0):
                result = self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],
                                          operations=[dict(id=bg,**operation)]),expected)
                return result if expected else result['document']
            fill = dict(op='pixel_fill',rect=dict(x=0,y=0,width=1,height=1))
            painted = edit(doc,dict(fill,color=[31,79,201,255]))
            extend = dict(op='canvas',action=dict(type='extent',width=5,height=1,anchor='center'))
            expanded = self.invoke(dict(command='document.edit',document=painted,expected_revision=1,operations=[extend]))['document']
            self.assertEqual(expanded['background']['fixed_pixel_bounds'],[2,0,1,1])
            self.assertEqual(self.pixels(expanded),'ffffffff'*2+'1f4fc9ff'+'ffffffff'*2)
            self.assertEqual(self.pixels(self.read(base64.b64decode(self.export(expanded,version)['data']))['document']),self.pixels(expanded))
            for op in [dict(fill,color=[31,79,201,127]),dict(op='properties',opacity=.5),
                       dict(op='transform',matrix=[1,0,0,1,2,0])]:
                error = edit(painted,op,1)
                self.assertEqual((error['code'],error['item_id']),('BACKGROUND_PROTECTED',bg))
            for shown in (True,False):
                changed = edit(painted,dict(op='properties',visible=shown))
                raw = base64.b64decode(self.export(changed,version)['data'])
                parsed = f.parse(raw)
                self.assertEqual(parsed['channels'],3 if shown else 4)
                record = parsed['layers'][0]
                self.assertEqual(([c for c,_ in record['channels']],record['tags'][b'lspf']),([0,1,2],f.U32(13)))
                self.assertEqual((record['rgba'],record['bounds']),(bytes([31,79,201,255]),[0,1,1,2]))
                reopened = self.read(raw)['document']
                self.assertEqual(reopened['background']['fixed_pixel_bounds'],[1,0,1,1])
                self.assertEqual(self.pixels(reopened),'ffffffff1f4fc9ffffffffff' if shown else '00'*12)
            regular = edit(painted,dict(op='background',action=dict(type='restore_source')))
            self.assertNotIn('background',regular)
            self.assertEqual(edit(regular,dict(fill,color=[1,2,3,4]))['items'][0]['content']['rgba_hex'],'01020304')

    def test_background_role_depends_on_bottom_pixel_semantics(self):
        rgb = pixel('misleading name',channel_ids=[0,1,2])
        for record in [dict(rgb,opacity=127),dict(rgb,blend=b'mul '),pixel('Background')]:
            d = self.read(f.make([record],w=2,h=1),color_policy='assume_srgb')['document']
            self.assertNotIn('background',d)
        for bad in [dict(rgb,xy=(-1,0)),pixel('Background',extra=f.tag(b'lspf',f.U32(13)))]:
            error = self.read(f.make([bad],w=2,h=1),1,color_policy='assume_srgb')
            self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        d = self.document(2,1)
        d['items'] = [dict(id='base',content=dict(type='raster',width=2,height=1,rgba_hex='fd784bff'*2))]
        d['background'] = dict(item_id='base',matte=[255]*3)
        self.assertEqual(self.export(d)['layered']['background_source_id'],'base')
        d['background']['matte']=[1,2,3]
        self.assertEqual(self.export(d,expected=1)['item_id'],'base')
        d['background']['matte']=[255]*3
        d['items'][0]['content']['rgba_hex']='fd784bfffd784b03'
        self.assertEqual(self.export(d,expected=1)['item_id'],'base')

    def test_background_retains_inactive_fill_until_released(self):
        base = pixel('paper',channel_ids=[0,1,2],extra=f.tag(b'iOpa',bytes([96,0,0,0])))
        for version in (1,2):
            doc = self.read(f.make([base],w=2,h=1,version=version),color_policy='assume_srgb')['document']
            self.assertEqual(doc['background']['inactive_fill_byte'],96)
            expected = '11dd67ffbe1f4fff'
            self.assertEqual(self.pixels(doc),expected)
            owner = doc['items'][0]['id']
            edit = dict(op='properties',id=owner,fill_opacity=0)
            changed = self.invoke(dict(command='document.edit',document=doc,expected_revision=0,operations=[edit]))['document']
            self.assertEqual(changed['background']['inactive_fill_byte'],0)
            self.assertEqual(self.pixels(changed),expected)
            raw = base64.b64decode(self.export(changed,version)['data'])
            self.assertEqual(f.parse(raw)['layers'][0]['tags'][b'iOpa'],bytes(4))
            self.assertEqual(self.read(raw)['document']['background']['inactive_fill_byte'],0)
            release = dict(op='background',id=owner,action=dict(type='restore_source'))
            ordinary = self.invoke(dict(command='document.edit',document=changed,expected_revision=1,operations=[release]))['document']
            self.assertNotIn('background',ordinary)
            self.assertEqual(self.pixels(ordinary),expected)

    def test_cropped_rgb_without_transparency_keeps_white_exterior_and_original_samples(self):
        paper = dict(name='paper',width=1,height=1,rgba=[254,65,32,255],channel_ids=[0,1,2],xy=(1,0),opacity=128)
        for records in ([paper],[marker(3),paper,marker(1)]):
            result = self.read(f.make(records,w=3,h=1),color_policy='assume_srgb')
            doc = result['document']
            item = next(i for i in doc['items'] if i['name']=='paper')
            self.assertEqual(result['opaque_rgb_extensions'],[dict(item_id=item['id'],source_bounds=[0,1,1,2],pixel_bounds=[0,0,1,3])])
            self.assertEqual(item['content']['rgba_hex'],'fffffffffe4120ffffffffff')
            self.assertEqual(self.pixels(doc),'ffffff80fe412080ffffff80')
            self.assertEqual(self.pixels(self.read(base64.b64decode(self.export(doc)['data']))['document']),self.pixels(doc))
        # The source rectangle and the canvas can extend past one another.
        offset=dict(paper,xy=(-1,1))
        result=self.read(f.make([offset],w=3,h=2),color_policy='assume_srgb')
        self.assertEqual(result['opaque_rgb_extensions'][0]['pixel_bounds'],[0,-1,2,3])
        self.assertEqual(result['document']['items'][0]['content']['rgba_hex'],'ffffffff'*4+'fe4120ff'+'ffffffff'*3)
        error=self.read(f.make([paper],w=257,h=256,compression=2),1,color_policy='assume_srgb')
        self.assertEqual(error['code'],'RESOURCE_LIMIT')

    def test_vector_pdf_preflight_identifies_the_layer_that_would_lose_its_knockout(self):
        doc = self.document(1,1)
        paint = dict(type='raster',width=1,height=1,rgba_hex='ae352aff')
        doc['items'] = [dict(id='paper',content=paint),
                        dict(id='hole',content=paint,fill_opacity=0,knockout_target='deep')]
        self.assertEqual(bytes.fromhex(self.pixels(doc)),bytes(4))
        with tempfile.TemporaryDirectory() as root:
            for color in ('display','native_inks'):
                options = dict(color=color)
                output = dict(output_root=root,file_name='page.pdf',format='pdf',pdf_options=options)
                error = self.invoke(dict(command='document.export',document=doc,format='pdf',pdf_options=options),1)
                self.assertEqual((error['code'],error['item_id']),('UNSUPPORTED','hole'))
                preflight = self.invoke(dict(command='document.preflight',document=doc,output=output))
                self.assertFalse(preflight['ready'])
                self.assertEqual(preflight['issues'][0]['error'],error)
            self.assertFalse((Path(root)/'page.pdf').exists())

    def test_regional_and_whole_render_share_the_deep_knockout_backdrop(self):
        width=513
        doc=self.document(width,1)
        doc['items']=[dict(id='paper',content=dict(type='raster',width=width,height=1,rgba_hex='a22452ff'*width)),
                      dict(id='folder',content=dict(type='group',isolated=False)),
                      dict(id='paint',parent='folder',content=dict(type='raster',width=width,height=1,rgba_hex='3498abff'*width)),
                      dict(id='cut',parent='folder',knockout_target='deep',fill_opacity=0,
                           transform=[1,0,0,1,126,0],content=dict(type='raster',width=260,height=1,rgba_hex='443322ff'*260))]
        expected=bytes.fromhex('3498abff')*126+bytes(260*4)+bytes.fromhex('3498abff')*(width-386)
        for evaluation in ('whole','tiled'):
            artifact=self.invoke(dict(command='document.export',format='png',document=doc,render_options=dict(evaluation=evaluation)))
            self.assertEqual(png_pixels(base64.b64decode(artifact['data']))[:3],(width,1,expected))

    def test_session_can_edit_publish_and_undo_one_pixel_knockout(self):
        layers = [pixel('base'),pixel('cut',extra=f.tag(b'knko',bytes([2,0,0,0]))+f.tag(b'iOpa',bytes(4)))]
        raw = f.make(layers,w=2,h=1)
        with tempfile.TemporaryDirectory() as root:
            source = Path(root)/'source.psd'
            source.write_bytes(raw)
            client = Client()
            try:
                client.initialize()
                doc = client.success('layered.import',source_path=str(source),id='knockout',color_policy='assume_srgb')['document']
                cut = doc['items'][1]['id']
                session = dict(session_root=root,session_id='knockout')
                client.success('session.create',**session,document=doc,request_id='create')
                edit = dict(expected_revision=0,request_id='remove',action=dict(type='edit',operations=[dict(op='properties',id=cut,knockout_target='none')]))
                changed = client.success('session.apply',**session,**edit)['document']
                self.assertNotEqual(self.pixels(changed),self.pixels(doc))
                self.assertTrue(client.success('session.apply',**session,**edit)['replayed'])
                client.success('session.publish',**session,expected_revision=1,output=dict(output_root=root,file_name='edited.psb',format='layered_large'))
                saved = client.success('layered.import',source_path=str(Path(root)/'edited.psb'),id='saved')['document']
                self.assertNotIn('knockout_target',saved['items'][1])
                self.assertEqual(self.pixels(saved),self.pixels(changed))
                undo = client.success('session.apply',**session,expected_revision=1,request_id='undo',action=dict(type='undo'))['document']
                self.assertEqual(undo['items'][1]['knockout_target'],'deep')
                self.assertEqual(self.pixels(undo),self.pixels(doc))
                self.assertEqual(source.read_bytes(),raw)
            finally:
                client.close()
    def test_unbalanced_markers_unknown_modes_nonpixel_samples_and_subtypes_fail(self):
        for records in [[marker(3)],[marker(1)],[marker(1),marker(3)],[marker(3),marker(3),marker(1)]]:
            self.assertEqual(self.read(f.make(records),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
        for extra in [f.U32(4),f.U32(1)+b'8BIMvLit',f.U32(1)+b'8BIMnorm'+f.U32(1)]:
            folder=marker(1);folder['extra']=f.tag(b'lsct',extra);self.assertEqual(self.read(f.make([marker(3),folder]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for extra in [b'',b'\0'*5,f.U32(1)+b'BAD!norm']:
            folder=marker(1);folder['extra']=f.tag(b'lsct',extra);self.assertEqual(self.read(f.make([marker(3),folder]),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
        for folder in [dict(marker(1),width=1,height=1,rgba=[1,2,3,4]),dict(marker(1),mask=bytes(17)+b'\4\0\0')]:
            self.assertEqual(self.read(f.make([marker(3),folder]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        boundary=marker(3)
        boundary['extra']+=f.tag(b'iOpa',b'\x80\0\0\0')
        self.assertEqual(self.read(f.make([boundary,marker(1)]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        bad=marker(1,channel_data=[b'\0\0x']*4);self.assertEqual(self.read(f.make([marker(3),bad]),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')
    def test_folder_record_budget_is_separate_from_editable_items_and_depth(self):
        cap = capabilities()['layered_interchange']
        maximum = cap['maximum_layers']
        records=[r for i in range(maximum) for r in [marker(3,id=0),marker(1,str(i),id=i+1)]]
        r=self.read(f.make(records),color_policy='assume_srgb');self.assertEqual((r['layers'],r['serialized_records']),(maximum,cap['groups']['serialized_records']))
        self.assertEqual(self.read(f.make(records+[pixel(id=5000)]),1,color_policy='assume_srgb')['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.read(f.make([pixel(id=i+1) for i in range(maximum+1)]),1,color_policy='assume_srgb')['code'],'RESOURCE_LIMIT')
        maximum_depth = cap['groups']['ancestor_levels']
        for depth,wanted in [(maximum_depth,0),(maximum_depth+1,1)]:
            records=[marker(3) for _ in range(depth)]+[pixel()]+[marker(1,str(i)) for i in range(depth)]
            r=self.read(f.make(records),wanted,color_policy='assume_srgb')
            if wanted:self.assertEqual(r['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.read(f.make([marker(3,id=9),pixel(id=1),marker(1,id=1)]),1,color_policy='assume_srgb')['code'],'INVALID_LAYERED_FILE')

    def test_folder_opacity_visibility_and_transform_losses_are_explicit(self):
        d=self.scene()
        for visible in [True,False]:
            for opacity in [0,64/255,1]:
                d['items'][1].update(visible=visible,opacity=opacity);encoded=base64.b64decode(self.export(d)['data']);self.assertEqual(self.pixels(self.read(encoded)['document']),self.pixels(d))
        for change in [dict(fill_opacity=.5,content=dict(type='group',isolated=True)),dict(blend='vivid_light',content=dict(type='group',isolated=True)),dict(transform=[1,0,0,1,.5,0]),dict(transform=[2,0,0,1,0,0]),dict(content=dict(type='group',knockout=True)),dict(content=dict(type='group',role='layer'))]:
            bad=copy.deepcopy(d);bad['items'][1].update(change);self.assertEqual(self.export(bad,expected=1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
    def test_nonpixel_flags_and_ordinary_channel_validation_are_not_weakened(self):
        for minimum in [70,80]:
            self.assertIn('lyvr:minimum_reader_'+str(minimum),self.read(f.make([pixel(extra=f.tag(b'lyvr',f.U32(minimum)))]),color_policy='assume_srgb')['omitted_nonappearance_records'])
        for minimum in [0,69,81,130,2**32-1]:
            self.assertEqual(self.read(f.make([pixel(extra=f.tag(b'lyvr',f.U32(minimum)))]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        compatibility = f.tag(b'lyvr',f.U32(130))
        folder = marker(1)
        folder['extra'] = compatibility + folder['extra']
        self.assertIn('lyvr:minimum_reader_130',self.read(f.make([marker(3),folder]),color_policy='assume_srgb')['omitted_nonappearance_records'])
        boundary = marker(3)
        boundary['extra'] += compatibility
        self.assertEqual(self.read(f.make([boundary,marker(1)]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for channel_ids in [[],[0],[0,1],[-1,0,1]]:
            self.assertEqual(self.read(f.make([pixel(channel_ids=channel_ids)]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for change in [dict(flags=24),dict(blend=b'pass'),dict(width=0,height=0,rgba=[])]:
            self.assertEqual(self.read(f.make([dict(pixel(),**change)]),1,color_policy='assume_srgb')['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
    def test_durable_group_import_edit_publication_and_history_preserve_source(self):
        d=self.scene()
        next(i for i in d['items'] if i['id']=='inner')['blend']='multiply'
        encoded=base64.b64decode(self.export(d,2)['data'])
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'original.psb';source.write_bytes(encoded);c=Client();c.initialize();s=dict(session_root=root,session_id='folders')
            try:
                capabilities=c.success('capabilities')['layered_interchange'];self.assertEqual(capabilities['groups']['serialized_records'],512);self.assertIn('empty_name_source_ids',capabilities['empty_layer_names'])
                imported=c.success('layered.import',source_path=str(source),id='folders',expected_sha256=hashlib.sha256(encoded).hexdigest())['document'];g=next(i['id'] for i in imported['items'] if i['name']=='inner')
                c.success('session.create',**s,request_id='create',document=imported);edit=dict(expected_revision=0,request_id='blend',action=dict(type='edit',operations=[dict(op='properties',id=g,blend='screen',fill_opacity=63/255)]));changed=c.success('session.apply',**s,**edit)
                c.success('session.publish',**s,expected_revision=1,output=dict(output_root=root,file_name='edited.psb',format='layered_large'));reopened=c.success('layered.import',source_path=str(Path(root)/'edited.psb'),id='reopened')['document'];self.assertEqual(tree(reopened),tree(changed['document']))
                folder = next(i for i in reopened['items'] if i['name']=='inner')
                self.assertEqual((folder['blend'],folder['fill_opacity'],folder['opacity']),('screen',63/255,128/255))
                undo=c.success('session.apply',**s,expected_revision=1,request_id='undo',action=dict(type='undo'));self.assertEqual(self.pixels(undo['document']),self.pixels(imported));self.assertTrue(c.success('session.apply',**s,**edit)['replayed']);self.assertTrue(c.success('session.verify',**s)['valid']);self.assertEqual(source.read_bytes(),encoded)
                self.assertEqual(next(i for i in undo['document']['items'] if i['id']==g)['blend'],'multiply')
            finally:c.close()

if __name__=='__main__':unittest.main()
