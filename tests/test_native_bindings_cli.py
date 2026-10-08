"""Explicit source ink interpretation before ordered native composition."""
import base64
import copy
from fractions import Fraction as F
import hashlib
import itertools
import json
from pathlib import Path
import tempfile
import unittest
import pdf_reader
import test_native_objects_cli as objects
import test_native_images_cli as images
import test_native_warps_cli as warps
import test_native_blending_cli as blends
import test_native_filters_cli as spatial
import test_native_nonlinear_cli as nonlinear
from test_vector_plates_cli import named, color, spot
from test_effects_coverage_cli import effect
from test_profiles_cli import embedded
from test_native_print_cli import page_image
from test_mcp import Client
from cmyk_fixtures import cmyk_profile


def binding(path=('placed',), source='a', target='shared'):
    return dict(object_path=list(path),source_spot=source,target_spot=target)


class NativeBindingTests(unittest.TestCase):
    invoke = objects.NativeObjectTests.invoke
    document = objects.NativeObjectTests.document
    planes = objects.NativeObjectTests.planes
    values = objects.NativeObjectTests.values
    assertRows = objects.NativeObjectTests.assertRows

    def source(self, w=1, h=1):
        d=self.document(w,h);d['swatches']=dict(p=color([.5,.25,.125,.0625]),a=spot('Source a'),b=spot('Source b'))
        d['swatches']['b']['definition']['alternate']['components']=[1,0,0,0]
        d['items']=[images.fill('process',named('p',opacity=.25),box=(0,0,w,h)),images.fill('a',named('a',tint=.375,opacity=.5,overprint='preserve'),box=(0,0,w,h)),images.fill('b',named('b',tint=.75,opacity=.625,overprint='preserve'),box=(0,0,w,h))]
        return d

    def scene(self, source=None, **placement):
        source=source or self.source();d=self.document(source['width'],source['height']);d['swatches']=dict(back=color([.75,.5,.25,.125]),shared=spot('Destination ink'))
        d['items']=[images.fill('back',named('back'),box=(0,0,d['width'],d['height'])),images.fill('destination',named('shared',tint=.625,overprint='preserve'),box=(0,0,d['width'],d['height'])),objects.placed(source,**placement)]
        return d

    def bindings(self):return [binding(source='a'),binding(source='b')]

    def settings(self, bindings=None):
        return dict(profile=embedded(cmyk_profile()),antialias='none',spot_fallback='multiplicative_declared',ink_bindings=self.bindings() if bindings is None else bindings)

    def export(self,d,bindings=None,**kw):
        return self.invoke(dict(command='document.export',document=d,format='pdf',pdf_options=dict(prepress=self.settings(bindings),**kw)))

    def collapsed(self,d,source):
        """Equivalent authored single-ink isolated group, no routing options."""
        ref=copy.deepcopy(d);ref['swatches'].update(copy.deepcopy(source['swatches']))
        for id in ['a','b']:ref['swatches'][id]=dict(name='Explicit alias',definition=dict(type='tint',base='shared',tint=1))
        ref['items'][-1]['content']=dict(type='group',isolated=True)
        ref['items'].extend(dict(copy.deepcopy(i),parent=i.get('parent','placed')) for i in source['items'])
        return ref

    def test_ordered_shared_ink_composition_matches_independent_rationals(self):
        d=self.scene(opacity=.5);before=copy.deepcopy(d);r=self.planes(d,ink_bindings=self.bindings(),samples=[[0,0]])
        alpha=1-F(3,4)*F(1,2)*F(3,8);ink=F(3,8)*F(1,2)*F(3,8)+F(3,4)*F(5,8)
        original=[F(1,8),F(1,16),F(1,32),F(1,64),ink];back=list(map(F,[.75,.5,.25,.125,.625]));expected=[v/2+b*(1-alpha/2) for v,b in zip(original,back)]
        self.assertEqual([p['id'] for p in r['plates']],['cyan','magenta','yellow','black','shared']);self.assertRows([r['samples'][0]['ink_fractions']],[expected],2e-15)
        self.assertEqual(len(r['coverage_sources']['ink_bindings']),2);self.assertTrue(all(b['applied'] for b in r['coverage_sources']['ink_bindings']))
        self.assertEqual(r['image_sources'][0]['spot_mapping'],[dict(source_id=None,target_spot='shared',id='shared',name='Destination ink')]);self.assertEqual(d,before)
        self.assertNotEqual(ink,F(3,8)*F(1,2)+F(3,4)*F(5,8))

    def test_every_blend_and_overprint_policy_resolves_aliases_before_compositing(self):
        for mode,policy in itertools.product(blends.MODES,['knockout','preserve','preserve_nonzero']):
            source=self.source();source['items'][-1]['blend']=mode;source['items'][-1]['content']['paint']['overprint']=policy
            source['swatches']['tint']=dict(name='Retained tint',definition=dict(type='tint',base='a',tint=.5));source['items'][1]['content']['paint']['swatch']='tint'
            local=[F(1,8),F(1,16),F(1,32),F(1,64),F(0)];alpha=F(1,4)
            local,alpha=blends.over(local,alpha,[F(0)]*4+[F(3,16)],F(1,2),[False]*4+[True])
            local,alpha=blends.over(local,alpha,[F(0)]*4+[F(3,4)],F(5,8),[True]*5 if policy=='knockout' else [False]*4+[True],mode)
            d=self.scene(source);back=list(map(F,[.75,.5,.25,.125,.625]));expected=[v+b*(1-alpha) for v,b in zip(local,back)]
            with self.subTest(mode=mode,policy=policy):self.assertRows(self.values(d,ink_bindings=self.bindings()),[expected],3e-12)

    def test_nested_and_sibling_routes_share_targets_without_changing_unbound_identity(self):
        leaf=self.source(2,1);leaf['items']=[images.fill('a',named('a',tint=.5,opacity=.5),box=(0,0,1,1)),images.fill('b',named('b',tint=.75,opacity=.5),box=(1,0,1,1))]
        middle=self.document(2,1);middle['swatches']=dict(a=spot('Source a'));middle['items']=[images.fill('a',named('a',tint=.25,opacity=.5),box=(0,0,2,1)),objects.placed(leaf,id='inner')]
        d=self.scene(middle);d.update(width=4,height=1);d['items']=d['items'][-1:]+[objects.placed(leaf,id='right',transform=[1,0,0,1,2,0])]
        routes=[binding(source='a'),binding(('placed','inner'),'a'),binding(('placed','inner'),'b'),binding(('right',),'a')]
        r=self.planes(d,ink_bindings=routes);self.assertEqual([p['id'] for p in r['plates']],['cyan','magenta','yellow','black','/right/b','shared'])
        self.assertRows(self.values(d,ink_bindings=routes),[[0,0,0,0,0,F(5,16)],[0,0,0,0,0,F(7,16)],[0,0,0,0,0,F(1,4)],[0,0,0,0,F(3,8),0]],2e-15)
        self.assertEqual(r['image_sources'][0]['spot_mapping'],[dict(source_id=None,target_spot='shared',id='shared',name='Destination ink')])
        self.assertEqual(self.planes(d,ink_bindings=list(reversed(routes))),r)

    def test_destination_declaration_controls_name_and_alternate_without_changing_amounts(self):
        d=self.scene();r=self.planes(d,ink_bindings=self.bindings());artifact=self.export(d);original=copy.deepcopy(d)
        self.assertEqual(artifact['pages'][0]['spot_fallback']['alternate_cmyk']['shared'],[0,1,0,0])
        d['swatches']['shared']['name']='Chosen destination';d['swatches']['shared']['definition']['alternate']['components']=[.125,.25,.5,.75]
        changed=self.planes(d,ink_bindings=self.bindings());self.assertEqual(changed['interleaved_sha256'],r['interleaved_sha256']);self.assertEqual(changed['plates'][-1]['name'],'Chosen destination')
        receipt=changed['coverage_sources']['ink_bindings'][0];self.assertEqual(receipt['target_alternate']['components'],[.125,.25,.5,.75]);self.assertEqual(receipt['source_alternate']['components'],[0,1,0,0]);self.assertEqual(d['items'],original['items'])
        artifact=self.export(d);self.assertEqual(artifact['pages'][0]['spot_fallback']['alternate_cmyk']['shared'],[.125,.25,.5,.75])
        self.assertNotIn(b'@shared',base64.b64decode(artifact['data']))

    def test_invalid_duplicate_nonspot_and_malformed_paths_fail_explicitly(self):
        d=self.scene();source=json.loads(d['items'][-1]['content']['object']['snapshot']);source['swatches']['alias']=dict(name='Tint alias',definition=dict(type='tint',base='a',tint=.5));d['items'][-1]=objects.placed(source)
        d['swatches']['alias']=dict(name='Root alias',definition=dict(type='tint',base='shared',tint=.5))
        bad=[binding(()),binding(('missing',)),binding(('back',)),binding(('placed','a')),binding(source='missing'),binding(source='p'),binding(source='alias'),binding(target='missing'),binding(target='back'),binding(target='alias'),binding(('placed',)*5),binding(('../placed',)),binding(source='/a')]
        for route in bad:
            with self.subTest(route=route):self.assertEqual(self.planes(d,1,ink_bindings=[route])['code'],'INVALID_INK_BINDING')
        for routes in [[binding(),binding()],[binding(),binding(target='alias')]]:self.assertEqual(self.planes(d,1,ink_bindings=routes)['code'],'INVALID_INK_BINDING')
        error=self.planes(d,1,ink_bindings=[dict(binding(),surprise=True)]);self.assertIn(error['code'],['INVALID_REQUEST','INVALID_JSON'])

    def test_bounds_count_unique_effective_channels_and_keep_source_count_limit(self):
        source=self.source();source['items']=source['items'][1:2];d=self.document(1,1);d['swatches']=dict(shared=spot());d['items']=[objects.placed(source,id=f'o{i:02}') for i in range(32)]
        self.assertEqual(self.planes(d,1)['code'],'RESOURCE_LIMIT');routes=[binding((f'o{i:02}',)) for i in range(32)]
        r=self.planes(d,ink_bindings=routes,samples=[[0,0]]);self.assertEqual(len(r['plates']),5);self.assertRows([r['samples'][0]['ink_fractions']],[[0,0,0,0,F(3,8)*(1-F(1,2)**32)]],2e-15)
        d['items'].append(objects.placed(source,id='extra'));self.assertEqual(self.planes(d,1,ink_bindings=routes+[binding(('extra',))])['code'],'RESOURCE_LIMIT')
        self.assertEqual(self.planes(self.scene(),1,ink_bindings=[binding()]*1025)['code'],'RESOURCE_LIMIT')
        # Many local source aliases still share one physical channel before the 28-ink bound.
        source=self.document(1,1);source['swatches']={f'a{i:02}':spot() for i in range(40)};source['items']=[images.fill(f'a{i:02}',named(f'a{i:02}',tint=.5,opacity=.5),box=(0,0,1,1)) for i in range(40)];d=self.scene(source);routes=[binding(source=f'a{i:02}') for i in range(40)];self.assertEqual(len(self.planes(d,ink_bindings=routes)['plates']),5)

    def test_hidden_unused_sources_are_valid_but_report_unapplied(self):
        source=self.source();source['swatches']['unused']=spot();d=self.scene(source);d['items'].append(objects.placed(source,id='hidden',visible=False));routes=self.bindings()+[binding(source='unused'),binding(('hidden',),'a')]
        r=self.planes(d,ink_bindings=routes);applied={(tuple(b['object_path']),b['source_spot']):b['applied'] for b in r['coverage_sources']['ink_bindings']}
        self.assertEqual(applied,{(('placed',),'a'):True,(('placed',),'b'):True,(('placed',),'unused'):False,(('hidden',),'a'):False});self.assertEqual(len(r['plates']),5)

    def test_selected_pages_validate_original_paths_and_report_per_page_application(self):
        source=self.source(4,3);d=self.document(16,8);d['swatches']=dict(shared=spot());d['items']=[dict(id='pageA',content=dict(type='frame',frame=dict(role='artboard',width=4,height=3))),objects.placed(source,id='left',parent='pageA'),dict(id='pageB',transform=[1,0,0,1,6,0],content=dict(type='frame',frame=dict(role='artboard',width=4,height=3))),objects.placed(source,id='right',parent='pageB')]
        routes=[binding((p,),s) for p in ['left','right'] for s in ['a','b']]
        receipts=[]
        for page,selected in [('pageA','left'),('pageB','right')]:
            r=self.planes(d,ink_bindings=routes,artboard_id=page);receipts.append(r)
            self.assertTrue(all(b['applied']==(b['object_path']==[selected]) for b in r['coverage_sources']['ink_bindings']))
        artifact=self.export(d,routes,artboards=dict(type='ids',ids=['pageB','pageA']));self.assertEqual(len(artifact['pages']),2)
        pdf=pdf_reader.Pdf(artifact)
        for i,r in enumerate(reversed(receipts)):
            self.assertEqual(artifact['pages'][i]['coverage_sources']['ink_bindings'],r['coverage_sources']['ink_bindings']);self.assertEqual(hashlib.sha256(page_image(pdf,i)[1]).hexdigest(),r['interleaved_sha256'])

    def test_native_filters_and_effects_see_one_resolved_source_channel(self):
        for operator in spatial.operators()+nonlinear.operators():
            source=self.source(8,4);source['items'][-1]['transform']=[1,0,0,1,1,0];source['items'][-1]['content']['width']=6;source['items'][-1]['filters']=[dict(id='filter',operator=operator,border='reflect')]
            source['items'][1]['effects']=[effect('overlay','overlay',named('b',tint=.25,opacity=.5,overprint='preserve'))]
            d=self.scene(source);ref=self.collapsed(d,source)
            with self.subTest(operator=operator):self.assertRows(self.values(d,ink_bindings=self.bindings()),self.values(ref),3e-13)

    def test_named_noise_uses_destination_identity_without_perturbing_unbound_inks(self):
        source=self.source(8,4);source['swatches']['untouched']=spot();source['items'].append(images.fill('u',named('untouched',tint=.375,overprint='preserve'),box=(0,0,8,4)))
        source['items'].insert(0,dict(id='group',content=dict(type='group',isolated=True),filters=[dict(id='noise',operator=dict(type='detail',operator=dict(type='noise',amount=.125,seed=71,monochrome=False,distribution='uniform')))]))
        for item in source['items'][1:]:item['parent']='group'
        d=self.scene(source);base=self.planes(d,samples=[[x,y] for y in range(4) for x in range(8)]);bound=self.planes(d,ink_bindings=self.bindings(),samples=[[x,y] for y in range(4) for x in range(8)])
        bi=[p['id'] for p in base['plates']].index('/placed/untouched');ci=[p['id'] for p in bound['plates']].index('/placed/untouched')
        self.assertEqual([p['ink_fractions'][bi] for p in base['samples']],[p['ink_fractions'][ci] for p in bound['samples']])
        ref=self.collapsed(d,source);reference=self.planes(ref,samples=[[x,y] for y in range(4) for x in range(8)]);ri=[p['id'] for p in reference['plates']].index('shared');ci=[p['id'] for p in bound['plates']].index('shared');self.assertRows([[p['ink_fractions'][ci]] for p in bound['samples']],[[p['ink_fractions'][ri]] for p in reference['samples']],3e-14)

    def test_binding_precedes_warp_reconstruction_and_keeps_saved_sources(self):
        source=self.source(8,8);source['items']=[];rows=[]
        for i in range(64):
            a=F(i%4+1,4);b=F((i*3)%5,4);ta=F(i%7,8);tb=F((i*5)%9,8)
            source['items'].extend([images.fill(f'a{i}',named('a',opacity=float(a),tint=float(ta)),box=(i%8,i//8,1,1)),images.fill(f'b{i}',named('b',opacity=float(b),tint=float(tb),overprint='preserve'),box=(i%8,i//8,1,1))]);rows.append([F(0)]*4+[ta*a*(1-b)+tb*b,a+(1-a)*b])
        for warp,method in itertools.product(warps.warps(),['nearest','bilinear']):
            d=self.scene(source,pixel_warp=warp,settings=dict(sampling=method));before=copy.deepcopy(d);_,inverse=warps.maps(warp);expected=[]
            for y in range(8):
                for x in range(8):
                    q=inverse([F(2*x+1,2),F(2*y+1,2)]);p=[F(0)]*6 if q is None else objects.sample(rows,(8,8),q,method);back=list(map(F,[.75,.5,.25,.125,.625]));expected.append([p[c]+back[c]*(1-p[-1]) for c in range(5)])
            self.assertRows(self.values(d,ink_bindings=self.bindings()),expected,3e-14);self.assertEqual(d,before)

    def test_link_source_bytes_and_create_only_pdf_survive_explicit_routing(self):
        source=self.source(4,3)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'source.json';path.write_bytes((json.dumps(source,indent=3)+'\n').encode());original=path.read_bytes();obj=self.invoke(dict(command='object.import',source_path=str(path),link_key=path.name))['object'];d=self.scene(source);d['items'][-1]['content']['object']=obj
            original_parent=copy.deepcopy(d);output=dict(output_root=directory,file_name='shared.pdf',format='pdf',pdf_options=dict(prepress=self.settings()))
            receipt=self.invoke(dict(command='document.publish',document=d,output=output));raw=(root/'shared.pdf').read_bytes();r=self.planes(d,ink_bindings=self.bindings());self.assertEqual(hashlib.sha256(page_image(pdf_reader.Pdf(dict(data=base64.b64encode(raw).decode())))[1]).hexdigest(),r['interleaved_sha256'])
            self.assertEqual(receipt['pages'][0]['coverage_sources']['ink_bindings'],r['coverage_sources']['ink_bindings']);self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output),1)['code'],'OUTPUT_EXISTS');self.assertEqual(path.read_bytes(),original);self.assertEqual(d,original_parent)

    def test_cancellation_invalid_routes_and_timeout_leave_no_artifact(self):
        d=self.scene();original=copy.deepcopy(d)
        with tempfile.TemporaryDirectory() as directory:
            marker=Path(directory)/'cancel';marker.write_text('cancel');output=dict(output_root=directory,file_name='failed.pdf',format='pdf',pdf_options=dict(prepress=self.settings()))
            for control,code in [(dict(timeout_ms=0),'TIMEOUT'),(dict(cancel_file=str(marker)),'CANCELLED')]:
                self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output,control=control),1)['code'],code)
            output['pdf_options']['prepress']['ink_bindings']=[binding(('missing',))];self.assertEqual(self.invoke(dict(command='document.publish',document=d,output=output),1)['code'],'INVALID_INK_BINDING');self.assertFalse((Path(directory)/'failed.pdf').exists());self.assertEqual(d,original)

    def test_agent_bindings_schema_history_and_replayed_source_edit(self):
        source=self.source(4,3);d=self.invoke(dict(command='document.validate',document=self.scene(source)));original=copy.deepcopy(d);before=self.planes(d,ink_bindings=self.bindings());changed_source=copy.deepcopy(source);changed_source['items'][-1]['content']['paint']['tint']=.125;obj=objects.retained(changed_source)
        caps=self.invoke(dict(command='capabilities'))['native_prepress']['ink_bindings'];self.assertEqual(caps['max_bindings'],1024)
        c=Client();c.initialize();self.addCleanup(c.close)
        with tempfile.TemporaryDirectory() as directory:
            s=dict(session_root=str(Path(directory)/'sessions'),session_id='native-bindings');c.success('session.create',**s,request_id='create',document=d);options={k:v for k,v in self.settings().items() if k!='spot_fallback'}
            self.assertEqual(c.success('document.prepress',document=d,options=options)['interleaved_sha256'],before['interleaved_sha256'])
            req=dict(request_id='edit',expected_revision=0,action=dict(type='edit',operations=[dict(op='object_replace',id='placed',object=obj)]));changed=c.success('session.apply',**s,**req)['document'];after=self.planes(changed,ink_bindings=self.bindings());self.assertNotEqual(after['interleaved_sha256'],before['interleaved_sha256'])
            output=dict(output_root=directory,file_name='shared.pdf',format='pdf',pdf_options=dict(prepress=self.settings()));c.success('session.publish',**s,expected_revision=1,output=output);raw=(Path(directory)/'shared.pdf').read_bytes()
            self.doCleanups();c=Client();c.initialize();self.addCleanup(c.close);undo=c.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.planes(undo,ink_bindings=self.bindings())['interleaved_sha256'],before['interleaved_sha256'])
            redo=c.success('session.apply',**s,request_id='redo',expected_revision=2,action=dict(type='redo'))['document'];self.assertEqual(self.planes(redo,ink_bindings=self.bindings())['interleaved_sha256'],after['interleaved_sha256']);self.assertTrue(c.success('session.apply',**s,**req)['replayed']);self.assertTrue(c.success('session.verify',**s)['valid']);self.assertEqual((Path(directory)/'shared.pdf').read_bytes(),raw);self.assertEqual(d,original)


if __name__=='__main__':unittest.main()
