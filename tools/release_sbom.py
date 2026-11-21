"""Generate a CycloneDX inventory for the binary from a completed native Cargo build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib
from urllib.parse import quote


REGISTRY = 'registry+https://github.com/rust-lang/crates.io-index'


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def build_inputs(log, binary, root_id):
    features = {}
    executables = []
    with log.open(encoding='utf8') as stream:
        last = None
        for line in stream:
            last = json.loads(line)
            if last['reason'] != 'compiler-artifact':
                continue
            features.setdefault(last['package_id'], set()).update(last['features'])
            if last['package_id'] == root_id and last['executable'] and last['target']['kind'] == ['bin']:
                executables.append(Path(last['executable']))
    if not last or last.get('reason') != 'build-finished' or last.get('success') is not True:
        raise ValueError('Expected a successful, completed Cargo build log')
    if len(executables) != 1 or not binary.samefile(executables[0]):
        raise ValueError('The native executable must match the Cargo build artifact')
    return features


def build_edges(tree, package_refs, root_ref):
    edges = {}
    parents = []
    for line in tree.splitlines():
        level, label = line.split('|', 1)
        depth = int(level)
        name, version = label.split()[:2]
        ref = package_refs.get((name, version.removeprefix('v')))
        if ref is None or depth > len(parents) or (depth == 0 and (parents or ref != root_ref)):
            raise ValueError(f'Cargo build log and dependency tree disagree at {label}')
        parents[depth:] = [ref]
        edges.setdefault(ref, set())
        if depth:
            edges[parents[depth-1]].add(ref)
    if set(edges) != set(package_refs.values()):
        raise ValueError('Cargo build log and dependency tree have different packages')
    return edges


def inventory(binary, target, log):
    compiler = subprocess.check_output(['rustc', '-vV'], text=True)
    if f'host: {target}' not in compiler.splitlines():
        raise ValueError('Run the inventory on the native build target')
    metadata = json.loads(subprocess.check_output(
        ['cargo', 'metadata', '--frozen', '--format-version', '1', '--filter-platform', target]))
    root_id = metadata['resolve']['root']
    built = build_inputs(log, binary, root_id)
    packages = {p['id']: p for p in metadata['packages']}
    with (Path(metadata['workspace_root']) / 'Cargo.lock').open('rb') as stream:
        locked = {(p['name'], p['version'], p.get('source')): p for p in tomllib.load(stream)['package']}
    app = packages[root_id]
    app_ref = f"{app['name']}-{target}"
    refs = {root_id: app_ref}
    components = []
    for package_id in sorted(built.keys() - {root_id}):
        p = packages[package_id]
        name, version = p['name'], p['version']
        if p['source'] != REGISTRY or not p['license']:
            raise ValueError(f'Review the source and license for {name} {version}')
        checksum = locked[name, version, REGISTRY]['checksum']
        ref = f'pkg:cargo/{quote(name, safe="")}@{quote(version, safe="")}'
        refs[package_id] = ref
        components.append({
            'type': 'library', 'bom-ref': ref, 'purl': ref, 'name': name, 'version': version,
            'licenses': [{'expression': p['license'].replace('/', ' OR ')}],
            'externalReferences': [{'type': 'distribution',
                                    'url': f'https://static.crates.io/crates/{name}/{name}-{version}.crate',
                                    'hashes': [{'alg': 'SHA-256', 'content': checksum}]}],
        })
    tree = subprocess.check_output(['cargo', 'tree', '--frozen', '--target', target, '--edges', 'normal,build',
                                    '--prefix', 'depth', '--format', '|{p}'], text=True)
    package_refs = {(packages[k]['name'], packages[k]['version']): ref for k, ref in refs.items()}
    edges = build_edges(tree, package_refs, app_ref)
    sqlite_id, = (k for k in built if packages[k]['name'] == 'libsqlite3-sys')
    if 'bundled' not in built[sqlite_id] or any('sqlcipher' in f for f in built[sqlite_id]):
        raise ValueError('Review the native SQLite selection for this build')
    amalgamation = Path(packages[sqlite_id]['manifest_path']).parent / 'sqlite3' / 'sqlite3.c'
    with amalgamation.open(encoding='utf8') as source:
        for line in source:
            match = re.fullmatch(r'#define SQLITE_VERSION\s+"([0-9.]+)"', line.rstrip())
            if match:
                version = match.group(1)
                break
        else:
            raise ValueError('Missing SQLite version in the bundled amalgamation')
    sqlite = f'pkg:generic/sqlite@{version}'
    components.append({'type': 'library', 'bom-ref': sqlite, 'purl': sqlite, 'name': 'SQLite', 'version': version,
                       'licenses': [{'license': {'name': 'Public domain', 'url': 'https://sqlite.org/copyright.html'}}],
                       'properties': [{'name': 'inkbolt:amalgamation-sha256', 'value': file_hash(amalgamation)}]})
    edges[refs[sqlite_id]].add(sqlite)
    edges[sqlite] = set()
    return {'bomFormat': 'CycloneDX', 'specVersion': '1.6', 'version': 1,
            'metadata': {'component': {'type': 'application', 'bom-ref': app_ref, 'name': app['name'],
                                      'version': app['version'], 'licenses': [{'expression': app['license']}],
                                      'hashes': [{'alg': 'SHA-256', 'content': file_hash(binary)}],
                                      'properties': [{'name': 'inkbolt:target', 'value': target},
                                                     {'name': 'inkbolt:rustc', 'value': compiler.splitlines()[0]}]}},
            'components': sorted(components, key=lambda component: component['bom-ref']),
            'dependencies': [{'ref': key, 'dependsOn': sorted(edges[key])} for key in sorted(edges)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--build-log', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    data = (json.dumps(inventory(args.binary, args.target, args.build_log), indent=2) + '\n').encode('utf8')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as scratch:
        ready = Path(scratch) / 'inventory.json'
        ready.write_bytes(data)
        try:
            os.link(ready, args.out)
        except FileExistsError:
            if args.out.read_bytes() != data:
                raise ValueError('Existing inventory differs. Choose a fresh destination.')


if __name__ == '__main__':
    main()
