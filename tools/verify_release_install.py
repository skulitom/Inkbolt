"""Run distribution checks on the executable extracted from a native release archive."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
CASES = (
    'test_cli.CliTests.test_examples_and_validation',
    'test_agent_discovery.AgentDiscoveryTests.test_cli_version_matches_the_installed_engine_and_mcp',
    'test_agent_discovery.AgentDiscoveryTests.test_doctor_reports_actual_store_paths_and_access_without_writing',
    'test_agent_discovery.AgentDiscoveryTests.test_essentials_has_bounded_discovery_and_mode_bound_cursors',
    'test_agent_discovery.AgentDiscoveryTests.test_routed_edit_render_retry_conflict_and_undo_match_direct_execution',
    'test_agent_workspace.AgentWorkspaceTests.test_readme_first_png_from_an_empty_workspace',
    'test_agent_workspace.AgentWorkspaceTests.test_historical_references_render_compare_and_publish_without_mutation',
    'test_boolean_precision_cli.BooleanPrecisionTests.test_tight_xor_subdivides_local_chords_and_scales_to_default_tolerance',
)


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('installation', type=Path, help='directory containing the extracted binary and notices')
    parser.add_argument('--built-binary', type=Path, help='require a byte-for-byte match with the original build')
    parser.add_argument('--thorough', action='store_true', help='run every Python CI module against the installed executable')
    parser.add_argument('--jobs', type=int, default=1, choices=range(1, 9), help='parallel modules for --thorough')
    parser.add_argument('--log-dir', type=Path, help='save full module logs in a new directory with --thorough')
    args = parser.parse_args()
    if args.log_dir and not args.thorough:
        parser.error('--log-dir requires --thorough')
    folder = args.installation.resolve(strict=True)
    binary = folder / ('inkbolt.exe' if os.name == 'nt' else 'inkbolt')
    digest = sha256(binary)
    if args.built_binary and sha256(args.built_binary) != digest:
        raise ValueError('Extracted executable differs from the original build')
    for name in ('LICENSE', 'README.md', 'THIRD_PARTY_NOTICES.md'):
        if (folder / name).read_text(encoding='utf8') != (ROOT / name).read_text(encoding='utf8'):
            raise ValueError(f'Packaged {name} differs from the source checkout')
    with (ROOT / 'Cargo.toml').open('rb') as stream:
        package = tomllib.load(stream)['package']
    expected = {'ok': True, 'result': {'name': package['name'], 'version': package['version']}}
    with tempfile.TemporaryDirectory() as directory:
        reply = subprocess.run([str(binary), '--version'], cwd=directory, capture_output=True,
                               check=True, timeout=15)
        if json.loads(reply.stdout) != expected:
            raise ValueError('Installed version differs from Cargo.toml')
    print(f"Testing {binary} (SHA-256 {digest})", flush=True)
    # All selected CLI and MCP clients take their subprocess path from this variable at import.
    os.environ['INKBOLT_EXE'] = str(binary)
    if args.thorough:
        from verify import python_checks
        os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
        python_checks(args.jobs, args.log_dir)
        if sha256(binary) != digest:
            raise ValueError('Installed executable changed during the suite')
        if args.log_dir:
            identity = {'name': package['name'], 'version': package['version'], 'binary_sha256': digest}
            (args.log_dir / 'installation.json').write_text(json.dumps(identity, indent=2) + '\n', encoding='utf8')
        return 0
    sys.path.insert(0, str(ROOT / 'tests'))
    suite = unittest.defaultTestLoader.loadTestsFromNames(CASES)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() and result.testsRun == len(CASES) and not result.skipped else 1


if __name__ == '__main__':
    raise SystemExit(main())
