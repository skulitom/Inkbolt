"""Original profile assignment/conversion fixtures and independent colour equations."""
import base64
import copy
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import hashlib
import json
import struct
import tempfile
import unittest
import test_editing_cli as editing
import test_samples_cli as samples
import test_profiles_cli as profiles
from test_mcp import Client


def unpack(grid):
    data=bytes.fromhex(grid['data_hex']);fmt={'u8':'B','u16':'H','f32':'f'}[grid['depth']]
    return struct.unpack('<'+fmt*(len(data)//struct.calcsize(fmt)),data)

def tags_of(data):
    return {data[i:i+4]:data[o:o+n] for i in range(132,132+12*int.from_bytes(data[128:132],'big'),12) for o,n in [struct.unpack_from('>II',data,i+4)]}

def repack(header,tags):
    start=132+12*len(tags);directory=[];body=bytearray()
    for name,data in sorted(tags.items()):
        directory.append(name+struct.pack('>II',start+len(body),len(data)));body.extend(data);body.extend(bytes(-len(body)%4))
    header=bytearray(header[:128]);struct.pack_into('>I',header,0,start+len(body))
    return bytes(header)+struct.pack('>I',len(tags))+b''.join(directory)+body

def intent_profile(white=(.9642,1,.8249)):
    """Original RGB LUT profile with intentionally distinguishable intent tables."""
    base=profiles.linear_profile();tags={k:v for k,v in tags_of(base).items() if k in (b'desc',b'cprt',b'wtpt')}
    fixed=lambda v:struct.pack('>i',round(v*65536))
    tags[b'wtpt']=b'XYZ '+bytes(4)+b''.join(fixed(v) for v in white)
    identity=struct.pack('>6H',0,65535,0,65535,0,65535)
    for i,value in enumerate((.2,.4,.6)):
        corner=[round(x*value*32768) for x in (.9642,1,.8249)]
        tags[b'A2B'+bytes([48+i])]=b'mft2'+bytes(4)+bytes([3,3,2,0])+b''.join(fixed(v) for v in [1,0,0,0,1,0,0,0,1])+struct.pack('>HH',2,2)+identity+struct.pack('>24H',*(corner*8))+identity
    header=bytearray(base);header[12:16]=b'scnr'
    return repack(header,tags)

def solve3(matrix,vector):
    """Exact rational elimination, independent of the colour library."""
    a=[row[:]+[v] for row,v in zip(matrix,vector)]
    for i in range(3):
        divisor=a[i][i];a[i]=[v/divisor for v in a[i]]
        for j in range(3):
            if i!=j:
                factor=a[j][i];a[j]=[v-factor*w for v,w in zip(a[j],a[i])]
    return [row[3] for row in a]


class SampleProfileTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    document=samples.SampleTests.document
    edit=samples.SampleTests.edit
    def change(self,d,action,id='source',expected=0):return self.edit(d,[dict(op='sample_profile',id=id,action=action)],expected)
    def pixels(self,d):return bytes.fromhex(self.invoke(dict(command='document.render',document=d))['data'])
    def measured(self,d):return self.invoke(dict(command='sample.measure',document=d,points=[[x,y] for y in range(d['height']) for x in range(d['width'])]))

    def test_assignment_preserves_exact_bytes_conversion_changes_values_and_preserves_appearance(self):
        for depth,maximum in [('u8',255),('u16',65535),('f32',1)]:
            values=[v for k in (0,.125,.25,.5,.75,1) for v in ([round(k*maximum),round((1-k)*maximum),round(.5*maximum),maximum] if depth!='f32' else [k,1-k,.5,1])]
            d=self.document([samples.layer(values,depth)]);before=copy.deepcopy(d)
            profile=profiles.builtin('linear_srgb')
            assigned=self.change(d,dict(type='assign',profile=profile));grid=assigned['items'][0]['content']['grid']
            self.assertEqual(grid['data_hex'],d['items'][0]['content']['grid']['data_hex']);self.assertEqual(grid['encoding'],'profiled_rgb')
            self.assertEqual(grid['profile'],profile);self.assertNotEqual(self.pixels(assigned),self.pixels(d))
            converted=self.change(d,dict(type='convert',profile=profile));converted_grid=converted['items'][0]['content']['grid']
            self.assertNotEqual(converted_grid['data_hex'],grid['data_hex']);self.assertEqual(unpack(converted_grid)[3::4],tuple(values[3::4]))
            if depth!='u8':self.assertLessEqual(max(abs(a-b) for a,b in zip(self.pixels(converted),self.pixels(d))),1)
            with localcontext() as c:
                c.prec=50
                actual=unpack(converted_grid)
                for i in range(0,len(values),4):
                    for channel in range(3):
                        v=D(str(values[i+channel]))/maximum
                        reference=v/D('12.92') if v<=D('.04045') else ((v+D('.055'))/D('1.055'))**D('2.4')
                        self.assertLessEqual(abs(actual[i+channel]/maximum-float(reference)),(.51/maximum if depth!='f32' else 0)+.00006)
            cleared=self.change(assigned,dict(type='assign',profile=None));self.assertEqual(self.pixels(cleared),self.pixels(d))
            self.assertEqual(d,before)

    def test_same_profile_identity_gray_expansion_hidden_rgb_and_all_intents(self):
        for depth,values in [('u8',[33,255,79,0,127,1]),('u16',[9017,65535,23041,0,32768,1]),('f32',[.137,1,.312,0,.5,2**-149])]:
            d=self.document([samples.layer(values,depth,'gray_alpha')])
            tagged=self.change(d,dict(type='assign',profile=profiles.builtin('srgb')))
            for intent in ('relative_colorimetric','absolute_colorimetric','perceptual','saturation'):
                identical=self.change(tagged,dict(type='convert',profile=profiles.builtin('srgb'),intent=intent))
                self.assertEqual(identical['items'][0]['content'],tagged['items'][0]['content'])
            converted=self.change(tagged,dict(type='convert',profile=profiles.builtin('linear_srgb')));g=converted['items'][0]['content']['grid'];actual=unpack(g)
            self.assertEqual(g['channels'],'rgba');self.assertEqual(actual[3::4],unpack(tagged['items'][0]['content']['grid'])[1::2])
            self.assertGreater(actual[4],0);self.assertEqual(actual[4],actual[5]);self.assertEqual(actual[5],actual[6])

    def test_profiled_source_linear_compositing_uses_linear_values_before_blending(self):
        a=samples.layer([.2,.4,.6,1],depth='f32',id='base')
        b=samples.layer([.8,.6,.4,.5],depth='f32',id='top')
        d=self.document([a,b])
        for id in ('base','top'):d=self.change(d,dict(type='assign',profile=profiles.builtin('linear_srgb')),id)
        linear=self.edit(d,[dict(op='working_space',color_space='linear_srgb')])
        measured=self.measured(linear)
        self.assertEqual(measured['working_space'],'linear_srgb')
        expected=[.5,.5,.5,1]
        for v,q in zip(measured['samples'][0]['rgba'],expected):self.assertAlmostEqual(v,q,delta=.0001)
        encoded=self.measured(d)['samples'][0]['rgba']
        expected=[(profiles.encode_srgb(x)+profiles.encode_srgb(y))/2 for x,y in zip([.2,.4,.6],[.8,.6,.4])]+[1]
        for v,q in zip(encoded,expected):self.assertAlmostEqual(v,q,delta=.0001)
        self.assertGreater(abs(encoded[0]-profiles.encode_srgb(.5)),.03)

    def test_exact_embedded_profile_snapshots_export_and_source_identity(self):
        p=profiles.linear_profile(gamma=1.8);profile=profiles.embedded(p)
        d=self.document([samples.layer([12000,24000,48000,65535,36000,16000,24000,32768])])
        tagged=self.change(d,dict(type='assign',profile=profile));before=copy.deepcopy(tagged)
        saved=json.loads(self.invoke(dict(command='document.export',document=tagged,format='snapshot'))['data'])
        self.assertEqual(self.invoke(dict(command='document.validate',document=saved)),tagged)
        self.assertEqual(base64.b64decode(saved['items'][0]['content']['grid']['profile']['data']),p)
        exported=self.edit(tagged,[dict(op='output_profile',profile=profile)])
        artifact=self.invoke(dict(command='document.export',document=exported,format='png'))
        self.assertEqual(profiles.png_profile(base64.b64decode(artifact['data'])),p)
        self.assertEqual(tagged,before)

    def test_locks_invalid_contexts_atomic_failure_and_cancellation(self):
        d=self.document([samples.layer([12000,24000,48000,65535])]);assign=dict(type='assign',profile=profiles.builtin('display_p3'))
        locked=self.edit(d,[dict(op='properties',id='source',locked=True)])
        self.assertEqual(self.change(locked,assign,expected=1)['code'],'LOCKED')
        before=copy.deepcopy(d);tagged=self.change(d,assign)
        bad=copy.deepcopy(tagged);bad['items'][0]['content']['grid'].pop('profile')
        self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'INVALID_DOCUMENT')
        bad=copy.deepcopy(tagged);bad['items'][0]['content']['grid']['encoding']='linear_srgb'
        self.assertEqual(self.invoke(dict(command='document.validate',document=bad),1)['code'],'UNSUPPORTED_HDR_MODE')
        self.assertEqual(self.edit(tagged,[dict(op='sample_convert',id='source',conversion=dict(depth='u8',channels='rgba'))],1)['code'],'PROFILE_CONVERSION_REQUIRED')
        self.assertEqual(self.change(d,dict(type='convert',profile=None,intent='not_an_intent'),expected=1)['code'],'INVALID_REQUEST')
        malformed=profiles.embedded(b'x'*132)
        self.assertEqual(self.change(d,dict(type='assign',profile=malformed),expected=1)['code'],'INVALID_PROFILE')
        self.edit(d,[dict(op='sample_profile',id='source',action=assign),dict(op='remove',id='missing')],1)
        self.assertEqual(self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='sample_profile',id='source',action=assign)],control=dict(timeout_ms=0)),1)['code'],'TIMEOUT')
        self.assertEqual(d,before)

    def test_mcp_assignment_conversion_undo_redo_and_reopen(self):
        d=self.document([samples.layer([12000,24000,48000,65535])]);original=copy.deepcopy(d)
        with tempfile.TemporaryDirectory() as root:
            c=Client();c.initialize();s=dict(session_root=root,session_id='profiles')
            try:
                c.success('session.create',**s,request_id='create',document=d)
                a=c.success('session.apply',**s,expected_revision=0,request_id='assign',action=dict(type='edit',operations=[dict(op='sample_profile',id='source',action=dict(type='assign',profile=profiles.builtin('linear_srgb')))]))['document']
                b=c.success('session.apply',**s,expected_revision=1,request_id='convert',action=dict(type='edit',operations=[dict(op='sample_profile',id='source',action=dict(type='convert',profile=None,intent='relative_colorimetric'))]))['document']
                self.assertEqual(b['items'][0]['content']['grid'].get('profile'),None)
                self.assertLessEqual(max(abs(x-y) for x,y in zip(self.pixels(a),self.pixels(b))),1)
                u=c.success('session.apply',**s,expected_revision=2,request_id='undo',action=dict(type='undo'))['document'];self.assertEqual(u['items'],a['items'])
                c.success('session.apply',**s,expected_revision=3,request_id='redo',action=dict(type='redo'))
            finally:c.close()
            c=Client();c.initialize()
            try:
                reopened=c.success('session.read',**s)['document'];self.assertEqual(reopened['items'],b['items']);c.success('session.verify',**s)
            finally:c.close()
        self.assertEqual(d,original)

    def test_distinct_intent_tables_and_absolute_white_scale_against_exact_pcs_equations(self):
        target=profiles.linear_profile();tags=tags_of(target)
        matrix=[[F(struct.unpack_from('>i',tags[c+b'XYZ'],8+4*r)[0],65536) for c in (b'r',b'g',b'b')] for r in range(3)]
        d=self.document([samples.layer([.1,.3,.7,1,.9,.2,.4,0],depth='f32')])
        for white in ((.9642,1,.8249),(.8,1,.6)):
            assigned=self.change(d,dict(type='assign',profile=profiles.embedded(intent_profile(white))))
            for intent,value in [('perceptual',.2),('relative_colorimetric',.4),('saturation',.6),('absolute_colorimetric',.4)]:
                xyz=[F(round(v*value*32768),32768) for v in (.9642,1,.8249)]
                if intent=='absolute_colorimetric':xyz=[v*F(round(w*65536),round(t*65536)) for v,w,t in zip(xyz,white,(.9642,1,.8249))]
                expected=solve3(matrix,xyz)
                converted=self.change(assigned,dict(type='convert',profile=profiles.embedded(target),intent=intent));raw=unpack(converted['items'][0]['content']['grid'])
                tolerance=.00015 if intent=='absolute_colorimetric' else .00004
                for i in (0,4):
                    for c in range(3):self.assertLessEqual(abs(raw[i+c]-float(expected[c])),tolerance,(white,intent,c,raw[i+c],expected[c]))
                self.assertEqual(raw[3::4],(1,0))

    def test_destination_intent_tables_and_default_fallback_are_not_ignored(self):
        base=intent_profile();tags=tags_of(base);identity=struct.pack('>6H',0,65535,0,65535,0,65535)
        fixed=lambda v:struct.pack('>i',v*65536)
        for i,value in enumerate((.15,.35,.55)):
            samples16=[round(value*65535)]*24
            tags[b'B2A'+bytes([48+i])]=b'mft2'+bytes(4)+bytes([3,3,2,0])+b''.join(fixed(v) for v in [1,0,0,0,1,0,0,0,1])+struct.pack('>HH',2,2)+identity+struct.pack('>24H',*samples16)+identity
        target=profiles.embedded(repack(base,tags));d=self.document([samples.layer([.1,.3,.7,1],depth='f32')])
        for intent,value in [('perceptual',.15),('relative_colorimetric',.35),('saturation',.55),('absolute_colorimetric',.35)]:
            converted=self.change(d,dict(type='convert',profile=target,intent=intent));raw=unpack(converted['items'][0]['content']['grid'])
            for v in raw[:3]:self.assertAlmostEqual(v,round(value*65535)/65535,delta=.00004)
        source_tags=tags_of(base);source_tags.pop(b'A2B1');source_tags.pop(b'A2B2')
        assigned=self.change(d,dict(type='assign',profile=profiles.embedded(repack(base,source_tags))))
        results=[]
        for intent in ['perceptual','relative_colorimetric','saturation']:
            results.append(unpack(self.change(assigned,dict(type='convert',profile=profiles.builtin('linear_srgb'),intent=intent))['items'][0]['content']['grid']))
        self.assertEqual(results[0],results[1]);self.assertEqual(results[1],results[2])

    def test_profile_budget_and_absolute_connection_range_fail_without_mutation(self):
        d=self.document([samples.layer([.1,.3,.7,1],depth='f32')])
        assigned=self.change(d,dict(type='assign',profile=profiles.embedded(intent_profile((8,1,.6)))))
        before=copy.deepcopy(assigned)
        self.assertEqual(self.change(assigned,dict(type='convert',profile=profiles.embedded(profiles.linear_profile()),intent='absolute_colorimetric'),expected=1)['code'],'UNSUPPORTED_PROFILE_RANGE')
        self.assertEqual(assigned,before)
        profile=profiles.embedded(profiles.linear_profile(large=True));item=copy.deepcopy(d['items'][0]);item['content']['grid'].update(encoding='profiled_rgb',profile=profile)
        large=copy.deepcopy(d);large['items']=[dict(item,id='p'+str(i)) for i in range(4)]
        self.assertEqual(self.invoke(dict(command='document.validate',document=large),1)['code'],'RESOURCE_LIMIT')

    def test_wide_gamut_matrix_charts_keep_signed_linear_values_and_report_native_clipping(self):
        black=self.document([samples.layer([0.,0.,0.,1.],depth='f32')]);matrices={}
        for name in ('display_p3','linear_srgb'):
            tagged=self.edit(black,[dict(op='output_profile',profile=profiles.builtin(name))])
            output=self.invoke(dict(command='document.export',document=tagged,format='png'))
            tags=tags_of(profiles.png_profile(base64.b64decode(output['data'])))
            matrices[name]=[[F(struct.unpack_from('>i',tags[c+b'XYZ'],8+4*r)[0],65536) for c in (b'r',b'g',b'b')] for r in range(3)]
        colors=[(r,g,b) for r in (0,.25,.5,1) for g in (0,.25,.5,1) for b in (0,.25,.5,1)]
        d=self.document([samples.layer([v for p in colors for v in (*p,1)],depth='f32',w=8)])
        d=self.change(d,dict(type='assign',profile=profiles.builtin('display_p3')))
        linear=self.edit(d,[dict(op='working_space',color_space='linear_srgb')]);measured=self.measured(linear)
        self.assertGreater(measured['negative_color_channels'],0);self.assertGreater(measured['above_white_color_channels'],0)
        for color,sample in zip(colors,measured['samples']):
            v=[F(profiles.decode_srgb(x)) for x in color];xyz=[sum(a*b for a,b in zip(row,v)) for row in matrices['display_p3']];expected=solve3(matrices['linear_srgb'],xyz)
            for a,b in zip(sample['rgba'][:3],expected):self.assertAlmostEqual(a,float(b),delta=.00003)
        green=self.document([samples.layer([0.,1.,0.,1.],depth='f32')]);green=self.change(green,dict(type='assign',profile=profiles.builtin('display_p3')))
        response=self.invoke(dict(command='document.edit',document=green,expected_revision=green['revision'],operations=[dict(op='sample_profile',id='source',action=dict(type='convert',profile=profiles.builtin('linear_srgb')))]))
        self.assertEqual(unpack(response['document']['items'][0]['content']['grid']),(0,1,0,1))
        self.assertEqual(response['changes'][0]['details']['clipped_color_channels'],3)

    def test_builtin_media_white_and_adaptation_against_rational_bradford_equations(self):
        d=self.document([samples.layer([0,0,0,65535])])
        cone=[[F(str(v)) for v in row] for row in [[.8951,.2664,-.1614],[-.7502,1.7135,.0367],[.0389,-.0685,1.0296]]]
        source=[F(3127,3290),F(1),F(3583,3290)];target=[F('0.9642'),F(1),F('0.8249')]
        mul=lambda a,b:[sum(x*y for x,y in zip(row,b)) for row in a]
        ratio=[b/a for a,b in zip(mul(cone,source),mul(cone,target))]
        columns=[solve3(cone,[ratio[i]*cone[i][j] for i in range(3)]) for j in range(3)]
        for name in ['srgb','linear_srgb','display_p3']:
            tagged=self.edit(d,[dict(op='output_profile',profile=profiles.builtin(name))])
            artifact=self.invoke(dict(command='document.export',document=tagged,format='png'))
            data=profiles.png_profile(base64.b64decode(artifact['data']));tags=tags_of(data)
            self.assertEqual(data[12:16],b'mntr')
            self.assertEqual(struct.unpack_from('>3i',tags[b'wtpt'],8),tuple(round(x*65536) for x in target))
            matrix=[[F(struct.unpack_from('>i',tags[b'chad'],8+4*(i*3+j))[0],65536) for j in range(3)] for i in range(3)]
            for i in range(3):
                for j in range(3):self.assertLessEqual(abs(matrix[i][j]-columns[j][i]),F(1,65536))
            for actual,expected in zip(mul(matrix,source),target):self.assertLessEqual(abs(actual-expected),F(3,65536))

    def test_absolute_matrix_scaling_and_nonlinear_gamut_clipping_against_equations(self):
        target=profiles.linear_profile(gamma=1.8);tags=tags_of(target)
        tags[b'wtpt']=b'XYZ '+bytes(4)+struct.pack('>3i',*(round(v*65536) for v in (.8,.9,.6)))
        header=bytearray(target);header[12:16]=b'prtr';target=repack(header,tags)
        matrix=[[F(struct.unpack_from('>i',tags[c+b'XYZ'],8+4*r)[0],65536) for c in (b'r',b'g',b'b')] for r in range(3)]
        colors=[(r,g,b) for r in (0,.125,.5,1) for g in (0,.125,.5,1) for b in (0,.125,.5,1)]
        d=self.document([samples.layer([v for p in colors for v in (*p,1)],depth='f32',w=8)])
        tagged=self.change(d,dict(type='assign',profile=profiles.builtin('display_p3')))
        output=self.invoke(dict(command='document.export',document=self.edit(d,[dict(op='output_profile',profile=profiles.builtin('display_p3'))]),format='png'))
        source_tags=tags_of(profiles.png_profile(base64.b64decode(output['data'])))
        source_matrix=[[F(struct.unpack_from('>i',source_tags[c+b'XYZ'],8+4*r)[0],65536) for c in (b'r',b'g',b'b')] for r in range(3)]
        scale=[F(a,b) for a,b in zip(struct.unpack_from('>3i',source_tags[b'wtpt'],8),struct.unpack_from('>3i',tags[b'wtpt'],8))]
        converted=self.change(tagged,dict(type='convert',profile=profiles.embedded(target),intent='absolute_colorimetric'))
        actual=unpack(converted['items'][0]['content']['grid']);gamma=F(round(1.8*256),256)
        for i,color in enumerate(colors):
            rgb=[F(profiles.decode_srgb(v)) for v in color]
            xyz=[sum(a*b for a,b in zip(row,rgb))*s for row,s in zip(source_matrix,scale)]
            expected=[min(1,max(0,float(v)))**float(1/gamma) for v in solve3(matrix,xyz)]
            for c,v in enumerate(expected):self.assertAlmostEqual(actual[4*i+c],v,delta=.0002)
            self.assertEqual(actual[4*i+3],1)

    def test_linear_destination_with_gamma_sampled_and_distinct_channel_curves(self):
        colors=[(r,g,b) for r in (0,.125,.5,.75,1) for g in (0,.125,.5,.75,1) for b in (0,.125,.5,.75,1)]
        d=self.document([samples.layer([v for p in colors for v in (*p,1)],depth='f32',w=5)])
        artifact=self.invoke(dict(command='document.export',document=self.edit(d,[dict(op='output_profile',profile=profiles.builtin('linear_srgb'))]),format='png'))
        dest=tags_of(profiles.png_profile(base64.b64decode(artifact['data'])))
        matrix=lambda t:[[F(struct.unpack_from('>i',t[c+b'XYZ'],8+4*r)[0],65536) for c in (b'r',b'g',b'b')] for r in range(3)]
        destination=matrix(dest);base=profiles.linear_profile(1.8)
        for kind in ['gamma','identity','sampled','distinct']:
            tags=tags_of(base);curves=[]
            for c,color in enumerate(b'rgb'):
                gamma=[1.8,2.2,1.0][c] if kind=='distinct' else 1.8
                table=([round((i/32)**([1.8,2.2,1.0][c])*65535) for i in range(33)] if kind=='sampled' else ([] if kind=='identity' else [round(gamma*256)]))
                tags[bytes([color])+b'TRC']=b'curv'+bytes(4)+struct.pack('>I',len(table))+struct.pack('>'+'H'*len(table),*table);curves.append(table)
            source=matrix(tags);assigned=self.change(d,dict(type='assign',profile=profiles.embedded(repack(base,tags))))
            linear=self.edit(assigned,[dict(op='working_space',color_space='linear_srgb')]);actual=self.measured(linear)['samples']
            for rgb,got in zip(colors,actual):
                values=[]
                for x,table in zip(rgb,curves):
                    if len(table)==0:v=x
                    elif len(table)==1:v=x**(table[0]/256)
                    else:
                        u=x*(len(table)-1);i=min(int(u),len(table)-2);v=(table[i]+(table[i+1]-table[i])*(u-i))/65535
                    values.append(F(v))
                expected=solve3(destination,[sum(a*b for a,b in zip(row,values)) for row in source])
                for v,e in zip(got['rgba'][:3],expected):self.assertAlmostEqual(v,float(e),delta=.00005,msg=(kind,rgb))


if __name__=='__main__':unittest.main()
