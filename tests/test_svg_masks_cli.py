"""Independent SVG mask coordinates, rational composition, editing and history."""
import base64
import copy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import test_editing_cli as editing
import test_svg_text_cli as text_tests
from test_artwork_masks_cli import byte
from test_layer_clipping_cli import premul, over
from test_svg_import_cli import svg
from test_mcp import Client


class SvgMaskTests(unittest.TestCase):
    invoke=editing.EditingCliTests.invoke
    def imported(self,body,attrs='width="32" height="24"',expected=0,**kw):
        return self.invoke(dict(command='svg.import',id='svg-masks',source=dict(kind='text',text=svg(body,attrs)),**kw),expected)
    def item(self,r,id):
        mapped=next(v['item_id'] for v in r['mapping'] if v['source_id']==id)
        return next(i for i in r['document']['items'] if i['id']==mapped)
    def pixels(self,d,scale=1,**kw):
        r=self.invoke(dict(command='document.export',document=d,format='png',scale=scale,**kw))
        return editing.png_pixels(base64.b64decode(r['data']))[:3]
    def alpha(self,d,oracle,scale=1,**kw):
        w,h,p=self.pixels(d,scale,**kw)
        for y in range(h):
            for x in range(w):
                self.assertEqual(p[(y*w+x)*4+3],byte(oracle((x+.5)/scale,(y+.5)/scale)),(x,y))
    def edit(self,d,ops,**kw):return self.invoke(dict(command='document.edit',document=d,expected_revision=d['revision'],operations=ops,**kw))['document']
    def roundtrip(self,d,**kw):
        out=self.invoke(dict(command='document.export',document=d,format='svg',**kw))
        again=self.invoke(dict(command='svg.import',id='again',source=dict(kind='text',text=out['data'])))['document']
        for scale in (1,2,3):self.assertEqual(self.pixels(d,scale,**kw),self.pixels(again,scale))
        tree=ET.fromstring(out['data']);ids=[e.get('id') for e in tree.iter() if e.get('id')];self.assertEqual(len(ids),len(set(ids)))
        return tree

    def test_default_luminance_empty_mask_and_legacy_region_defaults(self):
        for content,coverage in [('',0),('<rect width="32" height="24" fill="#808080"/>',128/255),('<rect width="32" height="24"/>',0)]:
            r=self.imported(f'<defs><mask id="m">{content}</mask></defs><rect id="r" x="4" y="4" width="20" height="10" fill="red" mask="url(#m)"/>')
            m=self.item(r,'r')['artwork_mask'];self.assertEqual(m['region'],[-.1,-.1,1.2,1.2]);self.assertEqual(m['mode'],'luminance');self.assertEqual(m['region_transform'],[20,0,0,10,4,4]);self.assertEqual(m['transform'],[1,0,0,1,0,0])
            self.alpha(r['document'],lambda x,y:coverage if 4<=x<24 and 4<=y<14 else 0)
            self.assertEqual(self.item(r,'m')['content']['type'],'mask_source');self.roundtrip(r['document'])

    def test_alpha_luminance_colored_overlaps_and_object_opacity_match_rationals(self):
        for mode in ('alpha','luminance'):
            body=f'<mask id="m" mask-type="{mode}" maskUnits="userSpaceOnUse" x="0" y="0" width="32" height="24"><g opacity=".6"><rect width="24" height="24" fill="#c8285a" fill-opacity=".4"/><rect x="8" width="24" height="24" fill="#1eb4dc" fill-opacity=".8" opacity=".3"/></g></mask><rect width="32" height="24" fill="blue" opacity=".7" mask="url(#m)"/>'
            r=self.imported(body)
            def expected(x,y):
                v=premul([200,40,90,102]) if x<24 else [F(0)]*4
                if x>=8:v=over(v,premul([30,180,220,204]),F(3,10))
                v=v[3] if mode=='alpha' else sum(v[c]*k for c,k in enumerate([F(2125,10000),F(7154,10000),F(721,10000)]))
                return float(v*F(3,5)*F(7,10))
            for scale in (1,2,3):self.alpha(r['document'],expected,scale)
            self.roundtrip(r['document'])

    def test_independent_region_and_content_units_all_four_combinations(self):
        for content_box in (False,True):
            for region_box in (False,True):
                source='<rect x=".25" width=".5" height="1" fill="white"/>' if content_box else '<rect x="8" y="4" width="8" height="8" fill="white"/>'
                region='x="12.5%" y="0" width="75%" height="100%"' if region_box else 'x="6" y="4" width="12" height="8"'
                body=f'<rect id="r" x="4" y="4" width="16" height="8" transform="translate(2,1)" mask="url(#m)"/><mask id="m" maskUnits="{"objectBoundingBox" if region_box else "userSpaceOnUse"}" maskContentUnits="{"objectBoundingBox" if content_box else "userSpaceOnUse"}" {region}>{source}</mask>'
                r=self.imported(body);m=self.item(r,'r')['artwork_mask']
                self.assertEqual(m['transform'],[16,0,0,8,4,4] if content_box else [1,0,0,1,0,0])
                for scale in (1,2):self.alpha(r['document'],lambda x,y:1 if 10<=x<18 and 5<=y<13 else 0,scale)
                self.roundtrip(r['document'])

    def test_user_region_physical_units_percentages_viewbox_and_reflection(self):
        body='<mask id="m" maskUnits="userSpaceOnUse" x="25%" y="1.5pt" width="50%" height="50%"><rect width="16" height="12" fill="white"/></mask><rect id="r" width="16" height="12" mask="url(#m)" transform="translate(16,0) scale(-1,1)"/>'
        r=self.imported(body,'width="32" height="24" viewBox="0 0 16 12"')
        self.assertEqual(self.item(r,'r')['artwork_mask']['region'],[4,2,8,6])
        self.alpha(r['document'],lambda x,y:1 if 8<=x<24 and 4<=y<16 else 0)
        self.roundtrip(r['document'])

    def test_group_object_box_ignores_display_none_but_includes_hidden_geometry(self):
        body='<mask id="m" maskContentUnits="objectBoundingBox"><rect width=".5" height="1" fill="white"/></mask><g id="g" transform="translate(2,1)" mask="url(#m)"><rect width="8" height="8"/><rect x="12" width="4" height="8" visibility="hidden"/><rect x="20" width="10" height="10" display="none"/></g>'
        r=self.imported(body);self.assertEqual(self.item(r,'g')['artwork_mask']['transform'],[16,0,0,8,0,0]);self.alpha(r['document'],lambda x,y:1 if 2<=x<10 and 1<=y<9 else 0)
        self.roundtrip(r['document'])

    def test_definition_inheritance_ignores_ancestor_effects_display_and_mask_opacity(self):
        body='<g transform="translate(20,0)" opacity=".1" display="none" fill="white" color="red"><defs><mask id="m" opacity="0" display="none" visibility="hidden"><g visibility="visible"><rect width="32" height="24" fill="currentColor"/></g></mask></defs></g><rect id="r" width="32" height="24" color="blue" mask="url(#m)"/>'
        r=self.imported(body);self.alpha(r['document'],lambda x,y:.2125)
        source=self.item(r,'m');self.assertEqual(source['opacity'],1);self.assertTrue(source['visible']);self.assertEqual(source['transform'],[1,0,0,1,0,0]);self.roundtrip(r['document'])

    def test_mask_type_mode_noninheritance_explicit_inherit_and_shorthand_order(self):
        for style,wanted in [('mask:url(#m);mask-mode:alpha',1),('mask-mode:alpha;mask:url(#m)',.2125),('mask:url(#a);mask-mode:luminance',.2125)]:
            r=self.imported(f'<defs mask-type="alpha"><mask id="m"><rect width="32" height="24" fill="red"/></mask><mask id="a" mask-type="inherit"><rect width="32" height="24" fill="red"/></mask></defs><rect width="32" height="24" style="{style}"/>')
            self.alpha(r['document'],lambda x,y:wanted)
        # Mask does not inherit automatically; explicit inheritance multiplies again.
        for attr,coverage in [('',.5),('mask="inherit"',.25)]:
            r=self.imported(f'<mask id="m"><rect width="32" height="24" fill="white" opacity=".5"/></mask><g mask="url(#m)"><rect width="32" height="24" {attr}/></g>');self.alpha(r['document'],lambda x,y:coverage)
        r=self.imported('<mask id="m" mask-type="alpha"><rect width="32" height="24" fill="red"/></mask><rect width="32" height="24" mask="url(#m)"/>');self.alpha(r['document'],lambda x,y:1)
        r=self.imported('<mask id="m"><rect width="32" height="24" fill="red"/></mask><g style="mask:url(#m);mask-mode:alpha"><rect width="32" height="24" mask="inherit"/></g>');self.alpha(r['document'],lambda x,y:1)

    def test_gradient_clip_definitions_inside_masks_keep_viewport_percent_basis(self):
        body='<mask id="m" maskContentUnits="objectBoundingBox"><defs><linearGradient id="g" gradientUnits="userSpaceOnUse" x2="100%"><stop offset="0" stop-color="black"/><stop offset="1" stop-color="white"/></linearGradient><clipPath id="c"><rect x=".25" width=".5" height="1"/></clipPath></defs><rect width="1" height="1" fill="url(#g)" clip-path="url(#c)"/></mask><rect x="4" y="4" width="24" height="16" mask="url(#m)"/>'
        r=self.imported(body);self.assertEqual({v['source_id'] for v in r['definitions']},{'m','g','c'})
        for scale in (1,2):self.alpha(r['document'],lambda x,y:(x-4)/(24*32) if 10<=x<22 and 4<=y<20 else 0,scale)
        self.roundtrip(r['document'])

    def test_shared_source_edits_keep_per_owner_boxes_and_locks(self):
        body='<mask id="m" maskContentUnits="objectBoundingBox"><rect id="window" width=".5" height="1" fill="white"/></mask><rect id="a" width="8" height="8" mask="url(#m)"/><rect id="b" x="12" width="16" height="8" mask="url(#m)"/>'
        r=self.imported(body);a,b=self.item(r,'a'),self.item(r,'b');self.assertEqual(a['artwork_mask']['source'],b['artwork_mask']['source']);d=r['document'];original=copy.deepcopy(d)
        edited=self.edit(d,[dict(op='properties',id=self.item(r,'window')['id'],opacity=.25)])
        self.alpha(edited,lambda x,y:.25 if y<8 and (x<4 or 12<=x<20) else 0)
        locked=self.edit(d,[dict(op='properties',id=b['id'],locked=True)])
        err=self.invoke(dict(command='document.edit',document=locked,expected_revision=locked['revision'],operations=[dict(op='properties',id=self.item(r,'window')['id'],opacity=.5)]),1);self.assertEqual(err['code'],'LOCKED');self.assertEqual(d,original)

    def test_curved_mask_clips_nested_owner_masks_and_scaled_export_roundtrip(self):
        body='<mask id="m" maskUnits="userSpaceOnUse" x="1" y="1" width="28" height="20"><clipPath id="c"><rect x="2" y="2" width="24" height="16"/></clipPath><g opacity=".6" clip-path="url(#c)"><ellipse cx="14" cy="10" rx="12" ry="8" fill="white"/><path d="M0 18 C10 0 20 0 30 18 Z" fill="red" opacity=".4"/></g></mask><mask id="outer"><rect width="32" height="24" fill="white" opacity=".7"/></mask><g mask="url(#outer)"><rect width="32" height="24" mask="url(#m)"/></g>'
        r=self.imported(body);self.roundtrip(r['document'])
        w,h,p=self.pixels(r['document']);self.assertEqual(p[3],0);self.assertGreater(p[(10*w+14)*4+3],0)
        # Classify entire pixel squares analytically; uncertain curve-edge cells
        # retain the renderer's documented f32 antialiasing contract.
        checked=0
        for y in range(h):
            for x in range(w):
                if not (2<=x<26 and 2<=y<18):expected=0
                else:
                    far=max((xx-14)**2/144+(yy-10)**2/64 for xx in (x,x+1) for yy in (y,y+1))
                    near=(max(x-14,14-x-1,0))**2/144+(max(y-10,10-y-1,0))**2/64
                    ellipse=True if far<1 else False if near>1 else None
                    curve=lambda xx:18-1.8*xx+.06*xx*xx
                    high=max(curve(x),curve(x+1));low=curve(max(x,min(x+1,15)))
                    path=True if y>=high else False if y+1<=low else None
                    if ellipse is None or path is None:continue
                    luminance=(.2125*.4+(1-.4)*int(ellipse)) if path else int(ellipse)
                    expected=byte(.6*.7*luminance)
                self.assertEqual(p[(y*w+x)*4+3],expected,(x,y));checked+=1
        self.assertGreater(checked,600)

    def test_fractional_mask_region_matches_independent_pixel_area_at_three_scales(self):
        r=self.imported('<mask id="m" maskUnits="userSpaceOnUse" x="1.25" y="2.25" width="4.5" height="2.5"><rect width="32" height="24" fill="white"/></mask><rect width="32" height="24" mask="url(#m)"/>')
        for scale in (1,2,4):
            w,h,p=self.pixels(r['document'],scale)
            for y in range(h):
                for x in range(w):
                    overlap=max(0,min((x+1)/scale,5.75)-max(x/scale,1.25))*max(0,min((y+1)/scale,4.75)-max(y/scale,2.25))*scale**2
                    self.assertLessEqual(abs(p[(y*w+x)*4+3]-byte(overlap)),1)
            self.assertLess(abs(sum(p[3::4])/255/scale**2-11.25),.04)
        self.roundtrip(r['document'])

    def test_modern_unbounded_regions_zero_negative_and_degenerate_owner_boxes(self):
        body='<mask id="m"><rect x="0" width="32" height="24" fill="white"/></mask><line x1="4" x2="4" y1="2" y2="20" stroke="blue" stroke-width="4" mask="url(#m)"/>'
        self.assertEqual(self.imported(body,expected=1)['code'],'SVG_UNSUPPORTED')
        r=self.imported(body,'version="2.0" width="32" height="24"');self.alpha(r['document'],lambda x,y:1 if 2<=x<6 and 2<=y<20 else 0)
        tree=self.roundtrip(r['document']);self.assertEqual(tree.get('version'),'2.0');m=tree.find('.//{*}mask');self.assertFalse(any(m.get(k) for k in ['x','y','width','height']))
        for version in ('1.1','2.0'):
            for width in ('0','-1'):
                body=f'<mask id="m" width="{width}"><rect width="32" height="24" fill="white"/></mask><rect width="32" height="24" mask="url(#m)"/>'
                if width=='-1' and version=='1.1':self.assertEqual(self.imported(body,expected=1)['code'],'SVG_INVALID')
                else:self.alpha(self.imported(body,f'version="{version}" width="32" height="24"')['document'],lambda x,y:0)

    def test_text_mask_sources_and_text_owner_user_vs_object_coordinates(self):
        text_tests.SvgTextTests.setUp(self)
        options=dict(font_root=str(self.store),font_bindings=self.bindings)
        for content in ['maskContentUnits="userSpaceOnUse"','maskContentUnits="objectBoundingBox"']:
            shape='<rect width="8" height="24" fill="white"/>' if 'userSpace' in content else '<rect width=".5" height="1" fill="white"/>'
            r=self.imported(f'<mask id="m" {content}>{shape}</mask><text id="label" x="2" y="10" font-size="10" font-family="Geometry" mask="url(#m)">AA</text>',**options)
            self.alpha(r['document'],lambda x,y:1 if 2.5<=x<6.5 and 3<=y<10 else 0,2,font_root=str(self.store))
            self.assertEqual(self.item(r,'label')['content']['type'],'text');self.roundtrip(r['document'],font_root=str(self.store))
        r=self.imported('<mask id="m"><text id="glyphs" x="0" y="8" font-family="Geometry" font-size="10" fill="white">AA</text></mask><rect width="32" height="24" mask="url(#m)"/>',**options)
        self.alpha(r['document'],lambda x,y:1 if 1<=y<8 and (.5<=x<4.5 or 6.5<=x<10.5) else 0,2,font_root=str(self.store))
        self.roundtrip(r['document'],font_root=str(self.store));self.assertEqual(self.source.read_bytes(),__import__('synthetic_font').geometric_font())

    def test_mask_mapping_file_receipts_source_preservation_and_resource_discovery(self):
        text=svg('<mask id="external name"><title>Original reveal</title><rect width="32" height="24" fill="white"/></mask><rect width="8" height="8"/>')
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'source.svg';raw=text.encode();p.write_bytes(raw)
            r=self.invoke(dict(command='svg.import',id='svg-masks',source=dict(kind='file',source_path=str(p))))
            self.assertEqual(p.read_bytes(),raw);self.assertEqual(r['source']['sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(r['source']['bytes'],len(raw))
            m=self.item(r,'external name');self.assertEqual(m['name'],'Original reveal');self.assertEqual(r['definitions'][0]['item_id'],m['id'])
            self.assertNotIn(m['id'],self.invoke(dict(command='document.query',document=r['document'],query={}))['ids'])
            self.assertEqual(self.invoke(dict(command='document.query',document=r['document'],query=dict(types=['mask_source'],visible_only=False)))['ids'],[m['id']])
            self.alpha(r['document'],lambda x,y:1 if x<8 and y<8 else 0)

    def test_unknown_recursive_external_and_wrong_type_masks_fail_even_unused_or_hidden(self):
        bodies=[
            '<g display="none"><rect width="8" height="8" mask="url(#missing)"/></g>',
            '<clipPath id="c"><rect width="8" height="8"/></clipPath><rect width="8" height="8" mask="url(#c)"/>',
            '<mask id="m"><rect width="8" height="8" mask="url(#m)"/></mask>',
            '<mask id="m"><g mask="url(#n)"/></mask><mask id="n"><g mask="url(#m)"/></mask>',
            '<mask id="m" transform="translate(1)"/>','<mask id="m" mask-type="unknown"/>','<mask id="m" maskContentUnits="unknown"/>',
            '<mask id="m" x="1pt"/>','<mask id="m" color-interpolation="linearRGB"/>',
            '<mask id="m"><image href="remote.png"/></mask>','<mask id="m"><script/></mask>',
            '<rect width="8" height="8" mask="url(https://invalid.example/m.svg#m)"/>',
            '<rect width="8" height="8" style="mask:url(#a),url(#b)"/>',
            '<defs mask="url(#m)"><mask id="m"/></defs>',
        ]
        for body in bodies:
            with self.subTest(body=body):self.assertIn(self.imported(body,expected=1)['code'],('SVG_INVALID','SVG_UNSUPPORTED'))

    def test_definition_item_reference_and_snapshot_limits_have_no_partial_result(self):
        for body in [''.join(f'<mask id="m{i}"/>' for i in range(65)), '<mask id="m"/>'+''.join('<rect width="8" height="8" mask="url(#m)"/>' for _ in range(33)), '<mask id="m">'+''.join('<rect width="8" height="8"/>' for _ in range(255))+'</mask>']:
            self.assertEqual(self.imported(body,expected=1)['code'],'RESOURCE_LIMIT')

    def test_mcp_shared_mask_edit_retry_reopen_snapshot_and_undo(self):
        text=svg('<mask id="m"><rect id="window" width="16" height="24" fill="white"/></mask><rect id="r" width="32" height="24" mask="url(#m)"/>')
        with tempfile.TemporaryDirectory() as root:
            client=Client();client.initialize();params=dict(session_root=root,session_id='svg-mask')
            try:
                r=client.success('svg.import',id='svg-masks',source=dict(kind='text',text=text));d=r['document'];before=self.pixels(d)
                client.success('session.create',**params,request_id='create',document=d)
                action=dict(type='edit',operations=[dict(op='properties',id=self.item(r,'window')['id'],opacity=.4)])
                result=client.success('session.apply',**params,expected_revision=0,request_id='edit',action=action);after=self.pixels(result['document']);self.assertNotEqual(before,after)
                client.success('session.apply',**params,expected_revision=1,request_id='snapshot',action=dict(type='snapshot',name='masked'))
            finally:client.close()
            client=Client();client.initialize()
            try:
                replay=client.success('session.apply',**params,expected_revision=0,request_id='edit',action=action);self.assertEqual(replay['document'],result['document'])
                undo=client.success('session.apply',**params,expected_revision=2,request_id='undo',action=dict(type='undo'));self.assertEqual(self.pixels(undo['document']),before)
                saved=client.success('session.read',**params,snapshot='masked');self.assertEqual(self.pixels(saved['document']),after);client.success('session.verify',**params)
            finally:client.close()


if __name__=='__main__':unittest.main()
