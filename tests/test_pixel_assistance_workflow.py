"""Original withheld-truth quality checks for offline pixel assistance equivalents."""
import base64
import copy
import math
import random
import unittest
import test_editing_cli as editing
import test_variants_cli as variants
from segment_reference import original_document
from test_resampling_cli import reference as reconstruction_reference


class PixelAssistanceWorkflowTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    edit=variants.VariantTests.edit
    def valid(self,pixels,w,h):return self.invoke(dict(command='document.validate',document=original_document(pixels,w,h)))
    def pixels(self,d):return editing.png_pixels(base64.b64decode(self.invoke(dict(command='document.export',document=d,format='png'))['data']))[2]

    def test_selected_object_removal_recovers_withheld_original_texture_exactly(self):
        w,h=24,18
        clean=[[40+20*(x%2),70+30*(y%2),100+10*((x+y)%2),255] for y in range(h) for x in range(w)]
        damaged=copy.deepcopy(clean);truth=[]
        for y in range(h):
            for x in range(w):
                selected=10<=x<14 and 7<=y<11;truth.append(255 if selected else 0)
                if selected:damaged[y*w+x]=[230,20,210,255]
        source=self.valid(damaged,w,h);options=dict(foreground=[[11,8]],background=[[0,0],[1,0],[0,1],[1,1]])
        mask=self.invoke(dict(command='assist.segment',document=source,id='pixels',options=options))['mask'];self.assertEqual(bytes.fromhex(mask['gray_hex']),bytes(truth))
        repair=dict(region=dict(x=0,y=0,width=w,height=h,gray_hex=mask['gray_hex']),action=dict(type='fill',fill=dict(source_id='pixels',patch_radius=2,max_context_rms=0)))
        restored=self.edit(source,dict(op='repair',id='pixels',options=repair));actual=self.pixels(restored);self.assertEqual(actual,bytes(v for p in clean for v in p))
        self.assertEqual(bytes.fromhex(source['items'][0]['content']['rgba_hex']),bytes(v for p in damaged for v in p));self.assertEqual(restored,self.edit(source,dict(op='repair',id='pixels',options=repair)))
        for k,(old,new) in enumerate(zip(damaged,[list(actual[i:i+4]) for i in range(0,w*h*4,4)])):
            if not truth[k]:self.assertEqual(new,old)

    def test_self_guided_denoise_reduces_noise_without_a_clean_guide_or_moving_edge(self):
        w,h=32,24;clean=[[50,95,145,255] if x<16 else [185,120,55,255] for y in range(h) for x in range(w)]
        for seed in [21,72,103]:
            rng=random.Random(seed);noisy=[[max(0,min(255,v+rng.randint(-9,9))) for v in p[:3]]+[255] for p in clean];source=self.valid(noisy,w,h)
            options=dict(region=dict(x=0,y=0,width=w,height=h),action=dict(type='edge_correct',guide_id='pixels',radius=2,range_sigma=.1,max_change_rms=.1))
            result=self.edit(source,dict(op='repair',id='pixels',options=options));pixels=self.pixels(result);actual=[list(pixels[i:i+4]) for i in range(0,len(pixels),4)]
            rms=lambda a:math.sqrt(sum((p[c]-q[c])**2 for p,q in zip(a,clean) for c in range(3))/(w*h*3))
            self.assertLess(rms(actual),.65*rms(noisy))
            for y in range(h):
                self.assertLess(actual[y*w+15][0],100);self.assertGreater(actual[y*w+16][0],130)
            self.assertTrue(all(p[3]==255 for p in actual));self.assertEqual(result,self.edit(source,dict(op='repair',id='pixels',options=options)))
            self.assertEqual(bytes.fromhex(source['items'][0]['content']['rgba_hex']),bytes(v for p in noisy for v in p))

    def test_local_upscale_matches_independent_reconstruction_and_improves_smooth_chart(self):
        w,h=12,10;nw,nh=36,30
        function=lambda x,y:[110+45*math.sin(2*math.pi*x/w),120+35*math.cos(2*math.pi*y/h),50+4*x+3*y,255]
        original=[[round(v) for v in function(x+.5,y+.5)] for y in range(h) for x in range(w)];source=self.valid(original,w,h)
        operation=dict(op='canvas',action=dict(type='scale',width=nw,height=nh,sampling='lanczos3'))
        enlarged=self.edit(source,operation);rgba=self.pixels(enlarged);reference=reconstruction_reference(original,w,h,nw,nh,'lanczos3')
        self.assertLessEqual(max(abs(a-float(b)) for a,b in zip(rgba,(v for p in reference for v in p))),.5000001)
        exact=[];smooth=[];nearest=[]
        for y in range(nh):
            for x in range(nw):
                u=(x+.5)*w/nw;v=(y+.5)*h/nh
                if 3<=u<w-3 and 3<=v<h-3:
                    exact.extend(function(u,v)[:3]);smooth.extend(rgba[(y*nw+x)*4:(y*nw+x)*4+3]);nearest.extend(original[int(v)*w+int(u)][:3])
        rms=lambda a:math.sqrt(sum((v-t)**2 for v,t in zip(a,exact))/len(exact))
        self.assertLess(rms(smooth),.5*rms(nearest));self.assertEqual(enlarged['items'][0]['content']['rgba_hex'],source['items'][0]['content']['rgba_hex'])
        self.assertEqual(enlarged,self.edit(source,operation));self.assertEqual((enlarged['width'],enlarged['height']),(nw,nh))
