"""Explicit session roots through Unix directory aliases, across CLI and MCP."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from test_mcp import Client
from test_session_lineage import V1
from test_sessions_cli import invoke


@unittest.skipUnless(os.name == 'posix', 'Unix directory-alias regression')
class SessionPathTests(unittest.TestCase):
    def test_parent_aliases_cover_history_operations_without_following_database_links(self):
        for transport in ('cli','mcp'):
            with self.subTest(transport=transport), tempfile.TemporaryDirectory() as temp:
                base=Path(temp);real=base/'real';real.mkdir()
                alias=base/'alias';alias.symlink_to(real,target_is_directory=True)
                client=Client(args=('--tools','core')) if transport=='mcp' else None
                try:
                    if client:client.initialize()
                    def call(command,error=None,**args):
                        result=(client.tool('run',command=command,arguments=args)['structuredContent']
                                if client else invoke(dict(command=command,**args)))
                        self.assertEqual(result['ok'],error is None,result)
                        if error:
                            self.assertEqual(result['error']['code'],error);return result['error']
                        return result['result']
                    capabilities=call('capabilities')['session_contract']
                    self.assertTrue(capabilities['parent_directory_aliases'])
                    self.assertFalse(capabilities['database_symlinks'])
                    document=call('document.create',id='original',kind='vector',width=8,height=6)
                    root=alias/'new'/'sessions'
                    args=dict(session_root=str(root),session_id='work')
                    created=call('session.create',request_id='create',document=document,**args)
                    replay=call('session.create',request_id='create',document=document,**args)
                    self.assertEqual(replay['receipt'],created['receipt']);self.assertTrue(replay['replayed'])
                    call('session.apply',expected_revision=0,request_id='named',action=dict(type='snapshot',name='first'),**args)
                    state=call('session.read',**args)
                    direct=dict(args,session_root=str(real/'new'/'sessions'))
                    self.assertEqual(state,call('session.read',**direct))
                    self.assertEqual(call('session.verify',**args)['revision'],1)
                    output=dict(output_root=str(alias),file_name='history.sqlite3')
                    source=call('session.backup',expected_revision=1,output=output,**args)['backup']
                    before=(real/'history.sqlite3').read_bytes()
                    call('session.backup',expected_revision=1,output=output,error='OUTPUT_EXISTS',**args)
                    recovered=dict(args,session_root=str(alias/'recovered'))
                    call('session.recover',source=source,**recovered)
                    self.assertEqual(call('session.read',**recovered),state)
                    parent=dict(source=source,session_id='work',revision=1)
                    next_=call('session.continue',session_root=str(alias/'continued'),session_id='next',request_id='continue',parent=parent)
                    self.assertEqual(next_['document'],dict(state['document'],revision=0))
                    self.assertEqual(next_['lineage']['parent'],parent)
                    # Build an original version-1 backup from its frozen schema.
                    v1=alias/'v1.sqlite3'
                    with closing(sqlite3.connect(real/'history.sqlite3')) as current, closing(sqlite3.connect(v1)) as old:
                        old.execute('PRAGMA application_id=1229867859');old.execute('PRAGMA user_version=1')
                        for statement in V1:old.execute(statement)
                        for table in ('states','meta','requests','snapshots'):
                            for row in current.execute('SELECT * FROM '+table):
                                old.execute(f"INSERT INTO {table} VALUES({','.join('?' for _ in row)})",row)
                        old.commit()
                    original=v1.read_bytes()
                    identity=dict(file_path=str(v1),bytes=len(original),sha256=hashlib.sha256(original).hexdigest())
                    migrated=call('session.migrate',session_id='work',source=identity,target_version=2,
                                  output=dict(output_root=str(alias),file_name='migrated.sqlite3'))
                    self.assertTrue(migrated['history_preserved']);self.assertEqual(migrated['session']['storage_version'],2)
                    self.assertEqual(v1.read_bytes(),original);self.assertEqual((real/'history.sqlite3').read_bytes(),before)
                    link=alias/'linked-source.sqlite3';link.symlink_to(real/'history.sqlite3')
                    call('session.recover',session_root=str(alias/'refused'),session_id='work',
                         source=dict(source,file_path=str(link)),error='INVALID_REQUEST')
                    database=root/(hashlib.sha256(b'work').hexdigest()+'.sqlite3')
                    retained=alias/'retained.sqlite3';database.rename(retained);database.symlink_to(retained)
                    bytes_before=retained.read_bytes()
                    call('session.read',error='SESSION_CORRUPT',**args)
                    call('session.create',request_id='create',document=document,error='SESSION_CORRUPT',**args)
                    self.assertEqual(retained.read_bytes(),bytes_before)
                    call('session.read',session_root=str(alias/'missing'),session_id='work',error='SESSION_NOT_FOUND')
                finally:
                    if client:client.close()


if __name__=='__main__':unittest.main()
