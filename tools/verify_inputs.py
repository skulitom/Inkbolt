"""Conservative content fingerprints; no coverage heuristic can waive a check."""
import ast
from fnmatch import fnmatchcase
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def snapshot(root):
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root).decode('utf-8').split('\0')
    result = {}
    for name in sorted(set(names) - {''}):
        path = root / name
        if path.is_symlink():
            result[name] = 'symlink:' + os.readlink(path)
        elif path.is_file():
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            result[name] = '<missing>'
    return result


def dependency_graph(root, files):
    """Parse each helper once; file-reference lookup is constant-time."""
    modules, references, graph = {}, {}, {}
    for name in files:
        references.setdefault(name, set()).add(name)
        references.setdefault(Path(name).name, set()).add(name)
        if name.startswith(('tests/', 'tools/')) and name.endswith('.py'):
            modules.setdefault(Path(name).stem, set()).add(name)
    def imported(module):
        parts = module.split('.')
        # Package imports must not silently drop dependencies. Select the
        # package's Python files as well as ambiguous flat module matches.
        matches = set(modules.get(parts[0], ()))
        for prefix in (parts[0] + '/', 'tests/' + parts[0] + '/', 'tools/' + parts[0] + '/'):
            matches.update(p for p in files if p.startswith(prefix) and p.endswith('.py'))
        return matches
    for name in files:
        if not name.endswith('.py') or files[name] == '<missing>':
            continue
        try:
            source = (root / name).read_text(encoding='utf-8-sig')
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            graph[name] = None
            continue
        if 'ls-files' in source:
            graph[name] = None
            continue
        edges, unknown, file_loaders = set(), False, 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    edges.update(imported(alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    edges.update(files)  # Unclassified relative package import.
                elif node.module:
                    edges.update(imported(node.module))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value.replace('\\', '/')
                # Includes split ROOT / 'examples' / 'file.json' expressions.
                edges.update(references.get(value, ()))
            elif isinstance(node, ast.Call):
                function = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ''
                if function in ('glob', 'rglob'):
                    if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                        unknown = True
                    else:
                        # A fixture enumerating generated *.rgba8 files does
                        # not import every Python module. Bind all candidate
                        # files matching the pattern, regardless of directory;
                        # newly matching files also change this fingerprint.
                        pattern = node.args[0].value
                        edges.update(p for p in files if fnmatchcase(p, pattern) or fnmatchcase(Path(p).name, pattern))
                elif function == 'spec_from_file_location':
                    file_loaders += 1
                    literals = [v.value for v in ast.walk(node.args[1]) if isinstance(v, ast.Constant) and isinstance(v.value, str)] if len(node.args) > 1 else []
                    matched = {p for value in literals for p in references.get(value.replace('\\', '/'), ()) if p.endswith('.py')}
                    if matched:
                        edges.update(matched)
                    else:
                        unknown = True
                elif function == '__import__':
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        edges.update(imported(node.args[0].value))
                    else:
                        unknown = True
                elif function == 'import_module':
                    unknown = True
        if 'importlib' in source and not file_loaders:
            unknown = True
        graph[name] = None if unknown else edges
    return graph


def python_closure(root, start, files, graph=None):
    """Transitive imports/literal files; unknown dynamic dependencies use all inputs."""
    graph = dependency_graph(root, files) if graph is None else graph
    pending, seen = [start], set()
    while pending:
        name = pending.pop()
        if name in seen or name not in files:
            continue
        seen.add(name)
        edges = graph.get(name, set())
        if edges is None:
            return set(files)
        pending.extend(edges)
    return seen


def fingerprints(root, files, environment, modules):
    infrastructure = {p for p in files if p.startswith('tools/verify')}
    # Unclassified files, lockfiles, configuration and examples invalidate all
    # engine checks. Markdown is selected through fixture references instead.
    engine = {p for p in files if not p.startswith(('tests/', 'tools/')) and not p.endswith('.md')}
    rust = engine | {p for p in files if p.startswith('tests/') and p.endswith('.rs')}
    def key(name, selected):
        return digest([name, environment, {p: files[p] for p in sorted(selected | infrastructure)}])
    result = {name: key(name, rust) for name in ('build', 'fmt', 'clippy', 'rust')}
    graph = dependency_graph(root, files)
    for name in modules:
        result[name] = key(name, engine | python_closure(root, f'tests/{name}.py', files, graph))
    return result


def environment_identity(root):
    versions = {}
    for command in (['rustc', '-vV'], ['cargo', '--version']):
        versions[command[0]] = subprocess.check_output(command, cwd=root, timeout=10).decode('utf-8').strip()
    # Hash values rather than storing environment secrets in the run record.
    # The copied executable is a verifier-internal input, keyed separately.
    environment = {k: v for k, v in os.environ.items() if k != 'INKBOLT_EXE'}
    return digest([sys.executable, sys.version, sys.platform, versions, environment, str(root)])
