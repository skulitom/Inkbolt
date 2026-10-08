"""Independent coverage probabilities, scalar mask equations and native ink transport."""
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
import test_editing_cli as editing
from cmyk_fixtures import cmyk_profile
from test_profiles_cli import embedded
from test_vector_plates_cli import rect, named, color, spot
from test_native_images_cli import fill, raster, process
from test_native_print_cli import page_image
from test_artwork_masks_cli import source, group, rect as mask_rect
from test_layer_clipping_cli import premul, over
from test_samples_cli import layer
from test_masks_cli import inverse
from test_mcp import Client


def mask(**kw):
    result=dict(source='source',region=[0,0,12,8]);result.update(kw);return result


def enumerate_clip(back, base, top, base_address, top_address, probabilities, isolated=False):
    """Sum discrete coverage states; no premultiplied transfer implementation."""
    out=[F(0)]*len(back)
    for flags in itertools.product((False,True),repeat=len(probabilities)):
        weight=F(1)
        for active,p in zip(flags,probabilities):weight*=p if active else 1-p
        b,t,base_control,outer_control=flags
        result=list(back)
        if b and base_control and outer_control:
            if isolated:result=[F(0)]*len(back)
            for c,address in enumerate(base_address):
                if address:result[c]=base[c]
            if t:
                for c,address in enumerate(top_address):
                    if address:result[c]=top[c]
        for c,value in enumerate(result):out[c]+=weight*value
    return out


class NativeCoverageTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def document(self,w=8,h=4,kind='raster'):
        d=self.invoke(dict(command='document.create',id='native-coverage',kind=kind,width=w,height=h))
        d['swatches']=dict(b=color([.5,.25,.125,0]),s=spot())
        return d
    def planes(self,d,expected=0,**kw):
        options=dict(profile=embedded(cmyk_profile()),antialias='none');options.update(kw)
        return self.invoke(dict(command='document.prepress',document=d,options=options),expected)
    def values(self,d,points=None,**kw):
        points=points or [[x,y] for y in range(d['height']) for x in range(d['width'])]
        return [s['ink_fractions'] for s in self.planes(d,samples=points,**kw)['samples']]
    def assertValues(self,actual,expected,tolerance=2e-12):
        for a,b in zip(actual,expected,strict=True):self.assertAlmostEqual(a,float(b),delta=tolerance)
    def edit(self,d,ops):return self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops))['document']
    def export(self,d,**kw):return self.invoke(dict(command='document.export',document=d,format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()),antialias='none',spot_fallback='multiplicative_declared'),**kw)))

    def test_shared_alpha_luminance_overlap_keeps_inks_and_float_mask_precision(self):
        colors=[[200,40,90,83],[30,180,220,137]]
        for mode,isolated in itertools.product(['alpha','luminance'],[False,True]):
            d=self.document(8,4,kind='vector')
            d['items']=[source(opacity=.6),mask_rect('left',w=6,h=4,color=colors[0],parent='source'),mask_rect('right',x=2,w=6,h=4,color=colors[1],parent='source',opacity=.4),rect('back',named('b'),box=(0,0,8,4)),group('outer',opacity=.7),rect('ink',named('s',tint=.75,overprint='preserve'),box=(0,0,8,4),parent='outer',artwork_mask=mask(mode=mode,region=[0,0,8,4]))]
            d['items'][4]['content']['isolated']=isolated;original=copy.deepcopy(d)
            actual=self.values(d)
            for i,p in enumerate(actual):
                x=i%8;q=premul(colors[0]) if x<6 else [F(0)]*4
                if x>=2:q=over(q,premul(colors[1]),F(2,5))
                m=(q[3] if mode=='alpha' else sum(q[c]*v for c,v in enumerate([F(2125,10000),F(7154,10000),F(721,10000)])))*F(3,5)*F(7,10)
                self.assertValues(p,[v*(1-m if isolated else 1) for v in [F(1,2),F(1,4),F(1,8),F(0)]]+[F(3,4)*m])
            r=self.planes(d);self.assertEqual([p['id'] for p in r['plates'][4:]],['s']);self.assertEqual(len(r['coverage_sources']['artwork_masks']),1);self.assertEqual(d,original)

    def test_mask_gradient_nested_clips_and_supersampling_match_point_equations(self):
        gradient=dict(type='linear',start=[0,0],end=[8,0],stops=[dict(offset=0,color=[255,0,0,0]),dict(offset=1,color=[255,0,0,255])])
        clip=lambda x,w:dict(geometry=dict(shape='rect',x=x,y=0,width=w,height=4))
        d=self.document();d['items']=[source(clip=clip(1,6)),group('mask-group',parent='source',opacity=.5),mask_rect('r',w=8,h=4,parent='mask-group',color=gradient),fill('ink',named('s',tint=.5),artwork_mask=mask(mode='luminance',region=[0,0,8,4]),clip=clip(2,4))]
        for aa in ['none','coverage','supersample2','supersample4']:
            for i,p in enumerate(self.values(d,antialias=aa)):
                x=i%8;m=F(2125,10000)*F(1,2)*F(2*x+1,16) if 2<=x<6 else 0
                self.assertValues(p,[0,0,0,0,F(1,2)*m],1e-9)
        d['items'][-1]['artwork_mask']['region']=[0,0,0,4]
        self.assertTrue(all(v==0 for p in self.values(d) for v in p))
        d['items'][-1]['artwork_mask']['clip_region']=False
        self.assertGreater(self.values(d)[3][4],0)

    def test_linked_unlinked_source_and_region_transforms_are_independent_of_owner(self):
        for linked in [False,True]:
            d=self.document(8,8,kind='vector');owner=[0,1,-1,0,8,0];mt=[1,0,0,1,1,0];st=[1,0,0,1,0,1];rt=[1,0,0,1,1,0]
            d['items']=[source(transform=st),mask_rect('m',w=4,h=3,parent='source'),rect('ink',named('s',tint=.5),box=(0,0,8,8),transform=owner,artwork_mask=mask(region=[0,0,2,8],transform=mt,region_transform=rt,linked=linked))]
            for i,p in enumerate(self.values(d)):
                point=[i%8+.5,i//8+.5];q=inverse(owner,point) if linked else point;q=inverse(mt,q);local=inverse(st,q);region=inverse(rt,q)
                visible=0<=local[0]<4 and 0<=local[1]<3 and 0<=region[0]<2 and 0<=region[1]<8
                self.assertValues(p,[0,0,0,0,.5 if visible else 0])

    def test_clipped_layer_alpha_masks_and_base_controls_match_discrete_states(self):
        d=self.document(4,1);back=[F(1,8),F(1,4),F(3,8),F(1,16),F(0)];base=[F(1,2),F(1,4),F(1,8),F(0),F(0)];top=[F(1,4),F(3,4),F(1,2),F(1,8),F(0)]
        d['swatches']['back']=color([float(v) for v in back[:4]]);d['swatches']['top']=color([float(v) for v in top[:4]])
        bm=[0,64,128,255];tm=[255,128,192,64]
        d['items']=[fill('back',named('back'),box=(0,0,4,1)),fill('base',named('b',opacity=.5),box=(0,0,4,1),opacity=.5,fill_opacity=.75,mask=dict(width=4,height=1,gray_hex=bytes(bm).hex())),fill('clip',named('top',opacity=.75),box=(0,0,4,1),clip_to='base',opacity=.5,mask=dict(width=4,height=1,gray_hex=bytes(tm).hex()))]
        for i,p in enumerate(self.values(d)):
            expected=enumerate_clip(back,base,top,[True]*5,[True]*5,[F(1,2),F(3,4)*F(1,2)*F(tm[i],255),F(1,2)*F(3,4)*F(bm[i],255),F(1)])
            self.assertValues(p,expected[:4])
        d['items'][1]['visible']=False
        for p in self.values(d):self.assertValues(p,back[:4])

    def test_native_overprint_and_clipping_keep_per_ink_retention_separate_from_alpha(self):
        back=[F(1,8),F(1,4),F(3,8),F(1,16),F(1,2)]
        base=[F(1,2),F(0),F(1,4),F(0),F(0)];top=[F(0),F(0),F(0),F(0),F(3,4)]
        for bm,tm,isolated in itertools.product(['knockout','preserve','preserve_nonzero'],['knockout','preserve','preserve_nonzero'],[False,True]):
            d=self.document(1,1);d['swatches']['b']=color([float(v) for v in base[:4]]);d['swatches']['back']=color([float(v) for v in back[:4]])
            d['items']=[fill('back',named('back'),box=(0,0,1,1)),fill('spotback',named('s',tint=.5,overprint='preserve'),box=(0,0,1,1)),dict(id='g',opacity=.75,content=dict(type='group',isolated=isolated)),fill('base',named('b',opacity=.5,overprint=bm),box=(0,0,1,1),parent='g',opacity=.5),fill('clip',named('s',tint=.75,opacity=.75,overprint=tm),box=(0,0,1,1),parent='g',clip_to='base')]
            ba=[True]*5 if bm=='knockout' else [(bm!='preserve_nonzero' or base[c]!=0) if c<4 else False for c in range(5)]
            ta=[True]*5 if tm=='knockout' else [False]*4+[True]
            expected=enumerate_clip(back,base,top,ba,ta,[F(1,2),F(3,4),F(1,2),F(3,4)],isolated)
            self.assertValues(self.values(d)[0],expected)

    def test_clipped_group_unions_and_stacked_sources_preserve_base_coverage(self):
        d=self.document(4,1);d['swatches']['zero']=color([0,0,0,0]);d['items']=[group('base',opacity=.5),fill('left',named('zero',opacity=.5),box=(0,0,3,1),parent='base'),fill('right',named('zero',opacity=.25),box=(1,0,3,1),parent='base'),group('clip',clip_to='base',opacity=.5),fill('top',named('s',tint=.75,overprint='preserve',opacity=.5),box=(0,0,4,1),parent='clip'),fill('again',named('b',opacity=.25,overprint='preserve'),box=(0,0,4,1),clip_to='base')]
        for p,alpha in zip(self.values(d),[F(1,2),F(5,8),F(5,8),F(1,4)]):
            self.assertValues(p,[F(1,2)*F(1,4)*alpha*F(1,2),F(1,4)*F(1,4)*alpha*F(1,2),F(1,8)*F(1,4)*alpha*F(1,2),0,F(3,4)*F(1,2)*F(1,2)*alpha*F(1,2)])

    def test_opaque_background_clipping_covers_matte_outside_source_and_matches_layer_conversion(self):
        d=self.document(8,1);d['items']=[raster([[20,70,210,128]]*2,2,opacity=.5,transform=[1,0,0,1,3,0]),fill('clip',named('s',tint=.75,opacity=.5,overprint='preserve'),box=(0,0,8,1),clip_to='pixels')];d['background']=dict(item_id='pixels',matte=[230,190,140]);before=copy.deepcopy(d)
        matte=process([v/255 for v in d['background']['matte']]);paint=process([20/255,70/255,210/255])
        for i,p in enumerate(self.values(d)):
            a=F(128,255)*F(1,2) if 3<=i<5 else 0
            self.assertValues(p,[float(a)*s+(1-float(a))*b for s,b in zip(paint,matte)]+[.375],.00001)
        converted=self.edit(d,[dict(op='background',id='pixels',action=dict(type='to_layer',source_id='retained',matte_id='matte'))])
        self.assertEqual(self.planes(converted)['interleaved_sha256'],self.planes(d)['interleaved_sha256']);self.assertEqual(d,before)

    def test_shared_masks_on_base_and_clipped_source_apply_in_their_own_order(self):
        d=self.document(4,1);d['items']=[source(opacity=.5),mask_rect('m',w=4,h=1,parent='source',color=[255,0,0,128]),fill('base',named('b',opacity=.5),box=(0,0,4,1),artwork_mask=mask(region=[0,0,4,1])),fill('clip',named('s',tint=.75,opacity=.5),box=(0,0,4,1),clip_to='base',artwork_mask=mask(region=[0,0,4,1],mode='luminance'))]
        mask_alpha=F(1,2)*F(128,255);clip_alpha=F(1,2)*mask_alpha*F(2125,10000)
        for p in self.values(d):self.assertValues(p,[v*F(1,2)*(1-clip_alpha)*mask_alpha for v in [F(1,2),F(1,4),F(1,8),0]]+[F(3,4)*clip_alpha*F(1,2)*mask_alpha])

    def test_component_mask_artboards_bleed_exact_pdf_transport_and_source_receipts(self):
        d=self.document(40,30,kind='vector');d['items']=[source(),mask_rect('m',w=4,h=6,parent='source'),dict(id='master',content=dict(type='component_source')),rect('ink',named('s',tint=.5),box=(0,0,8,6),parent='master',artwork_mask=mask(region=[0,0,8,6])),dict(id='board',transform=[1,0,0,1,10,10],content=dict(type='frame',frame=dict(role='artboard',width=6,height=4,bleed=dict(left=1,right=3,top=2,bottom=4)))),dict(id='placed',parent='board',transform=[1,0,0,1,-1,-2],content=dict(type='instance',instance=dict(source='master')))]
        before=copy.deepcopy(d)
        for bleed in [False,True]:
            planes=self.planes(d,artboard_id='board',include_bleed=bleed);artifact=self.export(d,artboards=dict(type='ids',ids=['board']),include_bleed=bleed);pdf=pdf_reader.Pdf(artifact);image,raw=page_image(pdf)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),planes['interleaved_sha256']);self.assertEqual(artifact['pages'][0]['coverage_sources'],planes['coverage_sources'])
            w,h=(10,10) if bleed else (6,4);expected=bytes(v for y in range(h) for x in range(w) for v in [0,0,0,0,128 if (x<4 and y<6 if bleed else x<3) else 0])
            self.assertEqual(raw,expected);self.assertEqual((image['Width'],image['Height']),(w,h))
        self.assertEqual(d,before)

    def test_coverage_limits_unsupported_mask_semantics_and_cancellation_are_explicit(self):
        d=self.document(512,512,kind='vector');d['items']=[source(),mask_rect('m',w=512,h=512,parent='source')]+[rect(f'p{i}',named('s'),box=(0,0,512,512),artwork_mask=mask(region=[0,0,512,512])) for i in range(5)]
        error=self.planes(d,1);self.assertEqual(error['code'],'RESOURCE_LIMIT');self.assertIn('coverage',error['message'])
        d=self.document(4,1);d['items']=[source(),mask_rect('m',w=4,h=1,parent='source',color=named('s',overprint='preserve')),fill('ink',named('b'),box=(0,0,4,1),artwork_mask=mask(region=[0,0,4,1]))]
        self.assertEqual(self.planes(d,1)['code'],'OVERPRINT_PREVIEW_UNSUPPORTED')
        d['items'][1]['content']['fill']=[255]*4
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);cancel=root/'cancel';cancel.write_text('cancel')
            out=dict(output_root=str(root),file_name='cancelled.pdf',format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()))))
            error=self.invoke(dict(command='document.publish',document=d,output=out,control=dict(cancel_file=str(cancel))),1)
            self.assertEqual(error['code'],'CANCELLED');self.assertFalse((root/'cancelled.pdf').exists())

    def test_agent_shared_edit_clipping_undo_redo_retry_and_exact_publication(self):
        d=self.document(16,16);d['items']=[source(),mask_rect('m',w=16,h=16,parent='source',opacity=.5),fill('base',named('b',opacity=.5),box=(0,0,16,16),artwork_mask=mask(region=[0,0,16,16])),fill('clip',named('s',tint=.75,overprint='preserve'),box=(0,0,16,16),clip_to='base')]
        c=Client();c.initialize();self.addCleanup(c.close)
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);s=dict(session_root=str(root/'sessions'),session_id='native-coverage');c.success('session.create',**s,request_id='create',document=d)
            before=c.success('session.read',**s)['document'];a=self.planes(before);edit=dict(request_id='edit',expected_revision=0,action=dict(type='edit',operations=[dict(op='properties',id='m',opacity=.25),dict(op='layer_clip',id='clip',clip_to=None)]))
            changed=c.success('session.apply',**s,**edit)['document'];b=self.planes(changed);self.assertNotEqual(a['interleaved_sha256'],b['interleaved_sha256']);self.assertNotEqual(a['coverage_sources']['artwork_masks'][0]['source_sha256'],b['coverage_sources']['artwork_masks'][0]['source_sha256'])
            output=dict(output_root=str(root),file_name='native.pdf',format='pdf',pdf_options=dict(prepress=dict(profile=embedded(cmyk_profile()),antialias='none',spot_fallback='multiplicative_declared',marks={})))
            c.success('session.publish',**s,expected_revision=1,output=output);raw=(root/'native.pdf').read_bytes();pdf=pdf_reader.Pdf(dict(data=base64.b64encode(raw).decode()));self.assertEqual(hashlib.sha256(page_image(pdf)[1]).hexdigest(),b['interleaved_sha256'])
            undo=c.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.planes(undo)['interleaved_sha256'],a['interleaved_sha256'])
            c.success('session.apply',**s,request_id='redo',expected_revision=2,action=dict(type='redo'));self.assertTrue(c.success('session.apply',**s,**edit)['replayed']);self.assertTrue(c.success('session.verify',**s)['valid']);self.assertEqual((root/'native.pdf').read_bytes(),raw)

    def test_shared_mask_palette_edit_changes_evaluated_receipt_and_preserves_printed_ink(self):
        d=self.document(4,1,kind='vector')
        swatch=lambda rgb:dict(name='Mask tone',definition=dict(type='spot',alternate=dict(space='srgb',components=rgb)))
        d['swatches']['tone']=swatch([1,0,0])
        d['items']=[source(),mask_rect('m',w=4,h=1,parent='source',color=named('tone',opacity=.5)),rect('ink',named('s',tint=.75),box=(0,0,4,1),artwork_mask=mask(region=[0,0,4,1],mode='luminance'))]
        d=self.invoke(dict(command='document.validate',document=d));before=copy.deepcopy(d);a=self.planes(d,samples=[[0,0]])
        changed=self.edit(d,[dict(op='swatch',id='tone',swatch=swatch([0,1,0]))]);b=self.planes(changed,samples=[[0,0]])
        ar=a['coverage_sources']['artwork_masks'][0];br=b['coverage_sources']['artwork_masks'][0]
        self.assertEqual(ar['source_sha256'],br['source_sha256']);self.assertNotEqual(ar['evaluated_source_sha256'],br['evaluated_source_sha256'])
        for result,coefficient in [(a,F(2125,10000)),(b,F(7154,10000))]:
            self.assertEqual([p['id'] for p in result['plates'][4:]],['s'])
            self.assertValues(result['samples'][0]['ink_fractions'],[0,0,0,0,F(3,4)*F(1,2)*coefficient])
        self.assertEqual(d,before);self.assertEqual(changed['items'],d['items'])


if __name__=='__main__':unittest.main()
