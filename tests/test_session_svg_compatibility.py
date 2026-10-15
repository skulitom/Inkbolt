"""Historical SVG action identities, independent hashes and unchanged saved receipts."""
from contextlib import closing
import copy
import hashlib
import json
import sqlite3
import unittest

import test_sessions_cli as sessions


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


def action():
    return dict(type='edit', label='Original \u03bb artwork', operations=[
        dict(op='add_svg', svg='<rect id="a" width="1" height="1"/>', prefix='first'),
        dict(op='add_svg', svg='<rect id="b" x="2" width="1" height="1"/>', prefix='second')])


def fingerprint(value, version, revision=0):
    # Original AddSvg serialization (e9c493e), then images (c923b85), then policy.
    normalized = copy.deepcopy(value)
    normalized.setdefault('label', '')
    for op in normalized['operations']:
        if op['op'] != 'add_svg':
            continue
        op.setdefault('parent', None)
        op.setdefault('prefix', None)
        op.setdefault('font_bindings', [])
        if version != 'original':
            op.setdefault('images', dict(source_root=None, color_policy='assume_srgb',
                                         sampling='bilinear'))
        if version == 'current':
            op.setdefault('unsupported', 'error')
    return digest(dict(expected_revision=revision, action=normalized))


class SessionSvgCompatibilityTests(unittest.TestCase):
    setUp = sessions.SessionTests.setUp
    create = sessions.SessionTests.create
    apply = sessions.SessionTests.apply
    db_path = sessions.SessionTests.db_path

    def call(self, command, expected=None, **arguments):
        request = dict(command=command, session_root=str(self.root), **arguments)
        if command != 'session.apply_proposal':
            request['session_id'] = self.session
        result = sessions.invoke(request)
        self.assertEqual(result['ok'], expected is None, result)
        if expected:
            self.assertEqual(result['error']['code'], expected, result)
            return result['error']
        return result['result']

    def rows(self):
        with closing(sqlite3.connect(self.db_path())) as db:
            return db.execute('SELECT * FROM requests ORDER BY revision').fetchall()

    def historical_row(self, value, version):
        old = fingerprint(value, version)
        with closing(sqlite3.connect(self.db_path())) as db:
            current, payload = db.execute(
                'SELECT fingerprint,payload FROM requests WHERE request_id=?', ('draw',)).fetchone()
            self.assertEqual(current, fingerprint(value, 'current'))
            self.assertNotEqual(old, current)
            # Construct a checksum-valid historical identity; retain the exact receipt bytes.
            db.execute('UPDATE requests SET fingerprint=?,sha256=? WHERE request_id=?',
                       (old, digest([old, list(payload)]), 'draw'))
            db.commit()
        return old

    def test_historical_retries_return_original_receipt_without_rewriting_identity(self):
        for version in ('original', 'images'):
            with self.subTest(version=version):
                self.session = version
                self.create()
                value = action()
                first = self.apply(0, 'draw', value)
                self.historical_row(value, version)
                self.apply(1, 'advance', dict(type='snapshot', name='later'))
                before = self.rows()
                retry = self.apply(0, 'draw', value, control=dict(timeout_ms=0))
                self.assertTrue(retry['replayed'])
                self.assertEqual(retry['receipt'], first['receipt'])
                self.assertEqual(retry['document'], first['document'])
                self.assertEqual(retry['current_revision'], 2)
                self.call('session.dry_run', request_id='draw', expected_revision=0,
                          action=value, expected='REQUEST_ALREADY_COMMITTED')
                self.assertEqual(self.rows(), before)
                self.assertTrue(self.call('session.verify')['valid'])

    def test_old_proposal_applies_once_then_replays_with_current_or_old_saved_identity(self):
        for version in ('original', 'images'):
            with self.subTest(version=version):
                self.session = version
                self.create()
                value = action()
                predicted = self.call('session.dry_run', request_id='draw',
                                      expected_revision=0, action=value)
                proposal = dict(predicted['proposal'], request_fingerprint=fingerprint(value, version))
                first = self.call('session.apply_proposal', proposal=proposal, action=value)
                self.assertFalse(first['replayed'])
                self.assertEqual(first['receipt'], predicted['predicted_receipt'])
                self.assertTrue(self.call('session.apply_proposal', proposal=proposal,
                                         action=value)['replayed'])
                self.historical_row(value, version)
                before = self.rows()
                retry = self.call('session.apply_proposal', proposal=proposal, action=value)
                self.assertEqual(retry['receipt'], first['receipt'])
                self.assertTrue(retry['replayed'])
                for field in ('base_state_sha256', 'result_state_sha256'):
                    self.call('session.apply_proposal', proposal=dict(proposal, **{field: '0'*64}),
                              action=value, expected='PROPOSAL_MISMATCH')
                self.assertEqual(self.rows(), before)

    def test_historical_identity_never_hides_changed_action_revision_or_options(self):
        for version in ('original', 'images'):
            with self.subTest(version=version):
                self.session = version
                self.create()
                value = action()
                predicted = self.call('session.dry_run', request_id='draw',
                                      expected_revision=0, action=value)
                self.apply(0, 'draw', value)
                old = self.historical_row(value, version)
                proposal = dict(predicted['proposal'], request_fingerprint=old)
                changed = []
                for field, replacement in (
                    ('svg', '<circle r="1"/>'), ('parent', 'another-parent'),
                    ('prefix', 'different'), ('unsupported', 'omit_and_report'),
                    ('font_bindings', [dict(family='Original', font_id='chosen-font',
                                           weight=400, style='normal')]),
                    ('images', dict(sampling='nearest')),
                    ('images', dict(color_policy='require_srgb')),
                    ('images', dict(source_root=str(self.root))),
                ):
                    altered = copy.deepcopy(value)
                    altered['operations'][1][field] = replacement
                    changed.append(altered)
                changed.append(dict(value, label='Changed label'))
                changed.append(dict(value, operations=list(reversed(value['operations']))))
                changed.append(dict(value, operations=value['operations'] + [dict(op='remove', id='extra')]))
                before = self.rows()
                for altered in changed:
                    self.apply(0, 'draw', altered, expected='REQUEST_ID_REUSED')
                    self.call('session.dry_run', request_id='draw', expected_revision=0,
                              action=altered, expected='REQUEST_ID_REUSED')
                    self.call('session.apply_proposal', proposal=proposal, action=altered,
                              expected='PROPOSAL_MISMATCH')
                self.apply(1, 'draw', value, expected='REQUEST_ID_REUSED')
                self.call('session.apply_proposal', proposal=dict(proposal, expected_revision=1),
                          action=value, expected='PROPOSAL_MISMATCH')
                self.assertEqual(self.rows(), before)

    def test_images_era_identity_retains_explicit_image_options(self):
        self.create()
        value = action()
        value['operations'][0]['images'] = dict(source_root=None, color_policy='assume_srgb',
                                               sampling='nearest')
        first = self.apply(0, 'draw', value)
        self.historical_row(value, 'images')
        self.assertEqual(self.apply(0, 'draw', value)['receipt'], first['receipt'])
        self.apply(0, 'draw', action(), expected='REQUEST_ID_REUSED')

    def test_current_and_explicit_default_identities_still_match(self):
        capabilities = sessions.invoke(dict(command='capabilities'))['result']
        self.assertEqual(capabilities['session_contract']['svg_retry_fingerprints'], dict(
            accepted=['current', 'before_unsupported_policy', 'before_image_options'],
            introduced_fields_must_equal_defaults=True, stored_rows_rewritten=False))
        self.create()
        value = action()
        first = self.apply(0, 'draw', value)
        with closing(sqlite3.connect(self.db_path())) as db:
            saved = db.execute('SELECT fingerprint FROM requests WHERE request_id=?', ('draw',)).fetchone()[0]
        self.assertEqual(saved, fingerprint(value, 'current'))
        for op in value['operations']:
            op['unsupported'] = 'error'
            op['images'] = dict(source_root=None, color_policy='assume_srgb', sampling='bilinear')
        before = self.rows()
        self.assertEqual(self.apply(0, 'draw', value)['receipt'], first['receipt'])
        self.assertEqual(self.rows(), before)


if __name__ == '__main__':
    unittest.main()
