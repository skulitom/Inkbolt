"""Independent pixel/grid oracles for immutable revision review."""
from contextlib import closing
import base64
import copy
import hashlib
import unittest
from external_workspace import files as workspace_files

import test_agent_workspace as workspace
from test_editing_cli import png_pixels
from test_render_quality_cli import rect, crop
from test_profiles_cli import embedded, linear_profile
from test_focused_previews import mapped
from test_hdr_cli import layer
from test_images_cli import png
from test_effects_coverage_cli import effect
from test_mcp import Client
from test_mcp_preview import restore


class VisualDiffTests(unittest.TestCase):
    setUp=workspace.AgentWorkspaceTests.setUp
    cli=workspace.AgentWorkspaceTests.cli
    save=workspace.AgentWorkspaceTests.save
    ref=workspace.AgentWorkspaceTests.ref

    def document(self,items=None,width=12,height=10,kind='vector'):
        d=self.cli('document.create',id='review-original',kind=kind,width=width,height=height)
        d['items']=items or []
        return self.cli('document.validate',document=d)

    def compare(self,a,b,**options):
        return self.cli('document.diff.preview',before=a,after=b,options=options)

    def files(self):
        return {str(p.relative_to(self.root)):(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()) for p in workspace_files(self.root) if p.is_file()}

    def pixels(self,result,key):
        artifact=result['artifacts'][key];data=base64.b64decode(artifact['data'])
        self.assertEqual(artifact['sha256'],hashlib.sha256(data).hexdigest())
        w,h,p,chunks=png_pixels(data)
        self.assertIn(b'sRGB',chunks);self.assertNotIn(b'iCCP',chunks)
        self.assertEqual((w,h),(result['width'],result['height']))
        return p

    def oracle(self,result,before,after,threshold=0):
        self.assertEqual(self.pixels(result,'before'),before)
        self.assertEqual(self.pixels(result,'after'),after)
        count=0;marked=0;mask=bytearray();changed=[];highlighted=[];maximum=0
        for n in range(len(before)//4):
            delta=max(abs(a-b) for a,b in zip(before[n*4:n*4+4],after[n*4:n*4+4]))
            maximum=max(maximum,delta)
            if delta:count+=1;changed.append((n%result['width'],n//result['width']))
            if delta>threshold:marked+=1;highlighted.append((n%result['width'],n//result['width']))
            mask.extend([255,0,255,255] if delta>threshold else [0]*4)
        def bounds(points):
            return [min(x for x,y in points),min(y for x,y in points),max(x for x,y in points)+1,max(y for x,y in points)+1] if points else None
        self.assertEqual(result['pixels'],dict(changed_pixels=count,changed_bounds=bounds(changed),highlighted_pixels=marked,highlighted_bounds=bounds(highlighted),maximum_channel_delta=maximum,threshold=threshold))
        self.assertEqual(self.pixels(result,'mask'),bytes(mask))

    def canvas(self,d,origin,size):
        return self.cli('document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='vector_canvas',action=dict(type='set',origin=origin,size=size,unit='px',process_space='rgb'))])['document']

    def test_exact_and_thresholded_delta_include_alpha(self):
        raw=bytes([40,80,120,255]*12)
        a=self.document([dict(id='pixels',content=dict(type='raster',width=4,height=3,rgba_hex=raw.hex()))],4,3,'raster')
        updated=bytearray(raw);updated[4]+=1;updated[8]+=17;updated[-1]-=3
        b=copy.deepcopy(a);b['items'][0]['content']['rgba_hex']=updated.hex()
        for threshold in [0,1,3,17,255]:
            r=self.compare(a,b,threshold=threshold)
            self.oracle(r,raw,bytes(updated),threshold)
            self.assertEqual(r['before']['comparison_mapping']['pixel_to_world'],[1,0,0,1,0,0])
            self.assertEqual(r['before']['changed_world_corners'],[[1,0],[4,0],[4,3],[1,3]])
            self.assertEqual(r['structural']['items'][0]['id'],'pixels')
        same=self.compare(a,a);self.oracle(same,raw,raw)
        self.assertIsNone(same['before']['changed_world_corners']);self.assertFalse(same['structural']['changed'])
        self.assertEqual(self.files(),{})

    def test_union_item_focus_preserves_old_and_new_locations_and_context(self):
        a=self.document([rect('moving',x=1,y=2,w=2,h=2),rect('removed',x=7,y=1,w=1,h=1),rect('context',x=4,y=2,w=1,h=1,color=[200,20,40,255])])
        b=copy.deepcopy(a);b['items'][0]['transform']=[1,0,0,1,5,0];b['items'].pop(1)
        b['items'].append(rect('added',x=3,y=4,w=1,h=1,color=[90,110,130,255]))
        r=self.compare(a,b,focus=dict(type='items',ids=['moving','removed','added'],margin=.5))
        self.assertEqual(r['requested_bounds'],[.5,.5,8.5,5.5]);self.assertEqual(r['actual_bounds'],[0,0,9,6])
        expected=[]
        for after in [False,True]:
            data=bytearray()
            for y in range(6):
                for x in range(9):
                    c=[0]*4
                    if (6 if after else 1)<=x<(8 if after else 3) and 2<=y<4:c=[30,100,210,255]
                    if not after and (x,y)==(7,1):c=[30,100,210,255]
                    if (x,y)==(4,2):c=[200,20,40,255]
                    if after and (x,y)==(3,4):c=[90,110,130,255]
                    data.extend(c)
            expected.append(bytes(data))
        self.oracle(r,*expected)
        self.assertEqual({i['id']:i['change'] for i in r['structural']['items']},{'moving':'changed','removed':'removed','added':'added','context':'changed'})
        self.assertEqual(next(i for i in r['structural']['items'] if i['id']=='context')['fields'],['derived.sibling_index'])
        hidden=copy.deepcopy(b);hidden['items'].append(rect('hidden',x=-2,y=-1,w=1,h=1,visible=False))
        r=self.compare(b,hidden,focus=dict(type='items',ids=['hidden','moving']))
        self.assertEqual(r['requested_bounds'],[-2,-1,8,4]);self.assertTrue(r['clipped_to_render'])
        self.assertEqual(r['pixels']['changed_pixels'],0);self.assertTrue(r['structural']['changed'])

    def test_resized_shifted_canvases_align_in_world_coordinates(self):
        original=self.document([rect(x=-10,y=-10,w=30,h=30,color=[40,90,130,255])])
        a=self.canvas(original,[.25,.5],[4,3]);b=self.canvas(original,[2.25,-.5],[3,4])
        for scale in [1,2,3]:
            r=self.compare(a,b,scale=scale)
            self.assertEqual(r['actual_bounds'],[.25,-.5,5.25,3.5])
            self.assertEqual((r['width'],r['height']),(5*scale,4*scale))
            expected=[]
            for bounds in [[.25,.5,4.25,3.5],[2.25,-.5,5.25,3.5]]:
                data=bytearray()
                for y in range(r['height']):
                    for x in range(r['width']):
                        wx=.25+(x+.5)/scale;wy=-.5+(y+.5)/scale
                        data.extend([40,90,130,255] if bounds[0]<=wx<bounds[2] and bounds[1]<=wy<bounds[3] else [0]*4)
                expected.append(bytes(data))
            self.oracle(r,*expected)
            for side in ['before','after']:
                m=r[side]['comparison_mapping'];self.assertEqual(m['pixel_to_world'],[1/scale,0,0,1/scale,.25,-.5])
                for point in [[0,0],[.5,.5],[r['width'],r['height']]]:
                    recovered=mapped(m['world_to_pixel'],mapped(m['pixel_to_world'],point))
                    for actual,want in zip(recovered,point):self.assertAlmostEqual(actual,want)
            region=self.compare(a,b,scale=scale,focus=dict(type='region',bounds=[1.25,.5,3.25,2.5]))
            self.oracle(region,*[crop(p,5*scale,scale,scale,2*scale,2*scale) for p in expected])

    def test_fractional_phase_is_explicit_and_compatible_scale_preserves_samples(self):
        d=self.document([rect(x=-4,y=-4,w=12,h=12)])
        a=self.canvas(d,[.25,.5],[3,2]);b=self.canvas(d,[.75,.5],[3,2])
        self.cli('document.diff.preview',before=a,after=b,error='INCOMPATIBLE_PIXEL_GRIDS')
        r=self.compare(a,b,scale=2,include_structural=False)
        self.assertIsNone(r['structural']);self.assertEqual(r['actual_bounds'],[.25,.5,3.75,2.5])
        self.oracle(r,bytes(([30,100,210,255]*6+[0]*4)*4),bytes(([0]*4+[30,100,210,255]*6)*4))

    def test_artboard_local_alignment_retains_distinct_world_maps(self):
        group=dict(id='parent',opacity=.2,transform=[0,1,-1,0,20,10],content=dict(type='group'))
        board=dict(id='board',parent='parent',transform=[2,0,0,3,0,0],content=dict(type='frame',frame=dict(role='artboard',width=4,height=3,background=[40,90,130,255],bleed=dict(left=1,right=1,top=1,bottom=1))))
        a=self.document([group,board],30,30);b=copy.deepcopy(a);b['items'][0]['transform']=[1,0,0,1,30,5]
        focus=dict(type='artboard',id='board',include_bleed=True)
        r=self.compare(a,b,focus=focus,scale=2)
        self.oracle(r,bytes([40,90,130,255]*12*10),bytes([40,90,130,255]*12*10))
        self.assertEqual(r['bounds_space'],'artboard_local');self.assertTrue(r['structural']['changed'])
        self.assertEqual(r['before']['comparison_mapping']['pixel_to_world'],[0,1,-1.5,0,23,8])
        self.assertEqual(r['after']['comparison_mapping']['pixel_to_world'],[1,0,0,1.5,28,2])
        b['items'][1]['content']['frame']['background']=[200,60,20,255]
        r=self.compare(a,b,focus=focus,scale=2)
        self.oracle(r,bytes([40,90,130,255]*12*10),bytes([200,60,20,255]*12*10))
        self.assertEqual(r['before']['changed_world_corners'],[[23,8],[23,20],[8,20],[8,8]])
        self.assertEqual(r['after']['changed_world_corners'],[[28,2],[40,2],[40,17],[28,17]])

    def test_output_profiles_are_reported_but_not_compared_as_display_bytes(self):
        a=self.document([rect(w=4,h=3,color=[100,150,200,173])],4,3)
        b=copy.deepcopy(a);b['output_profile']=embedded(linear_profile())
        r=self.compare(a,b);pixels=bytes([100,150,200,173]*12);self.oracle(r,pixels,pixels)
        self.assertIn('output_profile',[m['field'] for m in r['structural']['metadata']])
        self.assertEqual(r['after']['original_output_profile'],b['output_profile'])
        self.assertEqual(r['after']['document_sha256'],self.cli('document.preview',document=b)['document_sha256'])
        actual=png_pixels(base64.b64decode(self.cli('document.export',document=b,format='png')['data']))[2]
        self.assertNotEqual(actual,pixels)
        self.assertEqual(self.files(),{})

    def test_hdr_needs_explicit_per_side_views_and_preserves_source_samples(self):
        a=self.document([dict(id='source',content=dict(type='raster',width=1,height=1,rgba_hex='ff0000ff'))],1,1,'raster')
        b=copy.deepcopy(a);b['color_space']='linear_srgb';b['items']=[layer([2,0,0,1])]
        self.cli('document.diff.preview',before=a,after=b,error='HDR_VIEW_REQUIRED')
        before=copy.deepcopy(b)
        r=self.compare(a,b,after_render_options=dict(view=dict(tone_map='clip')))
        self.oracle(r,bytes([255,0,0,255]),bytes([255,0,0,255]))
        self.assertTrue(r['structural']['changed']);self.assertEqual(b,before)
        self.assertEqual(r['after']['full_render']['view']['tone_map'],'clip')

    def test_pinned_proposal_session_file_and_mcp_results_are_identical(self):
        a=self.document([rect(x=1,y=1,w=2,h=2)]);self.save(a)
        action=dict(type='edit',operations=[dict(op='transform',id='art',matrix=[1,0,0,1,3,1],space='world')])
        initial=self.files()
        proposal=self.cli('session.dry_run',session_id='work',request_id='move',expected_revision=0,action=action,options=dict(include_document=True))
        expected=self.compare(self.ref(),proposal['proposed_document']);self.assertEqual(self.files(),initial)
        self.cli('session.apply_proposal',proposal=proposal['proposal'],action=action)
        self.assertEqual(self.compare(self.ref(),self.ref(1)),expected)
        self.cli('session.apply',session_id='work',request_id='later',expected_revision=1,action=dict(type='edit',operations=[dict(op='properties',id='art',opacity=.5)]))
        session=self.cli('session.diff.preview',session_id='work',from_revision=0,to_revision=1)
        self.assertEqual(session,dict(expected,session_id='work',observed_current_revision=2))
        receipt=self.cli('document.publish',document=self.ref(1),output=dict(file_name='pinned.json',format='snapshot'))
        reference=dict(file_path='pinned.json',sha256=receipt['sha256']);before=self.files()
        self.assertEqual(self.compare(self.ref(),reference),expected)
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize()
            presented=c.tool('session.diff.preview',session_id='work',from_revision=0,to_revision=1,response_format='preview')
            self.assertEqual(restore(presented),dict(ok=True,result=session));self.assertEqual(len(presented['content']),4)
            presented=c.tool('run',command='document.diff.preview',arguments=dict(before=self.ref(),after=reference),response_format='preview')
            self.assertEqual(restore(presented),dict(ok=True,result=expected))
            same=c.tool('session.diff.preview',session_id='work',from_revision=0,to_revision=0,response_format='preview')
            self.assertEqual(len(same['content']),3) # shared before/after payload plus mask
            self.assertEqual(restore(same)['result']['pixels']['changed_pixels'],0)
        self.assertEqual(self.files(),before)

    def test_limits_and_errors_never_change_sources(self):
        a=self.document([rect()]);self.save(a);before=self.files()
        bad=[(dict(type='items',ids=[]),'INVALID_REQUEST'),(dict(type='items',ids=['art','art']),'INVALID_REQUEST'),(dict(type='items',ids=['absent']),'NOT_FOUND'),(dict(type='items',ids=['art'],margin=-1),'INVALID_REQUEST'),(dict(type='region',bounds=[0,0,0,1]),'EMPTY_PREVIEW'),(dict(type='region',bounds=[20,20,21,21]),'FOCUS_OUTSIDE_CANVAS')]
        for focus,error in bad:self.cli('document.diff.preview',before=self.ref(),after=self.ref(),options=dict(focus=focus),error=error)
        self.cli('document.diff.preview',before=a,after=a,options=dict(threshold=256),error='INVALID_REQUEST')
        self.cli('session.diff.preview',session_id='work',from_revision=0,to_revision=0,control=dict(timeout_ms=0),error='TIMEOUT')
        self.assertEqual(self.files(),before)
        (self.root/'cancel').write_text('stop');before=self.files()
        for command in ['document.diff','document.diff.preview']:
            self.cli(command,before=a,after=a,control=dict(cancel_file='cancel'),error='CANCELLED')
        self.assertEqual(self.files(),before)
        large=self.document(width=1025,height=1024)
        self.cli('document.diff.preview',before=large,after=large,options=dict(focus=dict(type='region',bounds=[0,0,1,1])),error='RESOURCE_LIMIT')
        # Individual renders fit, but their common union does not; a focused crop does.
        a=self.canvas(self.document(width=1,height=1),[-1000,-1000],[1,1]);b=self.canvas(a,[1000,1000],[1,1])
        self.cli('document.diff.preview',before=a,after=b,error='RESOURCE_LIMIT')
        r=self.compare(a,b,focus=dict(type='region',bounds=[-1000,-1000,-999,-999]))
        self.oracle(r,bytes(4),bytes(4))

    def test_each_revision_resolves_its_pinned_resource_bindings(self):
        pixels=bytes([21,61,141,255]*4);source=self.root/'source.png';source.write_bytes(png(2,2,pixels))
        asset=self.cli('asset.import',source_path='source.png',store_root='first')['asset']
        self.cli('asset.import',source_path='source.png',store_root='second')
        a=self.document(width=2,height=2);a['assets']={'source':asset};a['items']=[dict(id='image',content=dict(type='image',asset_id='source',width=2,height=2))]
        self.save(a,resources=dict(asset_root='first',font_root=None))
        self.cli('session.apply',session_id='work',request_id='bind',expected_revision=0,action=dict(type='resources',resources=dict(asset_root='second',font_root=None)))
        before=self.files();r=self.compare(self.ref(),self.ref(1));self.oracle(r,pixels,pixels)
        self.assertTrue(r['structural']['resource_bindings_changed'])
        session=self.cli('session.diff.preview',session_id='work',from_revision=0,to_revision=1)
        self.assertEqual(session,dict(r,session_id='work',observed_current_revision=1))
        self.cli('document.diff.preview',before=self.ref(),after=self.ref(1),after_resources=dict(asset_root='missing'),error='ASSET_MISSING')
        self.cli('document.diff.preview',before=self.ref(),after=self.ref(1),before_resources=dict(asset_root=None),error='ASSET_ROOT_REQUIRED')
        self.assertEqual(self.files(),before)

    def test_crop_preserves_complete_effects_and_distinct_render_settings(self):
        a=self.document([rect(x=2,y=2,w=3,h=3,effects=[effect('shadow','shadow',[200,40,10,173],sigma=.75,offset=[2.5,1.25])])])
        b=copy.deepcopy(a);b['items'][0]['content']['fill']=[190,20,40,255]
        qa=dict(padding=2,crop_to_canvas=False,antialias='supersample2')
        qb=dict(padding=1,crop_to_canvas=False,antialias='coverage')
        r=self.compare(a,b,focus=dict(type='region',bounds=[1.2,1.2,7.6,7.6]),before_render_options=qa,after_render_options=qb)
        self.assertEqual(r['actual_bounds'],[1,1,8,8])
        expected=[]
        for d,q in [(a,qa),(b,qb)]:
            artifact=self.cli('document.export',document=d,format='png',render_options=q)
            w,h,p,_=png_pixels(base64.b64decode(artifact['data']));start=1+q['padding']
            expected.append(crop(p,w,start,start,7,7))
        self.oracle(r,*expected)
        self.assertEqual(r['before']['full_render']['antialias'],'supersample2')
        self.assertEqual(r['after']['full_render']['padding'],1)


if __name__=='__main__':unittest.main()
