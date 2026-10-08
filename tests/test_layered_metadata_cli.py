"""Original descriptor, ancillary-state and hostile-framing fixtures."""
import struct,unittest
import layered_fixtures as f
import test_layered_cli as core

def key(s):
    b=s.encode('ascii');return f.U32(0 if len(b)==4 else len(b))+b
def desc(cls,fields,name='\0'):
    return f.unicode(name)+key(cls)+f.U32(len(fields))+b''.join(key(k)+value for k,value in fields)
def obj(cls,fields):return b'Objc'+desc(cls,fields)
def versioned(cls,fields):return f.U32(16)+desc(cls,fields)
def txt(s):return b'TEXT'+f.unicode(s+'\0')
def boolean(v):return b'bool'+bytes([v])
def integer(v):return b'long'+f.I32(v)
def number(v):return b'doub'+struct.pack('>d',v)
def enum(kind,value):return b'enum'+key(kind)+key(value)
def sequence(values):return b'VlLs'+f.U32(len(values))+b''.join(values)
def global_tag(k,data):return b'8BIM'+k+f.section(data)+bytes(-len(data)%4)
def timestamp(value=172800.125,extra=[],cls='metadata',padding=0):
    payload=versioned(cls,[('layerTime',number(value))]+extra)+bytes(padding)
    return f.tag(b'shmd',f.U32(1)+b'8BIMcust'+bytes(4)+f.section(payload))
def ocio(kind='icc',display='',view='',extra=[]):
    return versioned('documentColorManagementInfo',[('Knd ',txt(kind)),('ocio_display_view',obj('viewColorManagementInfo',[('display',txt(display)),('view',txt(view))]))]+extra)
def provenance(enabled=False,guid='',tail=bytes(8)):
    return f.U32(3)+versioned('null',[('enab',boolean(enabled)),('generationalGuid',txt(guid))])+tail
def generation(active=False,values=[]):
    return versioned('genTechInfo',[('isUsingGenTech',integer(active)),('externalModelList',sequence(values))])
def backend():
    ver=obj('null',[(k,integer(v)) for k,v in [('major',1),('minor',2),('fix',3)]])
    return versioned('null',[('Vrsn',ver),('psVersion',ver),('description',txt('original fixture')),('reason',txt('')),
        ('Engn',enum('Engn','compCoreGPU')),('enableCompCoreGPU',enum('enable','feature')),('enableCompCoreThreads',enum('enable','feature')),('compCoreGPUSupport',enum('reason','supported'))])

