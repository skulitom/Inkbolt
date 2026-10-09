"""Negative publication tests with invented sensitive markers and temporary repositories."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_repo", ROOT / "tools/check_repo.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class RepositoryGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="inkbolt-guard-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "--quiet")
        (self.root / ".git/private-content-policy.json").write_text(
            json.dumps({"patterns": ["BlockedVendorToken"]}), encoding="utf-8")
        (self.root / ".gitignore").write_text((ROOT / ".gitignore").read_text(), encoding="utf-8")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, check=True)

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def test_clean_candidate_and_index_pass(self):
        self.write("README.md", b"Original source\n")
        self.assertEqual(guard.check_repository(self.root)[0], [])
        self.git("add", ".")
        self.assertEqual(guard.check_repository(self.root, staged=True)[0], [])

    def test_actual_index_bytes_checked_despite_clean_working_copy(self):
        self.write("README.md", b"BlockedVendorToken\n")
        self.git("add", "README.md")
        self.write("README.md", b"Original source\n")
        self.assertEqual(guard.check_repository(self.root)[0], [])
        self.assertTrue(any("Private content restriction" in issue for issue in guard.check_repository(self.root, staged=True)[0]))

    def test_forced_private_additions_are_rejected(self):
        for name in ["audits/result.json", ".research/notes.md", "captures/screen.png", "project.gpr", "source.psd", "source.ai"]:
            self.write(name, b"{}")
            self.git("add", "-f", name)
        issues, _ = guard.check_repository(self.root, staged=True)
        self.assertGreaterEqual(sum("Ignored material" in issue for issue in issues), 6)

    def test_binary_disguised_as_source_is_rejected(self):
        self.write("fake.rs", b"\0payload")
        self.assertTrue(any("Binary" in issue for issue in guard.check_repository(self.root)[0]))

    def test_missing_or_empty_policy_fails_closed(self):
        policy = self.root / ".git/private-content-policy.json"
        policy.unlink()
        with self.assertRaises(ValueError):
            guard.check_repository(self.root)
        policy.write_text('{"patterns": []}', encoding="utf-8")
        with self.assertRaises(ValueError):
            guard.check_repository(self.root)

    def test_sensitive_filename_is_rejected(self):
        self.write("BlockedVendorToken.md", b"Original text")
        self.assertTrue(any("restriction in path" in issue for issue in guard.check_repository(self.root)[0]))

    def test_batch_reads_empty_repeated_unicode_and_newline_named_index_blobs(self):
        names = ['empty.md', 'repeated.md', 'space name.md', 'unicode_\u03bb.md']
        if __import__('os').name != 'nt':
            names.append('line\nbreak.md')
        for name in names:
            self.write(name, b'' if name == 'empty.md' else b'Original shared bytes\n')
        self.git('add', '.')
        self.assertEqual(guard.check_repository(self.root, staged=True), ([], len(names) + 1))

    def test_large_index_blob_is_rejected_without_loading_its_contents(self):
        self.write('large.md', b'x' * (guard.MAX_BYTES + 1))
        self.write('good.md', b'Original source\n')
        self.git('add', '.')
        issues, count = guard.check_repository(self.root, staged=True)
        self.assertEqual(issues, ['Binary or oversized material: large.md'])
        self.assertEqual(count, 2)

    def test_unmerged_and_symlink_index_entries_fail_closed(self):
        self.write('source.md', b'Original\n')
        self.git('add', '.')
        oid = self.git('hash-object', '-w', 'source.md').stdout.decode().strip()
        self.git('update-index', '--add', '--cacheinfo', f'120000,{oid},link.md')
        self.assertIn('Unexpected index entry: link.md', guard.check_repository(self.root, staged=True)[0])
        subprocess.run(['git', 'update-index', '--index-info'], cwd=self.root,
                       input=f'100644 {oid} 1\tunmerged.md\n'.encode(), check=True, capture_output=True)
        self.assertIn('Unexpected index entry: unmerged.md', guard.check_repository(self.root, staged=True)[0])


if __name__ == "__main__":
    unittest.main()
