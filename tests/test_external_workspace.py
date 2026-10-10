"""Generated workspace inventories cannot hide source-file dependencies."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import external_workspace as workspace


class ExternalWorkspaceTests(unittest.TestCase):
    def test_complete_nested_hidden_and_empty_file_inventory_preserves_contents(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            expected={'.inkbolt/empty':b'', '.inkbolt/deep/source.bin':bytes(range(256)),
                      'output image.png':b'original', 'one.txt':b'one'}
            for name,data in expected.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            (root/'unused-directory').mkdir()
            actual={p.relative_to(root).as_posix():p.read_bytes() for p in workspace.files(root)}
            self.assertEqual(actual,expected)
            self.assertEqual(workspace.files(root),workspace.files(root))

    def test_checkout_root_descendants_and_normalized_paths_are_rejected(self):
        for root in [workspace.CHECKOUT,workspace.CHECKOUT.parent,workspace.CHECKOUT/'tests',workspace.CHECKOUT/'tests'/'..']:
            with self.subTest(root=root),self.assertRaisesRegex(ValueError,'outside the checkout'):
                workspace.files(root)
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/'ordinary';file.write_bytes(b'file')
            with self.assertRaisesRegex(ValueError,'outside the checkout'):workspace.files(file)
            with self.assertRaises(FileNotFoundError):workspace.files(Path(temp)/'missing')

    def test_a_file_resolving_into_checkout_is_rejected_without_reading_contents(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);file=root/'link';file.write_bytes(b'placeholder')
            original=Path.resolve
            def resolve(path,*args,**kwargs):
                return workspace.CHECKOUT/'README.md' if path==file else original(path,*args,**kwargs)
            with patch.object(Path,'resolve',resolve),self.assertRaisesRegex(ValueError,'resolves into'):
                workspace.files(root)


if __name__=='__main__':unittest.main()
