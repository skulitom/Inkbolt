"""Original font metrics and geometric pixels for retained first-line placement."""
import copy,json,struct,tempfile,unittest
from pathlib import Path
import test_text_cli as text
from test_mcp import Client
from synthetic_font import geometric_font,pack
from synthetic_unicode_font import sfnt,unicode_font
from synthetic_variable_font import tables,variable_font,variation_store


def metric_font(cap=700,xheight=500,raw=None):
    data=tables(geometric_font() if raw is None else raw);os2=bytearray(96)
    struct.pack_into('>HHHH',os2,0,4,600,400,5);os2[58:62]=b'INKB'
    struct.pack_into('>HHHhhhHH',os2,62,0xC0,32,0xFFFF,800,-200,0,800,200)
    struct.pack_into('>hhHHH',os2,86,xheight,cap,0,32,2);data[b'OS/2']=bytes(os2)
    return sfnt(data)


class FirstBaselineTests(unittest.TestCase):
    invoke=text.TextCliTests.invoke
    document=text.TextCliTests.document
    edit=text.TextCliTests.edit
    inspect=text.TextCliTests.inspect
    pixels=text.TextCliTests.pixels

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name);self.store=self.directory/'fonts';self.sources={}
        self.license=self.directory/'LICENSE.txt';self.license.write_bytes((Path(__file__).resolve().parents[1]/'LICENSE').read_bytes())
        self.font=self.add_font('metrics',metric_font())

    def add_font(self,name,data):
        p=self.directory/(name+'.ttf')
        with p.open('xb') as f:f.write(data)
        self.sources[p]=data
        return self.invoke(dict(command='font.import',source_path=str(p),license_path=str(self.license),store_root=str(self.store)))

    def baselines(self,d):return [line['baseline'] for line in self.inspect(d)['layout']['lines']]

    def test_metrics_minimums_default_and_empty_frames(self):
        default=self.document(text='A\nA',leading=12,overflow='visible')
        self.assertNotIn('first_baseline',default['items'][0]['content']['frame']);self.assertEqual(self.baselines(default),[8,20])
        for kind in ['vector','raster']:
            for metric,start in [('ascent',8),('cap_height',7),('x_height',5),('leading',12),('fixed',0)]:
                for minimum in [0,6,19.25]:
                    d=self.document(kind,text='A\nA',leading=12,overflow='visible',first_baseline=dict(metric=metric,minimum=minimum))
                    expected=max(start,minimum);self.assertEqual(self.baselines(d),[expected,expected+12])
                    self.assertEqual(d['items'][0]['transform'],[1,0,0,1,0,0])
        empty=self.document(text='',first_baseline=dict(metric='cap_height'),overflow='visible')
        self.assertEqual(self.baselines(empty),[7]);self.assertEqual(self.inspect(empty)['layout']['glyphs'],[])
        for p,b in self.sources.items():self.assertEqual(p.read_bytes(),b)

    def test_placement_moves_all_glyphs_without_changing_breaks_advances_or_spacing(self):
        base=self.document(text='AB A\nA',width=60,leading=18,overflow='visible')
        large=dict(font_id='geometry',size=20,fill=[10,40,90,255])
        base=self.edit(base,[dict(op='text_range',id='label',start=1,end=2,style=large)])
        frame=copy.deepcopy(base['items'][0]['content']['frame']);frame['first_baseline']=dict(metric='cap_height',minimum=0)
        shifted=self.edit(base,[dict(op='text',id='label',frame=frame)])
        a=self.inspect(base)['layout'];b=self.inspect(shifted)['layout'];delta=-2
        self.assertEqual(len(a['lines']),len(b['lines']))
        for x,y in zip(a['lines'],b['lines']):
            self.assertAlmostEqual(y['baseline']-x['baseline'],delta)
            self.assertEqual({k:v for k,v in x.items() if k!='baseline'},{k:v for k,v in y.items() if k!='baseline'})
        for x,y in zip(a['glyphs'],b['glyphs']):
            self.assertEqual(x['glyph_id'],y['glyph_id']);self.assertEqual(x['advance'],y['advance'])
            self.assertEqual(x['origin'][0],y['origin'][0]);self.assertAlmostEqual(y['origin'][1]-x['origin'][1],delta)

    def test_cap_height_pixels_and_frame_clip_remain_in_the_original_coordinates(self):
        cap=self.document(kind='raster',text='A',first_baseline=dict(metric='cap_height'))
        self.assertEqual(self.inspect(cap)['layout']['ink_bounds'],[.5,0,4.5,7])
        d=self.document(text='A',width=20,height=8,overflow='clip',first_baseline=dict(metric='fixed',minimum=12))
        d=self.edit(d,[dict(op='transform',id='label',matrix=[1,0,0,1,0,10])]);w,h,p=self.pixels(d)
        for y in range(h):
            for x in range(w):
                if 1<=x<4 and 15<=y<18:self.assertEqual(p[(y*w+x)*4:(y*w+x+1)*4],bytes([25,100,200,255]))
                elif y<15 or y>=18 or x>=5:self.assertEqual(p[(y*w+x)*4:(y*w+x+1)*4],bytes(4))
        outlined=self.edit(d,[dict(op='text_outline',id='label')]);self.assertEqual(self.pixels(d),self.pixels(outlined))
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['overflow']='error'
        overflowing=self.edit(d,[dict(op='text',id='label',frame=frame)])
        self.assertEqual(self.inspect(overflowing,1)['code'],'TEXT_OVERFLOW')

    def test_missing_nonpositive_and_later_line_metrics_are_handled_explicitly(self):
        for name,raw in [('absent',geometric_font()),('zero',metric_font(cap=0)),('negative',metric_font(xheight=-10))]:
            font=self.add_font(name,raw);d=self.document(text='A',overflow='visible')
            d=self.edit(d,[dict(op='font_put',id='other',font=font)])
            frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['style']['font_id']='other'
            frame['first_baseline']=dict(metric='x_height' if name=='negative' else 'cap_height')
            changed=self.edit(d,[dict(op='text',id='label',frame=frame)])
            error=self.inspect(changed,1)
            self.assertEqual(error['code'],'FONT_METRIC_MISSING');self.assertEqual(error['font_id'],'other')
            frame['first_baseline']=dict(metric='fixed',minimum=10)
            self.assertEqual(self.baselines(self.edit(d,[dict(op='text',id='label',frame=frame)])),[10])
        d=self.document(text='A\nA',overflow='visible',first_baseline=dict(metric='cap_height'))
        missing=self.add_font('later',geometric_font());d=self.edit(d,[dict(op='font_put',id='later',font=missing),dict(op='text_range',id='label',start=2,end=3,style=dict(font_id='later',size=10,fill=[1,2,3,255]))])
        self.assertEqual(self.baselines(d),[7,17])

    def test_only_first_line_contributing_fallbacks_supply_the_metric(self):
        east=self.add_font('east',metric_font(cap=900,xheight=600,raw=unicode_font('east')))
        missing=self.add_font('missing-east',unicode_font('east'))
        d=self.document(text='A\u4e00\nA',overflow='visible')
        d=self.edit(d,[dict(op='font_put',id='east',font=east),dict(op='font_put',id='missing',font=missing)])
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['style']['fallback_fonts']=['east','missing']
        for metric,expected in [('cap_height',9),('x_height',6)]:
            frame['first_baseline']=dict(metric=metric)
            changed=self.edit(d,[dict(op='text',id='label',frame=frame)])
            layout=self.inspect(changed)['layout']
            self.assertEqual(layout['lines'][0]['baseline'],expected)
            self.assertEqual([g['font_id'] for g in layout['glyphs']],['geometry','east','geometry'])
        frame['style']['fallback_fonts']=['missing','east']
        changed=self.edit(d,[dict(op='text',id='label',frame=frame)])
        error=self.inspect(changed,1)
        self.assertEqual((error['code'],error['font_id']),('FONT_METRIC_MISSING','missing'))
        frame['text']='A\n\u4e00';frame['first_baseline']=dict(metric='cap_height')
        changed=self.edit(d,[dict(op='text',id='label',frame=frame)])
        # The later fallback has a 1000-unit ascent: 10px line step + 10px ascent - 1px shift.
        self.assertEqual(self.baselines(changed),[7,19])

    def test_variation_metrics_are_taken_from_the_pinned_instance(self):
        data=tables(variable_font());entries=[(b'cpht',[100,-50,0,0]),(b'xhgt',[50,-25,0,0])]
        data[b'MVAR']=pack('HHHHHH',1,0,0,8,2,28)+b''.join(tag+pack('HH',0,i) for i,(tag,_) in enumerate(entries))+variation_store([r for _,r in entries])
        font=self.add_font('variable',sfnt(data));d=self.document(text='A',overflow='visible')
        d=self.edit(d,[dict(op='font_put',id='var',font=font)])
        for metric,default,change in [('cap_height',7,1),('x_height',5,.5)]:
            for weight,factor in [(100,-.5),(400,0),(900,1)]:
                frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['style'].update(font_id='var',font_variations={'var':{'wght':weight}})
                frame['first_baseline']=dict(metric=metric)
                self.assertAlmostEqual(self.baselines(self.edit(d,[dict(op='text',id='label',frame=frame)]))[0],default+change*factor)

    def test_invalid_options_paths_and_unmapped_layered_delivery_fail(self):
        d=self.document(text='A',overflow='visible');base=d['items'][0]['content']['frame']
        for value in [-1,32768.01]:
            frame=copy.deepcopy(base);frame['first_baseline']=dict(metric='ascent',minimum=value)
            self.assertEqual(self.edit(d,[dict(op='text',id='label',frame=frame)],1)['code'],'INVALID_DOCUMENT')
        frame=copy.deepcopy(base);frame['first_baseline']=dict(metric='unknown')
        self.assertEqual(self.edit(d,[dict(op='text',id='label',frame=frame)],1)['code'],'INVALID_REQUEST')
        # A path owns its baseline; rectangular-frame placement cannot be ignored.
        frame=copy.deepcopy(base);frame.update(wrap=False,first_baseline=dict(metric='ascent'))
        frame['path']=dict(geometry={'shape':'path','commands':[{'verb':'move','to':[0,0]},{'verb':'line','to':[40,0]}]})
        error=self.edit(d,[dict(op='text',id='label',frame=frame)],1);self.assertEqual(error['code'],'UNSUPPORTED')
        raster=self.document(kind='raster',text='A',overflow='visible',wrap=False,first_baseline=dict(metric='fixed',minimum=10))
        request=dict(command='document.export',document=raster,format='layered',font_root=str(self.store),layered_options=dict(text=dict(reconstruction='native_layout',shape_owner='OriginalOwner')))
        error=self.invoke(request,1);self.assertEqual(error['code'],'UNSUPPORTED_LAYERED_SEMANTICS');self.assertIn('first-baseline',error['message'])

    def test_snapshot_cli_mcp_and_durable_history_keep_the_control(self):
        d=self.document(text='A',first_baseline=dict(metric='cap_height'))
        saved=self.invoke(dict(command='document.export',document=d,format='snapshot'));self.assertEqual(json.loads(saved['data']),d)
        c=Client()
        try:
            c.initialize();r=c.success('text.inspect',document=d,id='label',font_root=str(self.store))
            self.assertEqual(r,self.inspect(d))
        finally:c.close()
        root=str(self.directory/'sessions');args=dict(session_root=root,session_id='baseline')
        created=self.invoke(dict(command='session.create',**args,request_id='create',document=d,resources=dict(font_root=str(self.store))))
        frame=copy.deepcopy(d['items'][0]['content']['frame']);frame['first_baseline']=dict(metric='fixed',minimum=20)
        edit=dict(command='session.apply',**args,request_id='change',expected_revision=0,action=dict(type='edit',operations=[dict(op='text',id='label',frame=frame)]))
        changed=self.invoke(edit);retry=self.invoke(edit)
        self.assertFalse(changed['replayed']);self.assertTrue(retry['replayed'])
        self.assertEqual(retry,dict(changed,replayed=True))
        self.assertEqual(self.baselines(changed['document']),[20])
        undo=self.invoke(dict(command='session.apply',**args,request_id='undo',expected_revision=1,action=dict(type='undo')))
        self.assertEqual(undo['document']['items'],created['document']['items']);self.assertEqual(self.pixels(undo['document']),self.pixels(d))
        redo=self.invoke(dict(command='session.apply',**args,request_id='redo',expected_revision=2,action=dict(type='redo')))
        self.assertEqual(self.baselines(redo['document']),[20]);self.assertTrue(self.invoke(dict(command='session.verify',**args))['valid'])


if __name__=='__main__':unittest.main()
