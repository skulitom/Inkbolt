"""Original rational ink fixtures and analytic color conversion checks."""
import copy
from fractions import Fraction as F
import hashlib
import itertools
import math
from pathlib import Path
import tempfile
import unittest
from cmyk_fixtures import cmyk_profile, separation
import test_editing_cli as editing
from test_profiles_cli import embedded, decode_srgb
from test_proof_cli import scalar, xyz
from test_mcp import Client
from synthetic_font import geometric_font


def named(swatch, **kw):
    return dict(swatch=swatch, **kw)


def color(cmyk):
    return dict(name='Original process', definition=dict(type='process', color=dict(space='cmyk', components=cmyk)))


def spot(label='Original spot'):
    return dict(name=label, definition=dict(type='spot', alternate=dict(space='cmyk', components=[0, 1, 0, 0])))


def rect(id, fill, box=(0, 0, 8, 8), **kw):
    x, y, w, h = box
    return dict(id=id, content=dict(type='vector', geometry=dict(shape='rect', x=x, y=y, width=w, height=h), fill=fill), **kw)


def project(v):
    return math.floor(v * 255 + F(1, 2))


class VectorPlateTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke

    def document(self, width=8, height=8):
        return self.invoke(dict(command='document.create', id='inks', kind='vector', width=width, height=height))

    def plates(self, d, expected=0, **options):
        options.setdefault('profile', embedded(cmyk_profile()))
        options.setdefault('antialias', 'none')
        return self.invoke(dict(command='document.prepress', document=d, options=options), expected)

    def values(self, d, **options):
        return self.plates(d, samples=[[2, 2]], **options)['samples'][0]['ink_fractions']

    def assertFractions(self, actual, expected):
        self.assertEqual(len(actual), len(expected))
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, float(b), delta=2e-15)

    def test_direct_process_exact_spot_identity_tints_and_scalar_bytes(self):
        d = self.document()
        d['swatches'] = dict(base=color([.5, .25, 0, .125]), z=spot('Same label'), a=spot('Same label'),
                            alias=dict(name='Tint', definition=dict(type='tint', base='a', tint=.5)))
        d['items'] = [rect('base', named('base')), rect('z', named('z', tint=.25, overprint='preserve')),
                      rect('a', named('alias', tint=.5, overprint='preserve_nonzero'))]
        original = copy.deepcopy(d)
        for scale in (1, 2, 4):
            r = self.plates(d, raster_scale=scale, samples=[[0, 0]])
            expected = [F(1, 2), F(1, 4), 0, F(1, 8), F(1, 4), F(1, 4)]
            self.assertFractions(r['samples'][0]['ink_fractions'], expected)
            self.assertEqual([p['id'] for p in r['plates']], ['cyan', 'magenta', 'yellow', 'black', 'a', 'z'])
            interleaved = bytes(v for _ in range((8*scale)**2) for v in map(project, expected))
            self.assertEqual(r['interleaved_sha256'], hashlib.sha256(interleaved).hexdigest())
            for p, v in zip(r['plates'], expected):
                w, h, data, _ = scalar(p)
                self.assertEqual((w, h), (8*scale, 8*scale))
                self.assertEqual(data, bytes([project(v)])*(w*h))
            self.assertFalse(r['source_changed'])
            self.assertFalse(r['profile']['profile_embedded'])
        self.assertEqual(d, original)

    def test_overprint_zero_components_and_zero_spot_tint_are_distinct(self):
        d = self.document()
        d['swatches'] = dict(bottom=color([.75, .5, .25, .125]), top=color([0, .25, 0, .5]), s=spot())
        for mode in ['knockout', 'preserve', 'preserve_nonzero']:
            d['items'] = [rect('b', named('bottom')), rect('s', named('s', tint=.5, overprint='preserve')),
                          rect('t', named('top', opacity=.5, overprint=mode))]
            expected = [F(3, 8), F(3, 8), F(1, 8), F(5, 16), F(1, 4) if mode=='knockout' else F(1, 2)]
            if mode=='preserve_nonzero':
                expected[0] = F(3, 4); expected[2] = F(1, 4)
            self.assertFractions(self.values(d), expected)
        d['items'] = [rect('b', named('bottom')), rect('s', named('s', tint=.5, overprint='preserve')),
                      rect('z', named('s', tint=0, overprint='preserve_nonzero'))]
        self.assertFractions(self.values(d), [F(3, 4), F(1, 2), F(1, 4), F(1, 8), 0])

    def test_translucent_backdrop_keeps_premultiplied_unaddressed_ink(self):
        d = self.document()
        d['swatches'] = dict(c=color([1, 0, 0, 0]), s=spot())
        # In the transparent group, cyan's amount stays .25 while shared alpha
        # rises from .25 to .625. Preserving straight cyan would be incorrect.
        d['items'] = [dict(id='g', opacity=.5, content=dict(type='group', isolated=True)),
                      rect('c', named('c', opacity=.25), parent='g'),
                      rect('s', named('s', opacity=.5, overprint='preserve'), parent='g')]
        self.assertFractions(self.values(d), [F(1, 8), 0, 0, 0, F(1, 4)])

    def test_isolation_pass_through_and_group_masks_follow_rational_equations(self):
        d = self.document()
        d['swatches'] = dict(c=color([1, 0, 0, 0]), m=color([0, 1, 0, 0]), s=spot())
        for isolated, opacity, mask_byte in itertools.product([False, True], [.25, .5, 1], [0, 64, 128, 255]):
            d['items'] = [rect('c', named('c', tint=.75)),
                          dict(id='g', opacity=opacity, mask=dict(width=8, height=8, gray_hex=(bytes([mask_byte])*64).hex()), content=dict(type='group', isolated=isolated)),
                          rect('m', named('m', opacity=.25), parent='g'),
                          rect('s', named('s', opacity=.5, overprint='preserve'), parent='g')]
            g = F(opacity)*F(mask_byte,255)
            alpha = F(5, 8)
            cyan = F(3, 4)*(1-g*alpha) if isolated else F(3, 4)*(1-g*F(1, 4))
            self.assertFractions(self.values(d), [cyan, F(1, 4)*g, 0, 0, F(1, 2)*g])

    def test_opacity_applies_once_to_fill_and_stroke(self):
        d = self.document()
        d['swatches'] = dict(c=color([1, 0, 0, 0]), s=spot())
        item = rect('r', named('c'), box=(2, 2, 4, 4), opacity=.5, fill_opacity=.5)
        item['content']['stroke'] = dict(color=named('s', overprint='preserve'), width=2)
        d['items'] = [item]
        r = self.plates(d, samples=[[2, 2], [4, 4], [1, 2], [0, 0]])
        expected = [[.25, 0, 0, 0, .25], [.25, 0, 0, 0, 0], [0, 0, 0, 0, .25], [0]*5]
        for p, e in zip(r['samples'], expected): self.assertFractions(p['ink_fractions'], e)

    def test_geometry_clips_transformed_masks_and_supersampling(self):
        d = self.document()
        d['swatches'] = dict(c=color([1, 0, 0, 0]))
        d['items'] = [rect('r', named('c'), transform=[1, 0, 0, 1, 2, 1],
                           clip=dict(geometry=dict(shape='rect', x=0, y=0, width=4, height=4)),
                           mask=dict(width=4, height=4, gray_hex=bytes([128]*16).hex()))]
        r = self.plates(d, samples=[[1, 1], [2, 1], [5, 4], [6, 4]])
        for s, e in zip(r['samples'], [0, F(128, 255), F(128, 255), 0]):
            self.assertFractions(s['ink_fractions'], [e, 0, 0, 0])
        d['items'] = [rect('quarter', named('c'), box=(.25, .25, 2, 2))]
        r = self.plates(d, antialias='supersample4', samples=[[0, 0], [1, 1], [2, 2]])
        for s, e in zip(r['samples'], [F(9, 16), 1, F(1, 16)]):
            self.assertFractions(s['ink_fractions'], [e, 0, 0, 0])

    def test_rgb_gray_lab_convert_before_alpha_and_preserve_direct_cmyk(self):
        matrix = [[.4360747,.3850649,.1430804], [.2225045,.7168786,.0606169], [.0139322,.0971045,.7141733]]
        colors = [('srgb', [.2, .4, .7]), ('gray', .4), ('lab', [55, 15, -20])]
        for modern, intent, (space, values) in itertools.product([False, True], ['relative_colorimetric','absolute_colorimetric'], colors):
            d = self.document()
            declaration = dict(space=space, **({'component': values} if space=='gray' else {'components': values}))
            d['swatches'] = dict(p=dict(name='Color', definition=dict(type='process', color=declaration)))
            d['items'] = [rect('p', named('p', opacity=.5))]
            raw_xyz = xyz(values) if space=='lab' else [sum(row[c]*decode_srgb(([values]*3 if space=='gray' else values)[c]) for c in range(3)) for row in matrix]
            white = (.8, .9, .7)
            if intent=='absolute_colorimetric':
                raw_xyz = [v*a/(round(b*65536)/65536) for v,a,b in zip(raw_xyz,[.9642,1,.8249],white)]
            expected = [v*.5 for v in separation([v*(.5 if modern else 32768/65535) for v in raw_xyz])]
            actual = self.values(d, profile=embedded(cmyk_profile(modern=modern,white=white)), intent=intent)
            for a, e in zip(actual,expected): self.assertAlmostEqual(a,e,delta=.00004)

    def test_gradient_conversion_uses_each_color_before_ink_alpha(self):
        d = self.document()
        gradient = dict(type='linear', start=[0,0], end=[8,0], stops=[dict(offset=0,color=[0,0,0,128]),dict(offset=1,color=[255,255,255,128])])
        d['items'] = [rect('g',gradient)]
        r = self.plates(d, samples=[[x,2] for x in range(8)])
        white = [.96422,1,.82521]
        for x,s in enumerate(r['samples']):
            expected = [v*128/255 for v in separation([decode_srgb((x+.5)/8)*w*32768/65535 for w in white])]
            for a,b in zip(s['ink_fractions'],expected): self.assertAlmostEqual(a,b,delta=.00004)

    def test_paper_has_no_ink_and_invisible_spots_do_not_allocate_plates(self):
        d = self.document()
        d['swatches'] = dict(unused=spot(), hidden=spot())
        d['items'] = [dict(id='g',visible=False,content=dict(type='group')),rect('hidden',named('hidden'),parent='g')]
        r = self.plates(d)
        self.assertEqual(len(r['plates']),4)
        for p in r['plates']: self.assertEqual(scalar(p)[2],bytes(64))

    def test_artboard_bleed_and_external_component_keep_native_identity(self):
        d=self.document(40,30);d['swatches']=dict(s=spot())
        d['items']=[dict(id='master',content=dict(type='component_source')),
                    rect('ink',named('s',tint=.5),box=(-1,-2,8,8),parent='master'),
                    dict(id='page',transform=[1,0,0,1,10,10],content=dict(type='frame',frame=dict(role='artboard',width=6,height=4,bleed=dict(left=1,right=3,top=2,bottom=4)))),
                    dict(id='placed',parent='page',content=dict(type='instance',instance=dict(source='master')))]
        original=copy.deepcopy(d)
        for bleed,size in [(False,(6,4)),(True,(10,10))]:
            r=self.plates(d,artboard_id='page',include_bleed=bleed)
            self.assertEqual((r['width'],r['height']),size)
            w,h,data,_=scalar(r['plates'][4]);self.assertEqual(r['plates'][4]['id'],'s')
            expected=bytes(128 if not bleed or (x<8 and y<8) else 0 for y in range(h) for x in range(w))
            self.assertEqual(data,expected)
        self.assertEqual(d,original)

    def test_named_glyphs_use_original_outlines_and_keep_font_source(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);source=root/'original.ttf';raw=geometric_font();source.write_bytes(raw)
            license=root/'LICENSE.txt';license.write_bytes((Path(__file__).resolve().parents[1]/'LICENSE').read_bytes())
            store=root/'fonts';font=self.invoke(dict(command='font.import',source_path=str(source),license_path=str(license),store_root=str(store)))
            d=self.document(24,12);d['swatches']=dict(s=spot());d['fonts']=dict(geometry=font)
            d['items']=[dict(id='label',content=dict(type='text',frame=dict(text='AA',width=24,height=12,style=dict(font_id='geometry',size=10,fill=named('s',tint=.5)))))]
            original=copy.deepcopy(d)
            r=self.invoke(dict(command='document.prepress',document=d,font_root=str(store),options=dict(profile=embedded(cmyk_profile()),antialias='none')))
            w,h,data,_=scalar(r['plates'][4])
            for y in range(h):
                for x in range(w):
                    if 1<=y<8 and (1<=x<4 or 7<=x<10):self.assertEqual(data[y*w+x],128)
                    elif y<1 or y>=8 or x>=11:self.assertEqual(data[y*w+x],0)
            self.assertEqual(d,original);self.assertEqual(source.read_bytes(),raw)

    def test_maximum_named_plate_bound_includes_only_visible_used_identities(self):
        d=self.document(1,1);d['swatches']={f'i{i}':spot() for i in range(29)}
        d['items']=[rect(f'p{i}',named(f'i{i}',tint=.5,overprint='preserve'),box=(0,0,1,1)) for i in range(29)]
        self.assertEqual(self.plates(d,1)['code'],'RESOURCE_LIMIT')
        d['items'][-1]['visible']=False
        self.assertEqual(len(self.plates(d)['plates']),32)

    def test_unsupported_semantics_bounds_and_cancellation_are_explicit(self):
        d = self.document()
        d['swatches'] = dict(c=color([1,0,0,0]))
        d['items'] = [rect('r',named('c'))]
        for patch in [dict(content=dict(type='group',isolated=False),filters=[dict(id='unsupported',operator=dict(type='surface',radius=1,threshold=.25))])]:
            bad = copy.deepcopy(d);bad['items'][0].update(patch)
            self.assertEqual(self.plates(bad,1)['code'],'UNSUPPORTED')
        for options in [dict(include_bleed=True),dict(samples=[[8,0]]),dict(raster_scale=5),dict(samples=[[0,0]]*65)]:
            self.assertEqual(self.plates(d,1,**options)['code'],'INVALID_REQUEST')
        large=self.document(1024,1024);large['swatches']=d['swatches'];large['items']=d['items']
        self.assertEqual(self.plates(large,1)['code'],'RESOURCE_LIMIT')
        with tempfile.TemporaryDirectory() as root:
            marker=Path(root)/'cancel';marker.write_text('cancel')
            for control in [dict(timeout_ms=0),dict(cancel_file=str(marker))]:
                r=self.invoke(dict(command='document.prepress',document=d,options=dict(profile=embedded(cmyk_profile())),control=control),1)
                self.assertEqual(r['code'],'TIMEOUT' if 'timeout_ms' in control else 'CANCELLED')

    def test_agent_read_preserves_saved_revision_and_history(self):
        d = self.document();d['swatches']=dict(c=color([1,0,0,0]));d['items']=[rect('r',named('c'))]
        c=Client();self.addCleanup(c.close);c.initialize()
        with tempfile.TemporaryDirectory() as root:
            session=dict(session_root=root,session_id='native')
            c.success('session.create',**session,request_id='create',document=d)
            before=c.success('session.read',**session)
            options=dict(profile=embedded(cmyk_profile()),samples=[[2,2]],antialias='none')
            first=c.success('document.prepress',document=before['document'],options=options)
            self.assertEqual(first,c.success('document.prepress',document=before['document'],options=options))
            self.assertEqual(before,c.success('session.read',**session))
            self.assertEqual(first,self.plates(d,**options))


if __name__ == '__main__':
    unittest.main()
