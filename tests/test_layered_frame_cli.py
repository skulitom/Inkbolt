"""Original frame graphs and rectangle topology, independent of text caches."""
import json,tempfile,unittest,hashlib
from pathlib import Path
import test_layered_cli as core
import test_layered_story_cli as s
from test_mcp import Client


def rectangle(bounds=(-3.5,2.25,24.5,39.75),reverse=False,start=0):
    x0,y0,x1,y1=bounds;corners=[(x0,y0),(x1,y0),(x1,y1),(x0,y1)]
    if reverse:corners.reverse()
    corners=corners[start:]+corners[:start]
    return [v for i,a in enumerate(corners) for p in (a,a,corners[(i+1)%4],corners[(i+1)%4]) for v in p]


def point():return {'0':{'2':{}}}


def box(bounds=(-3.5,2.25,24.5,39.75),**kwargs):
    return {'0':{'1':{'0':rectangle(bounds,**kwargs)},'2':{'0':1}}}


def graph(frame=None):
    g=s.global_data();g['0']['8']={'0':[box() if frame is None else frame]}
    g['1']['1'][0]['1']={'0':[{'0':0}]}
    return g


class LayeredFrameTests(unittest.TestCase):
    invoke=core.LayeredTests.invoke
    read=core.LayeredTests.read

    def load(self,g=None,**kwargs):
        return self.read(s.source(global_=graph() if g is None else g,**kwargs),1,color_policy='assume_srgb')

    def frame(self,g=None,**kwargs):return self.load(g,**kwargs)['details']['global_story']['frame']

    def test_story_and_frame_indices_are_independent_and_unused_frames_are_untrusted(self):
        g=graph();g['0']['8']['0']=[{'unmapped':True},point(),box()]
        g['1']['1']=[s.story('Other'),g['1']['1'][0]]
        g['1']['1'][1]['1']['0'][0]['0']=2
        for version in [1,2]:
            r=self.frame(g,index=1,version=version)
            self.assertEqual((r['frame_index'],r['frame_count'],r['shape']),(2,3,'rectangle'))
            self.assertEqual(r['bounds'],[-3.5,2.25,24.5,39.75]);self.assertEqual(r['frame_transform'],[1,0,0,1,0,0])
            self.assertTrue(r['selected_reference_and_geometry_validated'])
            for key in ['other_frames_validated','remaining_frame_properties_validated','local_geometry_consistency_validated','layout_semantics_validated']:
                self.assertFalse(r[key])
            self.assertLess(len(json.dumps(self.load(g,index=1)['details']).encode()),8192)
        g['1']['1'][1]['1']['0'][0]['0']=1
        self.assertEqual(self.frame(g,index=1)['shape'],'point');self.assertIsNone(self.frame(g,index=1)['bounds'])
        self.assertFalse(self.frame(s.global_data())['present'])

    def test_point_rectangle_and_separate_affine_values_are_retained_exactly(self):
        for reverse in [False,True]:
            for start in range(4):
                f=box(reverse=reverse,start=start);f['0']['2']['2']=[1.25,.375,-.125,.75,7.25,-9.5]
                r=self.frame(graph(f));self.assertEqual(r['bounds'],[-3.5,2.25,24.5,39.75])
                self.assertEqual(r['frame_transform'],[1.25,.375,-.125,.75,7.25,-9.5])
        p=point();p['0']['2']['2']=[-1,0,0,1,12,9];r=self.frame(graph(p))
        self.assertEqual(r['shape'],'point');self.assertEqual(r['frame_transform'],[-1,0,0,1,12,9])
        self.assertEqual(r['first_baseline'],dict(metric='ascent',minimum=0));self.assertFalse(r['first_baseline_explicit'])

    def test_first_baseline_mapping_is_typed_bounded_and_explicit(self):
        for mode,metric in enumerate(['fixed','ascent','cap_height','leading','x_height']):
            for minimum in [0,3.25,32768]:
                f=box();f['0']['2']['10']={'0':mode,'1':minimum};r=self.frame(graph(f))
                self.assertTrue(r['first_baseline_explicit']);self.assertEqual(r['first_baseline'],dict(metric=metric,minimum=minimum))
        for value,code in [(5,'UNSUPPORTED_LAYERED_SEMANTICS'),(-1,'INVALID_LAYERED_FILE'),(True,'INVALID_LAYERED_FILE'),(1.0,'INVALID_LAYERED_FILE'),('1','INVALID_LAYERED_FILE')]:
            f=box();f['0']['2']['10']={'0':value,'1':0};self.assertEqual(self.load(graph(f))['code'],code)
        for value,code in [(-.01,'UNSUPPORTED_LAYERED_SEMANTICS'),(32768.01,'UNSUPPORTED_LAYERED_SEMANTICS'),(True,'INVALID_LAYERED_FILE'),('1','INVALID_LAYERED_FILE'),(s.Name('nil'),'INVALID_LAYERED_FILE')]:
            f=box();f['0']['2']['10']={'0':1,'1':value};self.assertEqual(self.load(graph(f))['code'],code)
        for value in [{},{'0':1},{'1':0},[],0]:
            f=box();f['0']['2']['10']=value;self.assertEqual(self.load(graph(f))['code'],'INVALID_LAYERED_FILE')

    def test_incomplete_or_invalid_frame_references_do_not_use_local_geometry(self):
        for index in [-1,1,2**63,1.0,True,'0',s.Name('nil')]:
            g=graph();g['1']['1'][0]['1']['0'][0]['0']=index
            self.assertEqual(self.load(g)['code'],'INVALID_LAYERED_FILE')
        for refs in [[],[{}],[0],[{'0':0.0}]]:
            g=graph();g['1']['1'][0]['1']['0']=refs;self.assertEqual(self.load(g)['code'],'INVALID_LAYERED_FILE')
        g=graph();g['1']['1'][0]['1']['0']=[{'0':0},{'0':0}]
        self.assertEqual(self.load(g)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for part in ['layout','resource','shape','properties']:
            g=graph()
            if part=='layout':g['1']['1'][0]['1']={}
            elif part=='resource':del g['0']['8']
            elif part=='shape':g['0']['8']['0'][0]={}
            else:g['0']['8']['0'][0]['0']['2']=[]
            self.assertEqual(self.load(g)['code'],'INVALID_LAYERED_FILE')
        g=graph();g['0']['8']['0']=[box()]*257
        self.assertEqual(self.load(g)['code'],'RESOURCE_LIMIT')

    def test_curves_disconnected_diagonal_crossed_and_degenerate_paths_refuse(self):
        variants=[]
        for at in [0,2,6]:
            coords=rectangle();coords[at]+=.1;variants.append(coords)
        variants.extend([rectangle()[:-1],rectangle()+rectangle(),rectangle((0,0,0,10)),rectangle((0,0,.0005,10))])
        # Straight closed polygon with the same four corners, but crossing diagonals.
        corners=[(0,0),(10,10),(0,10),(10,0)]
        variants.append([v for i,a in enumerate(corners) for p in [a,a,corners[(i+1)%4],corners[(i+1)%4]] for v in p])
        # An axis-aligned boundary which revisits a corner rather than forming a rectangle.
        corners=[(0,0),(10,0),(10,10),(10,0)]
        variants.append([v for i,a in enumerate(corners) for p in [a,a,corners[(i+1)%4],corners[(i+1)%4]] for v in p])
        for coords in variants:
            f=box();f['0']['1']['0']=coords
            self.assertEqual(self.load(graph(f))['code'],'UNSUPPORTED_LAYERED_SEMANTICS')

    def test_unknown_types_bad_numeric_values_and_budgets_fail_explicitly(self):
        for kind in [0,2,7]:
            f=point();f['0']['2']['0']=kind;self.assertEqual(self.load(graph(f))['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for kind in [-1,True,1.0,'1']:
            f=point();f['0']['2']['0']=kind;self.assertEqual(self.load(graph(f))['code'],'INVALID_LAYERED_FILE')
        f=point();f['0']['1']={'0':rectangle()};self.assertEqual(self.load(graph(f))['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for values,code in [([1,0,0,1,0],'INVALID_LAYERED_FILE'),([1,0,0,True,0,0],'INVALID_LAYERED_FILE'),([1,0,0,1,'0',0],'INVALID_LAYERED_FILE'),([1,0,0,1,32769,0],'RESOURCE_LIMIT')]:
            f=box();f['0']['2']['2']=values;self.assertEqual(self.load(graph(f))['code'],code)
        for value,code in [(True,'INVALID_LAYERED_FILE'),('1','INVALID_LAYERED_FILE'),(s.Name('nil'),'INVALID_LAYERED_FILE'),(32769,'RESOURCE_LIMIT')]:
            f=box();f['0']['1']['0'][0]=value;self.assertEqual(self.load(graph(f))['code'],code)

    def test_unknown_frame_properties_are_not_certified_by_geometry_diagnostics(self):
        f=box();f['0']['2']['unknown']={'nested':[s.Name('nil'),b'opaque',True]}
        r=self.frame(graph(f));self.assertFalse(r['remaining_frame_properties_validated'])
        self.assertFalse(self.load(graph(f))['details']['editable_import_supported'])
        # A singular matrix is reported as data, never promoted to a renderable item.
        f['0']['2']['2']=[0,0,0,0,0,0];r=self.frame(graph(f))
        self.assertEqual(r['frame_transform'],[0]*6);self.assertFalse(r['layout_semantics_validated'])

    def test_cli_mcp_agree_and_preserve_sources_without_creating_outputs(self):
        g=graph();g['0']['8']['0'][0]['0']['2']['10']={'0':2,'1':3.5};data=s.source(global_=g)
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'original.psd';p.write_bytes(data)
            args=dict(source_path=str(p),id='incoming',color_policy='assume_srgb',expected_sha256=hashlib.sha256(data).hexdigest())
            expected=self.invoke(dict(command='layered.import',**args),1);client=Client()
            try:
                client.initialize();result=client.tool('layered.import',**args)
                self.assertTrue(result['isError']);self.assertEqual(result['structuredContent']['error'],expected)
                self.assertEqual(client.tool('layered.import',**args,control=dict(timeout_ms=0))['structuredContent']['error']['code'],'TIMEOUT')
            finally:client.close()
            self.assertEqual(p.read_bytes(),data);self.assertEqual(list(Path(root).iterdir()),[p])


if __name__=='__main__':unittest.main()
