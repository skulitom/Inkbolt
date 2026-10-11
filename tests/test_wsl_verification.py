"""A Linux snapshot must be complete, content-bound and confined to its mirror."""
import json
from pathlib import Path, PurePosixPath
import sys
import tempfile
import unittest
import zipfile

from test_cli import ROOT
sys.path.insert(0, str(ROOT/'tools'))
import verify_wsl as wsl


class WslVerificationTests(unittest.TestCase):
    def test_transient_windows_interop_is_removed_from_actual_linux_environment(self):
        original = dict(WSL_INTEROP='/run/WSL/100_interop', PATH='/original/tools', PWD='/mnt/c/source', CARGO_HOME='/cache')
        actual = wsl.linux_environment(original, PurePosixPath('/owned/linux'))
        self.assertEqual(actual, dict(PATH='/original/tools', PWD='/owned/linux', CARGO_HOME='/cache'))
        self.assertIn('WSL_INTEROP', original)
        later = dict(original, WSL_INTEROP='/run/WSL/200_interop')
        self.assertEqual(actual, wsl.linux_environment(later, PurePosixPath('/owned/linux')))

    def test_snapshot_rejects_tampering_unexpected_entries_and_private_git_paths(self):
        data, policy = b'original source', b'{"patterns":["example-private-pattern"]}'
        with tempfile.TemporaryDirectory() as directory:
            for index, (name, payload, extra) in enumerate([
                    ('src/lib.rs', data, False), ('src/lib.rs', b'changed', False),
                    ('src/lib.rs', data, True), ('../escape.rs', data, False),
                    ('.git/config', data, False)]):
                package = Path(directory)/f'{index}.zip'
                meta = dict(source='owned source', files={name: wsl.sha(data)}, policy_sha256=wsl.sha(policy))
                with zipfile.ZipFile(package, 'w') as archive:
                    archive.writestr('manifest.json', json.dumps(meta))
                    archive.writestr('private-content-policy.json', policy)
                    archive.writestr('files/'+name, payload)
                    if extra: archive.writestr('unexpected', b'unreviewed')
                if index == 0:
                    actual, files, private = wsl.unpack(package)
                    self.assertEqual(actual, meta)
                    self.assertEqual(files, {'src/lib.rs': data})
                    self.assertEqual(private, policy)
                else:
                    with self.assertRaises(ValueError): wsl.unpack(package)

    def test_paths_cannot_escape_or_address_git_metadata(self):
        for name in ('../x', '/x', '.git/config', 'a/../x', 'a\\x', './x', ''):
            with self.subTest(name=name), self.assertRaises(ValueError): wsl.safe_name(name)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(wsl.confined(root, 'src/original.rs'), root/'src/original.rs')
