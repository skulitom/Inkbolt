"""Locate retained content and receipt IDs without prescribing solver folder names."""
from contextlib import closing
import sqlite3

from benchmark_runtime import require
from workload_cases import sha


def contained_file(root,path):
    return (path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root)
            and not any((root/parent).is_symlink() for parent in path.relative_to(root).parents))


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
