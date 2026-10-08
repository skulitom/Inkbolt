"""Original native ink surfaces, independent reconstruction and retained sources."""
import base64
import copy
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import hashlib
import itertools
import json
from pathlib import Path
import tempfile
import unittest
import pdf_reader
import test_editing_cli as editing
import test_native_images_cli as images
import test_native_warps_cli as warps
import test_native_raw_cli as raw_images
import test_objects_cli as objects
import test_raw_cli as raw
import test_resampling_cli as kernels
import test_hdr_cli as hdr
import test_images_cli as image_io
from test_native_print_cli import page_image
from test_vector_plates_cli import named, color, spot, rect
from test_profiles_cli import embedded, linear_profile
from test_samples_cli import layer
from test_mcp import Client
from cmyk_fixtures import cmyk_profile
from test_effects_coverage_cli import effect


def retained(source, **kw):
    snapshot = json.dumps(source, ensure_ascii=False, indent=2) + '\n'
    obj = dict(snapshot=snapshot, sha256=hashlib.sha256(snapshot.encode()).hexdigest(),
               width=source['width'], height=source['height'], sampling='nearest', surface_scale=1)
    obj.update(kw)
    return obj


def placed(source, id='placed', settings=None, **kw):
    return dict(id=id, content=dict(type='object', object=retained(source, **(settings or {}))), **kw)


