"""Retained-store lookup stays content-bound, read-only and inside its capture."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest

from test_cli import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from benchmark_runtime import TaskFailure
from benchmark_stores import photo_asset_store,retained_asset_store,retained_publication_store
from test_images_cli import canonical
from workload_cases import sha


class RetainedStoreTests(unittest.TestCase):
    def test_photo_store_rebases_old_windows_paths_and_requires_every_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            (root/'chosen tiles').mkdir()
            origin='D:/archived/work'
            store=origin+'/chosen tiles'
            case=SimpleNamespace(root=root,driver_evidence={'imported': True})
            imported={'storage':{'store_root':store}}
            review={'base_ref':{'session_root':origin+'/sessions','session_id':'photo','revision':0},
                    'proposed_resources':{'asset_root':store}}
            outputs={name:{'path':origin+'/'+name+'.tiff'} for name in ('edited','historical')}
            receipts={name:{'session_id':'photo','resources':{'asset_root':store}}
                      for name in ('create','edit','undo','redo')}
            def locate():
                return photo_asset_store(case,imported,review,outputs,'sessions',receipts)
            self.assertEqual(locate(),'chosen tiles')
            case.driver_evidence['solve_workspace']=origin
            self.assertEqual(locate(),'chosen tiles')
            for recorded in (origin+'/wrong',origin+'/../work/chosen tiles','D:/outside/chosen tiles'):
                receipts['undo']['resources']['asset_root']=recorded
                with self.assertRaises(TaskFailure):locate()
            receipts['undo']['resources']['asset_root']=store
            case.driver_evidence['solve_workspace']='D:/other'
            with self.assertRaises(TaskFailure):locate()
            case.driver_evidence.pop('solve_workspace')
            outputs['historical']['path']='D:/unrelated/historical.tiff'
            with self.assertRaises(TaskFailure):locate()

    def files(self,root):
        return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def assets(self,root,resources):
        root.mkdir(parents=True,exist_ok=True)
        for raw in resources:(root/(sha(raw)+'.rgba8')).write_bytes(raw)

    def ledger(self,root,*requests):
        root.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(root/'publications.sqlite3')) as db:
            db.execute('CREATE TABLE publications(request_id TEXT PRIMARY KEY)')
            db.executemany('INSERT INTO publications VALUES (?)',[(name,) for name in requests]);db.commit()

    def test_image_store_requires_all_exact_original_resources_together(self):
        resources=[canonical(1,1,bytes(color)) for color in ([1,2,3,255],[4,5,6,255])]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();case=SimpleNamespace(root=root)
            self.assets(root/'chosen images',resources);before=self.files(root)
            self.assertEqual(retained_asset_store(case,resources),'chosen images');self.assertEqual(self.files(root),before)
            path=root/'chosen images'/(sha(resources[1])+'.rgba8');path.write_bytes(resources[0])
            with self.assertRaises(TaskFailure):retained_asset_store(case,resources)
            path.unlink();self.assets(root/'another store',[resources[1]])
            with self.assertRaises(TaskFailure):retained_asset_store(case,resources)
            self.assets(root/'another store',resources)
            self.assertEqual(retained_asset_store(case,resources),'another store')

    def test_receipt_lookup_supports_separate_ledgers_without_writing_to_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();case=SimpleNamespace(root=root)
            self.ledger(root/'first receipts','wide');self.ledger(root/'second receipts','square','tall')
            (root/'unused').mkdir();(root/'unused/publications.sqlite3').write_bytes(b'not a receipt database')
            before=self.files(root)
            self.assertEqual(retained_publication_store(case,'wide'),'first receipts')
            self.assertEqual(retained_publication_store(case,'tall'),'second receipts')
            with self.assertRaises(TaskFailure):retained_publication_store(case,'missing')
            self.assertEqual(self.files(root),before)
            self.ledger(root/'duplicate receipts','wide')
            with self.assertRaises(TaskFailure):retained_publication_store(case,'wide')

    def test_linked_resource_and_receipt_files_do_not_escape_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory).resolve();root=base/'capture';root.mkdir();case=SimpleNamespace(root=root)
            raw=canonical(1,1,bytes([1,2,3,255]));self.assets(base/'external',[raw]);self.ledger(base/'external','wide')
            try:
                (root/(sha(raw)+'.rgba8')).symlink_to(base/'external'/(sha(raw)+'.rgba8'))
                (root/'publications.sqlite3').symlink_to(base/'external/publications.sqlite3')
            except OSError as error:self.skipTest('Host cannot create fixture symlinks: '+str(error))
            with self.assertRaises(TaskFailure):retained_asset_store(case,[raw])
            with self.assertRaises(TaskFailure):retained_publication_store(case,'wide')


if __name__=='__main__':unittest.main()
