"""Original rational viewport, physical-page and source-retention checks."""
import base64
import copy
from fractions import Fraction as F
import hashlib
import itertools
import json
import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import pdf_reader
import test_editing_cli as editing
from test_editing_cli import png_pixels
from test_vector_plates_cli import rect, named, color
from test_native_objects_cli import placed
from test_native_print_cli import page_image
from test_profiles_cli import embedded
from cmyk_fixtures import cmyk_profile
from test_mcp import Client
from test_metadata_cli import carrier
from test_appearance_cli import original as appearance_fixture
from test_ink_recipes_cli import channel, recipe

FACTORS={'px':F(1),'pt':F(1,72),'pc':F(1,6),'mm':F(5,127),'cm':F(50,127),'in':F(1)}

def action(origin=(-2.25,1.5),size=(5.25,3.5),unit='px',process_space='rgb'):
    return dict(type='set',origin=list(origin),size=list(size),unit=unit,process_space=process_space)


class VectorCanvasTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,ppi=96):
        return self.invoke(dict(command='document.create',id='logical-canvas',kind='vector',width=8,height=8,resolution_ppi=ppi))
    def edit(self,d,a,expected=0):
        r=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='vector_canvas',action=a)]),expected)
        return r if expected else r['document']
    def canvas(self,**kw):return self.edit(self.document(),action(**kw))
    def planes(self,d,**kw):return self.invoke(dict(command='document.prepress',document=d,options=dict(profile=embedded(cmyk_profile()),**kw)))
    def export(self,d,format='png',**kw):return self.invoke(dict(command='document.export',document=d,format=format,**kw))
    def full(self,d,paint=None):
        d['items']=[rect('paint',[48,112,192,255] if paint is None else paint,(-100,-100,200,200))];d.update(self.invoke(dict(command='document.validate',document=d)));return d

    def test_exact_physical_unit_conversion_and_preference_do_not_move_artwork(self):
        for unit,ppi in itertools.product(FACTORS,[72,96,300]):
            d=self.document(ppi);d['items']=[rect('art',[40,80,120,255],(-3.5,2.25,4.5,1.25))];d=self.invoke(dict(command='document.validate',document=d));original=copy.deepcopy(d)
            d=self.edit(d,action(origin=(-.25,.125),size=(.5,.25),unit=unit));factor=FACTORS[unit]*(1 if unit=='px' else ppi)
            expected=[float(F(v)*factor) for v in [-.25,.125,.5,.25]];v=d['vector_canvas']
            self.assertEqual(v['origin_px']+v['size_px'],expected);self.assertEqual(d['items'],original['items']);self.assertEqual([d['width'],d['height']],[math.ceil(x) for x in expected[2:]])
            for display in FACTORS:
                d=self.edit(d,dict(type='unit',unit=display));self.assertEqual(d['vector_canvas']['origin_px']+d['vector_canvas']['size_px'],expected)
                inspected=self.invoke(dict(command='document.inspect',document=d));f=FACTORS[display]*(1 if display=='px' else ppi)
                self.assertEqual(inspected['vector_canvas']['size_in_unit'],[float(F(x)/f) for x in expected[2:]])

    def test_fractional_preview_cells_have_independent_coverage_and_exact_origin(self):
        d=self.full(self.canvas());original=copy.deepcopy(d)
        for scale,aa in itertools.product([1,2,3,4],['none','coverage','supersample2','supersample4']):
            a=self.export(d,scale=scale,render_options=dict(antialias=aa));w,h,p,_=png_pixels(base64.b64decode(a['data']));self.assertEqual((w,h),(math.ceil(5.25*scale),math.ceil(3.5*scale)))
            factor=1 if aa in ['none','coverage'] else int(aa[-1]);native=scale*factor
            for y in range(h):
                for x in range(w):
                    if aa=='none':coverage=int(F(2*x+1,2*scale)<F(21,4) and F(2*y+1,2*scale)<F(7,2))
                    else:coverage=max(0,min(F(1),F(21,4)*scale-x))*max(0,min(F(1),F(7,2)*scale-y))
                    alpha=int(coverage*255+F(1,2));expected=[48,112,192,alpha] if alpha else [0]*4
                    self.assertEqual(list(p[(y*w+x)*4:(y*w+x+1)*4]),expected,(scale,aa,x,y))
            self.assertEqual(a['render_settings']['origin'],[-2.25,1.5]);self.assertEqual(d,original)

    def test_origin_rebases_linked_and_unlinked_masks_without_changing_sources(self):
        d=self.full(self.canvas(origin=(-2,-1),size=(3.5,2.5)));d['items'][0]['mask']=dict(width=2,height=2,gray_hex='ff800040',linked=False,transform=[1,0,0,1,-2,-1])
        shifted=copy.deepcopy(d);shifted.pop('vector_canvas');shifted['items'][0]['transform']=[1,0,0,1,2,1];shifted['items'][0]['mask']['transform']=[1,0,0,1,0,0]
        a=self.invoke(dict(command='document.render',document=d));b=self.invoke(dict(command='document.render',document=shifted));self.assertEqual(a['data'],b['data'])
        d=self.invoke(dict(command='document.validate',document=d));original=copy.deepcopy(d);d=self.edit(d,dict(type='unit',unit='mm'));self.assertEqual(d['items'],original['items']);self.assertEqual(self.invoke(dict(command='document.render',document=d))['data'],a['data'])

    def test_svg_physical_size_viewbox_and_source_coordinates_are_explicit(self):
        for ppi,unit in itertools.product([72,96,300],FACTORS):
            d=self.full(self.edit(self.document(ppi),action()));d=self.edit(d,dict(type='unit',unit=unit));svg=self.export(d,'svg');root=ET.fromstring(svg['data']);self.assertEqual(list(map(float,root.get('viewBox').split())),[-2.25,1.5,5.25,3.5])
            width=root.get('width');suffix=unit;value=float(width[:-len(suffix)])
            expected=5.25*96/ppi if unit=='px' else float(F(5.25)/(FACTORS[unit]*ppi));self.assertAlmostEqual(value,expected,places=12)
            node=root.find('.//{http://www.w3.org/2000/svg}rect');self.assertEqual(float(node.get('x')),-100);self.assertEqual(d['items'][0]['content']['geometry']['x'],-100)

    def test_standard_pdf_uses_fractional_physical_page_and_shifted_geometry(self):
        for ppi in [72,96,300]:
            d=self.full(self.edit(self.document(ppi),action()));artifact=self.export(d,'pdf');pdf=pdf_reader.Pdf(artifact);page=pdf.pages[0];physical=[float(v)*page['UserUnit'] for v in page['MediaBox']]
            for a,b in zip(physical,[0,0,5.25*72/ppi,3.5*72/ppi]):self.assertAlmostEqual(a,b,places=10)
            self.assertEqual(artifact['pages'][0]['logical_size'],[5.25,3.5]);self.assertEqual(d['vector_canvas']['origin_px'],[-2.25,1.5])

    def test_original_viewport_provenance_and_actual_delivery_dimensions(self):
        d=self.full(self.canvas());policy=dict(provenance=True);canonical=json.dumps(d,sort_keys=True,separators=(',',':')).encode();digest=hashlib.sha256(canonical).hexdigest()
        for scale in [1,3]:
            artifact=self.export(d,scale=scale,metadata_policy=policy);packet=json.loads(carrier(base64.b64decode(artifact['data']),'png'))
            self.assertEqual([packet['delivery']['width'],packet['delivery']['height']],[math.ceil(5.25*scale),math.ceil(3.5*scale)]);self.assertEqual(packet['delivery']['vector_canvas']['origin_px'],[-2.25,1.5]);self.assertEqual(packet['provenance']['source_sha256'],digest)
        for options in [{},dict(print=dict(profile=embedded(cmyk_profile()),matte=[255,255,255],raster_scale=3))]:
            pdf=pdf_reader.Pdf(self.export(d,'pdf',pdf_options=options,metadata_policy=policy));root=ET.fromstring(pdf.streams[pdf.catalog['Metadata']]);packet=json.loads(root.find('.//{urn:inkbolt:pdf:metadata:1}packet').text)['pages'][0]['packet']
            self.assertEqual(packet['delivery']['vector_canvas']['origin_px'],[-2.25,1.5]);self.assertEqual(packet['delivery']['vector_canvas']['size_px'],[5.25,3.5]);self.assertEqual(packet['provenance']['source_sha256'],digest)
            self.assertEqual(pdf.pages[0]['MediaBox'],[0,0,3.9375,2.625])

    def test_canvas_alignment_and_explicit_bake_viewport_use_world_coordinates(self):
        d=self.canvas();d['items']=[rect('small',[40,80,120,255],(0,0,1,1))];d=self.invoke(dict(command='document.validate',document=d))
        operations=[dict(op='align',ids=['small'],axis='x',anchor='min',reference=dict(type='canvas')),dict(op='align',ids=['small'],axis='y',anchor='max',reference=dict(type='canvas'))]
        aligned=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=operations))['document'];bounds=self.invoke(dict(command='document.inspect',document=aligned))['items'][0]['geometry_bounds'];self.assertEqual(bounds,[-2.25,4,-1.25,5])
        d=self.invoke(dict(command='document.validate',document=appearance_fixture()));d=self.edit(d,action(origin=(-1,1),size=(23.5,18.25)));original=copy.deepcopy(d)
        with tempfile.TemporaryDirectory() as root:
            baked=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],asset_root=root,operations=[dict(op='appearance_bake',id='icon',asset_id='pixels',image_id='image',region=dict(origin=[0,0],width=24,height=20,scale=1))]))['document']
            self.assertEqual(self.export(d)['data'],self.export(baked,asset_root=root)['data']);self.assertEqual(baked['vector_canvas'],d['vector_canvas']);self.assertEqual(d,original)

    def test_clear_canvas_is_explicit_and_cmyk_preview_print_is_rejected(self):
        d=self.full(self.canvas(process_space='cmyk'));before=copy.deepcopy(d)
        error=self.invoke(dict(command='document.export',document=d,format='pdf',pdf_options=dict(print=dict(profile=embedded(cmyk_profile()),matte=[255,255,255]))),1);self.assertEqual(error['code'],'COLOR_POLICY_REQUIRED')
        cleared=self.edit(d,dict(type='clear'));self.assertNotIn('vector_canvas',cleared);self.assertEqual(cleared['items'],d['items']);self.assertEqual(self.invoke(dict(command='document.inspect',document=cleared))['canvas_bounds'],[0,0,6,4]);self.assertEqual(d,before)

    def test_scalar_ink_recipe_preserves_density_pixel_pitch_and_fractional_page(self):
        d=self.canvas(process_space='cmyk');values=list(range(0,240,10));d['channels']=dict(gray=channel(values,6,4));d['ink_recipe']=recipe(1);d=self.invoke(dict(command='document.validate',document=d));before=copy.deepcopy(d)
        for scale in [1,2,3,4]:
            a=self.export(d,'pdf',pdf_options=dict(ink_recipe=dict(raster_scale=scale)));pdf=pdf_reader.Pdf(a);w,h=math.ceil(5.25*scale),math.ceil(3.5*scale);image,data=page_image(pdf)
            self.assertEqual([image['Width'],image['Height']],[w,h]);self.assertEqual(data,bytes(255-values[(y//scale)*6+x//scale] for y in range(h) for x in range(w)));self.assertEqual(pdf.pages[0]['MediaBox'],[0,0,3.9375,2.625]);self.assertEqual(a['pages'][0]['logical_size'],[5.25,3.5]);self.assertEqual(d,before)

    def test_cmyk_canvas_preserves_native_inks_and_requires_explicit_page_policy(self):
        d=self.canvas(process_space='cmyk');d['swatches']=dict(p=color([.25,.5,.125,.375]));self.full(d,named('p'));original=copy.deepcopy(d)
        for fmt in ['svg','pdf']:
            err=self.invoke(dict(command='document.export',document=d,format=fmt),1);self.assertIn(err['code'],['COLOR_POLICY_REQUIRED','SWATCH_EXPORT_UNSUPPORTED'])
        self.assertEqual(self.invoke(dict(command='document.render',document=d),1)['code'],'SWATCH_PREVIEW_REQUIRED')
        for scale in [1,2,3]:
            plates=self.planes(d,raster_scale=scale,samples=[[0,0],[math.ceil(5.25*scale)-1,math.ceil(3.5*scale)-1]])
            tail=(F(21,4)*scale-(math.ceil(5.25*scale)-1))*(F(7,2)*scale-(math.ceil(3.5*scale)-1))
            for row,coverage in zip(plates['samples'],[1,tail]):
                for a,b in zip(row['ink_fractions'],[float(v*coverage) for v in map(F,[.25,.5,.125,.375])]):self.assertAlmostEqual(a,b,places=12)
            artifact=self.export(d,'pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()),raster_scale=scale)));pdf=pdf_reader.Pdf(artifact);self.assertEqual(hashlib.sha256(page_image(pdf)[1]).hexdigest(),plates['interleaved_sha256']);self.assertEqual(artifact['pages'][0]['logical_size'],[5.25,3.5]);self.assertEqual(d,original)

    def test_fractional_artboard_scope_bleed_and_inherited_colour_remain_exact(self):
        d=self.canvas(process_space='cmyk');d['swatches']=dict(p=color([.25,.5,.125,0]));d['items']=[dict(id='board',transform=[1,0,0,1,-2.5,1.25],content=dict(type='frame',frame=dict(role='artboard',width=5,height=4,logical_size=[4.5,3.25],bleed=dict(left=1,right=2,top=2,bottom=1)))),rect('art',named('p'),(-2,-3,10,10),parent='board')]
        options=dict(artboards=dict(type='ids',ids=['board']),include_bleed=True,prepress=dict(profile=embedded(cmyk_profile())));a=self.export(d,'pdf',pdf_options=options);self.assertEqual(a['pages'][0]['logical_size'],[7.5,6.25]);self.assertEqual(a['pages'][0]['pixel_dimensions'],[8,7]);self.assertEqual(a['pages'][0]['render_settings']['vector_canvas']['process_space'],'cmyk')
        preview=self.planes(d,artboard_id='board',include_bleed=True);self.assertEqual(hashlib.sha256(page_image(pdf_reader.Pdf(a))[1]).hexdigest(),preview['interleaved_sha256'])

    def test_fractional_svg_import_has_bounded_pixels_and_source_preservation(self):
        raw=b'<svg xmlns="http://www.w3.org/2000/svg" width="5.25" height="3.5" viewBox="-2.25 1.5 5.25 3.5"><rect x="-10" y="-10" width="30" height="30" fill="#3070c0"/></svg>'
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'original.svg';path.write_bytes(raw);r=self.invoke(dict(command='svg.import',source=dict(kind='file',source_path=str(path)),id='fractional'));d=r['document'];self.assertEqual(d['vector_canvas']['size_px'],[5.25,3.5]);self.assertEqual(path.read_bytes(),raw)
            self.assertEqual(self.export(d)['data'],self.export(self.full(self.canvas()))['data'])

    def test_retained_source_and_snapshots_preserve_the_logical_canvas(self):
        source=self.full(self.canvas());parent=self.invoke(dict(command='document.create',id='parent',kind='raster',width=6,height=4));parent['items']=[placed(source)]
        source_pixels=self.invoke(dict(command='document.render',document=source));parent_pixels=self.invoke(dict(command='document.render',document=parent));self.assertEqual(parent_pixels['data'],source_pixels['data'])
        snapshot=self.export(source,'snapshot');opened=self.invoke(dict(command='document.validate',document=json.loads(snapshot['data'])));self.assertEqual(opened,source)

    def test_unit_edits_diff_and_session_history_are_durable(self):
        d=self.full(self.canvas());d['revision']=0;a=dict(type='unit',unit='mm');changed=self.edit(d,a);diff=self.invoke(dict(command='document.diff',before=d,after=changed));self.assertIn('vector_canvas',[x['field'] for x in diff['metadata']]);self.assertEqual(changed['items'],d['items'])
        with tempfile.TemporaryDirectory() as root:
            c=Client();c.initialize();self.addCleanup(c.close);s=dict(session_root=root,session_id='canvas');c.success('session.create',**s,request_id='create',document=d)
            op=dict(request_id='unit',expected_revision=d['revision'],action=dict(type='edit',operations=[dict(op='vector_canvas',action=a)]));done=c.success('session.apply',**s,**op)['document'];self.assertEqual(done,changed)
            undo=c.success('session.apply',**s,request_id='undo',expected_revision=done['revision'],action=dict(type='undo'))['document'];self.assertEqual(undo['vector_canvas'],d['vector_canvas']);c.success('session.apply',**s,request_id='redo',expected_revision=undo['revision'],action=dict(type='redo'));self.assertTrue(c.success('session.apply',**s,**op)['replayed']);self.assertTrue(c.success('session.verify',**s)['valid'])

    def test_invalid_extents_cache_and_raster_context_fail_without_changes(self):
        d=self.document();original=copy.deepcopy(d)
        for a in [action(size=(0,2)),action(size=(1e-12,2)),action(size=(32769,1)),action(origin=(32768,0),size=(1,1))]:self.assertEqual(self.edit(d,a,1)['code'],'INVALID_CANVAS')
        bad=self.canvas();bad['width']+=1;self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'INVALID_CANVAS')
        raster=copy.deepcopy(d);raster['kind']='raster';self.assertEqual(self.edit(raster,action(),1)['code'],'INVALID_CANVAS');self.assertEqual(d,original)


if __name__=='__main__':unittest.main()
