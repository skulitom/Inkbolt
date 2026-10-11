"""Verify the current Windows candidate in an owned, cached native Linux checkout.

Usage: python tools/verify_wsl.py [--distribution Ubuntu] [--python python3.11]
                               [the usual tools/verify.py options]
The local private guard remains mandatory on both sides. No commits or pushes
are made in the mirror, and no Windows target directory is copied into Linux.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def safe_name(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or '..' in path.parts or '\\' in name
            or path.as_posix() != name or path.parts[0] == '.git'):
        raise ValueError('Invalid mirror candidate path')
    return path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def linux_environment(environment, root):
    result = dict(environment)
    # Each wsl.exe invocation receives a different Windows-launch socket. Checks
    # use native Linux tools only. Remove it from the actual child environment,
    # rather than teaching the verifier to ignore arbitrary environment changes.
    result.pop('WSL_INTEROP', None)
    result['PWD'] = str(root)
    return result


def unpack(package):
    """Validate the entire snapshot before changing a mirror."""
    with zipfile.ZipFile(package) as archive:
        meta = json.loads(archive.read('manifest.json'))
        files = meta['files']
        expected = {'manifest.json', 'private-content-policy.json'} | {'files/' + name for name in files}
        if set(archive.namelist()) != expected or len(archive.namelist()) != len(expected):
            raise ValueError('Unexpected or duplicate snapshot entries')
        contents = {}
        for name, digest in files.items():
            safe_name(name)
            data = archive.read('files/' + name)
            if sha(data) != digest:
                raise ValueError('Candidate hash mismatch: ' + name)
            contents[name] = data
        policy = archive.read('private-content-policy.json')
        if sha(policy) != meta['policy_sha256']:
            raise ValueError('Private policy hash mismatch')
    return meta, contents, policy


def confined(root, name):
    path = root.joinpath(*safe_name(name).parts)
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Mirror path escapes its owned checkout')
    for parent in path.parents:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError('Mirror contains a directory link')
    return path


def linux_run(package, arguments):
    import fcntl
    meta, contents, policy = unpack(package)
    root = Path.home() / '.cache/inkbolt/wsl' / sha(meta['source'].encode())[:16]
    marker = root / '.git/inkbolt-wsl-owner.json'
    if root.exists():
        if root.is_symlink() or (root / '.git').is_symlink() or not marker.is_file():
            raise ValueError('Refusing to adopt an unowned Linux checkout')
        previous = json.loads(marker.read_text())
        if previous['source'] != meta['source']:
            raise ValueError('Linux checkout belongs to another source')
    else:
        root.mkdir(parents=True)
        subprocess.run(['git', 'init', '--quiet', str(root)], check=True)
        previous = dict(source=meta['source'], files={})
        marker.write_text(json.dumps(previous))
    with (root / '.git/inkbolt-wsl.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # A direct verifier must also have finished before source synchronization.
        state = root / '.git/inkbolt-verify'
        state.mkdir(exist_ok=True)
        with (state / 'lock').open('a+b') as verifier_lock:
            fcntl.flock(verifier_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Preserve any edits someone made inside this owned mirror.
            present = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root).decode().split('\0')
            if set(present) - {''} - previous['files'].keys():
                raise ValueError('Unexpected source files in Linux mirror; preserve and inspect them')
            for name, digest in previous['files'].items():
                path = confined(root, name)
                if not path.is_file() or sha(path.read_bytes()) != digest:
                    raise ValueError('Linux mirror has local edits: ' + name)
            for name in previous['files'].keys() - contents.keys():
                confined(root, name).unlink()
            for name, data in contents.items():
                path = confined(root, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists() or path.read_bytes() != data:
                    path.write_bytes(data)
            (root / '.git/private-content-policy.json').write_bytes(policy)
            hook = root / '.git/hooks/pre-commit'
            hook.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' '
                            + shlex.quote(str(root / 'tools/check_repo.py')) + ' --staged\n')
            hook.chmod(0o700)
            subprocess.run(['git', 'add', '--all'], cwd=root, check=True, capture_output=True)
            marker.write_text(json.dumps(meta, indent=2) + '\n')
        print(f'Linux checkout: {root}\nCandidate: {sha(json.dumps(meta["files"], sort_keys=True).encode())}', flush=True)
        return subprocess.call([sys.executable, 'tools/verify.py', *arguments], cwd=root,
                               env=linux_environment(os.environ, root))


def windows_run(distribution, python, arguments):
    import check_repo
    from verify_inputs import snapshot
    issues, _ = check_repo.check_repository(ROOT)
    if issues:
        raise ValueError('\n'.join(issues))
    before = snapshot(ROOT)
    policy_path = Path(check_repo.git(ROOT, 'rev-parse', '--git-path', 'private-content-policy.json').decode().strip())
    if not policy_path.is_absolute():
        policy_path = ROOT / policy_path
    policy = policy_path.read_bytes()
    meta = dict(source=str(ROOT.resolve()), files=before, policy_sha256=sha(policy))
    prefix = ['wsl', '--distribution', distribution, '--exec']
    def linux_path(path):
        return subprocess.check_output(prefix + ['wslpath', '-a', '-u', str(Path(path).resolve())], text=True).strip()
    arguments = list(arguments)
    for index, argument in enumerate(arguments):
        if argument == '--report' and index + 1 < len(arguments):
            arguments[index + 1] = linux_path(arguments[index + 1])
        elif argument.startswith('--report='):
            arguments[index] = '--report=' + linux_path(argument.split('=', 1)[1])
    with tempfile.TemporaryDirectory(prefix='inkbolt-wsl-') as directory:
        package = Path(directory) / 'candidate.zip'
        with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', json.dumps(meta))
            archive.writestr('private-content-policy.json', policy)
            for name in before:
                data = (ROOT / safe_name(name)).read_bytes()
                if sha(data) != before[name]:
                    raise ValueError('Source changed while preparing Linux snapshot')
                archive.writestr('files/' + name, data)
        # bash supplies the distribution's Cargo PATH; all variable values are
        # positional arguments, never interpolated shell source.
        code = subprocess.call(prefix + ['bash', '-lc', 'exec "$@"', 'inkbolt-wsl',
            python, linux_path(__file__), '--sync-package', linux_path(package), *arguments])
    if snapshot(ROOT) != before or policy_path.read_bytes() != policy:
        raise ValueError('Windows candidate changed during Linux verification; rerun before accepting')
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--distribution', default='Ubuntu')
    parser.add_argument('--python', default='python3.11')
    parser.add_argument('--public', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--sync-package', type=Path, help=argparse.SUPPRESS)
    args, arguments = parser.parse_known_args()
    if args.public:
        parser.error('The WSL development mirror always requires the private guard; public clones use tools/verify.py --public directly')
    if args.sync_package:
        if sys.platform != 'linux':
            parser.error('Snapshot synchronization requires Linux')
        return linux_run(args.sync_package, arguments)
    if os.name != 'nt':
        parser.error('Run this entry point from Windows; Linux uses tools/verify.py directly')
    return windows_run(args.distribution, args.python, arguments)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        raise SystemExit(f'WSL verification failed: {error}') from error
