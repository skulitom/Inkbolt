"""Original CSS fixtures with explicit cascade, pixel and saved-state oracles."""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
import test_svg_import_cli as svg_support
from test_mcp import Client


class SvgStyleTests(unittest.TestCase):
    invoke=svg_support.SvgImportTests.invoke
    imported=svg_support.SvgImportTests.imported
    pixels=svg_support.SvgImportTests.pixels
    item=svg_support.SvgImportTests.item

    def test_specificity_source_order_lists_and_inline_against_presentation(self):
        cases=[
            ('*{fill:blue}', '', [0,0,255,255]),
            ('#mark{fill:blue}.a.b{fill:lime}', '', [0,0,255,255]),
            ('.a.a{fill:blue}.a{fill:lime}', '', [0,0,255,255]),
            ('rect.a{fill:blue}.a{fill:lime}', '', [0,0,255,255]),
            ('.a{fill:blue}.b{fill:lime}', '', [0,255,0,255]),
            ('rect.b#mark.a{fill:blue}rect.c{fill:lime}', '', [0,0,255,255]),
            ('#missing,.a{fill:blue}rect.b{fill:lime}', '', [0,255,0,255]),
            ('#mark{fill:blue}', 'style="fill:lime;fill:#123456"', [18,52,86,255]),
            ('rect{fill:blue;fill:lime}', '', [0,255,0,255]),
            ('Rect{fill:blue}', '', [255,0,0,255]),
        ]
        for css,inline,wanted in cases:
            with self.subTest(css=css,inline=inline):
                text=svg_support.svg(f'<rect id="mark" class="a a b" width="4" height="3" fill="red" {inline}/><style>{css}</style>')
                r=self.imported(text)
                self.assertEqual(self.item(r,'mark')['content']['fill'],wanted)
                w,h,p=self.pixels(r['document'])
                self.assertEqual(p,b''.join(bytes(wanted) if x<4 and y<3 else bytes(4) for y in range(h) for x in range(w)))
                self.assertEqual(r['source']['sha256'],hashlib.sha256(text.encode()).hexdigest())
        # A repeated class token on the element never increases .a specificity.
        r=self.imported(svg_support.svg('<style>.a{fill:red}.b{fill:blue}</style><rect id="r" class="a a b" width="1" height="1"/>'))
        self.assertEqual(self.item(r,'r')['content']['fill'],[0,0,255,255])

    def test_later_blocks_inheritance_current_color_and_noninherited_opacity(self):
        text=svg_support.svg('<style>g{fill:red;opacity:.5;color:#123456}.show{visibility:visible}</style>'
            '<g visibility="hidden"><rect id="hidden" width="4" height="4"/>'
            '<rect id="shown" class="show" x="4" width="4" height="4"/>'
            '<g display="none"><rect class="show" width="20" height="20"/></g></g>'
            '<style>.show{fill:currentColor}</style>')
        r=self.imported(text);w,h,p=self.pixels(r['document'])
        self.assertEqual(self.item(r,'shown')['opacity'],1)
        self.assertEqual(p,b''.join(bytes([18,52,86,128]) if 4<=x<8 and y<4 else bytes(4) for y in range(h) for x in range(w)))

    def test_comments_cdata_class_only_and_number_lexemes(self):
        value='1.1234567890123457';opacity='0.12345678901234567'
        text=svg_support.svg(f'<style type="text/css"><![CDATA[/* begin */ rect/**/.a {{ FILL:rgb(18,/*g*/52,86);stroke:blue;stroke-width:{value};opacity:{opacity} }}]]></style>'
            '<rect id="r" class="a" x="2" y="2" width="5" height="5"/>'
            '<rect class="unmatched" width="1" height="1"/>')
        r=self.imported(text);item=self.item(r,'r')
        self.assertEqual(item['content']['fill'],[18,52,86,255])
        self.assertEqual(item['content']['stroke']['width'],float(value))
        self.assertEqual(item['opacity'],float(opacity))
        self.assertEqual(len(r['document']['items']),3)
        self.assertTrue(any('Classes, selectors' in loss for loss in r['losses']))
        r=self.imported(svg_support.svg('<style>rect{fill:red}<!-- rect{fill:blue} --></style><rect id="r" width="1" height="1"/>'))
        self.assertEqual(self.item(r,'r')['content']['fill'],[255,0,0,255])

    def test_gradient_stops_and_clip_geometry_share_the_cascade(self):
        body='<defs><style>.stop{stop-color:#2468ac}.hole{clip-rule:evenodd}</style>'
        body+='<linearGradient id="paint" stop-color="red"><stop class="stop" offset="0"/><stop class="stop" offset="1"/></linearGradient>'
        body+='<clipPath id="clip"><path class="hole" d="M0 0H8V8H0Z M2 2H6V6H2Z"/></clipPath></defs>'
        body+='<rect id="r" class="painted" width="8" height="8"/><style>.painted{fill:url("#paint");clip-path:url(#clip)}</style>'
        r=self.imported(svg_support.svg(body));w,h,p=self.pixels(r['document'])
        self.assertEqual(p,b''.join(bytes([36,104,172,255]) if x<8 and y<8 and not (2<=x<6 and 2<=y<6) else bytes(4) for y in range(h) for x in range(w)))
        body='<defs><linearGradient id="g"><stop offset="0"/><stop offset="1"/></linearGradient></defs>'
        body+='<rect width="4" height="4" fill="url(#g)"/><style>linearGradient{stop-color:red;stop-opacity:.25}</style>'
        r=self.imported(svg_support.svg(body));w,h,p=self.pixels(r['document'])
        self.assertEqual(p,b''.join(bytes([0,0,0,255]) if x<4 and y<4 else bytes(4) for y in range(h) for x in range(w)))

    def test_mask_shorthand_reset_obeys_specificity_and_declaration_order(self):
        for css,wanted in [
            ('#r{mask-mode:alpha}.a{mask:url(#m)}',bytes([255,0,0,255])),
            ('.a{mask-mode:alpha;mask:url(#m)}',bytes(4)),
            ('.a{mask:url(#m);mask-mode:alpha}',bytes([255,0,0,255])),
            ('.a{mask-mode:alpha}#r{mask:url(#m)}',bytes(4)),
        ]:
            with self.subTest(css=css):
                body='<defs><mask id="m" maskUnits="userSpaceOnUse" x="0" y="0" width="4" height="4"><rect class="black" width="4" height="4"/></mask></defs>'
                body+='<rect id="r" class="a" width="4" height="4" fill="red"/><style>.black{fill:black}'+css+'</style>'
                r=self.imported(svg_support.svg(body));w,h,p=self.pixels(r['document'])
                self.assertEqual(p,b''.join(wanted if x<4 and y<4 else bytes(4) for y in range(h) for x in range(w)))

    def test_unsupported_and_malformed_css_are_located_even_when_unmatched(self):
        for css in ['g rect{fill:red}','g>rect{fill:red}','rect+rect{fill:red}','[id]{fill:red}',
                'rect:hover{fill:red}','svg|rect{fill:red}',r'.\61 {fill:red}',
                '@media all{rect{fill:red}}','rect{fill:red!important}',
                '.missing{filter:blur(1px)}','.missing{fill:unknown}',
                'rect{fill:red;fill:unknown}','rect{fill:r/**/ed}',
                'rect{stroke-width:1/**/px}', 'rect, {fill:red}',
                'rect{fill:red','rect{fill:rgb(1,2,3}','rect{fill:"red}',
                'rect{fill:red}/*unclosed','rect{fill:var(--color)}',
                '.missing{font-family:123foo}', '.missing{font-family:family 2}',
                '.missing{font-family:initial}', '.missing{font-family:inherit,Geometry}']:
            with self.subTest(css=css):
                text=svg_support.svg('<title>\u03bb</title>\n<style>'+css+'</style><rect width="1" height="1"/>')
                error=self.imported(text,1)
                self.assertIn(error['code'],('SVG_INVALID','SVG_UNSUPPORTED'))
                details=error['details'];self.assertEqual(details['element'],'style')
                self.assertEqual(details['byte_offset'],len(text[:text.index('<style>')].encode()))
                self.assertEqual(details['line'],2);self.assertIn('css_byte_offset',details)
        for attrs in ['media="screen"','type="text/plain"','title="alternate"']:
            e=self.imported(svg_support.svg(f'<style {attrs}>rect{{fill:red}}</style>'),1)
            self.assertEqual(e['code'],'SVG_UNSUPPORTED');self.assertEqual(e['details']['context'],'stylesheet')
        self.imported(svg_support.svg('<style>.missing{font-family:"123foo","initial"}</style>'))

    def test_css_budgets_are_reported_and_enforced(self):
        cap=self.invoke(dict(command='capabilities'))['svg_import']['css']
        self.assertTrue(cap['embedded_style']);self.assertFalse(cap['important'])
        cases=[('.a'* (cap['selector_components']+1)+'{fill:red}', ''),
               ('rect{}'*(cap['rules']+1),''),
               ('.a{}'*cap['rules'],'<rect class="a" width="1" height="1"/>'*400)]
        for css,body in cases:
            with self.subTest(size=len(css)):
                e=self.imported(svg_support.svg('<style>'+css+'</style>'+body),1,**({'resource_profile':'large_vector'} if body else {}))
                self.assertEqual(e['code'],'RESOURCE_LIMIT');self.assertIn('CSS',e['message'])
        css='rect{'+'fill:red;'*(cap['declarations']+1)+'}'
        e=self.imported(svg_support.svg('<style>'+css+'</style>'),1,resource_profile='large_vector')
        self.assertEqual(e['code'],'RESOURCE_LIMIT');self.assertIn('declaration',e['message'])
        with tempfile.TemporaryDirectory() as directory:
            marker=Path(directory)/'cancel';marker.touch()
            e=self.imported(svg_support.svg('<style>rect{fill:red}</style>'),1,control=dict(cancel_file=str(marker)))
            self.assertEqual(e['code'],'CANCELLED')

    def test_mcp_insertion_is_atomic_and_preserves_retry_undo_and_source(self):
        client=Client();self.addCleanup(client.close);client.initialize()
        text=svg_support.svg('<rect id="r" class="a" width="4" height="4"/><style>.a{fill:#123456}</style>')
        original=text
        expected=self.imported(text)['document']
        with tempfile.TemporaryDirectory() as directory:
            common=dict(session_root=directory,session_id='css')
            empty=self.invoke(dict(command='document.create',id='css',kind='vector',width=32,height=24))
            client.success('session.create',**common,request_id='create',document=empty)
            request=dict(**common,request_id='insert',expected_revision=0,action=dict(type='edit',operations=[dict(op='add_svg',svg=text)]))
            applied=client.success('session.apply',**request)
            self.assertEqual(self.pixels(applied['document']),self.pixels(expected))
            self.assertEqual(client.success('session.apply',**request),{**applied,'replayed':True})
            before=copy.deepcopy(applied['document'])
            bad=dict(command='session.apply',**common,request_id='bad',expected_revision=1,action=dict(type='edit',operations=[dict(op='add_svg',svg=text.replace('.a{','g .a{'))]))
            e=self.invoke(bad,1);self.assertEqual(e['code'],'SVG_UNSUPPORTED');self.assertEqual(e['operation_index'],0)
            self.assertEqual(self.invoke(dict(command='session.read',**common))['document'],before)
            undone=client.success('session.apply',**common,request_id='undo',expected_revision=1,action=dict(type='undo'))
            self.assertEqual(undone['document']['items'],[]);self.assertEqual(text,original)

    def test_inserted_css_error_locations_refer_to_original_fragment_or_document(self):
        document=self.invoke(dict(command='document.create',id='located',kind='vector',width=8,height=8))
        bad='<style>rect:hover{fill:red}</style>'
        for prefix in ('','<g/>','<title>\u03bb</title>','<title>\u03bb</title>\n'):
            for complete in (False,True):
                with self.subTest(prefix=prefix,complete=complete):
                    source=prefix+bad
                    if complete:source=svg_support.svg(source)
                    before=source[:source.index('<style>')]
                    e=self.invoke(dict(command='document.edit',document=document,expected_revision=0,
                        operations=[dict(op='add_svg',svg=source)]),1)
                    self.assertEqual(e['code'],'SVG_UNSUPPORTED');self.assertEqual(e['operation_index'],0)
                    details=e['details'];self.assertEqual(details['byte_offset'],len(before.encode()))
                    self.assertEqual(details['line'],before.count('\n')+1)
                    self.assertEqual(details['column'],len(before.rsplit('\n',1)[-1])+1)
                    self.assertNotIn('synthetic',details);self.assertEqual(details['css_byte_offset'],5)

    def test_generated_fragment_root_error_has_no_invented_source_position(self):
        document=self.invoke(dict(command='document.create',id='synthetic',kind='vector',width=8,height=8))
        # Matching these valid, unused selectors exhausts the advertised byte-work
        # budget on the generated root, before any source artwork is visited.
        source='<style>'+('.'+'a'*1024+'{}')*4096+'</style>'
        e=self.invoke(dict(command='document.edit',document=document,expected_revision=0,
            operations=[dict(op='add_svg',svg=source)]),1)
        self.assertEqual(e['code'],'RESOURCE_LIMIT');self.assertIn('CSS matching',e['message'])
        self.assertTrue(e['details']['synthetic'])
        for field in ('byte_offset','line','column'):self.assertIsNone(e['details'][field])


if __name__=='__main__': unittest.main()
