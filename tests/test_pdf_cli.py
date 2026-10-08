"""Original page, path, typography, resource and create-only PDF delivery fixtures."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
import test_boards_cli as boards
import test_bidi_text_cli as bidi
import test_font_controls_cli as font_controls
import test_metadata_cli as metadata
from pdf_reader import Pdf, Ref


class PdfTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    edit=boards.BoardCliTests.edit
    board=boards.BoardCliTests.board
    rectangle=boards.BoardCliTests.rectangle
    fixture=boards.BoardCliTests.fixture

    def export(self,d,status=0,**kw):
        return self.invoke(dict(command='document.export',document=d,format='pdf',**kw),status)

    def test_classic_xref_pages_and_deterministic_empty_canvas(self):
        for kind in ['vector','raster']:
            d=self.invoke(dict(command='document.create',id='empty',kind=kind,width=96,height=144))
            a=self.export(d);p=Pdf(a)
            self.assertEqual(p.pages[0]['MediaBox'],[0,0,72,108]);self.assertEqual(p.paths(),[])
            self.assertEqual(a,self.export(d));self.assertEqual(a['pdf']['image_pixels'],0)
            self.assertEqual(p.get(p.trailer['Info']),{'Producer':'Inkbolt'})

    def test_two_artboards_have_independently_parsed_sizes_content_bounds_and_order(self):
        d=self.fixture();before=copy.deepcopy(d)
        a=self.export(d,pdf_options=dict(artboards=dict(type='all')));p=Pdf(a)
        self.assertEqual([v['artboard_id'] for v in a['pages']],['wide','tall'])
        self.assertEqual([v['MediaBox'] for v in p.pages],[[0,0,3.75,3],[0,0,2.25,4.5]])
        self.assertEqual([v['color'] for v in p.paths(0)],[[20/255,30/255,40/255],[210/255,20/255,30/255],[0,200/255,0]])
        # Independent coordinates include outside shapes; nested frame clips trim them.
        red=p.paths(0)[1]['path'];self.assertEqual(red[0],('m',[[-.75,.75]]))
        blue=p.paths(1)[0]['path'];self.assertEqual(blue[0],('m',[[.75,-.75]]))
        self.assertEqual(d,before)
        for selection,ids in [(dict(type='ids',ids=['tall','wide']),['tall','wide']),
            (dict(type='range',start=1,end=2),['tall'])]:
            result=self.export(d,pdf_options=dict(artboards=selection))
            self.assertEqual([v['artboard_id'] for v in result['pages']],ids)
            self.assertEqual(len(Pdf(result).pages),len(ids))

    def test_asymmetric_bleed_boxes_units_and_local_artboard_placement(self):
        d=self.fixture();options=dict(artboards=dict(type='ids',ids=['wide']),include_bleed=True)
        a=self.export(d,pdf_options=options);p=Pdf(a)
        self.assertEqual(p.pages[0]['MediaBox'],[0,0,6,5.25])
        self.assertEqual(p.pages[0]['TrimBox'],[.75,1.5,4.5,4.5])
        self.assertEqual(p.pages[0]['BleedBox'],p.pages[0]['MediaBox'])
        self.assertEqual(p.paths()[1]['path'][0],('m',[[0,1.5]]))
        moved=self.edit(d,[dict(op='transform',id='wide',matrix=[0,2,-2,0,20,8])])
        self.assertEqual(self.export(moved,pdf_options=options),a)

    def test_resolution_changes_physical_size_without_changing_source_or_ink(self):
        d=self.fixture();d['resolution_ppi']=144
        a=self.export(d);self.assertEqual(Pdf(a).pages[0]['MediaBox'],[0,0,16,12])
        self.assertEqual(a['pages'][0]['physical_points'],[16,12])
        large=copy.deepcopy(d);large.update(width=32768,height=16384,resolution_ppi=1)
        p=Pdf(self.export(large));u=p.pages[0]['UserUnit']
        self.assertEqual(u,164);self.assertLessEqual(max(p.pages[0]['MediaBox']),14400)
        self.assertAlmostEqual(p.pages[0]['MediaBox'][2]*u,32768*72)

    def test_compound_winding_cubics_and_transforms_remain_paths(self):
        d=self.fixture();d['items']=[]
        commands=[dict(verb='move',to=[1,2]),dict(verb='cubic',control1=[2,4],control2=[4,1],to=[6,2]),dict(verb='line',to=[6,6]),dict(verb='close')]
        item=dict(id='curve',transform=[2,.5,-.25,1,4,3],content=dict(type='vector',geometry=dict(shape='path',commands=commands),fill=[10,20,30,128],fill_rule='even_odd'))
        d=self.edit(d,[dict(op='add',item=item)]);p=Pdf(self.export(d));path=p.paths()[0]
        self.assertEqual(path['rule'],'f*');self.assertAlmostEqual(path['alpha'],128/255)
        self.assertEqual(path['path'][0],('m',[[4.125,4.125]]))
        self.assertEqual(path['path'][1],('c',[[5.25,6],[8.8125,4.5],[11.625,6]]))
        self.assertFalse(any(o.get('Subtype')=='Image' for o in p.objects.values()))

    def test_isolated_group_opacity_is_applied_once_to_fill_and_stroke(self):
        d=self.fixture();d['items']=[]
        d=self.edit(d,[dict(op='add',item=dict(id='group',opacity=.5,content=dict(type='group'))),dict(op='add',item=dict(id='shape',parent='group',opacity=.8,fill_opacity=.5,content=dict(type='vector',geometry=dict(shape='rect',x=2,y=2,width=8,height=8),fill=[255,0,0,255],stroke=dict(color=[0,0,255,255],width=2))))])
        a=self.export(d);p=Pdf(a);paths=p.paths()
        self.assertEqual(len(paths),2)
        for path in paths:self.assertAlmostEqual(path['alpha'],.2)
        groups=[o['Group'] for o in p.objects.values() if o.get('Subtype')=='Form']
        self.assertTrue(all(g['I'] for g in groups));self.assertEqual(a['pdf']['image_pixels'],0)

    def test_geometric_and_frame_clips_use_correct_fill_rule_and_transform(self):
        d=self.fixture();next(i for i in d['items'] if i['id']=='red')['clip']=dict(geometry=dict(shape='rect',x=0,y=0,width=2,height=2),transform=[1,0,0,1,1,2],fill_rule='even_odd')
        p=Pdf(self.export(d,pdf_options=dict(artboards=dict(type='ids',ids=['wide']))))
        clips=[v for v in p.streams.values() if b'W* n' in v]
        self.assertEqual(len(clips),1);self.assertIn(b'1 2 m\n3 2 l',clips[0])

    def test_nearest_rgba_image_rows_and_alpha_streams_are_lossless(self):
        d=self.fixture('raster');d['items']=[]
        pixels=bytes([255,0,0,255,0,255,0,128,0,0,255,64,20,40,80,0])
        d=self.edit(d,[dict(op='add',item=dict(id='pixels',transform=[2,0,0,3,1,2],content=dict(type='raster',width=2,height=2,rgba_hex=pixels.hex())))])
        a=self.export(d);p=Pdf(a)
        images=[(id,o) for id,o in p.objects.items() if o.get('Subtype')=='Image' and o['ColorSpace']=='DeviceRGB']
        self.assertEqual(len(images),1);id,o=images[0]
        self.assertEqual(p.streams[id],bytes([255,0,0,0,255,0,0,0,255,20,40,80]))
        self.assertEqual(p.streams[o['SMask']],bytes([255,128,64,0]));self.assertFalse(o['Interpolate'])
        self.assertEqual(a['pdf']['image_pixels'],4)
        self.assertTrue(any(b'4 0 0 -6 1 8 cm' in s for s in p.streams.values()))

    def test_native_axial_radial_gradients_preserve_stops_and_transforms(self):
        d=self.fixture();d['items']=[]
        for kind in ['linear','radial']:
            paint=dict(type=kind,stops=[dict(offset=.2,color=[255,0,0,128]),dict(offset=.5,color=[0,255,0,128]),dict(offset=.5,color=[0,0,255,128]),dict(offset=.8,color=[255,255,255,128])],transform=[2,0,0,3,1,4])
            paint.update(dict(start=[0,0],end=[10,0]) if kind=='linear' else dict(center=[4,4],radius=3))
            one=self.edit(d,[dict(op='add',item=dict(id='gradient',content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=10,height=10),fill=paint)))])
            p=Pdf(self.export(one));shadings=[o for o in p.objects.values() if 'ShadingType' in o]
            self.assertEqual(shadings[0]['ShadingType'],2 if kind=='linear' else 3)
            f=p.get(shadings[0]['Function']);self.assertEqual(f['Bounds'],[.2,.5,.8,1])
            pieces=[p.get(r) for r in f['Functions']]
            self.assertEqual(pieces[1]['C1'],[0,1,0]);self.assertEqual(pieces[2]['C0'],[0,0,1])
            self.assertTrue(any(b'2 0 0 3 1 4 cm' in s for s in p.streams.values()))

    def test_gradient_terminal_discontinuity_keeps_the_last_stop_in_padded_regions(self):
        import bisect
        d=self.fixture();d['items']=[]
        for kind in ['linear','radial']:
            paint=dict(type=kind,stops=[dict(offset=0,color=[255,0,0,255]),dict(offset=1,color=[0,255,0,255]),dict(offset=1,color=[0,0,255,255])])
            paint.update(dict(start=[0,0],end=[8,0]) if kind=='linear' else dict(center=[8,8],radius=4))
            d['items']=[dict(id='gradient',content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=32,height=24),fill=paint))]
            p=Pdf(self.export(d));shading=next(o for o in p.objects.values() if 'ShadingType' in o)
            f=p.get(shading['Function']);self.assertEqual(shading['Domain'],[0,2]);self.assertEqual(f['Domain'],[0,2])
            for position,expected in [(-1,[1,0,0]),(.5,[.5,.5,0]),(1,[0,0,1]),(1.5,[0,0,1]),(20,[0,0,1])]:
                t=min(2,max(0,position));index=bisect.bisect_right(f['Bounds'],t)
                bounds=[0]+f['Bounds']+[2];u=(t-bounds[index])/(bounds[index+1]-bounds[index])
                piece=p.get(f['Functions'][index]);color=[a*(1-u)+b*u for a,b in zip(piece['C0'],piece['C1'])]
                self.assertEqual(color,expected)
            self.assertEqual(shading['Coords'],[0,0,16,0] if kind=='linear' else [8,8,0,8,8,8])

    def test_public_strip_and_selected_page_metadata_cannot_leak_unselected_notes(self):
        d=self.fixture();d['metadata']=metadata.PUBLIC
        next(i for i in d['items'] if i['id']=='wide')['metadata']=metadata.NOTE;next(i for i in d['items'] if i['id']=='tall')['metadata']=dict(note='unselected-marker')
        options=dict(artboards=dict(type='ids',ids=['wide']))
        a=self.export(d,pdf_options=options);p=Pdf(a)
        raw=p.streams[p.catalog['Metadata']];root=ET.fromstring(raw)
        packet=root.find('.//{urn:inkbolt:pdf:metadata:1}packet').text;envelope=json.loads(packet)
        self.assertEqual(envelope['pages'][0]['packet']['document'],metadata.public(metadata.PUBLIC))
        self.assertEqual(envelope['pages'][0]['packet']['items'],{'wide':metadata.public(metadata.NOTE)})
        for marker in [b'unselected-marker',b'private-note-marker',b'local_path']:self.assertNotIn(marker,p.data)
        self.assertEqual(a['metadata']['envelope_sha256'],hashlib.sha256(packet.encode()).hexdigest())
        stripped=Pdf(self.export(d,pdf_options=options,metadata_policy=dict(mode='strip')))
        self.assertNotIn('Metadata',stripped.catalog)
        self.assertEqual(p.paths(),stripped.paths())

    def test_create_only_publication_keeps_sources_and_reports_pages(self):
        d=self.fixture();before=copy.deepcopy(d)
        with tempfile.TemporaryDirectory() as directory:
            options=dict(output_root=directory,file_name='pages.pdf',format='pdf',pdf_options=dict(artboards=dict(type='all')))
            receipt=self.invoke(dict(command='document.publish',document=d,output=options));path=Path(directory)/'pages.pdf'
            expected=base64.b64decode(self.export(d,pdf_options=options['pdf_options'])['data'])
            self.assertEqual(path.read_bytes(),expected);self.assertEqual(len(receipt['pages']),2)
            self.assertEqual(receipt['sha256'],hashlib.sha256(expected).hexdigest())
            e=self.invoke(dict(command='document.publish',document=d,output=options),1);self.assertEqual(e['code'],'OUTPUT_EXISTS')
            self.assertEqual(path.read_bytes(),expected)
            options.update(file_name='single.pdf',artboard_id='wide',include_bleed=True);options.pop('pdf_options')
            receipt=self.invoke(dict(command='document.publish',document=d,output=options))
            self.assertEqual(receipt['pages'][0]['logical_size'],[8,7])
        self.assertEqual(d,before)

    def test_invalid_options_ranges_and_foreign_semantics_fail_explicitly(self):
        d=self.fixture()
        for kw in [dict(scale=2),dict(image_options=dict(quality=90)),dict(pdf_options=dict(include_bleed=True)),dict(pdf_options=dict(unknown=True)),dict(pdf_options=dict(artboards=dict(type='ids',ids=['missing']))),dict(pdf_options=dict(artboards=dict(type='range',start=1,end=1)))]:
            self.assertIn('code',self.export(d,1,**kw))
        self.assertEqual(self.invoke(dict(command='document.export',document=d,format='png',pdf_options={}),1)['code'],'INVALID_REQUEST')
        for property,value in [('blend','multiply'),('mask',dict(width=1,height=1,gray_hex='80'))]:
            bad=copy.deepcopy(d);next(i for i in bad['items'] if i['id']=='red')[property]=value
            self.assertIn('code',self.export(bad,1))
        bad=self.fixture('raster');next(i for i in bad['items'] if i['id']=='red')['content']['sampling']='bilinear'
        self.assertEqual(self.export(bad,1)['code'],'UNSUPPORTED')
        with tempfile.TemporaryDirectory() as directory:
            self.invoke(dict(command='document.publish',document=bad,output=dict(output_root=directory,file_name='absent.pdf',format='pdf')),1)
            self.assertEqual(list(Path(directory).iterdir()),[])


    def test_cropped_placed_asset_preserves_exact_rows_and_validates_identity(self):
        from test_images_cli import canonical
        pixels=bytes([10,20,30,255,40,50,60,128,70,80,90,255,100,110,120,64])
        d=self.fixture();d['items']=[]
        d['assets']={'source':dict(width=2,height=2,sha256=hashlib.sha256(canonical(2,2,pixels)).hexdigest(),storage=dict(type='embedded',rgba_hex=pixels.hex()))}
        d=self.edit(d,[dict(op='add',item=dict(id='image',content=dict(type='image',asset_id='source',width=6,height=8,crop=dict(x=1,y=0,width=1,height=2))))])
        before=copy.deepcopy(d);p=Pdf(self.export(d))
        ref=next(Ref(k) for k,o in p.objects.items() if o.get('ColorSpace')=='DeviceRGB' and o.get('Subtype')=='Image')
        self.assertEqual(p.streams[ref],bytes([40,50,60,100,110,120]))
        self.assertEqual(p.streams[p.get(ref)['SMask']],bytes([128,64]));self.assertEqual(d,before)
        d['assets']['source']['sha256']='0'*64
        self.assertIn('code',self.export(d,1))

    def test_image_copy_limit_is_global_across_pages_and_fails_before_publication(self):
        from test_images_cli import canonical
        pixels=bytes([10,20,30,255])*65536
        d=self.fixture();d['items']=[]
        d['assets']={'source':dict(width=256,height=256,sha256=hashlib.sha256(canonical(256,256,pixels)).hexdigest(),storage=dict(type='embedded',rgba_hex=pixels.hex()))}
        d['items']=[dict(id='copy-'+str(i),content=dict(type='image',asset_id='source',width=1,height=1)) for i in range(65)]
        self.assertEqual(self.export(d,1)['code'],'RESOURCE_LIMIT')
        d['items']=[]
        for page in range(3):
            id='page-'+str(page);d['items'].append(self.board(id,2,2))
            d['items'] += [dict(id=f'image-{page}-{i}',parent=id,content=dict(type='image',asset_id='source',width=1,height=1)) for i in range(23)]
        self.assertEqual(self.export(d,1,pdf_options=dict(artboards=dict(type='all')))['code'],'RESOURCE_LIMIT')

    def test_artboard_selection_does_not_include_unselected_unsupported_appearance(self):
        d=self.fixture();next(i for i in d['items'] if i['id']=='blue')['blend']='multiply'
        self.assertEqual(self.export(d,1)['code'],'UNSUPPORTED')
        selected=self.export(d,pdf_options=dict(artboards=dict(type='ids',ids=['wide'])))
        self.assertEqual(len(Pdf(selected).pages),1)

    def test_gradient_reconstruction_boundaries_and_disabled_masks_are_explicit(self):
        d=self.fixture();red=next(i for i in d['items'] if i['id']=='red')
        paint=dict(type='linear',start=[0,0],end=[8,0],stops=[dict(offset=0,color=[0,0,0,255]),dict(offset=1,color=[255,0,0,255])])
        red['content']['fill']=paint
        for key,value in [('spread','reflect'),('space','linear_rgb')]:
            paint[key]=value;self.assertEqual(self.export(d,1)['code'],'UNSUPPORTED');paint.pop(key)
        paint['stops'][1]['color'][3]=0
        self.assertEqual(self.export(d,1)['code'],'UNSUPPORTED')
        paint['stops'][1]['color'][3]=255
        red['mask']=dict(width=1,height=1,gray_hex='80',enabled=False)
        self.assertEqual(len(Pdf(self.export(d)).pages),1)

    def test_document_scaled_and_object_scaled_stroke_bounds_remain_distinct(self):
        d=self.fixture();d['items']=[]
        for scaling,extent in [('object',1.5),('document',.75)]:
            item=dict(id='line',transform=[2,0,0,2,0,0],content=dict(type='vector',geometry=dict(shape='path',commands=[dict(verb='move',to=[2,3]),dict(verb='line',to=[8,3])]),stroke=dict(width=2,color=[0,0,0,255],scaling=scaling)))
            one=self.edit(d,[dict(op='add',item=item)]);path=Pdf(self.export(one)).paths()[0]
            points=[v for _,points in path['path'] for v in points]
            self.assertEqual(min(p[1] for p in points),4.5-extent);self.assertEqual(max(p[1] for p in points),4.5+extent)

    def test_mcp_session_pdf_delivery_preserves_history_and_revision_conflicts(self):
        from test_mcp import Client
        with tempfile.TemporaryDirectory() as directory:
            c=Client();self.addCleanup(c.close);c.initialize()
            s=dict(session_root=str(Path(directory)/'sessions'),session_id='pdf')
            d=self.fixture();c.success('session.create',**s,request_id='create',document=d)
            before=c.success('session.history',**s,limit=10)
            d=c.success('session.read',**s)['document']
            options=dict(artboards=dict(type='all'),include_bleed=True)
            a=c.success('document.export',document=d,format='pdf',pdf_options=options)
            output=dict(output_root=directory,file_name='pages.pdf',format='pdf',pdf_options=options)
            receipt=c.success('session.publish',**s,expected_revision=0,output=output)
            self.assertEqual(receipt['observed_current_revision'],0);self.assertTrue(receipt['include_bleed'])
            self.assertEqual((Path(directory)/'pages.pdf').read_bytes(),base64.b64decode(a['data']))
            self.assertEqual(c.success('session.history',**s,limit=10),before)
            error=c.tool('session.publish',**s,expected_revision=1,output=dict(output,file_name='absent.pdf'))
            self.assertEqual(error['structuredContent']['error']['code'],'REVISION_CONFLICT')
            self.assertFalse((Path(directory)/'absent.pdf').exists())


class PdfTypographyTests(unittest.TestCase):
    invoke=bidi.BidiTextTests.invoke
    edit=bidi.BidiTextTests.edit
    inspect=bidi.BidiTextTests.inspect
    document=bidi.BidiTextTests.document
    setUp=bidi.BidiTextTests.setUp
    add_font=bidi.BidiTextTests.add_font
    make=bidi.BidiTextTests.make

    def pdf(self,d):return self.invoke(dict(command='document.export',document=d,format='pdf',font_root=str(self.store)))

    def test_bidi_cjk_marks_and_ligature_paths_match_independent_original_font_rectangles(self):
        from synthetic_unicode_font import rectangle, ADVANCES
        for kind in ["vector","raster"]:
            for text,gids in [('A \u05d0\u05d1 12 B',[2,1,3,4,1,18,17,1,3]),
                ('A \u0628\u0628\u062a B',[2,1,16,10,9,1,3]),('fi',[26]),
                ('\u4e00\u3042\u30a2',[19,20,21]),('A\u0301',[2,6])]:
                d=self.make(text,kind);before=copy.deepcopy(d);a=self.pdf(d);paths=Pdf(a).paths()
                self.assertEqual(a['pdf']['text_glyphs'],len(gids));self.assertEqual(len(paths),sum(g!=1 for g in gids))
                x=0;j=0
                for gid in gids:
                    bounds=rectangle(gid)
                    if bounds is not None:
                        # Original font's only combining acute has anchor (300,750).
                        origin=x if gid!=6 else x-6+3;baseline=10 if gid!=6 else 2.5
                        expected=[(origin+bounds[0]/100)*.75,(baseline-bounds[3]/100)*.75,
                            (origin+bounds[2]/100)*.75,(baseline-bounds[1]/100)*.75]
                        points=[point for _,points in paths[j]['path'] for point in points]
                        actual=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
                        for aa,bb in zip(actual,expected):self.assertAlmostEqual(aa,bb,places=10)
                        j+=1
                    x+=ADVANCES[gid]/100
                self.assertEqual(d,before)
                self.assertIn('outlines',a['pdf']['text']);self.assertTrue(any('searchable' in loss for loss in a['losses']))
                self.assertFalse(any('Font' in o.get('Resources',{}) for o in Pdf(a).objects.values()))
    def test_text_clipping_styles_and_path_baseline_deliver_visible_outlines(self):
        d=self.make('AB',width=8,height=12,overflow='clip');d['items'][0]['transform']=[2,0,0,2,4,5]
        a=self.pdf(d);p=Pdf(a);self.assertEqual(len(p.paths()),2)
        self.assertTrue(any(b'W n' in data for data in p.streams.values()))
        from test_path_text_cli import line
        f=copy.deepcopy(d['items'][0]['content']['frame']);f['path']=line((0,15),(50,15),start_offset=2);f['overflow']='visible'
        placed=self.edit(d,[dict(op='text',id='label',frame=f)])
        paths=Pdf(self.pdf(placed)).paths()
        points=[v for _,points in paths[0]['path'] for v in points]
        expected=[(4+2*2.5)*.75,(5+2*(15-4.1))*.75,(4+2*3.7)*.75,(5+2*15)*.75]
        actual=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
        for x,y in zip(actual,expected):self.assertAlmostEqual(x,y,places=10)

    def test_raster_text_and_pixel_layer_share_one_pdf_without_source_conversion(self):
        d=self.make('AB','raster');before=copy.deepcopy(d)
        d=self.edit(d,[dict(op='add',item=dict(id='pixel',transform=[2,0,0,2,20,20],content=dict(type='raster',width=1,height=1,rgba_hex='ff000080')))])
        result=self.pdf(d);p=Pdf(result)
        self.assertEqual(result['pdf']['image_pixels'],1);self.assertEqual(result['pdf']['text_glyphs'],2)
        self.assertEqual(len(p.paths()),2);self.assertEqual(d['kind'],'raster')
        self.assertEqual(d['items'][0]['content'],before['items'][0]['content'])

    def test_missing_pinned_font_fails_before_any_pdf_is_published(self):
        d=self.make('AB')
        result=self.invoke(dict(command='document.export',document=d,format='pdf'),1)
        self.assertIn('code',result)


class PdfVariableTypographyTests(unittest.TestCase):
    invoke=font_controls.FontControlTests.invoke
    edit=font_controls.FontControlTests.edit
    document=font_controls.FontControlTests.document
    setUp=font_controls.FontControlTests.setUp
    add_font=font_controls.FontControlTests.add_font

    def test_variable_axis_instance_and_feature_selection_reach_pdf_paths(self):
        for kind in ["vector","raster"]:
            for coords in [dict(wght=100,wdth=50),dict(wght=650,wdth=150),dict(wght=900,wdth=200)]:
                d=self.document('A',kind=kind,coords=coords,features=dict(salt=2))
                a=self.invoke(dict(command='document.export',document=d,format='pdf',font_root=str(self.store)))
                points=[v for _,points in Pdf(a).paths()[0]['path'] for v in points]
                dx,dy,_,_=font_controls.deformation(coords['wght'],coords['wdth'])
                expected=[.5*.75,(10-(4.25+dy/100))*.75,(2+dx/100)*.75,7.5]
                actual=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
                for x,y in zip(actual,expected):self.assertAlmostEqual(x,y,places=10)
