"""Original omission fixtures: exact source locations, pixels and atomic editing."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import test_svg_import_cli as importing
from test_svg_import_cli import svg
import test_svg_insertion_cli as insertion
from test_svg_insertion_cli import BOX
import test_svg_text_cli as labels
from test_mcp import Client
from external_workspace import files as workspace_files


class SvgOmissionTests(unittest.TestCase):
    invoke = importing.SvgImportTests.invoke
    imported = importing.SvgImportTests.imported
    pixels = importing.SvgImportTests.pixels

    def omitted(self, body, **options):
        return self.imported(svg(body), unsupported='omit_and_report', **options)

    def check_location(self, source, row, element):
        start = source.index(element)
        self.assertEqual(row['byte_offset'], len(source[:start].encode()))
        self.assertEqual(row['byte_end'], len(source[:start+len(element)].encode()))
        self.assertEqual(row['line'], source[:start].count('\n')+1)
        self.assertEqual(row['column'], len(source[:start].rsplit('\n',1)[-1])+1)

    def test_strict_default_and_explicit_error_reject_unknown_content(self):
        source = svg('<foreignObject id="skip"><rect width="32" height="24"/></foreignObject>'+BOX)
        for options in ({}, {'unsupported':'error'}):
            self.assertEqual(self.imported(source, expected=1, **options)['code'], 'SVG_UNSUPPORTED')
        result = self.imported(source, unsupported='omit_and_report')
        self.assertEqual(result['unsupported'], 'omit_and_report')
        self.assertEqual([r['source_id'] for r in result['omissions']], ['skip'])
        self.assertEqual(result['omissions'][0]['descendant_elements'], 1)
        w,h,p = self.pixels(result['document'])
        self.assertEqual(p, bytes(v for y in range(h) for x in range(w) for v in
                                 ([40,100,220,255] if 2<=x<6 and 3<=y<8 else [0]*4)))

    def test_original_unicode_locations_source_hash_and_file_preservation(self):
        removed = '<foreignObject id="removed">é🙂</foreignObject>'
        source = svg('<!-- é🙂 -->\n'+removed+'\n'+BOX)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'original.svg'
            raw = source.encode(); path.write_bytes(raw)
            result = self.invoke(dict(command='svg.import',id='imported',unsupported='omit_and_report',
                                     source=dict(kind='file',source_path=str(path))))
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(list(Path(folder).iterdir()), [path])
        self.check_location(source, result['omissions'][0], removed)
        self.assertEqual(result['source']['bytes'], len(raw))
        self.assertEqual(result['source']['sha256'], hashlib.sha256(raw).hexdigest())
        box = next(row for row in result['mapping'] if row['source_id']=='box')
        self.assertEqual(box['byte_offset'], raw.index(b'<rect'))
        self.assertTrue(result['omissions'][0]['reason'])
        self.assertEqual(result['omissions'][0]['cause']['byte_offset'], raw.index(b'<foreignObject'))

    def test_unsupported_attribute_omits_its_whole_container(self):
        result = self.omitted('<g id="effect" filter="url(#f)">'+BOX+'</g><rect id="keep" width="1" height="1"/>')
        self.assertEqual([r['source_id'] for r in result['omissions']], ['effect'])
        self.assertEqual([r['source_id'] for r in result['mapping']], [None,'keep'])

    def test_stylesheets_are_omitted_whole_with_reported_cascade_loss(self):
        result = self.omitted('<style id="sheet">rect{fill:red;filter:none}</style>'+BOX)
        self.assertEqual([r['source_id'] for r in result['omissions']], ['sheet'])
        self.assertEqual(result['omissions'][0]['cause']['context'], 'stylesheet')
        expected = self.imported(svg(BOX))
        self.assertEqual(self.pixels(result['document']), self.pixels(expected['document']))
        result = self.omitted('<g id="outer" filter="none"><style id="inner">rect{unknown:1}</style>'+BOX+'</g>')
        self.assertEqual([r['source_id'] for r in result['omissions']], ['outer'])
        self.assertEqual(result['omissions'][0]['covered_omissions'][0]['source_id'], 'inner')

    def test_omitted_definitions_propagate_to_explicit_css_and_use_dependencies(self):
        result = self.omitted('<defs><pattern id="p"><rect id="child" width="1" height="1"/></pattern></defs>'
                              '<style>.dependent{fill:url(#p)}</style>'
                              '<rect id="filled" class="dependent" width="2" height="2"/>'
                              '<use id="used" href="#child"/>'+BOX)
        self.assertEqual([r['source_id'] for r in result['omissions']], ['p','filled','used'])
        self.assertEqual(result['omissions'][1]['cause']['omitted_reference'], 'p')
        self.assertEqual(result['omissions'][2]['cause']['omitted_reference'], 'child')
        self.assertEqual(self.pixels(result['document']), self.pixels(self.imported(svg(BOX))['document']))

    def test_gradient_template_and_mask_dependencies_are_reported(self):
        result = self.omitted('<defs><pattern id="p"/><linearGradient id="g" href="#p"/></defs>'
                              '<rect id="r" fill="url(#g)" width="2" height="2"/>'
                              '<rect id="m" mask="url(#p)" width="2" height="2"/>'+BOX)
        self.assertEqual([r['source_id'] for r in result['omissions']], ['p','g','r','m'])

    def test_missing_references_invalid_numbers_and_roots_still_fail(self):
        for body, code in [('<use href="#missing"/>','SVG_INVALID'),
                           ('<rect width="oops" height="2"/>','SVG_INVALID')]:
            with self.subTest(body=body):
                self.assertEqual(self.omitted('<foreignObject/>'+body, expected=1)['code'], code)
        for source in ('<html/>', svg(BOX,'width="32" height="24" filter="none"')):
            self.assertEqual(self.imported(source, unsupported='omit_and_report', expected=1)['code'], 'SVG_UNSUPPORTED')

    def test_invalid_xml_duplicates_and_depth_fail_before_any_omission(self):
        for body in ('<foreignObject><broken></foreignObject>',
                     '<foreignObject><g id="same"/><g id="same"/></foreignObject>'):
            self.assertEqual(self.omitted(body, expected=1)['code'], 'SVG_INVALID')
        self.assertEqual(self.omitted('<foreignObject>'+'<g>'*100+'</g>'*100+'</foreignObject>', expected=1)['code'], 'RESOURCE_LIMIT')
        self.assertEqual(self.omitted('<foreignObject/>'*5000, expected=1)['code'], 'SVG_INVALID')

    def test_depth_scan_ignores_markup_in_comments_cdata_and_attributes(self):
        source = svg('<!-- '+'<g>'*100+' -->'+
                     '<style><![CDATA[/* '+'<g>'*100+' */ rect{fill:blue}]]></style>'+
                     '<g id="a&gt;b">'+BOX+'</g>')
        strict = self.imported(source)
        omitted = self.imported(source, unsupported='omit_and_report')
        self.assertEqual(omitted['omissions'], [])
        self.assertEqual(omitted['document'], strict['document'])

    def test_all_receipt_offsets_and_fatal_errors_refer_to_original_source(self):
        source = svg('<foreignObject/><!-- é -->'+
                     '<defs><linearGradient id="g"><stop offset="0" stop-color="red"/>'+
                     '<stop offset="1" stop-color="blue"/></linearGradient>'+
                     '<g id="shape"><path id="arc" d="M8 0 A8 8 0 0 1 0 8" fill="url(#g)"/></g></defs>'+
                     '<use id="first" href="#shape"/><use id="second" href="#shape"/>')
        result = self.imported(source, unsupported='omit_and_report')
        raw = source.encode()
        def check(value):
            if isinstance(value, dict):
                if isinstance(value.get('byte_offset'), int):
                    self.assertEqual(raw[value['byte_offset']:value['byte_offset']+1], b'<')
                    if value.get('source_id'):
                        tag = raw[value['byte_offset']:].split(b'>',1)[0]
                        self.assertIn(('id="'+value['source_id']+'"').encode(), tag)
                for child in value.values(): check(child)
            elif isinstance(value,list):
                for child in value: check(child)
        for section in ('mapping','definitions','approximations','reuse'): check(result[section])
        self.assertTrue(result['approximations']); self.assertTrue(result['reuse'])
        failed = svg('<foreignObject/>\n<rect width="1..2" height="1"/>')
        error = self.imported(failed, unsupported='omit_and_report', expected=1)
        self.assertEqual(error['code'], 'SVG_INVALID')
        self.assertEqual(error['details']['byte_offset'], failed.encode().index(b'<rect'))
        self.assertEqual((error['details']['line'],error['details']['column']), (2,1))

    def test_source_and_attempt_limits_and_cancellation_cannot_be_omitted(self):
        cap = self.invoke(dict(command='capabilities'))['svg_import']
        self.assertEqual(cap['unsupported']['default'], 'error')
        self.assertEqual(cap['insertion']['unsupported'], cap['unsupported'])
        self.assertEqual(self.omitted(' '*cap['source_bytes'], expected=1)['code'], 'RESOURCE_LIMIT')
        self.assertEqual(self.omitted('<foreignObject/>'*cap['unsupported']['max_attempts'], expected=1)['code'], 'RESOURCE_LIMIT')
        error = self.omitted('<foreignObject/>'+BOX, control=dict(timeout_ms=0), expected=1)
        self.assertIn(error['code'], ('TIMEOUT','CANCELLED','DEADLINE_EXCEEDED'))

    def test_foreign_namespaces_and_nested_version_failures_are_located(self):
        result = self.omitted('<x:foreign xmlns:x="urn:original-fixture" id="foreign"><x:child/></x:foreign>'
                              '<svg id="version" version="2.0" width="2" height="2"/>'+BOX)
        self.assertEqual([r['source_id'] for r in result['omissions']], ['foreign','version'])
        self.assertEqual(result['omissions'][0]['element'], 'foreign')

    def test_no_omissions_is_explicit_and_unknown_policies_fail(self):
        result = self.omitted(BOX)
        self.assertEqual(result['omissions'], [])
        strict = self.imported(svg(BOX))
        self.assertNotIn('omissions', strict)
        self.assertEqual(result['document'], strict['document'])
        self.imported(svg(BOX), unsupported='guess', expected=1)

    def test_mcp_cli_parity_and_schema_discovery(self):
        text = svg('<foreignObject/>'+BOX)
        request = dict(id='imported',source=dict(kind='text',text=text),unsupported='omit_and_report')
        client = Client(); self.addCleanup(client.close); client.initialize()
        self.assertEqual(client.success('svg.import',**request), self.invoke(dict(command='svg.import',**request)))
        schema = client.success('schema.lookup',name='svg.import',full=True)
        self.assertIn('omit_and_report', json.dumps(schema))


class SvgInsertionOmissionTests(unittest.TestCase):
    invoke = insertion.SvgInsertionTests.invoke
    create = insertion.SvgInsertionTests.create
    edit = insertion.SvgInsertionTests.edit
    insert = insertion.SvgInsertionTests.insert
    details = insertion.SvgInsertionTests.details

    def test_fragment_locations_and_fatal_batch_failure_keep_atomicity(self):
        document = self.create(); before = copy.deepcopy(document)
        for prefix in ('<!-- é🙂 -->', '<!-- é🙂 -->\n'):
            omitted = '<foreignObject id="skip"/>'
            source = prefix+omitted+BOX
            result = self.insert(document, source, unsupported='omit_and_report')
            receipt = self.details(result)
            SvgOmissionTests.check_location(self, source, receipt['omissions'][0], omitted)
            self.assertEqual(receipt['omissions'][0]['cause']['byte_offset'], len(prefix.encode()))
            self.assertEqual(receipt['source']['sha256'], hashlib.sha256(source.encode()).hexdigest())
        error = self.edit(document,dict(op='add_svg',svg='<foreignObject/>'+BOX,unsupported='omit_and_report'),
                          dict(op='properties',id='absent',visible=False),expected=1)
        self.assertEqual(error['operation_index'], 1)
        self.assertEqual(document, before)

    def test_deep_fragment_and_document_fail_without_process_crash(self):
        document = self.create()
        body = '<foreignObject>'+'<g>'*100+'</g>'*100+'</foreignObject>'
        for source in (body, svg(body)):
            self.assertEqual(self.insert(document,source,unsupported='omit_and_report',expected=1)['code'], 'RESOURCE_LIMIT')

    def test_session_proposal_retry_undo_and_fatal_rollback_preserve_reports(self):
        client = Client(('--tools','core')); self.addCleanup(client.close); client.initialize()
        with tempfile.TemporaryDirectory() as directory:
            common = dict(session_root=directory,session_id='omissions')
            client.success('session.create',**common,request_id='create',document=self.create())
            action = dict(type='edit',operations=[dict(op='add_svg',svg='<foreignObject id="skip"/>'+BOX,
                                                     unsupported='omit_and_report')])
            before = {str(p):p.read_bytes() for p in workspace_files(Path(directory)) if p.is_file()}
            dry = client.success('session.dry_run',**common,request_id='edit',expected_revision=0,
                                 action=action,options=dict(include_document=True))
            self.assertEqual(before,{str(p):p.read_bytes() for p in workspace_files(Path(directory)) if p.is_file()})
            applied = client.success('session.apply_proposal',session_root=directory,proposal=dry['proposal'],action=action)
            self.assertEqual(applied['receipt'],dry['predicted_receipt'])
            self.assertEqual(applied['document'],dry['proposed_document'])
            self.assertIn('omissions',json.dumps(applied['receipt']))
            retry = client.success('session.apply',**common,request_id='edit',expected_revision=0,action=action)
            self.assertTrue(retry['replayed']); self.assertEqual(retry['receipt'],applied['receipt'])
            bad = dict(type='edit',operations=[action['operations'][0],dict(op='properties',id='absent',visible=False)])
            self.assertTrue(client.tool('session.apply',**common,request_id='bad',expected_revision=1,action=bad)['isError'])
            self.assertEqual(client.success('session.read',**common)['document'],applied['document'])
            undo = client.success('session.apply',**common,request_id='undo',expected_revision=1,action=dict(type='undo'))
            self.assertEqual(undo['document']['items'],[])
            redo = client.success('session.apply',**common,request_id='redo',expected_revision=2,action=dict(type='redo'))
            self.assertEqual(redo['document']['items'],applied['document']['items'])


class SvgSpanOmissionTests(unittest.TestCase):
    setUp = labels.SvgTextTests.setUp
    invoke = labels.SvgTextTests.invoke
    imported = labels.SvgTextTests.imported
    item = labels.SvgTextTests.item
    pixels = labels.SvgTextTests.pixels
    label = labels.SvgTextTests.label

    def test_omission_removes_span_text_without_introducing_whitespace(self):
        result = self.imported(self.label(text='A<tspan id="skip" rotate="20">A</tspan>A'), unsupported='omit_and_report')
        expected = self.imported(self.label(text='AA'))
        self.assertEqual(self.item(result)['content']['frame']['text'], 'AA')
        self.assertEqual(self.pixels(result['document']), self.pixels(expected['document']))
        self.assertEqual([r['source_id'] for r in result['omissions']], ['skip'])


if __name__ == '__main__':
    unittest.main()
