"""Independent coordinate/pixel checks and source-preserving review workflows."""
from contextlib import closing
import base64
import copy
import hashlib
import itertools
import math
import unittest

import test_agent_workspace as workspace
from test_mcp import Client
from test_mcp_preview import restore
from test_editing_cli import png_pixels
from test_render_quality_cli import rect, crop
from test_effects_coverage_cli import effect
from test_profiles_cli import embedded, linear_profile, png_profile


def mapped(m, p):
    return [m[0]*p[0]+m[2]*p[1]+m[4], m[1]*p[0]+m[3]*p[1]+m[5]]


class FocusedPreviewTests(unittest.TestCase):
    setUp=workspace.AgentWorkspaceTests.setUp
    cli=workspace.AgentWorkspaceTests.cli
    save=workspace.AgentWorkspaceTests.save
    ref=workspace.AgentWorkspaceTests.ref

    def document(self,items=None,width=12,height=10):
        d=self.cli('document.create',id='focus-original',kind='vector',width=width,height=height)
        d['items']=items or []
        return self.cli('document.validate',document=d)

    def view(self,d,focus=None,scale=1,render_options=None,**kw):
        return self.cli('document.preview',document=d,options=dict(focus=focus or dict(type='canvas'),scale=scale,render_options=render_options or {}),**kw)

    def pixels(self,view):
        return png_pixels(base64.b64decode(view['artifact']['data']))[:3]

    def files(self):
        return {str(p.relative_to(self.root)):(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()) for p in self.root.rglob('*') if p.is_file()}

    def test_region_preserves_full_scene_filters_and_exact_grid(self):
        d=self.document([rect(x=-1,y=1,w=8,h=7,color=[30,100,210,128],effects=[effect('shadow','shadow',[200,40,10,173],sigma=.75,offset=[2.5,1.25])]),rect('foreground',x=4,y=3,w=3,h=2,color=[240,20,10,255])])
        before=copy.deepcopy(d)
        for scale,aa,keep in itertools.product([1,2],['none','coverage','supersample2'],[False,True]):
            quality=dict(antialias=aa,padding=2,crop_to_canvas=not keep)
            full=self.cli('document.export',document=d,format='png',scale=scale,render_options=quality)
            fw,fh,raw,_=png_pixels(base64.b64decode(full['data']))
            result=self.view(d,dict(type='region',bounds=[2.2,1.8,9.3,7.6]),scale,quality)
            pad=2 if keep else 0
            x,y=math.floor((2.2+pad)*scale),math.floor((1.8+pad)*scale)
            right,bottom=math.ceil((9.3+pad)*scale),math.ceil((7.6+pad)*scale)
            self.assertEqual(result['crop_pixels'],[x,y,right,bottom])
            w,h,p=self.pixels(result);self.assertEqual((w,h),(right-x,bottom-y))
            self.assertEqual(p,crop(raw,fw,x,y,w,h))
            origin=[x/scale-pad,y/scale-pad]
            self.assertEqual(result['actual_bounds'],origin+[right/scale-pad,bottom/scale-pad])
            self.assertEqual(result['mapping']['pixel_to_world'],[1/scale,0,0,1/scale,*origin])
            self.assertEqual(result['mapping']['world_to_pixel'],[scale,0,0,scale,-origin[0]*scale,-origin[1]*scale])
            self.assertEqual(result['full_render']['output_dimensions'],[fw,fh])
            self.assertFalse(result['clipped_to_render'])
        self.assertEqual(d,before);self.assertEqual(self.files(),{})

    def test_items_keep_context_and_geometry_contract_with_clipping(self):
        d=self.document([rect('target',x=2,y=3,w=3,h=2),rect('overlay',x=3,y=3,w=1,h=1,color=[200,20,40,255]),rect('hidden',x=-2,y=-1,w=1,h=1,visible=False)])
        r=self.view(d,dict(type='items',ids=['target'],margin=.5),scale=2)
        self.assertEqual(r['requested_bounds'],[1.5,2.5,5.5,5.5]);self.assertEqual(r['actual_bounds'],r['requested_bounds'])
        w,h,p=self.pixels(r);self.assertEqual((w,h),(8,6))
        for y in range(h):
            for x in range(w):
                wx,wy=1.5+(x+.5)/2,2.5+(y+.5)/2
                color=[200,20,40,255] if 3<=wx<4 and 3<=wy<4 else [30,100,210,255] if 2<=wx<5 and 3<=wy<5 else [0]*4
                self.assertEqual(list(p[(y*w+x)*4:(y*w+x+1)*4]),color)
        r=self.view(d,dict(type='items',ids=['target','hidden'],margin=0))
        self.assertEqual(r['requested_bounds'],[-2,-1,5,5]);self.assertEqual(r['actual_bounds'],[0,0,5,5]);self.assertTrue(r['clipped_to_render'])
        self.assertEqual(self.view(d)['document_sha256'],r['document_sha256'])

    def test_fractional_origin_pixel_centers_and_edge_coverage(self):
        d=self.document([rect(x=-10,y=-10,w=20,h=20,color=[48,112,192,255])])
        d=self.cli('document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='vector_canvas',action=dict(type='set',origin=[-2.25,1.5],size=[5.25,3.5],unit='px',process_space='rgb'))])['document']
        for scale in [1,2,3,4]:
            r=self.view(d,dict(type='region',bounds=[-2.1,1.6,4,6]),scale)
            w,h,p=self.pixels(r);self.assertEqual((w,h),(math.ceil(5.25*scale),math.ceil(3.5*scale)))
            self.assertEqual(r['mapping']['pixel_to_world'],[1/scale,0,0,1/scale,-2.25,1.5]);self.assertTrue(r['clipped_to_render'])
            for y in range(h):
                for x in range(w):
                    alpha=round(255*max(0,min(1,5.25*scale-x))*max(0,min(1,3.5*scale-y)))
                    actual=p[(y*w+x)*4:(y*w+x+1)*4]
                    self.assertEqual(list(actual[:3]),[48,112,192]);self.assertLessEqual(abs(actual[3]-alpha),1)
            point=mapped(r['mapping']['pixel_to_world'],[.5,.5]);self.assertEqual(point,[-2.25+.5/scale,1.5+.5/scale])

    def test_standalone_artboard_nested_transform_bleed_and_fractional_extent(self):
        # world: (x,y) -> (20-3*y,10+2*x), independent of ancestor opacity.
        group=dict(id='parent',opacity=.2,transform=[0,1,-1,0,20,10],content=dict(type='group'))
        board=dict(id='board',parent='parent',transform=[2,0,0,3,0,0],content=dict(type='frame',frame=dict(role='artboard',width=5,height=4,logical_size=[4.25,3.5],bleed=dict(left=1,right=2,top=2,bottom=1),background=[40,80,120,255])))
        d=self.document([group,board],width=30,height=30);before=copy.deepcopy(d)
        for bleed,scale,keep in itertools.product([False,True],[1,2],[False,True]):
            q=dict(padding=1,crop_to_canvas=not keep)
            r=self.view(d,dict(type='artboard',id='board',include_bleed=bleed),scale,q)
            ordinary=self.cli('artboard.export',document=d,selection=dict(type='ids',ids=['board']),format='png',scale=scale,include_bleed=bleed,render_options=q)
            self.assertEqual(r['artifact']['data'],ordinary['artifacts'][0]['artifact']['data'])
            self.assertEqual(r['composition'],'standalone_artboard')
            local=[(-1 if bleed else 0)-(1 if keep else 0),(-2 if bleed else 0)-(1 if keep else 0)]
            w,h,p=self.pixels(r)
            expected=[0,2/scale,-3/scale,0,20-3*local[1],10+2*local[0]]
            self.assertEqual(r['mapping']['pixel_to_world'],expected)
            for point in [[0,0],[w,h],[.5,.5],[w/2,h/2]]:
                world=mapped(expected,point);recovered=mapped(r['mapping']['world_to_pixel'],world)
                for a,b in zip(point,recovered):self.assertAlmostEqual(a,b)
            if not keep:self.assertEqual(list(p[:4]),[40,80,120,255]) # no ancestor attenuation
        self.assertEqual(d,before)

    def test_output_profile_and_reviewed_proposal_are_preserved(self):
        d=self.document([rect(w=12,h=10,color=[100,150,200,173])]);profile=linear_profile();d['output_profile']=embedded(profile)
        self.save(d);before=self.files()
        old=self.view(self.ref(),dict(type='region',bounds=[2,2,4,4]))
        self.assertEqual(png_profile(base64.b64decode(old['artifact']['data'])),profile)
        full=self.cli('document.export',document=self.ref(),format='png')
        self.assertEqual(self.pixels(old)[2],crop(png_pixels(base64.b64decode(full['data']))[2],12,2,2,2,2))
        action=dict(type='edit',operations=[dict(op='transform',id='art',matrix=[1,0,0,1,3,0],space='world')])
        proposed=self.cli('session.dry_run',session_id='work',request_id='review',expected_revision=0,action=action,options=dict(include_document=True))
        view=self.view(proposed['proposed_document'],dict(type='region',bounds=[0,0,5,5]))
        self.assertEqual(self.files(),before)
        self.cli('session.apply_proposal',proposal=proposed['proposal'],action=action)
        self.assertEqual(self.view(self.ref(1),dict(type='region',bounds=[0,0,5,5])),view)
        self.assertEqual(self.view(self.ref(),dict(type='region',bounds=[2,2,4,4])),old)
        before=self.files()
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize()
            actual=c.tool('document.preview',document=self.ref(),options=dict(focus=dict(type='region',bounds=[2,2,4,4])),response_format='preview')
            self.assertEqual(restore(actual),dict(ok=True,result=old));self.assertEqual(len(actual['content']),2)
        self.assertEqual(self.files(),before)

    def test_explicit_errors_and_full_evaluation_limits(self):
        d=self.document([rect()])
        for focus,error in [(dict(type='region',bounds=[0,0,0,1]),'EMPTY_PREVIEW'),(dict(type='region',bounds=[20,20,21,21]),'FOCUS_OUTSIDE_CANVAS'),(dict(type='items',ids=[]),'INVALID_OPERATION'),(dict(type='items',ids=['art','art']),'INVALID_OPERATION'),(dict(type='items',ids=['missing']),'NOT_FOUND'),(dict(type='items',ids=['art'],margin=-1),'INVALID_REQUEST'),(dict(type='artboard',id='art'),'INVALID_OPERATION')]:
            self.view(d,focus,error=error)
        self.view(d,scale=5,error='INVALID_REQUEST')
        self.view(d,control=dict(timeout_ms=0),error='TIMEOUT')
        self.view(self.document(width=2000,height=1000),dict(type='region',bounds=[0,0,1,1]),error='RESOURCE_LIMIT')
        marker=self.root/'cancel';marker.write_text('stop')
        before=self.files();self.view(d,control=dict(cancel_file='cancel'),error='CANCELLED');self.assertEqual(self.files(),before)

    def test_contact_sheet_exact_sampling_placement_and_bidirectional_maps(self):
        color=lambda x,y:[(x*31+y*13)%256,(x*17+y*29)%256,(x*11+y*43)%256,255]
        d=self.document([rect(f'p{x}-{y}',x=x,y=y,w=1,h=1,color=color(x,y)) for y in range(7) for x in range(11)],width=11,height=7)
        views=[dict(focus=dict(type='canvas')),dict(focus=dict(type='region',bounds=[1,1,5,4])),dict(focus=dict(type='canvas'),scale=2)]
        options=dict(views=views,columns=2,cell_size=[7,5],gap=2)
        result=self.cli('document.contact_sheet',document=d,options=options)
        w,h,p=self.pixels(result);self.assertEqual((w,h),(16,12));expected=bytearray(w*h*4)
        origins=[(0,0),(9,0),(0,7)]
        for i,(sw,sh,tw,th,scale,ox,oy) in enumerate([(11,7,7,4,1,0,0),(4,3,4,3,1,1,1),(22,14,7,4,2,0,0)]):
            left,top=origins[i][0]+(7-tw)//2,origins[i][1]+(5-th)//2
            entry=result['views'][i];self.assertEqual(entry['image_bounds'],[left,top,left+tw,top+th])
            self.assertNotIn('data',entry['preview']['source_artifact'])
            source=self.view(d,views[i]['focus'],views[i].get('scale',1))
            self.assertEqual(hashlib.sha256(base64.b64decode(source['artifact']['data'])).hexdigest(),entry['preview']['source_artifact']['sha256'])
            for y in range(th):
                for x in range(tw):
                    sx=(2*x+1)*sw//(2*tw);sy=(2*y+1)*sh//(2*th)
                    off=((top+y)*w+left+x)*4;expected[off:off+4]=bytes(color(sx//scale+ox,sy//scale+oy))
            for point in [[left,top],[left+tw,top+th],[left+.5,top+.5]]:
                world=mapped(entry['sheet_to_world'],point)
                analytic=[ox+(point[0]-left)*sw/tw/scale,oy+(point[1]-top)*sh/th/scale]
                for a,b in zip(world,analytic):self.assertAlmostEqual(a,b)
                for a,b in zip(mapped(entry['world_to_sheet'],world),point):self.assertAlmostEqual(a,b)
        self.assertEqual(p,bytes(expected));self.assertEqual(result['evaluation_pixels'],11*7*6)
        self.assertEqual(self.files(),{})
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize()
            response=c.tool('run',command='document.contact_sheet',arguments=dict(document=d,options=options),response_format='preview')
            self.assertEqual(restore(response),dict(ok=True,result=result));self.assertEqual(len(response['content']),2)

    def test_contact_sheet_profiles_partial_alpha_and_mixed_artboard_views(self):
        board=dict(id='board',transform=[0,1,-1,0,8,2],content=dict(type='frame',frame=dict(role='artboard',width=5,height=3,background=[80,130,190,128])))
        d=self.document([board]);profile=linear_profile();d['output_profile']=embedded(profile)
        options=dict(views=[dict(focus=dict(type='canvas')),dict(focus=dict(type='artboard',id='board'))],columns=2,cell_size=[12,10],gap=1)
        sheet=self.cli('document.contact_sheet',document=d,options=options)
        self.assertEqual(png_profile(base64.b64decode(sheet['artifact']['data'])),profile)
        w,h,p=self.pixels(sheet)
        for entry,options in zip(sheet['views'],options['views']):
            source=self.view(d,options['focus']);sw,sh,raw=self.pixels(source)
            left,top,right,bottom=entry['image_bounds'];self.assertEqual((right-left,bottom-top),(sw,sh))
            self.assertEqual(crop(p,w,left,top,sw,sh),raw)
        self.assertIn(128,p[3::4]);self.assertEqual(self.files(),{})

    def test_contact_sheet_limits_reject_before_view_resource_reads(self):
        d=self.document(width=1024,height=1024)
        # A missing external font would fail if any view were rendered before aggregate admission.
        d['fonts']={'missing':dict(sha256='a'*64,license_sha256='b'*64,face_index=0,bytes=100)}
        d['items']=[dict(id='label',content=dict(type='text',frame=dict(text='A',width=10,height=10,style=dict(font_id='missing',size=8,fill=[0,0,0,255]))))]
        self.cli('document.contact_sheet',document=d,options=dict(views=[{}]*5),error='RESOURCE_LIMIT')
        small=self.document()
        for options in [dict(views=[]),dict(views=[{}]*17),dict(views=[{}],columns=0),dict(views=[{}],columns=9),dict(views=[{}],cell_size=[0,5]),dict(views=[{}],cell_size=[5,513]),dict(views=[{}],gap=65)]:
            self.cli('document.contact_sheet',document=small,options=options,error='INVALID_REQUEST')
        self.cli('document.contact_sheet',document=small,options=dict(views=[{}]*16,cell_size=[512,512],gap=1),error='RESOURCE_LIMIT')
        self.cli('document.contact_sheet',document=small,options=dict(views=[{}]),control=dict(timeout_ms=0),error='TIMEOUT')
        self.assertEqual(self.files(),{})


if __name__=='__main__':unittest.main()