class LayeredMetadataTests(unittest.TestCase):
    invoke=core.LayeredTests.invoke
    read=core.LayeredTests.read
    pixels=core.LayeredTests.pixels
    def source(self,**kwargs):
        layer=dict(name='original \u0394',width=2,height=1,rgba=[10,20,30,64,200,80,40,255])
        layer.update(kwargs.pop('layer',{}));return f.make([layer],**kwargs)
    def load(self,raw,expected=0):return self.read(raw,expected,color_policy='assume_srgb')
    def test_density_selectors_are_display_units_and_never_rescale_fixed_ppi(self):
        for units in [(1,1),(1,2),(2,1),(2,2)]:
            for ppi in [72,96,300.25]:
                data=f.U32(round(ppi*65536))+f.U16(units[0])+f.U16(2)+f.U32(round(ppi*65536))+f.U16(units[1])+f.U16(3)
                r=self.load(self.source(extra_resources=f.resource(1005,data)));self.assertEqual(r['document']['resolution_ppi'],ppi);self.assertTrue(r['resolution_declared'])
        for xu,yu,y in [(0,1,96),(1,3,96),(1,1,120)]:
            data=f.U32(96*65536)+f.U16(xu)+f.U16(1)+f.U32(y*65536)+f.U16(yu)+f.U16(1)
            self.assertIn(self.load(self.source(extra_resources=f.resource(1005,data)),1)['code'],['INVALID_LAYERED_FILE','UNSUPPORTED_LAYERED_SEMANTICS'])
    def test_timestamp_and_inactive_global_metadata_preserve_exact_original_document(self):
        baseline=self.load(self.source())['document']
        for pad in range(4):
            globals=b''.join(global_tag(k,v) for k,v in [(b'Patt',b''),(b'CAI ',provenance()),(b'OCIO',ocio()),(b'GenI',generation()),(b'cinf',backend()),(b'FMsk',f.U16(0)+f.U16(1234)*4+f.U16(35))])
            r=self.load(self.source(layer=dict(extra=timestamp(padding=pad)),global_extra=globals));self.assertEqual(r['document'],baseline);self.assertEqual(len(r['omitted_nonappearance_records']),7);self.assertIn('shmd:layer_timestamp',r['omitted_nonappearance_records'])
        r=self.load(self.source(layer=dict(extra=f.tag(b'shmd',f.U32(0)))));self.assertEqual(r['document'],baseline)
        for padding in [bytes(4),b'\1']:self.assertEqual(self.load(self.source(global_extra=global_tag(b'GenI',generation()+padding)),1)['code'],'INVALID_LAYERED_FILE')
    def test_active_colour_generation_provenance_and_unknown_semantics_fail(self):
        for k,v in [(b'OCIO',ocio(kind='ocio')),(b'OCIO',ocio(display='monitor')),(b'OCIO',ocio(view='linear')),(b'OCIO',ocio(extra=[('gamma',number(2.2))])),(b'GenI',generation(True)),(b'GenI',generation(values=[txt('model')])),(b'CAI ',provenance(True)),(b'CAI ',provenance(guid='id')),(b'CAI ',provenance(tail=f.U32(1)+f.U32(0))),(b'Patt',b'pattern'),(b'FMsk',f.U16(8)+bytes(10)),(b'FMsk',bytes(10)+f.U16(101)),(b'zzzz',b'')]:
            with self.subTest(key=k,payload=v):self.assertEqual(self.load(self.source(global_extra=global_tag(k,v)),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for extra in [timestamp(extra=[('animation',boolean(1))]),timestamp(cls='animation'),timestamp(value=-1)]:
            self.assertEqual(self.load(self.source(layer=dict(extra=extra)),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
    def test_descriptor_duplicate_keys_types_versions_unicode_and_nonfinite_fail(self):
        bad=[versioned('genTechInfo',[('isUsingGenTech',integer(0)),('isUsingGenTech',integer(0)),('externalModelList',sequence([]))]),versioned('genTechInfo',[('isUsingGenTech',boolean(2))]),f.U32(15)+generation()[4:],f.U32(16)+f.U32(1)+b'\xd8\0',versioned('genTechInfo',[('isUsingGenTech',b'alis'+f.U32(0))]),versioned('genTechInfo',[('isUsingGenTech',boolean(0)),('externalModelList',sequence([]))])]
        for data in bad:self.assertIn(self.load(self.source(global_extra=global_tag(b'GenI',data)),1)['code'],['INVALID_LAYERED_FILE','UNSUPPORTED_LAYERED_SEMANTICS'])
        for n in [float('inf'),float('-inf'),float('nan')]:self.assertEqual(self.load(self.source(layer=dict(extra=timestamp(n))),1)['code'],'INVALID_LAYERED_FILE')
        for suffix in [b'\1',bytes(4)]:self.assertEqual(self.load(self.source(layer=dict(extra=timestamp()+suffix)),1)['code'],'INVALID_LAYERED_FILE')
    def test_descriptor_resource_bounds_and_unbounded_lists_fail_before_allocation(self):
        nested=sequence([])
        for _ in range(10):nested=sequence([nested])
        wide=sequence([sequence([integer(n) for n in range(128)]) for _ in range(5)])
        for data in [versioned('genTechInfo',[('externalModelList',nested)]),versioned('genTechInfo',[('externalModelList',wide)]),versioned('genTechInfo',[('externalModelList',b'VlLs'+f.U32(2**32-1))]),f.U32(16)+f.unicode('')+f.U32(2**32-1),f.U32(16)+f.U32(1025),bytes(65537)]:
            self.assertEqual(self.load(self.source(global_extra=global_tag(b'GenI',data)),1)['code'],'RESOURCE_LIMIT')
    def test_global_alignment_truncation_duplicates_and_layer_metadata_envelopes(self):
        good=global_tag(b'CAI ',provenance())
        for data in [good[:-1],good+good,good[:-1]+b'\1',b'8B64'+good[4:],good+bytes(4)]:
            self.assertEqual(self.load(self.source(global_extra=data),1)['code'],'INVALID_LAYERED_FILE')
        for data in [f.U32(1)+b'8BIMcust'+b'\2'+bytes(3)+f.U32(0),f.U32(1)+b'8BIMcust'+b'\0\1\0\0'+f.U32(0),f.U32(1)+b'8BIMcust'+bytes(4)+f.U32(2**32-1)]:
            self.assertEqual(self.load(self.source(layer=dict(extra=f.tag(b'shmd',data))),1)['code'],'INVALID_LAYERED_FILE')
    def test_transparency_metadata_requires_a_single_matching_channel_and_reports_omissions(self):
        records=[(1006,b'\5alpha'),(1045,f.unicode('alpha\0')),(1053,f.U32(0)),(1077,f.U32(1)+bytes(10)+f.U16(50)+b'\1')]
        baseline=self.load(self.source())['document']
        for k,v in records:
            r=self.load(self.source(extra_resources=f.resource(k,v)));self.assertEqual(r['document'],baseline);self.assertIn(f'resource:{k}',r['omitted_nonappearance_records'])
            self.assertEqual(self.load(self.source(extra_resources=f.resource(k,v),merged_channels=3),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
            extra=(v[4:] if k==1077 else v)
            self.assertEqual(self.load(self.source(extra_resources=f.resource(k,v+extra)),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for k,v in [(1053,f.U32(12)),(1077,f.U32(1)+bytes(12)+b'\2')]:self.assertEqual(self.load(self.source(extra_resources=f.resource(k,v)),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
    def test_print_resources_are_reported_without_trusting_them_as_document_metadata(self):
        resources=b''.join(f.resource(k,v) for k,v in [(10000,f.U16(1)+bytes(2)+f.U32(10)+f.U16(2)),(1013,bytes(72)),(1016,bytes(112)),(1050,b'original export-slice state')])
        r=self.load(self.source(extra_resources=resources));self.assertEqual(r['document'],self.load(self.source())['document']);self.assertEqual(len(r['omitted_nonappearance_records']),4)
        for bad in [bytes(10),f.U16(1)+b'\2'+bytes(7),f.U16(1)+b'\0\1'+bytes(6)]:self.assertEqual(self.load(self.source(extra_resources=f.resource(10000,bad)),1)['code'],'INVALID_LAYERED_FILE')

    def test_empty_guide_records_require_known_version_and_reject_nonempty_identity_or_geometry(self):
        baseline=self.load(self.source())['document']
        for spacing in [1,32,768,1000000]:
            resources=f.resource(1092,f.U32(2)+f.U32(spacing)*2+f.U32(0))+f.resource(1097,f.U32(0))
            r=self.load(self.source(extra_resources=resources));self.assertEqual(r['document'],baseline);self.assertEqual(r['omitted_nonappearance_records'],['resource:1092:empty_guides','resource:1097:empty_guide_identities'])
            r=self.load(self.source(extra_resources=f.resource(1032,f.U32(1)+f.U32(spacing)*2+f.U32(0))));self.assertEqual(r['document'],baseline)
        self.assertEqual(self.load(self.source(extra_resources=f.resource(1032,f.U32(1)+f.U32(32)*2+f.U32(1)+bytes(5))),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for k,v in [(1092,f.U32(3)+f.U32(32)*2+f.U32(0)),(1092,f.U32(2)+f.U32(0)+f.U32(32)+f.U32(0)),(1092,f.U32(2)+f.U32(32)*2+f.U32(1)+bytes(9)),(1097,f.U32(1)+bytes(4))]:
            self.assertEqual(self.load(self.source(extra_resources=f.resource(k,v)),1)['code'],'UNSUPPORTED_LAYERED_SEMANTICS')
        for k,v in [(1092,f.U32(2)+f.U32(32)*2+f.U32(0)+bytes(4)),(1097,bytes(8)),(1097,bytes(3))]:
            self.assertEqual(self.load(self.source(extra_resources=f.resource(k,v)),1)['code'],'INVALID_LAYERED_FILE')

if __name__=='__main__':unittest.main()
