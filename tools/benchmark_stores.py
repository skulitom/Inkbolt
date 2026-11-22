"""Locate retained content and receipt IDs without prescribing solver folder names."""
from contextlib import closing
from pathlib import Path, PurePosixPath, PureWindowsPath
import sqlite3

from benchmark_runtime import require
from workload_cases import sha


def contained_file(root,path):
    return (path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root)
            and not any((root/parent).is_symlink() for parent in path.relative_to(root).parents))


def recorded_path(value):
    """Compare captured path names without opening anything on the original host."""
    require(isinstance(value, str) and '\0' not in value, 'Expected a recorded absolute path')
    windows = PureWindowsPath(value)
    if windows.drive:
        path = PureWindowsPath(value.removeprefix('\\\\?\\'))
        require(len(path.drive) == 2 and path.drive[1] == ':', 'Expected a local Windows drive')
    else:
        path = PurePosixPath(value)
    require(path.is_absolute() and '..' not in path.parts, 'Invalid recorded absolute path')
    return path


def photo_asset_store(case, imported, review, publications, session_root, receipts):
    """Rebase the durable asset binding into the captured workspace."""
    require(isinstance(publications, dict) and set(publications) == {'edited', 'historical'},
            'Missing native publication receipts')
    edited_output = recorded_path(publications['edited']['path'])
    driver = getattr(case, 'driver_evidence', None) or {}
    if driver.get('imported') and 'solve_workspace' not in driver:
        # Older captures only recorded absolute paths inside the delivered
        # reports. Cross-check both outputs and the independently located DB.
        origin = edited_output.parent
    else:
        origin = recorded_path(driver.get('solve_workspace', str(case.root.resolve())))
    require(edited_output == origin/'edited.tiff' and
            recorded_path(publications['historical']['path']) == origin/'historical.tiff',
            'Photo publication paths differ from the captured outputs')
    base = review['base_ref']
    require(base['session_id'] == receipts['create']['session_id'] and base['revision'] == 0 and
            recorded_path(base['session_root']) == origin/session_root,
            'Photo review points to a different original session')
    store = recorded_path(imported['storage']['store_root'])
    require(store.is_relative_to(origin) and recorded_path(review['proposed_resources']['asset_root']) == store and
            all(recorded_path(r['resources']['asset_root']) == store for r in receipts.values()),
            'Photo import, review and saved revisions must bind the same workspace tile store')
    parts = store.relative_to(origin).parts
    relative = Path(*parts)
    require(relative.parts == parts and not relative.drive and not relative.root and
            all(':' not in part for part in parts), 'Tile store path cannot be relocated safely')
    root = case.root.resolve()
    local = root/relative
    require(not any((root/p).is_symlink() for p in (relative, *relative.parents)) and
            local.is_dir() and local.resolve().is_relative_to(root), 'Linked or missing captured tile store')
    require(all(contained_file(root,p) for p in local.glob('*.native-tile')),
            'Tile store contains a linked or nonregular block')
    return relative.as_posix()


def retained_asset_store(case,resources):
    """Require a complete store of the independently encoded original image bytes."""
    root=case.root.resolve();wanted={sha(raw)+'.rgba8':raw for raw in resources}
    require(bool(wanted),'Expected at least one pinned image resource')
    for first in sorted(root.rglob(next(iter(wanted)))):
        paths=[(first.parent/name,raw) for name,raw in wanted.items()]
        if all(contained_file(root,path) and path.stat().st_size==len(raw) and path.read_bytes()==raw
               for path,raw in paths):
            return first.parent.relative_to(root).as_posix()
    require(False,'Missing intact workspace image store with all pinned original samples')


def retained_publication_store(case,request_id):
    """Locate an ID read-only; the engine still validates the ledger and receipt."""
    root=case.root.resolve();stores=[]
    for path in sorted(root.rglob('publications.sqlite3')):
        require(contained_file(root,path),'Linked or external publication store')
        try:
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
                db.execute('PRAGMA trusted_schema=OFF')
                db.set_progress_handler(lambda:1,10000)
                found=db.execute('SELECT 1 FROM publications WHERE request_id=? LIMIT 1',(request_id,)).fetchone()
        except sqlite3.Error:
            continue  # An unreadable database cannot establish the requested ID.
        if found:stores.append(path.parent.relative_to(root).as_posix())
    require(len(stores)==1,'Missing or ambiguous captured publication store for the delivered request ID')
    return stores[0]
