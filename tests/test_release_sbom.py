"""Check that a release inventory describes the packages Cargo actually built."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

from test_cli import ROOT

sys.path.insert(0, str(ROOT / 'tools'))
from release_sbom import build_edges, build_inputs


class ReleaseInventoryTests(unittest.TestCase):
    def test_tree_retains_nested_shared_and_build_dependencies(self):
        refs = {('app', '1'): 'app', ('common', '2'): 'common', ('builder', '3'): 'builder'}
        tree = '0|app v1 (/workspace)\n1|common v2\n1|builder v3\n2|common v2 (*)\n'
        self.assertEqual(build_edges(tree, refs, 'app'),
                         {'app': {'common', 'builder'}, 'builder': {'common'}, 'common': set()})
        for bad in (tree.replace('builder v3', 'builder v4'), tree.replace('1|builder', '3|builder'),
                    '0|app v1\n1|common v2\n', tree + '0|app v1\n'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                build_edges(bad, refs, 'app')

    def test_only_a_finished_build_for_the_same_executable_can_supply_features(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / 'inkbolt'
            binary.write_bytes(b'test executable')
            log = root / 'messages.jsonl'
            artifact = {'reason': 'compiler-artifact', 'package_id': 'app', 'target': {'kind': ['bin']},
                        'features': [], 'executable': str(binary)}
            dep = {'reason': 'compiler-artifact', 'package_id': 'sqlite', 'target': {'kind': ['lib']},
                   'features': ['bundled'], 'executable': None}
            done = {'reason': 'build-finished', 'success': True}
            def record(*rows):
                log.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf8')
            record(dep, artifact, done)
            self.assertEqual(build_inputs(log, binary, 'app'), {'app': set(), 'sqlite': {'bundled'}})
            other = root / 'different'
            other.write_bytes(binary.read_bytes())
            with self.assertRaises(ValueError):
                build_inputs(log, other, 'app')
            for rows in ([artifact], [artifact, dict(done, success=False)], [dep, done]):
                record(*rows)
                with self.assertRaises(ValueError):
                    build_inputs(log, binary, 'app')
