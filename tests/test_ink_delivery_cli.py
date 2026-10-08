"""Original native ink declarations, parsed PDF operands and source-preserving edits."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
import pdf_reader
import test_swatches_cli as swatches
import test_boards_cli as boards
import test_instances_cli as instances
from test_mcp import Client


def cmyk(values, name='Process', spot=False):
    color=dict(space='cmyk',components=values)
    return dict(name=name,definition=dict(type='spot',alternate=color) if spot else dict(type='process',color=color))


def reference(id='ink', tint=1, opacity=1, overprint='knockout'):
    return dict(swatch=id,tint=tint,opacity=opacity,overprint=overprint)


def painted(pdf):
    """Read exactly emitted color/alpha/overprint operands in their resource scopes.

    Records declarations and group context, not a general PDF rasterizer.
    """
    records=[]
    def visit(data,resources,groups):
        args=[];stack=[];space='DeviceGray';values=[0];state={};path=[]
        for token in data.split():
            if token.startswith(b'/'):args.append(token[1:].decode());continue
            try:args.append(float(token));continue
            except ValueError:pass
            if token==b'q':stack.append((space,values,state,path))
            elif token==b'Q':space,values,state,path=stack.pop()
            elif token==b'gs':state=pdf.get(resources['ExtGState'][args[0]])
            elif token in (b'rg',b'k',b'g'):
                space={b'rg':'DeviceRGB',b'k':'DeviceCMYK',b'g':'DeviceGray'}[token];values=args[:]
            elif token==b'cs':space=pdf.get(resources['ColorSpace'][args[0]])
            elif token in (b'sc',b'scn'):values=args[:]
            elif token in (b'm',b'l',b'c'):path=path+[(token.decode(),args[:])]
            elif token==b'h':path=path+[('h',[])]
            elif token==b'n':path=[]
            elif token in (b'f',b'f*'):
                records.append(dict(space=space,values=values,state=state,path=path,groups=groups));path=[]
            elif token==b'Do':
                ref=resources['XObject'][args[0]];form=pdf.get(ref)
                if form['Subtype']=='Form':visit(pdf.streams[ref],form['Resources'],groups+[form.get('Group')])
            else:assert token in (b'cm',b'W',b'W*',b'sh'),token
            args=[]
        assert not args and not stack
    for page in pdf.pages:visit(pdf.streams[page['Contents']],page['Resources'],[page.get('Group')])
    return records


class InkDeliveryTests(unittest.TestCase):
    invoke=swatches.SwatchTests.invoke
    document=swatches.SwatchTests.document
    edit=swatches.SwatchTests.edit
    inspect=swatches.SwatchTests.inspect
    export=swatches.SwatchTests.export
    def pdf(self,d,**options):return self.export(d,'pdf',pdf_options=dict(color='native_inks',**options))

    def test_exact_cmyk_and_lab_process_operands_require_no_display_preview(self):
        values=[.0123456789012345,.2345678901234567,.4567890123456789,.67890123456789]
        lab=[64.125,-37.25,51.875]
        d=self.document({'ink':cmyk(values),'lab':swatches.process(space='lab',components=lab)},
            [swatches.rectangle(),swatches.rectangle('lab-art',reference('lab'),x=5)])
        artifact=self.pdf(d);pdf=pdf_reader.Pdf(artifact);p=painted(pdf)
        self.assertEqual(p[0]['space'],'DeviceCMYK');self.assertEqual(p[0]['values'],values)
        self.assertEqual(p[1]['space'][0],'Lab');self.assertEqual(p[1]['space'][1]['WhitePoint'],[.9642,1,.8249]);self.assertEqual(p[1]['values'],lab)
        self.assertEqual(pdf.pages[0]['Group']['CS'],'DeviceCMYK');self.assertTrue(artifact['swatches']['native_ink_preservation'])
        self.assertEqual(json.loads(self.export(d)['data']),d)

    def test_spot_alternates_and_nested_tints_have_exact_separation_functions(self):
        for space,color,white in [('srgb',[.125,.5,.875],[1,1,1]),('gray',.375,[1,1,1]),('cmyk',[.125,.25,.5,.75],[0,0,0,0]),('lab',[72,-24,48],[100,0,0])]:
            alternate=dict(space=space,component=color) if space=='gray' else dict(space=space,components=color)
            palette={'ink':dict(name='Original ink',definition=dict(type='spot',alternate=alternate)),
                'shade':swatches.tint('ink',.75),'pale':swatches.tint('shade',.5)}
            d=self.document(palette,[swatches.rectangle(fill=reference('pale',.25,.625))])
            pdf=pdf_reader.Pdf(self.pdf(d));p=painted(pdf)[0];s=p['space'];f=pdf.get(s[3])
            self.assertEqual(s[:2],['Separation','Inkbolt.ink']);self.assertEqual(p['values'],[.09375]);self.assertEqual(p['state']['ca'],.625)
            self.assertEqual(f['C0'],white);self.assertEqual(f['C1'],[color]*3 if space=='gray' else color);self.assertEqual(f['N'],1)
            self.assertIsNone(p['groups'][-1])

    def test_process_tints_use_declared_space_white_and_preserve_sources(self):
        for color,expected in [(cmyk([.25,.5,.75,1]),[.0625,.125,.1875,.25]),
            (swatches.process(space='lab',components=[60,-40,20]),[90,-10,5]),
            (swatches.process(space='srgb',components=[.25,.5,.75]),[.8125,.875,.9375])]:
            d=self.document({'ink':color},[swatches.rectangle(fill=reference(tint=.25))]);before=copy.deepcopy(d)
            self.assertEqual(painted(pdf_reader.Pdf(self.pdf(d)))[0]['values'],expected);self.assertEqual(d,before)

    def test_duplicate_labels_and_reserved_ids_remain_distinct_owned_spot_names(self):
        palette={id:cmyk([.25,.5,0,0],name='Same',spot=True) for id in ['Cyan','All','None','other']}
        d=self.document(palette,[swatches.rectangle(id,reference(id),x=i*3,w=2) for i,id in enumerate(palette)])
        pdf=pdf_reader.Pdf(self.pdf(d));names=[p['space'][1] for p in painted(pdf)]
        self.assertEqual(names,['Inkbolt.'+id for id in palette]);self.assertEqual(len(set(names)),4)

    def test_overprint_modes_are_per_paint_and_reset_before_ordinary_rgb(self):
        d=self.document({'ink':cmyk([.25,0,.5,0])},[swatches.rectangle('a',reference(overprint='preserve')),
            swatches.rectangle('b',reference(overprint='preserve_nonzero'),x=2),swatches.rectangle('c',reference(),x=4),
            swatches.rectangle('rgb',[20,40,60,255],x=6)])
        p=painted(pdf_reader.Pdf(self.pdf(d)))
        self.assertEqual([(q['state']['op'],q['state']['OP'],q['state']['OPM']) for q in p],[(True,True,0),(True,True,1),(False,False,0),(False,False,0)])
        self.assertTrue(all(q['groups'][-1] is None for q in p))

    def test_fill_and_outlined_stroke_have_independent_ink_overprint(self):
        item=swatches.rectangle(fill=reference(overprint='preserve_nonzero'))
        item['content']['stroke']=dict(width=1,color=reference('second',.5,overprint='preserve'))
        d=self.document({'ink':cmyk([1,0,0,0]),'second':cmyk([0,1,0,0],spot=True)},[item])
        p=painted(pdf_reader.Pdf(self.pdf(d)))
        self.assertEqual(p[0]['values'],[1,0,0,0]);self.assertEqual(p[0]['state']['OPM'],1)
        self.assertEqual(p[1]['space'][1],'Inkbolt.second');self.assertEqual(p[1]['values'],[.5]);self.assertEqual(p[1]['state']['OPM'],0)

    def test_real_group_isolation_and_item_opacity_are_retained(self):
        for isolated in [False,True]:
            g=dict(id='group',content=dict(type='group',isolated=isolated),opacity=.625)
            a=swatches.rectangle(fill=reference(overprint='preserve'),parent='group',opacity=.5)
            d=self.document({'ink':cmyk([1,0,0,0])},[g,a]);pdf=pdf_reader.Pdf(self.pdf(d));p=painted(pdf)[0]
            self.assertEqual(p['groups'][1]['I'],isolated);self.assertFalse(p['groups'][2]['I']);self.assertNotIn('CS',p['groups'][2])
            states=[v for v in pdf.objects.values() if isinstance(v,dict) and v.get('Type')=='ExtGState']
            self.assertTrue(any(v['ca']==.625 for v in states));self.assertTrue(any(v['ca']==.5 for v in states))

    def test_display_delivery_rejects_overprint_until_explicit_bake(self):
        d=self.document(items=[swatches.rectangle(fill=reference(overprint='preserve'))])
        self.assertEqual(self.invoke(dict(command='document.render',document=d),1)['code'],'OVERPRINT_PREVIEW_UNSUPPORTED')
        for format in ['svg','pdf']:
            self.assertEqual(self.export(d,format,1)['code'],'UNSUPPORTED')
        for format in ['png','tiff']:
            self.assertEqual(self.export(d,format,1)['code'],'OVERPRINT_PREVIEW_UNSUPPORTED')
        baked=self.edit(d,[dict(op='swatch_bake',ids=['art'])]);self.export(baked,'png');self.export(baked,'pdf')
        self.assertEqual(d['items'][0]['content']['fill']['overprint'],'preserve');self.assertEqual(baked['swatches'],d['swatches'])

    def test_non_cmyk_process_overprint_is_diagnosed_without_silent_conversion(self):
        for color in [swatches.process(components=[.25,.5,.75]),swatches.process(space='gray',component=.5),swatches.process(space='lab',components=[60,10,20])]:
            d=self.document({'ink':color},[swatches.rectangle(fill=reference(overprint='preserve'))])
            self.assertFalse(self.inspect(d)['ink_diagnostics']['paints'][0]['native_overprint_supported'])
            self.assertEqual(self.export(d,'pdf',1,pdf_options=dict(color='native_inks'))['code'],'UNSUPPORTED')

    def test_spot_process_conversion_retains_identity_tints_components_and_history_source(self):
        d=self.document({'ink':cmyk([.25,.5,.75,0],spot=True),'shade':swatches.tint('ink',.5)},[swatches.rectangle(fill=reference('shade',.25,overprint='preserve_nonzero'))])
        process=self.edit(d,[dict(op='swatch_convert',id='ink',kind='process')])
        self.assertEqual(process['items'],d['items']);self.assertEqual(process['swatches']['shade'],d['swatches']['shade'])
        self.assertEqual(process['swatches']['ink']['definition'],dict(type='process',color=d['swatches']['ink']['definition']['alternate']))
        self.assertEqual(painted(pdf_reader.Pdf(self.pdf(process)))[0]['values'],[.03125,.0625,.09375,0])
        restored=self.edit(process,[dict(op='swatch_convert',id='ink',kind='spot')]);self.assertEqual(restored['swatches'],d['swatches'])
        self.assertEqual(painted(pdf_reader.Pdf(self.pdf(restored)))[0]['values'],[.125])

    def test_native_global_recolor_updates_shared_function_without_rewriting_geometry(self):
        d=self.document({'ink':cmyk([.25,.5,0,0],spot=True),'shade':swatches.tint('ink',.25)},
            [swatches.rectangle('a',reference(overprint='preserve')),swatches.rectangle('b',reference('shade'),x=5)])
        replacement=cmyk([0,.25,.75,0],spot=True)
        changed=self.edit(d,[dict(op='swatch',id='ink',swatch=replacement)])
        self.assertEqual(changed['items'],d['items']);self.assertEqual(changed['swatches']['shade'],d['swatches']['shade'])
        for source,components in [(d,[.25,.5,0,0]),(changed,[0,.25,.75,0])]:
            pdf=pdf_reader.Pdf(self.pdf(source));p=painted(pdf)
            self.assertEqual(p[0]['space'],p[1]['space']);self.assertEqual(pdf.get(p[0]['space'][3])['C1'],components)
            self.assertEqual([v['values'] for v in p],[[1],[.25]])

    def test_conversion_explicit_replacement_locks_invalid_tints_and_batch_rollback(self):
        d=self.document();replacement=dict(space='cmyk',components=[.5,.25,0,0])
        converted=self.edit(d,[dict(op='swatch_convert',id='ink',kind='process',color=replacement)])
        self.assertEqual(converted['swatches']['ink']['definition']['color'],replacement)
        locked=copy.deepcopy(d);locked['items'][0]['locked']=True
        self.assertEqual(self.edit(locked,[dict(op='swatch_convert',id='ink',kind='process')],1)['code'],'LOCKED')
        alias=copy.deepcopy(d);alias['swatches']['shade']=swatches.tint('ink',.5)
        self.assertEqual(self.edit(alias,[dict(op='swatch_convert',id='shade',kind='spot')],1)['code'],'INVALID_SWATCH')
        self.edit(d,[dict(op='swatch_convert',id='ink',kind='process'),dict(op='swatch_convert',id='missing',kind='spot')],1)
        self.assertEqual(d['swatches']['ink']['definition']['type'],'spot')

    def test_transfer_remaps_native_ink_identity_and_keeps_paint_modes(self):
        source=self.document(items=[swatches.rectangle(fill=reference(overprint='preserve'))]);destination=self.invoke(dict(command='document.create',id='destination',kind='vector',width=16,height=8))
        copied=self.edit(destination,[dict(op='transfer',transfer=dict(source=source,ids=['art'],prefix='copy'))])
        p=painted(pdf_reader.Pdf(self.pdf(copied)))[0]
        self.assertEqual(p['space'][1],'Inkbolt.copy-ink');self.assertTrue(p['state']['op']);self.assertEqual(source['items'][0]['id'],'art')

    def test_components_resolve_paint_overrides_before_native_delivery(self):
        d=instances.InstanceTests().document();d['swatches']={'ink':cmyk([.5,0,.25,0],spot=True)}
        d['items'][1]['content']['fill']=reference(overprint='preserve')
        pdf=pdf_reader.Pdf(self.pdf(d));spots=[p for p in painted(pdf) if isinstance(p['space'],list) and p['space'][0]=='Separation']
        self.assertTrue(spots);self.assertTrue(all(p['space'][1]=='Inkbolt.ink' for p in spots))

    def test_ink_inventory_declares_structure_and_does_not_claim_plate_coverage(self):
        d=self.document({'ink':cmyk([.25,0,.5,0],spot=True),'other':cmyk([0,.5,0,0])},
            [swatches.rectangle(fill=reference(overprint='preserve')),swatches.rectangle('hidden',reference('other'),visible=False)])
        i=self.inspect(d)['ink_diagnostics'];self.assertEqual(i['spots'][0]['pdf_name'],'Inkbolt.ink');self.assertEqual(i['process_spaces'],['cmyk'])
        self.assertEqual(i['overprint_items'],['art']);self.assertIn('not_plate_coverage',i['scope']);self.assertEqual(len(i['paints']),2)

    def test_native_page_publication_is_create_only_and_retains_pdf_mode(self):
        d=self.document({'ink':cmyk([.5,0,0,0],spot=True)},[swatches.rectangle(fill=reference(overprint='preserve'))])
        with tempfile.TemporaryDirectory() as root:
            options=dict(output_root=root,file_name='inks.pdf',format='pdf',pdf_options=dict(color='native_inks'))
            receipt=self.invoke(dict(command='document.publish',document=d,output=options));self.assertTrue(receipt['swatches']['native_ink_preservation'])
            data=(Path(root)/'inks.pdf').read_bytes();self.assertEqual(data,base64.b64decode(self.pdf(d)['data']))
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=options),1)['code'],'OUTPUT_EXISTS');self.assertEqual((Path(root)/'inks.pdf').read_bytes(),data)

    def test_artboard_order_bleed_spot_resource_reuse_and_offboard_diagnostics(self):
        first=boards.BoardCliTests().board('first',8,6,bleed=dict(top=1,right=2,bottom=3,left=4))
        second=boards.BoardCliTests().board('second',6,4,x=20)
        palette={'ink':cmyk([.25,.5,0,0],spot=True),'rgb':swatches.process(components=[.25,.5,.75])}
        items=[first,swatches.rectangle('a',reference(overprint='preserve'),x=-2,parent='first'),
            second,swatches.rectangle('b',reference(tint=.5),parent='second'),swatches.rectangle('excluded',reference('rgb',overprint='preserve'))]
        d=self.document(palette,items,w=32,h=16)
        artifact=self.pdf(d,artboards=dict(type='ids',ids=['second','first']),include_bleed=True);pdf=pdf_reader.Pdf(artifact)
        self.assertEqual([p['artboard_id'] for p in artifact['pages']],['second','first'])
        self.assertEqual(pdf.pages[1]['MediaBox'],[0,0,10.5,7.5]);self.assertEqual(pdf.pages[1]['TrimBox'],[3,2.25,9,6.75])
        spaces=[v for v in pdf.objects.values() if isinstance(v,list) and v and v[0]=='Separation'];self.assertEqual(len(spaces),1)
        self.assertEqual([p['values'] for p in painted(pdf)],[[.5],[1]])
        self.assertTrue(all(all(p['item_id']!='excluded' for p in page['paints']) for page in artifact['swatches']['pages']))

    def test_named_text_ranges_and_raster_fills_retain_native_ink_controls(self):
        import test_text_cli as text
        helper=text.TextCliTests();helper.setUp();self.addCleanup(helper.doCleanups)
        d=helper.document(text='AB');d['swatches']={'ink':cmyk([0,.5,.25,0],spot=True)}
        d['items'][0]['content']['frame']['style']['fill']=reference(tint=.25,overprint='preserve')
        artifact=self.export(d,'pdf',pdf_options=dict(color='native_inks'),font_root=str(helper.store));paints=painted(pdf_reader.Pdf(artifact))
        self.assertEqual(len(paints),2);self.assertTrue(all(p['space'][1]=='Inkbolt.ink' and p['values']==[.25] and p['state']['op'] for p in paints))
        d=self.document({'ink':cmyk([.5,0,0,0])},[dict(id='fill',content=dict(type='fill',width=4,height=4,paint=reference(overprint='preserve_nonzero')))],kind='raster')
        p=painted(pdf_reader.Pdf(self.pdf(d)))[0];self.assertEqual(p['values'],[.5,0,0,0]);self.assertEqual(p['state']['OPM'],1)

    def test_invalid_modes_cancellation_and_failed_native_publication_leave_no_output(self):
        d=self.document()
        bad=copy.deepcopy(d);bad['items'][0]['content']['fill']['overprint']='guess'
        self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'INVALID_REQUEST')
        self.assertEqual(self.export(d,'pdf',1,pdf_options=dict(color='guess'))['code'],'INVALID_REQUEST')
        d=self.document({'ink':swatches.process(components=[.25,.5,.75])},[swatches.rectangle(fill=reference(overprint='preserve'))])
        with tempfile.TemporaryDirectory() as root:
            output=dict(output_root=root,file_name='rejected.pdf',format='pdf',pdf_options=dict(color='native_inks'))
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output),1)['code'],'UNSUPPORTED')
            self.assertFalse(list(Path(root).iterdir()))
            self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output,control=dict(timeout_ms=0)),1)['code'],'TIMEOUT')
            self.assertFalse(list(Path(root).iterdir()))

    def test_mcp_conversion_overprint_native_publication_undo_redo_and_retry(self):
        d=self.document({'ink':cmyk([.5,0,0,0],spot=True)},[swatches.rectangle(fill=reference(overprint='preserve_nonzero'))])
        client=Client();self.addCleanup(client.close);client.initialize()
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='native-inks');client.success('session.create',**session,request_id='create',document=d)
            edit=dict(type='edit',operations=[dict(op='swatch_convert',id='ink',kind='process')])
            changed=client.success('session.apply',**session,request_id='convert',expected_revision=0,action=edit)
            output=dict(output_root=root,file_name='inks.pdf',format='pdf',pdf_options=dict(color='native_inks'))
            receipt=client.success('session.publish',**session,expected_revision=1,output=output);self.assertTrue(receipt['swatches']['native_ink_preservation'])
            undo=client.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'));self.assertEqual(undo['document']['swatches'],d['swatches'])
            redo=client.success('session.apply',**session,request_id='redo',expected_revision=2,action=dict(type='redo'));self.assertEqual(redo['document']['swatches'],changed['document']['swatches'])
            self.assertTrue(client.success('session.apply',**session,request_id='convert',expected_revision=0,action=edit)['replayed']);self.assertTrue(client.success('session.verify',**session)['valid'])


if __name__=='__main__':unittest.main()
