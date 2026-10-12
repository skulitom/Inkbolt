"""Negative publication tests with invented sensitive markers and temporary repositories."""
import importlib.util
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

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

    def test_only_reviewed_workflow_path_is_admitted_with_all_other_checks(self):
        workflow = '.github/workflows/ci.yml'
        for public in (False, True):
            self.assertEqual(guard.inspect_file(workflow, b'name: Original\n', []), [])
            self.assertTrue(guard.inspect_file('.github/workflows/extra.yml', b'name: Original\n', []))
            self.assertTrue(guard.inspect_file('elsewhere/ci.yml', b'name: Original\n', []))
            self.write(workflow, b'BlockedVendorToken\n')
            issues, _ = guard.check_repository(self.root, public=public)
            self.assertEqual(bool(issues), not public)
            self.write(workflow, b'\0')
            self.assertTrue(guard.check_repository(self.root, public=public)[0])
        self.write(workflow, b'name: Original\n')
        self.write('.gitignore', b'/.github/\n')
        self.git('add', '-f', workflow)
        for public in (False, True):
            self.assertTrue(any('Ignored material' in issue for issue in guard.check_repository(self.root, public=public)[0]))

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

    def test_release_automation_types_only_in_their_folders(self):
        self.write(".github/workflows/release.yml", b"name: Release\n")
        self.write(".github/workflows/publish-registry.yml", b"name: Publish\n")
        self.write("mcpb/build.mjs", b"export {};\n")
        self.assertEqual(guard.check_repository(self.root)[0], [])
        stray = ["notes.yml", "src/tool.mjs", ".github/workflows/nested/extra.yml", "mcpb/build.yml"]
        for name in stray:
            self.write(name, b"x\n")
        issues = guard.check_repository(self.root)[0]
        for name in stray:
            self.assertIn(f"Unreviewed file type: {name}", issues)

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

    def test_public_mode_is_explicit_and_never_reads_or_claims_private_policy(self):
        self.write('README.md', b'BlockedVendorToken\n')
        policy = self.root/'.git/private-content-policy.json'
        for data in (None, '{}', '{"patterns": []}', 'not JSON'):
            if data is None: policy.unlink()
            else: policy.write_text(data, encoding='utf-8')
            output = io.StringIO()
            with patch.object(guard, 'local_patterns', side_effect=AssertionError('private policy read')), redirect_stdout(output):
                self.assertEqual(guard.main(['--public'], root=self.root), 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report, dict(ok=True, mode='public_structural', scope='candidate',
                                         private_policy='not_evaluated', checked_files=2, issues=[]))
            with self.assertRaises((ValueError, KeyError)):
                guard.check_repository(self.root)

    def test_public_mode_keeps_structural_and_forced_addition_rejections(self):
        for name, data in [('bad.bin', b'original'), ('binary.rs', b'\0'),
                           ('invalid.md', b'\xff'), ('large.md', b'x'*(guard.MAX_BYTES+1)),
                           ('private/notes.md', b'original')]:
            self.write(name, data)
            self.git('add', '-f', name)
        private_issues, _ = guard.check_repository(self.root)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(guard.main(['--public'], root=self.root), 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report['issues'], private_issues)
        self.assertEqual(report['private_policy'], 'not_evaluated')
        for kind in ('Unreviewed file type', 'Binary or oversized', 'Non-UTF-8',
                     'Excluded material directory', 'Ignored material'):
            self.assertTrue(any(kind in issue for issue in report['issues']), kind)

    def test_public_mode_cannot_select_indexed_content_or_replace_hook(self):
        with self.assertRaises(ValueError):
            guard.check_repository(self.root, staged=True, public=True)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            guard.main(['--public', '--staged'], root=self.root)
        self.assertEqual(error.exception.code, 2)

        project = self.root/'hook-project'
        project.mkdir()
        (project/'tools').mkdir()
        for name in ('check_repo.py', 'setup_private.py'):
            (project/'tools'/name).write_bytes((ROOT/'tools'/name).read_bytes())
        def run(*args, check=True):
            return subprocess.run(args, cwd=project, capture_output=True, check=check,
                                  env={**os.environ, 'CI':'true', 'GITHUB_ACTIONS':'true'})
        run('git', 'init', '--quiet')
        run('git', 'config', 'user.name', 'Original fixture')
        run('git', 'config', 'user.email', 'fixture@example.invalid')
        run('git', 'config', 'core.hooksPath', '.git/hooks')
        policy_source = self.root/'fixture-policy.json'
        policy_source.write_text('{"patterns":["BlockedVendorToken"]}', encoding='utf-8')
        run(sys.executable, 'tools/setup_private.py', '--research-root', str(self.root/'fixture-research'),
            '--policy', str(policy_source))
        hook = (project/'.git/hooks/pre-commit').read_text(encoding='utf-8')
        self.assertTrue(hook.rstrip().endswith('--staged'))
        self.assertNotIn('--public', hook)
        (project/'README.md').write_text('BlockedVendorToken\n', encoding='utf-8')
        run('git', 'add', '.')
        public = run(sys.executable, 'tools/check_repo.py', '--public')
        self.assertEqual(json.loads(public.stdout)['private_policy'], 'not_evaluated')
        rejected = run('git', 'commit', '-m', 'Must reject private fixture', check=False)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn(b'Private content restriction', rejected.stderr+rejected.stdout)
        (project/'.git/private-content-policy.json').unlink()
        run(sys.executable, 'tools/check_repo.py', '--public')
        rejected = run('git', 'commit', '-m', 'Must reject missing policy', check=False)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn(b'Required Git-private content policy is missing', rejected.stderr+rejected.stdout)
        (project/'.git/private-content-policy.json').write_bytes(policy_source.read_bytes())
        (project/'README.md').write_text('Original source\n', encoding='utf-8')
        run('git', 'add', 'README.md')
        run('git', 'commit', '-m', 'Private policy verified fixture')


if __name__ == "__main__":
    unittest.main()
