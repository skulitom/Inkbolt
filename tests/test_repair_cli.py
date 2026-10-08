"""Independent donor searches, analytic texture recovery and guided weighted quantiles."""
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
import test_editing_cli as editing
import test_retouch_cli as retouch
from test_mcp import Client


def region(x,y,w,h,mask=None):
    r=dict(x=x,y=y,width=w,height=h)
    if mask is not None:r['gray_hex']=bytes(mask).hex()
    return r


def fill(source='pixels',radius=1,error=0,**kw):
    return dict(source_id=source,patch_radius=radius,max_context_rms=error,**kw)


def options(r,action,**kw):return dict(region=r,action=action,**kw)


def weights(r,w,h):
    out=[0.0]*(w*h);m=bytes.fromhex(r['gray_hex']) if r.get('gray_hex') is not None else [255]*(r['width']*r['height'])
    for y in range(r['height']):
        for x in range(r['width']):out[(y+r['y'])*w+x+r['x']]=m[y*r['width']+x]/255
    return out


def window(i,w,h,r):
    return [(yy*w+xx,xx-i%w,yy-i//w) for yy in range(max(0,i//w-r),min(h,i//w+r+1)) for xx in range(max(0,i%w-r),min(w,i%w+r+1))]


def mse(a,b):return sum((x-y)**2 for x,y in zip(a,b))/4


def replay_synthesis(original,source,w,h,sw,sh,r,f,receipt,same=True):
    """Recompute every global minimum and priority independently of reported choices."""
    coverage=weights(r,w,h);unknown={i for i,a in enumerate(coverage) if a};was_unknown=set(unknown)
    values=list(map(retouch.pm,original));donors=list(map(retouch.pm,source));radius=f.get('patch_radius',1);trust=f.get('synthesized_weight',.5)
    allowed=weights(f['donor_region'],sw,sh) if f.get('donor_region') else [1]*(sw*sh)
    if same:
        for i in unknown:allowed[i]=0
    centers=[y*sw+x for y in range(radius,sh-radius) for x in range(radius,sw-radius) if all(allowed[j] for j,_,_ in window(y*sw+x,sw,sh,radius))]
    assert len(centers)==receipt['candidate_patches']
    for decision in receipt['patches']:
        priorities=[(-sum(j not in unknown for j,_,_ in window(i,w,h,radius)),i) for i in unknown]
        center=min(priorities)[1];assert decision['target_center']==[center%w,center//w]
        context=[t for t in window(center,w,h,radius) if t[0] not in unknown]
        total=sum(trust if j in was_unknown else 1 for j,_,_ in context)
        scores=[]
        for candidate in centers:
            score=sum((trust if j in was_unknown else 1)*mse(values[j],donors[candidate+dy*sw+dx]) for j,dx,dy in context)/total
            scores.append((score,candidate))
        best,candidate=min(scores)
        assert decision['source_center']==[candidate%sw,candidate//sw]
        assert abs(decision['context_rms']-math.sqrt(best))<1e-13
        assert decision['context_cells']==len(context) and abs(decision['context_weight']-total)<1e-13
        filled=0
        for i,dx,dy in window(center,w,h,radius):
            if i in unknown:values[i]=donors[candidate+dy*sw+dx];unknown.remove(i);filled+=1
        assert decision['filled_pixels']==filled
    assert not unknown
    return values,coverage


def output_pixels(original,values):
    return [a if retouch.pm(a)==b else retouch.encode(b) for a,b in zip(original,values)]


def guided_reference(target,guide,w,h,r,o,coverage):
    before=list(map(retouch.pm,target));g=list(map(retouch.pm,guide));out=copy.deepcopy(target);effective=[];max_change=0
    for i,a in enumerate(coverage):
        if not a:continue
        samples=[]
        for j,dx,dy in window(i,w,h,r):
            weight=(r+1-abs(dx))*(r+1-abs(dy))*math.exp(-mse(g[i],g[j])/(2*o['range_sigma']**2))
            if weight:samples.append((j,weight))
        total=sum(t for _,t in samples);effective.append(total*total/sum(t*t for _,t in samples));channels=[]
        for k in range(4):
            ranked=sorted((before[j][k],j,t) for j,t in samples);cumulative=0
            for v,_,t in ranked:
                cumulative+=t
                if cumulative>=total/2:channels.append(v);break
        value=[old+(new-old)*a*o.get('opacity',1) for old,new in zip(before[i],channels)]
        if value!=before[i]:out[i]=retouch.encode(value)
        max_change=max(max_change,math.sqrt(mse(before[i],retouch.pm(out[i]))))
    return out,min(effective) if effective else None,max_change


class RepairTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    document=retouch.RetouchTests.document
    colors=retouch.RetouchTests.colors
    close_pixels=retouch.RetouchTests.close_pixels
    def apply(self,d,o,expected=0,**kw):return self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='repair',id='pixels',options=o)],**kw),expected)

    def test_fill_recovers_original_periodic_texture_and_independent_global_minima(self):
        w,h=14,12;clean=[[30+(x%4)*40,50+(y%3)*60,80+((x+y)%3)*30,255] for y in range(h) for x in range(w)]
        damaged=copy.deepcopy(clean);r=region(5,4,3,4)
        for i,a in enumerate(weights(r,w,h)):
            if a:damaged[i]=[250,0,250,255]
        o=options(r,dict(type='fill',fill=fill()));d=self.document(w,h,damaged);before=copy.deepcopy(d);result=self.apply(d,o);out=self.colors(result['document'])
        self.assertEqual(out,clean);self.assertEqual(d,before)
        synthesized,coverage=replay_synthesis(damaged,damaged,w,h,w,h,r,fill(),result['changes'][0]['details']['action']['synthesis'])
        expected=output_pixels(damaged,[[(1-a)*old+a*new for old,new in zip(retouch.pm(c),v)] for c,v,a in zip(damaged,synthesized,coverage)])
        self.assertEqual(out,expected)

    def test_fill_uses_surrounding_content_and_external_binary_donor_restriction(self):
        w=h=9;sw,sh=14,9;source=[[30,70,100,255] if x<7 else [180,120,40,255] for y in range(sh) for x in range(sw)]
        r=region(3,3,3,3);donor=region(7,0,7,9);f=fill('source',1,0,donor_region=donor)
        for color in [[180,120,40,255],[30,70,100,255]]:
            target=[color[:] for _ in range(w*h)]
            for i,a in enumerate(weights(r,w,h)):
                if a:target[i]=[220,20,180,255]
            d=self.document(w,h,target,source,sw,sh);o=options(r,dict(type='fill',fill=f))
            if color[0]==180:
                out=self.apply(d,o);self.assertEqual(self.colors(out['document']),[color]*(w*h));replay_synthesis(target,source,w,h,sw,sh,r,f,out['changes'][0]['details']['action']['synthesis'],False)
            else:self.assertEqual(self.apply(d,o,1)['code'],'REPAIR_QUALITY')
            self.assertEqual(self.colors(d,'source'),source)

    def test_smooth_original_chart_fill_has_predeclared_reconstruction_error(self):
        w,h=16,12;clean=[[40+5*x,60+4*y,80+2*x+2*y,255] for y in range(h) for x in range(w)];damaged=copy.deepcopy(clean);r=region(6,4,3,3)
        for i,a in enumerate(weights(r,w,h)):
            if a:damaged[i]=[250,10,220,255]
        o=options(r,dict(type='fill',fill=fill(radius=2,error=.12)));out=self.colors(self.apply(self.document(w,h,damaged),o)['document'])
        errors=[math.sqrt(mse(retouch.pm(a),retouch.pm(b))) for a,b in zip(out,clean)]
        selected=[v for v,a in zip(errors,weights(r,w,h)) if a]
        self.assertLessEqual(max(selected),.15);self.assertLessEqual(sum(selected)/len(selected),.07)
        self.assertTrue(all(a==b for a,b,weight in zip(out,damaged,weights(r,w,h)) if not weight))

    def test_patch_search_finds_exact_translated_context_and_preserves_source(self):
        w=h=9;src=[[30+x*15,40+y*13,60+(x*11+y*7)%90,255] for y in range(h) for x in range(w)]
        target=copy.deepcopy(src);r=region(3,3,2,2)
        for i,a in enumerate(weights(r,w,h)):
            if a:target[i]=[255,0,255,255]
        action=dict(type='patch',source_id='source',source_origin=[2,4],search_radius=2,context_radius=1,max_context_rms=0,blend=dict(type='clone'))
        d=self.document(w,h,target,src);result=self.apply(d,options(r,action));detail=result['changes'][0]['details']['action']
        self.assertEqual(detail['source_origin'],[3,3]);self.assertEqual(detail['context_rms'],0);self.assertEqual(self.colors(result['document']),src);self.assertEqual(self.colors(result['document'],'source'),src)

    def test_patch_healing_matches_independent_dense_system_with_soft_coverage(self):
        w=h=7;src=[[20+x*10,40+y*8,70+(x+y)*6,220] for y in range(h) for x in range(w)];dst=[[60+x*5,70+y*7,90+x+y,200] for y in range(h) for x in range(w)]
        r=region(2,2,3,3,[255,128,255,64,0,255,255,255,128]);blend=dict(type='heal',screening=.3,tolerance=1e-12)
        o=options(r,dict(type='patch',source_id='source',source_origin=[2,2],max_context_rms=1,blend=blend),opacity=.7)
        ro=dict(source_id='source',region=r,mode=blend,opacity=.7);expected,_,_=retouch.reference(dst,src,w,h,w,h,ro)
        result=self.apply(self.document(w,h,dst,src),o);self.close_pixels(self.colors(result['document']),expected);self.assertLessEqual(max(result['changes'][0]['details']['action']['retouch']['solver_residuals']),1e-12)

    def test_patch_ties_prefer_requested_origin_then_row_order_and_reject_unknown_source(self):
        w=h=8;src=[[40,70,100,255]]*(w*h);dst=copy.deepcopy(src);r=region(3,3,2,2)
        for i,a in enumerate(weights(r,w,h)):
            if a:dst[i]=[250,0,200,255]
        a=dict(type='patch',source_id='source',source_origin=[3,3],search_radius=1,max_context_rms=0,blend=dict(type='clone'))
        result=self.apply(self.document(w,h,dst,src),options(r,a));self.assertEqual(result['changes'][0]['details']['action']['source_origin'],[3,3])
        a['source_id']='pixels';a['search_radius']=0
        self.assertEqual(self.apply(self.document(w,h,dst),options(r,a),1)['code'],'REPAIR_QUALITY')

    def test_content_move_restores_hole_and_retains_frozen_object_with_overlap(self):
        w,h=12,9;background=[40,70,110,255];original=[background[:] for _ in range(w*h)];r=region(3,3,3,2)
        for i,a in enumerate(weights(r,w,h)):
            if a:original[i]=[190+(i%w),30+(i//w),60,255]
        for offset in [[5,2],[1,0],[-2,-2]]:
            o=options(r,dict(type='move',offset=offset,fill=fill()));d=self.document(w,h,original);result=self.apply(d,o);out=self.colors(result['document']);expected=[background[:] for _ in range(w*h)]
            for i,a in enumerate(weights(r,w,h)):
                if a:expected[i+offset[1]*w+offset[0]]=original[i]
            self.assertEqual(out,expected);self.assertEqual(self.colors(d),original);self.assertEqual(result['changes'][0]['details']['action']['moved_pixels'],6)

    def test_soft_move_applies_mask_and_whole_opacity_once_and_zero_offset_is_noop(self):
        w=h=9;source=[[40,70,100,160]]*(w*h);target=copy.deepcopy(source);r=region(3,3,2,2,[255,128,64,255])
        for i,a in enumerate(weights(r,w,h)):
            if a:target[i]=[200,30,50,220]
        f=fill('source',1,0);o=options(r,dict(type='move',offset=[2,1],fill=f),opacity=.6);d=self.document(w,h,target,source);result=self.apply(d,o)
        values,a=replay_synthesis(target,source,w,h,w,h,r,f,result['changes'][0]['details']['action']['synthesis'],False)
        original=list(map(retouch.pm,target));combined=[[(1*t)*x+(1-t)*y for x,y in zip(v,b)] for v,b,t in zip(values,original,a)]
        for i,t in enumerate(a):
            if t:combined[i+w+2]=[(1-t)*b+t*s for b,s in zip(combined[i+w+2],original[i])]
        expected=output_pixels(target,[[b+(v-b)*.6 for b,v in zip(old,new)] for old,new in zip(original,combined)])
        self.close_pixels(self.colors(result['document']),expected)
        o['action']['offset']=[0,0];self.assertEqual(self.colors(self.apply(d,o)['document']),target)

    def test_guided_correction_removes_impulses_and_preserves_strong_thin_edges(self):
        w,h=11,9;guide=[[220,180,50,255] if x==5 else [30,60,100,255] for y in range(h) for x in range(w)];target=copy.deepcopy(guide)
        for i in [3*w+3,4*w+5,5*w+8]:target[i]=[250,20,220,255]
        r=region(0,0,w,h);a=dict(type='edge_correct',guide_id='source',radius=2,range_sigma=.04,max_change_rms=1,minimum_effective_samples=2)
        result=self.apply(self.document(w,h,target,guide),options(r,a));out=self.colors(result['document']);self.assertEqual(out,guide)
        expected,support,change=guided_reference(target,guide,w,h,2,a,weights(r,w,h));self.assertEqual(out,expected);detail=result['changes'][0]['details']['action'];self.assertAlmostEqual(detail['minimum_effective_samples'],support,delta=1e-12);self.assertAlmostEqual(detail['maximum_change_rms'],change,delta=1e-14)

    def test_guided_soft_alpha_correction_matches_weighted_quantiles_and_final_change_gate(self):
        w=h=6;target=[[20+x*27,40+y*19,100,40+(x+y)*19] for y in range(h) for x in range(w)];guide=[[x*35,y*35,80,255] for y in range(h) for x in range(w)]
        r=region(1,1,4,4,[0,64,128,255]*4);a=dict(type='edge_correct',guide_id='source',radius=2,range_sigma=.3,max_change_rms=1)
        o=options(r,a,opacity=.63);expected,support,change=guided_reference(target,guide,w,h,2,dict(a,opacity=.63),weights(r,w,h));d=self.document(w,h,target,guide);out=self.apply(d,o);self.close_pixels(self.colors(out['document']),expected)
        self.assertAlmostEqual(out['changes'][0]['details']['action']['maximum_change_rms'],change,delta=1e-14)
        a['max_change_rms']=change/2;self.assertEqual(self.apply(d,o,1)['code'],'REPAIR_QUALITY')

    def test_quality_gates_reject_context_boundary_and_insufficient_guide_support(self):
        w=h=7;target=[[30,60,90,255]]*(w*h);source=[[190,150,80,255]]*(w*h);d=self.document(w,h,target,source);r=region(2,2,3,3)
        self.assertEqual(self.apply(d,options(r,dict(type='fill',fill=fill('source',1,0))),1)['code'],'REPAIR_QUALITY')
        o=options(r,dict(type='fill',fill=fill('source',1,1)),max_boundary_rms=0);self.assertEqual(self.apply(d,o,1)['code'],'REPAIR_QUALITY')
        guide=[[0,0,0,255]]*(w*h);guide[3*w+3]=[255,255,255,255];d=self.document(w,h,target,guide)
        a=dict(type='edge_correct',guide_id='source',radius=1,range_sigma=.0001,max_change_rms=1,minimum_effective_samples=2)
        self.assertEqual(self.apply(d,options(region(3,3,1,1),a),1)['code'],'REPAIR_QUALITY')

    def test_full_unknown_domains_empty_donors_and_move_clipping_fail_explicitly(self):
        w=h=5;colors=[[30,60,90,255]]*(w*h);d=self.document(w,h,colors);r=region(0,0,w,h)
        self.assertEqual(self.apply(d,options(r,dict(type='fill',fill=fill())),1)['code'],'REPAIR_QUALITY')
        self.assertEqual(self.apply(d,options(region(2,2,1,1),dict(type='fill',fill=fill(donor_region=region(0,0,1,1)))),1)['code'],'REPAIR_QUALITY')
        self.assertEqual(self.apply(d,options(region(2,2,1,1),dict(type='move',offset=[4,0],fill=fill())),1)['code'],'INVALID_REPAIR')

    def test_selection_native_coordinates_source_locks_and_partial_region_preservation(self):
        w=h=8;src=[[50,80,100,255]]*(w*h);dst=copy.deepcopy(src);r=region(2,2,3,3)
        for i,a in enumerate(weights(r,w,h)):
            if a:dst[i]=[180,20,220,255]
        d=self.document(w,h,dst,src);d['items'][1]['locked']=True;selection=bytes(128 if x>=3 else 0 for y in range(h) for x in range(w));d['selection']=dict(width=w,height=h,gray_hex=selection.hex())
        a=dict(type='edge_correct',guide_id='source',radius=3,range_sigma=.1,max_change_rms=1);o=options(r,a,use_selection=True);result=self.apply(d,o)
        coverage=[v*s/255 for v,s in zip(weights(r,w,h),selection)];expected,_,_=guided_reference(dst,src,w,h,3,a,coverage);self.close_pixels(self.colors(result['document']),expected);self.assertEqual(result['document']['items'][1],d['items'][1]);self.assertEqual(result['document']['selection'],d['selection'])

    def test_strict_fields_limits_masks_guides_locks_and_batch_rollback(self):
        w=h=6;d=self.document(w,h,[[40,60,80,255]]*(w*h),[[90,110,130,255]]*(w*h));r=region(2,2,2,2)
        bad=[dict(type='fill',fill=fill(radius=0)),dict(type='fill',fill=fill(error=2)),dict(type='fill',fill=fill(synthesized_weight=0)),dict(type='fill',fill=fill('source',donor_region=region(0,0,3,3,[128]*9))),dict(type='patch',source_id='source',source_origin=[1,1],search_radius=33,max_context_rms=1,blend=dict(type='clone')),dict(type='edge_correct',guide_id='source',radius=0,range_sigma=.1,max_change_rms=1)]
        for a in bad:self.assertEqual(self.apply(d,options(r,a),1)['code'],'INVALID_REPAIR')
        self.assertEqual(self.apply(d,options(r,dict(type='fill',fill=fill(),unknown=True)),1)['code'],'INVALID_REQUEST')
        locked=copy.deepcopy(d);locked['items'][0]['locked']=True;self.assertEqual(self.apply(locked,options(r,dict(type='fill',fill=fill())),1)['code'],'LOCKED')
        mismatch=self.document(w,h,[[40,60,80,255]]*(w*h),[[90,110,130,255]]*9,3,3);a=dict(type='edge_correct',guide_id='source',radius=1,range_sigma=.1,max_change_rms=1);self.assertEqual(self.apply(mismatch,options(r,a),1)['code'],'INVALID_REPAIR')
        saved=copy.deepcopy(d);o=options(r,dict(type='fill',fill=fill('source',error=1)))
        error=self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='repair',id='pixels',options=o),dict(op='remove',id='missing')]),1);self.assertEqual(error['operation_index'],1);self.assertEqual(d,saved)

    def test_receipts_replay_hashes_and_lossless_snapshot_png(self):
        w=h=8;colors=[[40,70,100,255]]*(w*h);colors=copy.deepcopy(colors);colors[3*w+3]=[220,20,50,255];d=self.document(w,h,colors);o=options(region(3,3,1,1),dict(type='fill',fill=fill()))
        r=self.apply(d,o);self.assertEqual(r,self.apply(d,copy.deepcopy(o)));out=r['document'];detail=r['changes'][0]['details'];actual=self.colors(out)
        for key,c in [('target_before_sha256',colors),('result_sha256',actual)]:self.assertEqual(detail[key],hashlib.sha256(retouch.canonical(w,h,bytes(v for p in c for v in p))).hexdigest())
        self.assertEqual(detail['changed_pixels'],1);self.assertEqual(detail['changed_bounds'],[3,3,4,4]);self.assertEqual(detail['boundary_edges'],4);self.assertEqual(detail['boundary_rms_after'],0)
        snapshot=self.invoke(dict(command='document.export',document=out,format='snapshot'));self.assertEqual(json.loads(snapshot['data']),out)
        png=self.invoke(dict(command='document.export',document=out,format='png'));self.assertEqual(editing.png_pixels(base64.b64decode(png['data']))[2],bytes(v for p in actual for v in p))

    def test_mcp_move_history_quality_failure_and_publication_preserve_session(self):
        w=h=9;colors=[[40,70,100,255] for _ in range(w*h)];r=region(2,2,2,2)
        for i,a in enumerate(weights(r,w,h)):
            if a:colors[i]=[210,30,50,255]
        d=self.document(w,h,colors);o=options(r,dict(type='move',offset=[3,2],fill=fill()))
        with tempfile.TemporaryDirectory() as temp:
            c=Client();self.addCleanup(c.close);c.initialize();s=dict(session_root=str(Path(temp)/'sessions'),session_id='repair');c.success('session.create',**s,request_id='create',document=d)
            req=dict(**s,request_id='move',expected_revision=0,action=dict(type='edit',operations=[dict(op='repair',id='pixels',options=o)]))
            moved=c.success('session.apply',**req)['document'];self.assertEqual(c.success('session.apply',**req)['document'],moved);self.assertNotEqual(self.colors(moved),colors)
            bad=options(region(5,4,2,2),dict(type='move',offset=[-2,-1],fill=fill()),max_boundary_rms=0)
            failed=c.tool('session.apply',**s,request_id='bad',expected_revision=1,action=dict(type='edit',operations=[dict(op='repair',id='pixels',options=bad)]));self.assertTrue(failed['isError']);self.assertEqual(failed['structuredContent']['error']['code'],'REPAIR_QUALITY');self.assertEqual(c.success('session.read',**s)['document'],moved)
            undo=c.success('session.apply',**s,request_id='undo',expected_revision=1,action=dict(type='undo'))['document'];self.assertEqual(self.colors(undo),colors)
            redo=c.success('session.apply',**s,request_id='redo',expected_revision=2,action=dict(type='redo'))['document'];self.assertEqual(self.colors(redo),self.colors(moved))
            output=dict(output_root=temp,file_name='moved.png',format='png');c.success('document.publish',document=redo,output=output);self.assertTrue(c.tool('document.publish',document=redo,output=output)['isError'])

    def test_fill_image_edges_disconnected_domains_and_zero_coverage_bytes(self):
        w,h=8,7;sw,sh=12,10
        clean=[[40+(x%3)*50,60+(y%2)*70,90+((x+y)%2)*30,220] for y in range(h) for x in range(w)]
        source=[[40+(x%3)*50,60+(y%2)*70,90+((x+y)%2)*30,220] for y in range(sh) for x in range(sw)]
        mask=[255 if (x<2 and y<2) or (3<=x<=5 and 3<=y<=4) or (x==7 and y==6) else 0 for y in range(h) for x in range(w)]
        damaged=copy.deepcopy(clean)
        for i,a in enumerate(mask):
            if a:damaged[i]=[240,10,230,120]
        r=region(0,0,w,h,mask);f=fill('source',1,0);d=self.document(w,h,damaged,source,sw,sh);result=self.apply(d,options(r,dict(type='fill',fill=f)))
        self.assertEqual(self.colors(result['document']),clean);replay_synthesis(damaged,source,w,h,sw,sh,r,f,result['changes'][0]['details']['action']['synthesis'],False)
        empty=region(0,0,w,h,[0]*(w*h));self.assertEqual(self.colors(self.apply(d,options(empty,dict(type='fill',fill=f)))['document']),damaged)

    def test_work_limit_in_work_deadline_and_cancel_marker_preserve_inputs(self):
        w,h=160,128;d=self.document(w,h,[[40,70,100,255]]*(w*h));saved=copy.deepcopy(d);o=options(region(40,32,80,64),dict(type='fill',fill=fill(radius=2)))
        self.assertEqual(self.apply(d,o,1)['code'],'RESOURCE_LIMIT');self.assertEqual(d,saved)
        self.assertEqual(self.apply(d,o,1,control=dict(timeout_ms=5))['code'],'TIMEOUT');self.assertEqual(d,saved)
        with tempfile.TemporaryDirectory() as temp:
            marker=Path(temp)/'cancel';marker.write_text('stop')
            self.assertEqual(self.apply(d,o,1,control=dict(cancel_file=str(marker)))['code'],'CANCELLED')


if __name__=='__main__':unittest.main()
