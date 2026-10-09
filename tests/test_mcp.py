"""Independent stdio JSON-RPC client checks; no network transport or SDK dependency."""
from contextlib import closing
import hashlib
import json
import queue
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from test_cli import EXE
from test_sessions_cli import invoke
from test_editing_cli import png_pixels


class Client:
    def __init__(self, args=(), workspace=None):
        prefix=[] if workspace is None else ['--workspace',str(workspace)]
        self.process=subprocess.Popen([str(EXE),*prefix,'mcp',*args],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.messages=queue.Queue();self.saved={};self.next_id=0
        def receive():
            for line in self.process.stdout:
                try:self.messages.put(json.loads(line))
                except Exception as e:self.messages.put(e)
        self.reader=threading.Thread(target=receive,daemon=True);self.reader.start()

    def close(self):
        self.process.stdin.close()
        try:self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait();raise
        self.reader.join(timeout=2)
        stderr=self.process.stderr.read();self.process.stdout.close();self.process.stderr.close()
        assert self.process.returncode==0,(self.process.returncode,stderr)
        assert stderr==b'',stderr

    def send(self,method,params=None,notification=False):
        message=dict(jsonrpc='2.0',method=method)
        if not notification:self.next_id+=1;message['id']=self.next_id
        if params is not None:message['params']=params
        self.raw(json.dumps(message).encode()+b'\n')
        return message.get('id')

    def raw(self,data):self.process.stdin.write(data);self.process.stdin.flush()

    def response(self,rid):
        if rid in self.saved:return self.saved.pop(rid)
        while True:
            value=self.messages.get(timeout=20)
            if isinstance(value,Exception):raise value
            assert value['jsonrpc']=='2.0',value
            if value.get('id')==rid:return value
            self.saved[value.get('id')]=value

    def rpc(self,method,params=None):return self.response(self.send(method,params))

    def initialize(self,version='2025-11-25'):
        result=self.rpc('initialize',dict(protocolVersion=version,capabilities={},clientInfo=dict(name='independent-fixture-client',version='1')))['result']
        self.send('notifications/initialized',notification=True)
        return result

    def tool(self,operation,**kw):
        r=self.rpc('tools/call',dict(name='inkbolt_'+operation.replace('.','_'),arguments=kw))
        assert 'result' in r,r
        assert r['result']['isError']==(not r['result']['structuredContent']['ok']),r
        return r['result']

    def success(self,command,**kw):
        r=self.tool(command,**kw);assert not r['isError'],r;return r['structuredContent']['result']


class McpTests(unittest.TestCase):
    def setUp(self):self.client=Client();self.addCleanup(self.client.close)

    def test_handshake_pagination_schema_refs_annotations_and_cli_parity(self):
        c=self.client
        self.assertEqual(c.rpc('tools/list')['error']['code'],-32000)
        init=c.initialize('future-version')
        self.assertEqual(init['protocolVersion'],'2025-11-25');self.assertEqual(init['capabilities'],{'tools':{'listChanged':False}})
        self.assertEqual(c.rpc('ping')['result'],{})
        tools=[];cursor=None
        while True:
            page=c.rpc('tools/list',{} if cursor is None else dict(cursor=cursor))['result']
            self.assertLessEqual(len(page['tools']),8);tools.extend(page['tools']);cursor=page.get('nextCursor')
            if cursor is None:break
        capabilities=c.success('capabilities')
        self.assertEqual({t['name'] for t in tools},{'inkbolt_'+v.replace('.','_') for v in capabilities['commands']})
        self.assertEqual(capabilities,invoke(dict(command='capabilities'))['result'])
        for tool in tools:
            schema=tool['inputSchema'];self.assertEqual(schema['type'],'object');self.assertFalse(schema['additionalProperties']);self.assertNotIn('command',schema['properties'])
            def refs(value):
                if isinstance(value,dict):
                    if '$ref' in value:self.assertIn(value['$ref'].split('/')[-1],schema['$defs'])
                    for v in value.values():refs(v)
                elif isinstance(value,list):
                    for v in value:refs(v)
            refs(schema)
            self.assertEqual(tool['execution'],dict(taskSupport='forbidden'))
            self.assertFalse(tool['annotations']['openWorldHint'])
        by_name={t['name']:t for t in tools}
        self.assertTrue(by_name['inkbolt_document_diff']['annotations']['readOnlyHint'])
        self.assertFalse(by_name['inkbolt_document_publish']['annotations']['readOnlyHint'])
        self.assertTrue(by_name['inkbolt_session_apply']['annotations']['destructiveHint'])
        self.assertEqual(c.rpc('tools/list',dict(cursor='bad'))['error']['code'],-32602)
        self.assertEqual(c.rpc('tasks/list')['error']['code'],-32601)

    def test_malformed_duplicate_oversized_messages_and_reused_ids_recover(self):
        c=self.client;c.initialize()
        for raw,code in [(b'{\n',-32700),(b'{}\n',-32600),(b'[]\n',-32600),(b'{"jsonrpc":"2.0","id":null,"method":"ping"}\n',-32600),(b'{"jsonrpc":"2.0","id":99,"method":"ping","method":"tools/list"}\n',-32700),(b' '* (16*1024*1024+16385)+b'\n',-32600)]:
            c.raw(raw);self.assertEqual(c.response(None)['error']['code'],code)
            self.assertEqual(c.rpc('ping')['result'],{})
        request=dict(jsonrpc='2.0',id='unique',method='ping');c.raw(json.dumps(request).encode()+b'\n');self.assertEqual(c.response('unique')['result'],{})
        c.raw(json.dumps(request).encode()+b'\n');self.assertEqual(c.response('unique')['error']['code'],-32600)
        c.send('notifications/unknown',notification=True)
        c.send('notifications/cancelled',dict(requestId='unknown'),notification=True)
        c.send('notifications/cancelled',dict(requestId={}),notification=True)
        self.assertEqual(c.rpc('ping')['result'],{})
        self.assertEqual(c.saved,{})

    def test_tool_input_errors_are_structured_and_following_valid_work_succeeds(self):
        c=self.client;c.initialize()
        self.assertEqual(c.rpc('tools/call',dict(name='missing'))['error']['code'],-32602)
        self.assertEqual(c.rpc('tools/call',dict(name='inkbolt_capabilities',arguments=[]))['error']['code'],-32602)
        for kw in [dict(extra=True),dict(command='document.create'),dict(response_format='other')]:
            result=c.tool('capabilities',**kw);self.assertTrue(result['isError']);self.assertEqual(result['structuredContent']['error']['code'],'INVALID_REQUEST')
        result=c.tool('document.create',id='bad',kind='raster',width=0,height=1)
        self.assertEqual(result['structuredContent']['error']['code'],'INVALID_DOCUMENT')
        result=c.tool('document.create',id='valid',kind='raster',width=2,height=2,response_format='markdown')
        self.assertFalse(result['isError']);self.assertIn('```json',result['content'][0]['text'])
        self.assertEqual(result['structuredContent']['result']['width'],2)
        # Duplicate nested arguments must not be normalized away by the adapter.
        c.raw(b'{"jsonrpc":"2.0","id":"dupe","method":"tools/call","params":{"name":"inkbolt_document_create","arguments":{"id":"a","id":"b"}}}\n')
        self.assertEqual(c.response(None)['error']['code'],-32700)
        self.assertEqual(c.rpc('ping')['result'],{})

    def test_connection_request_id_budget_is_explicit_and_notifications_still_work(self):
        c=self.client;c.initialize()
        messages=[dict(jsonrpc='2.0',id=f'budget-{n}',method='ping') for n in range(4095)]
        c.raw(b''.join(json.dumps(m).encode()+b'\n' for m in messages))
        for m in messages:self.assertEqual(c.response(m['id'])['result'],{})
        self.assertEqual(c.rpc('ping')['error']['code'],-32000)
        c.send('notifications/cancelled',dict(requestId='unknown'),notification=True)

    def test_agent_workflow_edit_inspect_diff_publish_retry_and_undo(self):
        c=self.client;c.initialize()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);session=dict(session_root=str(root/'sessions'),session_id='design')
            doc=c.success('document.create',id='design',kind='vector',width=16,height=12)
            c.success('session.create',**session,request_id='create',document=doc)
            action=dict(type='edit',operations=[dict(op='add',item=dict(id='box',name='Original icon',content=dict(type='vector',geometry=dict(shape='rect',x=2,y=3,width=8,height=6),fill=[10,90,230,255])))])
            edited=c.success('session.apply',**session,request_id='draw',expected_revision=0,action=action)
            inspection=c.success('document.inspect',document=edited['document']);self.assertEqual(inspection['items'][0]['geometry_bounds'],[2,3,10,9])
            difference=c.success('session.diff',**session,from_revision=0,to_revision=1,compare_pixels=True)
            self.assertEqual(difference['rendered_pixels']['changed_pixels'],48)
            receipt=c.success('session.publish',**session,expected_revision=1,output=dict(output_root=str(root),file_name='icon.png',format='png'))
            data=(root/'icon.png').read_bytes();self.assertEqual(receipt['sha256'],hashlib.sha256(data).hexdigest())
            w,h,px,_=png_pixels(data);self.assertEqual((w,h),(16,12))
            for y in range(h):
                for x in range(w):self.assertEqual(px[(y*w+x)*4:(y*w+x+1)*4],bytes([10,90,230,255]) if 2<=x<10 and 3<=y<9 else bytes(4))
            retry=c.success('session.apply',**session,request_id='draw',expected_revision=0,action=action)
            self.assertTrue(retry['replayed']);self.assertEqual(retry['receipt'],edited['receipt'])
            c.success('session.apply',**session,request_id='undo',expected_revision=1,action=dict(type='undo'))
            self.assertFalse(c.success('session.diff',**session,from_revision=0,to_revision=2,compare_pixels=True)['changed'])
            error=c.tool('session.publish',**session,expected_revision=2,output=dict(output_root=str(root),file_name='icon.png',format='png'))
            self.assertEqual(error['structuredContent']['error']['code'],'OUTPUT_EXISTS');self.assertEqual((root/'icon.png').read_bytes(),data)

    def test_queued_cancellation_suppresses_response_and_preserves_persistent_state(self):
        c=self.client;c.initialize()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);s=dict(session_root=str(root),session_id='cancel-test')
            doc=c.success('document.create',id='cancel',kind='raster',width=2,height=2)
            c.success('session.create',**s,request_id='create',document=doc)
            path=root/(hashlib.sha256(b'cancel-test').hexdigest()+'.sqlite3')
            with closing(sqlite3.connect(path)) as db:
                db.execute('BEGIN EXCLUSIVE')
                first=c.send('tools/call',dict(name='inkbolt_session_verify',arguments=s))
                cancelled=c.send('tools/call',dict(name='inkbolt_session_apply',arguments=dict(**s,request_id='cancelled',expected_revision=0,action=dict(type='snapshot',name='must-not-exist'))))
                c.send('notifications/cancelled',dict(requestId=cancelled),notification=True)
                self.assertEqual(c.rpc('ping')['result'],{})
                db.rollback()
            c.response(first)
            state=c.success('session.read',**s);self.assertEqual(state['current_revision'],0);self.assertEqual(state['snapshots'],[])
            self.assertNotIn(cancelled,c.saved)
            self.assertEqual(c.tool('session.receipt',**s,request_id='cancelled')['structuredContent']['error']['code'],'REQUEST_NOT_FOUND')
            committed=c.success('session.apply',**s,request_id='valid',expected_revision=0,action=dict(type='snapshot',name='saved'))
            self.assertEqual(committed['current_revision'],1)


if __name__=='__main__':unittest.main()