def axis(method, point, width, extent):
    if method == 'nearest':
        return [(min(extent-1, max(0, point.numerator//point.denominator)), F(1))]
    if method == 'bilinear':
        q = point-F(1, 2); i = q.numerator//q.denominator; f = q-i
        return [(min(extent-1, max(0, i)), 1-f), (min(extent-1, max(0, i+1)), f)]
    return kernels.weights(method, point, width, extent)


def sample(rows, size, point, method, footprint=(1, 1)):
    """Tensor weights independently project a complete associated ink tuple."""
    with localcontext() as ctx:
        ctx.prec = 60
        conv = (lambda v: D(v.numerator)/D(v.denominator) if isinstance(v, F) else D(v)) if method == 'lanczos3' else F
        xs = axis(method, F(point[0]), F(footprint[0]), size[0])
        ys = axis(method, F(point[1]), F(footprint[1]), size[1])
        result = [conv(0) for _ in rows[0]]
        for y, wy in ys:
            for x, wx in xs:
                p = rows[y*size[0]+x]; weight = conv(wx)*conv(wy)
                for c in range(len(p)): result[c] += conv(p[c])*weight
        alpha = max(0, min(1, result[-1]))
        return [max(0, min(alpha, v)) for v in result[:-1]]+[alpha]


class NativeObjectTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke
    planes = images.NativeImageTests.planes
    values = warps.NativeWarpTests.values
    assertRows = warps.NativeWarpTests.assertRows
    edit = objects.ObjectTests.edit

    def document(self, w=8, h=8, kind='raster'):
        return self.invoke(dict(command='document.create', id='native-objects', kind=kind, width=w, height=h))

    def chart(self, w=8, h=8, spots=True):
        d = self.document(w, h, 'vector'); rows = []
        d['swatches'] = dict(s=spot('Original shared label')) if spots else {}
        for i in range(w*h):
            ink = [F((i*3+c*5)%9, 8) for c in range(4)]
            a = [F(0), F(1, 4), F(3, 4), F(1)][i%4]
            b = [F(0), F(1, 2), F(1, 4)][i%3] if spots else F(0)
            d['swatches'][f'c{i}'] = color(list(map(float, ink)))
            d['items'].append(rect(f'p{i}', named(f'c{i}', opacity=float(a)), (i%w, i//w, 1, 1)))
            if spots:
                d['items'].append(rect(f's{i}', named('s', tint=.625, opacity=float(b), overprint='preserve'), (i%w, i//w, 1, 1)))
            rows.append([v*a for v in ink]+([F(5, 8)*b] if spots else [])+[a+(1-a)*b])
        return d, rows

    def scene(self, source, **kw):
        d = self.document(source['width'], source['height']); d['items'] = [placed(source, **kw)]
        return d

    def test_isolated_native_operands_transparency_and_parent_inks_match_rationals(self):
        source, rows = self.chart(); source['metadata'] = dict(description='Original source', private={'marker':'kept privately'})
        d = self.scene(source); d['swatches'] = dict(p=color([.5, .25, .125, .0625]), s=spot('Original shared label'))
        d['items'][:0] = [images.fill('base', named('p'), box=(0,0,8,8)), images.fill('ink', named('s', tint=.75, overprint='preserve'), box=(0,0,8,8))]
        original = copy.deepcopy(d); r = self.planes(d)
        self.assertEqual([p['id'] for p in r['plates']], ['cyan','magenta','yellow','black','/placed/s','s'])
        expected = [[p[c]+F([8,4,2,1][c],16)*(1-p[-1]) for c in range(4)]+[p[4],F(3,4)*(1-p[-1])] for p in rows]
        self.assertRows(self.values(d), expected, 2e-15)
        receipt = r['image_sources'][0]; obj = d['items'][-1]['content']['object']
        self.assertEqual(receipt['source_sha256'], obj['sha256']); self.assertEqual(receipt['source_bytes'],len(obj['snapshot'].encode()))
        self.assertEqual(receipt['spot_mapping'],[dict(source_id='s',id='/placed/s',name='Original shared label')])
        self.assertFalse(receipt['link_read']); self.assertEqual(d,original)
        self.assertEqual(self.invoke(dict(command='object.open',document=d,id='placed'))['snapshot'],obj['snapshot'])

    def test_empty_and_explicit_white_sources_preserve_different_alpha(self):
        source = self.document(2,1,'vector'); source['swatches'] = dict(white=color([0,0,0,0])); source['items'] = [rect('white',named('white'),(0,0,1,1))]
        d = self.scene(source); d['swatches'] = dict(p=color([.25,.5,.75,1])); d['items'].insert(0,images.fill('base',named('p'),box=(0,0,2,1)))
        self.assertRows(self.values(d),[[0,0,0,0],[.25,.5,.75,1]],0)
        source['items'] = []; d['items'][-1] = placed(source); self.assertRows(self.values(d),[[.25,.5,.75,1]]*2,0)

    def test_all_reconstruction_methods_and_surface_scales_keep_native_ink_precision(self):
        source, original_rows = self.chart(4,3)
        for method, scale, size in itertools.product(['nearest','bilinear','area','bicubic','lanczos3'],[1,2,4],[(3,2),(7,5)]):
            d = self.document(*size); d['items'] = [placed(source,settings=dict(width=size[0],height=size[1],sampling=method,surface_scale=scale))]
            rows = [original_rows[(y//scale)*4+x//scale] for y in range(3*scale) for x in range(4*scale)]
            expected = [sample(rows,(4*scale,3*scale),(F(2*x+1,2)*4*scale/size[0],F(2*y+1,2)*3*scale/size[1]),method,(F(4*scale,size[0]),F(3*scale,size[1])))[:-1] for y in range(size[1]) for x in range(size[0])]
            with self.subTest(method=method,scale=scale,size=size): self.assertRows(self.values(d),expected,3e-14)
            self.assertEqual(self.planes(d)['image_sources'][0]['native_size'],[4*scale,3*scale])

    def test_all_retained_warps_use_associated_ink_inverse_sampling(self):
        source, rows = self.chart()
        for warp, method in itertools.product(warps.warps(),['nearest','bilinear']):
            d = self.scene(source,settings=dict(sampling=method),pixel_warp=warp)
            _, inverse = warps.maps(warp); expected = []
            for y in range(8):
                for x in range(8):
                    p = inverse([F(2*x+1,2),F(2*y+1,2)])
                    expected.append([F(0)]*5 if p is None else sample(rows,(8,8),p,method)[:-1])
            with self.subTest(warp=warp['type'],method=method): self.assertRows(self.values(d),expected,3e-14)
            self.assertEqual(self.planes(d)['image_sources'][0]['pixel_warp']['controls'],warp)

    def test_nested_spot_identity_is_unambiguous_stable_and_never_merged_by_label(self):
        source = self.document(2,1,'vector'); source['swatches'] = dict(s=spot('Same label')); source['items'] = [rect('p',named('s',tint=.5),(0,0,1,1))]
        inner = self.scene(source); inner['swatches'] = dict(s=spot('Same label')); inner['items'].insert(0,images.fill('ink',named('s',tint=.25),box=(0,0,2,1)))
        d = self.document(4,1); d['swatches'] = dict(s=spot('Same label')); d['items'] = [images.fill('root',named('s',tint=.75),box=(0,0,4,1)),placed(inner,id='left'),placed(inner,id='right',transform=[1,0,0,1,2,0])]
        ids = ['cyan','magenta','yellow','black','/left/placed/s','/left/s','/right/placed/s','/right/s','s']
        r = self.planes(d); self.assertEqual([p['id'] for p in r['plates']],ids)
        self.assertRows(self.values(d),[[0,0,0,0,.5,0,0,0,0],[0,0,0,0,0,.25,0,0,0],[0,0,0,0,0,0,.5,0,0],[0,0,0,0,0,0,0,.25,0]],0)
        inner['metadata'] = dict(description='Unrelated source change'); d['items'][1] = placed(inner,id='left')
        self.assertEqual([p['id'] for p in self.planes(d)['plates']],ids); self.assertEqual(self.planes(d)['interleaved_sha256'],r['interleaved_sha256'])

    def test_isolated_source_all_blends_and_filters_match_original_native_group(self):
        import test_native_nonlinear_cli as nonlinear
        import test_native_filters_cli as spatial
        source = self.document(); source['swatches'] = dict(p=color([.375,.625,.25,.125]),q=color([.75,.125,.5,.25]))
        source['items'] = [images.fill('p',named('p',opacity=.5),box=(0,0,8,8)), images.fill('q',named('q',opacity=.75),box=(1,1,6,6))]
        caps = self.invoke(dict(command='capabilities'))['native_prepress']
        operators = spatial.operators()+nonlinear.operators()
        for mode, operator in [(m,None) for m in caps['blending']['modes']]+[('normal',op) for op in operators]:
            src = copy.deepcopy(source); src['items'][1]['blend'] = mode
            if operator: src['items'][1]['filters'] = [dict(id='filter',operator=operator)]
            d = self.scene(src); d['swatches'] = dict(base=color([.125,.5,.25,.0625])); d['items'].insert(0,images.fill('base',named('base'),box=(0,0,8,8)))
            ref = copy.deepcopy(d); ref['swatches'].update(src['swatches']); ref['items'][-1] = dict(id='placed',content=dict(type='group',isolated=True))
            ref['items'].extend(dict(copy.deepcopy(i),parent='placed') for i in src['items'])
            with self.subTest(mode=mode,operator=operator): self.assertRows(self.values(d),self.values(ref),3e-14)

    def test_parent_controls_effects_masks_clipping_and_knockout_match_native_group(self):
        source = self.document(); source['swatches'] = dict(p=color([.5,.25,.125,.0625])); source['items'] = [images.fill('p',named('p',opacity=.75),box=(1,1,6,6))]
        for knockout in [False,True]:
            d = self.scene(source,opacity=.625,fill_opacity=.75,parent='g',mask=dict(width=8,height=8,gray_hex=bytes((i*31)%256 for i in range(64)).hex()),effects=[effect('overlay','overlay',[30,110,190,128])])
            d['swatches'] = dict(base=color([.125,.5,.25,.0625])); d['items'][:0] = [images.fill('base',named('base'),box=(0,0,8,8)),dict(id='g',content=dict(type='group',isolated=True,knockout=knockout))]
            ref = copy.deepcopy(d); ref['swatches'].update(source['swatches']); ref['items'][-1]['content'] = dict(type='group',isolated=True); ref['items'].extend(dict(copy.deepcopy(i),parent='placed') for i in source['items'])
            self.assertRows(self.values(d),self.values(ref),3e-14)
        d = self.scene(source,clip_to='base'); d['items'].insert(0,images.raster([[40,120,210,64+(i%4)*32] for i in range(64)],8)); d['items'][0]['id']='base'
        ref = copy.deepcopy(d); ref['swatches']=source['swatches']; ref['items'][-1]['content']=dict(type='group',isolated=True); ref['items'].extend(dict(copy.deepcopy(i),parent='placed') for i in source['items'])
        self.assertRows(self.values(d),self.values(ref),3e-14)

    def test_source_image_profiles_raw_and_native_depth_are_evaluated_before_placement(self):
        values = [v for i in range(8) for v in [12000+i,23000+i,45000-i,65535]]
        source = self.document(8,1); src = layer(values,w=8); src['content']['grid'].update(encoding='profiled_rgb',profile=embedded(linear_profile(gamma=2)))
        source['items']=[src]; d = self.scene(source)
        self.assertRows(self.values(d),self.values(source),3e-14)
        self.assertEqual(self.planes(d)['image_sources'][0]['image_sources'][0]['depth'],'u16')
        data,capture,_ = raw.fixture(8,8); source = self.document()
        source['items']=[raw_images.retained(data,capture,raw.settings(output='srgb16',range='clip'))]
        d=self.scene(source);self.assertRows(self.values(d),self.values(source),3e-14)
        self.assertEqual(self.planes(d)['image_sources'][0]['image_sources'][0]['source_sha256'],hashlib.sha256(data).hexdigest())

    def test_parent_affine_and_selected_page_bleed_preserve_the_source_frame(self):
        source, rows=self.chart(); d=self.scene(source,transform=[0,1,-1,0,8,0]);self.assertRows(self.values(d),[rows[(7-x)*8+y][:-1] for y in range(8) for x in range(8)],2e-15)
        d=self.scene(source);d.update(width=24,height=24);d['items'][0].update(parent='page',transform=[1,0,0,1,-1,-2]);d['items'].insert(0,dict(id='page',transform=[1,0,0,1,5,7],content=dict(type='frame',frame=dict(role='artboard',width=8,height=8,bleed=dict(left=1,right=2,top=2,bottom=1)))))
        for bleed in [False,True]:
            ref=self.scene(source);ref.update(width=11 if bleed else 8,height=11 if bleed else 8);ref['items'][0]['transform']=[1,0,0,1,0 if bleed else -1,0 if bleed else -2]
            self.assertEqual(self.planes(d,artboard_id='page',include_bleed=bleed)['interleaved_sha256'],self.planes(ref)['interleaved_sha256'])

    def test_supersampled_source_coverage_and_placement_average_associated_inks(self):
        source=self.document(2,1,'vector');source['swatches']=dict(p=color([.5,.25,.125,0]));source['items']=[rect('p',named('p'),(0,0,.5,1))]
        d=self.scene(source)
        for antialias in ['coverage','supersample2','supersample4']:
            r=self.planes(d,antialias=antialias,samples=[[0,0],[1,0]])
            source_r=self.planes(source,antialias=antialias,samples=[[0,0],[1,0]])
            self.assertRows([p['ink_fractions'] for p in r['samples']],[p['ink_fractions'] for p in source_r['samples']],2e-15)

    def test_missing_resources_corruption_and_explicit_unsupported_source_modes(self):
        source=self.document(1,1);source['items']=[hdr.layer([-2,3,8,.5],w=1)];source['color_space']='linear_srgb'
        d=self.scene(source,settings=dict(view=dict(tone_map='clip')));self.assertEqual(self.planes(d)['image_sources'][0]['evaluation']['boundary'],'explicit_retained_HDR_view')
        source=self.document(1,1);source['output_profile']=embedded(linear_profile());self.assertTrue(self.planes(self.scene(source))['image_sources'][0]['coverage_sources']['source_context']['has_RGB_output_profile'])
        source,_=self.chart(1,1);d=self.scene(source);d['items'][0]['content']['object']['snapshot']+=' ';self.assertEqual(self.planes(d,1)['code'],'OBJECT_HASH_MISMATCH')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);file=root/'source.png';file.write_bytes(image_io.png(1,1,bytes([40,120,200,128])));original=file.read_bytes()
            asset=self.invoke(dict(command='asset.import',source_path=str(file),store_root=str(root/'store')))['asset'];source=self.document(1,1);source['assets']=dict(p=asset);source['items']=[dict(id='p',content=dict(type='image',asset_id='p',width=1,height=1))]
            d=self.scene(source);self.planes(d,1)
            r=self.planes(d,root=root/'store',samples=[[0,0]]);self.assertRows([r['samples'][0]['ink_fractions']],[[v*128/255 for v in images.process([40/255,120/255,200/255])]],.00008);self.assertEqual(file.read_bytes(),original)

    def test_recursive_work_ink_count_controls_and_no_partial_publication(self):
        source=self.document(2,2);source['items']=[images.raster([[100,50,10,255]]*4,2)]
        nested=source
        for _ in range(4):nested=self.scene(nested)
        self.assertRows(self.values(nested),self.values(source),3e-14)
        bad=self.document(2,2);bad['items']=[placed(source,id=f'o{i}') for i in range(33)];self.assertEqual(self.planes(bad,1)['code'],'RESOURCE_LIMIT')
        spotted,_=self.chart(1,1);spotted['items'][1]['content']['fill']['opacity']=1;bad=self.document(1,1);bad['items']=[placed(spotted,id=f'o{i}') for i in range(29)];self.assertEqual(self.planes(bad,1)['code'],'RESOURCE_LIMIT')
        profiled=self.document(1,1);profiled['items']=[layer([10000,20000,30000,65535])];bad=self.document(1,1)
        for i in range(17):
            src=copy.deepcopy(profiled);src['items'][0]['content']['grid'].update(encoding='profiled_rgb',profile=embedded(linear_profile(gamma=1+i/32)));bad['items'].append(placed(src,id=f'o{i}'))
        self.assertEqual(self.planes(bad,1)['code'],'RESOURCE_LIMIT')
        large=self.document(128,128);large['items']=[images.fill('p',[100,50,10,255],box=(0,0,128,128))];bad=self.document(128,128);bad['items']=[placed(large,id=f'o{i}') for i in range(12)];self.assertEqual(self.planes(bad,1)['code'],'RESOURCE_LIMIT')
        with tempfile.TemporaryDirectory() as directory:
            marker=Path(directory)/'cancel';marker.write_text('cancel');output=dict(output_root=directory,file_name='failed.pdf',format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()),antialias='none')))
            for control,code in [(dict(timeout_ms=0),'TIMEOUT'),(dict(cancel_file=str(marker)),'CANCELLED')]:
                self.assertEqual(self.invoke(dict(command='document.publish',document=nested,output=output,control=control),1)['code'],code);self.assertFalse((Path(directory)/'failed.pdf').exists())
            self.assertEqual(self.invoke(dict(command='document.publish',document=bad,output=output),1)['code'],'RESOURCE_LIMIT');self.assertFalse((Path(directory)/'failed.pdf').exists())

    def test_linked_sources_never_refresh_implicitly_and_pdf_retains_exact_ink_bytes(self):
        source,_=self.chart(4,3)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'source.json';path.write_text(json.dumps(source,indent=3));original=path.read_bytes()
            obj=self.invoke(dict(command='object.import',source_path=str(path),link_key=path.name))['object'];d=self.scene(source);d['items'][0]['content']['object']=obj;r=self.planes(d)
            changed=copy.deepcopy(source);changed['items']=[];path.write_text(json.dumps(changed));changed_bytes=path.read_bytes()
            self.assertEqual(self.planes(d)['interleaved_sha256'],r['interleaved_sha256']);self.assertFalse(r['image_sources'][0]['link_read'])
            output=dict(output_root=directory,file_name='native.pdf',format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()),antialias='none',spot_fallback='multiplicative_declared')))
            receipt=self.invoke(dict(command='document.publish',document=d,output=output));pdf_bytes=(root/'native.pdf').read_bytes();pdf=pdf_reader.Pdf(dict(data=base64.b64encode(pdf_bytes).decode()));self.assertEqual(hashlib.sha256(page_image(pdf)[1]).hexdigest(),r['interleaved_sha256'])
            self.assertEqual(receipt['pages'][0]['image_sources'],r['image_sources']);self.assertIn(b'#2Fplaced#2Fs',pdf_bytes)
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output),1)['code'],'OUTPUT_EXISTS');self.assertEqual(path.read_bytes(),changed_bytes);self.assertEqual(obj['sha256'],hashlib.sha256(original).hexdigest())

    def test_agent_source_replace_undo_restart_and_retry_preserve_independent_copies(self):
        source,_=self.chart(4,3);d=self.scene(source);d['items'].append(placed(source,id='copy',visible=False));d=self.invoke(dict(command='document.validate',document=d));before=self.planes(d)
        changed_source=copy.deepcopy(source);changed_source['items'][-1]['content']['fill']['tint']=.125;replacement=retained(changed_source)
        caps=self.invoke(dict(command='capabilities'))['native_prepress'];self.assertNotIn('retained_objects',caps['unsupported']);self.assertIn('isolated_native',caps['object_sources']['boundary'])
        c=Client();c.initialize();self.addCleanup(c.close)
        with tempfile.TemporaryDirectory() as directory:
            s=dict(session_root=str(Path(directory)/'sessions'),session_id='native-objects');c.success('session.create',**s,request_id='create',document=d)
            req=dict(request_id='replace',expected_revision=0,action=dict(type='edit',operations=[dict(op='object_replace',id='placed',object=replacement)]));changed=c.success('session.apply',**s,**req)['document'];after=self.planes(changed)
            self.assertNotEqual(before['interleaved_sha256'],after['interleaved_sha256']);self.assertEqual(changed['items'][1],d['items'][1]);self.assertEqual([p['id'] for p in after['plates']],[p['id'] for p in before['plates']])
            output=dict(output_root=directory,file_name='placed.pdf',format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()),antialias='none',spot_fallback='multiplicative_declared')));c.success('session.publish',**s,expected_revision=1,output=output);pdf_bytes=(Path(directory)/'placed.pdf').read_bytes()
            self.doCleanups();c=Client();c.initialize();self.addCleanup(c.close);undone=c.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.planes(undone)['interleaved_sha256'],before['interleaved_sha256'])
            redone=c.success('session.apply',**s,request_id='redo',expected_revision=2,action=dict(type='redo'))['document'];self.assertEqual(self.planes(redone)['interleaved_sha256'],after['interleaved_sha256']);self.assertTrue(c.success('session.apply',**s,**req)['replayed']);self.assertTrue(c.success('session.verify',**s)['valid']);self.assertEqual((Path(directory)/'placed.pdf').read_bytes(),pdf_bytes)


if __name__ == '__main__': unittest.main()
