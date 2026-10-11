"""Explicit frame controls stay typed source data, separate from editable layout."""
import copy,hashlib,json,tempfile,unittest
from pathlib import Path
import test_layered_frame_cli as frames
import test_layered_editable_text_cli as editable
import layered_editable_text_fixtures as p
from test_mcp import Client


CONTROLS={'3':('row_count',3),'4':('column_count',4),'7':('row_gap',2.25),
          '8':('column_gap',5.75),'9':('spacing',1.125)}


class FrameControlTests(unittest.TestCase):
    invoke=frames.LayeredFrameTests.invoke
    read=frames.LayeredFrameTests.read
    load=frames.LayeredFrameTests.load
    frame=frames.LayeredFrameTests.frame

    def test_explicit_controls_are_exact_in_point_and_box_frames(self):
        c=self.invoke(dict(command='capabilities'))['layered_interchange']['text_diagnostics']['global_story']['frame']['layout_controls']
        self.assertEqual(c['integer_counts'],['row_count','column_count'])
        self.assertEqual(c['finite_source_distances'],['row_gap','column_gap','spacing'])
        self.assertFalse(c['missing_values_defaulted']);self.assertFalse(c['layout_ranges_validated'])
        for shape in [frames.point,frames.box]:
            for version in [1,2]:
                f=shape();f['0']['2'].update({k:v for k,(_,v) in CONTROLS.items()})
                r=self.frame(frames.graph(f),version=version)
                self.assertEqual(r['layout_controls'],{n:v for n,v in CONTROLS.values()})
                self.assertTrue(r['layout_control_types_validated'])
                for name in ['layout_controls_defaulted','remaining_frame_properties_validated',
                             'local_geometry_consistency_validated','layout_semantics_validated']:
                    self.assertFalse(r[name])

    def test_absent_controls_stay_absent_and_explicit_zero_is_retained(self):
        for key,(name,_) in CONTROLS.items():
            f=frames.point();self.assertEqual(self.frame(frames.graph(f))['layout_controls'],{})
            f['0']['2'][key]=0
            self.assertEqual(self.frame(frames.graph(f))['layout_controls'],{name:0})
        # Unknown frame records neither supply nor certify source controls.
        f['0']['2']={'6':[17.25,-9.0],'11':{'4':31,'18':8.125}}
        r=self.frame(frames.graph(f));self.assertEqual(r['layout_controls'],{})
        self.assertFalse(r['remaining_frame_properties_validated'])

    def test_signed_and_large_values_are_diagnostic_not_layout_acceptance(self):
        f=frames.point();f['0']['2'].update({'3':-(2**63),'4':2**63-1,'7':-2.125,'8':65536.125,'9':-65536.125})
        r=self.frame(frames.graph(f))
        self.assertEqual(r['layout_controls'],dict(row_count=-(2**63),column_count=2**63-1,
                                                  row_gap=-2.125,column_gap=65536.125,spacing=-65536.125))
        self.assertFalse(r['layout_semantics_validated'])

    def test_malformed_scalar_types_are_not_coerced(self):
        for key in CONTROLS:
            wrong=[True,False,'3',frames.s.Name('nil'),b'opaque',[],{}]
            wrong.extend([1.0,1.5] if key in ['3','4'] else [float('inf'),float('nan')])
            for value in wrong:
                f=frames.point();f['0']['2'][key]=value
                self.assertEqual(self.load(frames.graph(f))['code'],'INVALID_LAYERED_FILE',(key,value))

    def test_selected_frame_controls_do_not_validate_unused_frames(self):
        f=frames.point();f['0']['2']['4']=7
        invalid=frames.point();invalid['0']['2']['4']='bad'
        g=frames.graph();g['0']['8']['0']=[invalid,f]
        g['1']['1'][0]['1']['0'][0]['0']=1
        r=self.frame(g);self.assertEqual(r['layout_controls'],{'column_count':7})
        self.assertFalse(r['other_frames_validated'])
        g['1']['1'][0]['1']['0'][0]['0']=0
        self.assertEqual(self.load(g)['code'],'INVALID_LAYERED_FILE')

    def test_compact_cli_mcp_report_preserves_source_and_creates_no_output(self):
        f=frames.box();f['0']['2'].update({k:v for k,(_,v) in CONTROLS.items()})
        data=frames.s.source(global_=frames.graph(f))
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'source.psd';path.write_bytes(data)
            args=dict(source_path=str(path),id='incoming',color_policy='assume_srgb',
                      expected_sha256=hashlib.sha256(data).hexdigest())
            expected=self.invoke(dict(command='layered.import',**args),1)
            self.assertLess(len(json.dumps(expected).encode()),8192)
            client=Client()
            try:
                client.initialize();r=client.tool('layered.import',**args)
                self.assertTrue(r['isError']);self.assertEqual(r['structuredContent']['error'],expected)
            finally:client.close()
            self.assertEqual(path.read_bytes(),data);self.assertEqual(list(Path(root).iterdir()),[path])


class FrameControlAdmissionTests(unittest.TestCase):
    invoke=editable.EditableLayeredTextTests.invoke
    setUp=editable.EditableLayeredTextTests.setUp
    add_font=editable.EditableLayeredTextTests.add_font
    bindings=editable.EditableLayeredTextTests.bindings
    args=editable.EditableLayeredTextTests.args
    load=editable.EditableLayeredTextTests.load

    def test_recognized_values_still_require_an_editable_layout_mapping(self):
        for version in [1,2]:
            original=p.global_data();self.load(p.source(g=original,version=version))
            for key,(name,value) in CONTROLS.items():
                for explicit in [value,1 if key in ['3','4'] else 0]:
                    g=copy.deepcopy(original);g['0']['8']['0'][0]['0']['2'][key]=explicit
                    r=self.load(p.source(g=g,version=version),1)
                    self.assertEqual(r['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
                    self.assertEqual(r['details']['global_story']['frame']['layout_controls'],{name:explicit})
                    self.assertFalse(r['details']['editable_import_supported'])


if __name__=='__main__':unittest.main()
