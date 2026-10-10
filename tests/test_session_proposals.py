"""Read-only proposals, exact eventual receipts and rejection of changed review inputs."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import base64
import copy
import hashlib
import json
import sqlite3
import unittest
from external_workspace import files as workspace_files

import test_agent_workspace as workspace
from test_mcp import Client
from test_mcp_preview import restore
from test_editing_cli import png_pixels


def box():
    return dict(id='box',content=dict(type='vector',geometry=dict(shape='rect',x=0,y=0,width=1,height=1),fill=[20,80,170,255]))


class SessionProposalTests(unittest.TestCase):
    setUp=workspace.AgentWorkspaceTests.setUp
    cli=workspace.AgentWorkspaceTests.cli
    document=workspace.AgentWorkspaceTests.document
    save=workspace.AgentWorkspaceTests.save
    ref=workspace.AgentWorkspaceTests.ref

    def files(self):
        return {str(p.relative_to(self.root)):(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()) for p in workspace_files(self.root) if p.is_file()}

    def proposal(self,action,revision=0,request_id='propose',**options):
        before=self.files()
        result=self.cli('session.dry_run',session_id='work',request_id=request_id,expected_revision=revision,action=action,options=options)
        self.assertEqual(self.files(),before)
        self.assertTrue(result['dry_run']);self.assertFalse(result['committed'])
        self.assertFalse(result['source_changed'])
        self.assertEqual(result['proposal']['expected_revision'],revision)
        self.cli('session.receipt',session_id='work',request_id=request_id,error='REQUEST_NOT_FOUND')
        return result

    def test_every_action_predicts_exact_receipt_state_history_and_pixels(self):
        self.save()
        actions=[dict(type='edit',label='Original proposal',operations=[dict(op='add',item=box())]),
                 dict(type='snapshot',name='saved'),
                 dict(type='edit',operations=[dict(op='transform',id='box',matrix=[1,0,0,1,1,0],space='world')]),
                 dict(type='undo'),dict(type='redo'),dict(type='restore',name='saved'),
                 dict(type='resources',resources=dict(asset_root=str(self.root/'new-assets'),font_root=None)),
                 dict(type='remove_snapshot',name='saved')]
        for revision,action in enumerate(actions):
            with self.subTest(action=action):
                predicted=self.proposal(action,revision,request_id=f'action-{revision}',include_document=True,preview=True,compare_pixels=True)
                committed=self.cli('session.apply_proposal',proposal=predicted['proposal'],action=action)
                self.assertEqual(committed['receipt'],predicted['predicted_receipt'])
                self.assertEqual(committed['document'],predicted['proposed_document'])
                self.assertEqual(committed['resources'],predicted['proposed_resources'])
                read=self.cli('session.read',session_id='work')
                self.assertEqual(read['undo_depth'],predicted['history']['undo_depth'])
                self.assertEqual(read['redo_depth'],predicted['history']['redo_depth'])
                rendered=self.cli('document.render',document=self.ref(revision+1))
                width,height,pixels,_=png_pixels(base64.b64decode(predicted['preview']['data']))
                self.assertEqual((width,height),(2,2));self.assertEqual(pixels,bytes.fromhex(rendered['data']))
                actual_diff=self.cli('session.diff',session_id='work',from_revision=revision,to_revision=revision+1,compare_pixels=True)
                for key,value in predicted['difference'].items():self.assertEqual(actual_diff[key],value)
        self.assertEqual(self.cli('session.read',session_id='work')['snapshots'],[])
        self.cli('session.verify',session_id='work')

    def test_invalid_changes_stale_head_wrong_base_and_result_reject_without_writes(self):
        self.save();action=dict(type='edit',operations=[dict(op='add',item=box())]);predicted=self.proposal(action)
        before=self.files()
        changed=copy.deepcopy(action);changed['operations'][0]['item']['content']['fill']=[255,0,0,255]
        self.cli('session.apply_proposal',proposal=predicted['proposal'],action=changed,error='PROPOSAL_MISMATCH')
        for field,value,code in [('base_state_sha256','0'*64,'PROPOSAL_MISMATCH'),('result_state_sha256','0'*64,'PROPOSAL_MISMATCH'),
                                 ('request_fingerprint','0'*64,'PROPOSAL_MISMATCH'),('version',2,'INVALID_PROPOSAL'),
                                 ('base_state_sha256','not-a-hash','INVALID_PROPOSAL')]:
            altered=dict(predicted['proposal'],**{field:value})
            self.cli('session.apply_proposal',proposal=altered,action=action,error=code)
            self.assertEqual(self.files(),before)
        self.cli('session.apply_proposal',proposal=predicted['proposal'],action=action,control=dict(timeout_ms=0),error='TIMEOUT')
        self.assertEqual(self.files(),before)
        self.cli('session.create',session_root='different-store',session_id='work',request_id='create',document=dict(self.document(),width=3))
        self.cli('session.apply_proposal',session_root='different-store',proposal=predicted['proposal'],action=action,error='PROPOSAL_MISMATCH')
        self.cli('session.apply',session_id='work',request_id='competing',expected_revision=0,action=dict(type='snapshot',name='competing'))
        before=self.files()
        self.cli('session.apply_proposal',proposal=predicted['proposal'],action=action,error='REVISION_CONFLICT')
        self.cli('session.dry_run',session_id='work',request_id='stale',expected_revision=0,action=action,error='REVISION_CONFLICT')
        self.assertEqual(self.files(),before)

    def test_readonly_dry_run_atomic_invalid_batch_and_expired_work(self):
        self.save();source=self.files();action=dict(type='edit',operations=[dict(op='add',item=box()),dict(op='remove',id='missing')])
        self.cli('session.dry_run',session_id='work',request_id='invalid',expected_revision=0,action=action,error='NOT_FOUND')
        self.cli('session.dry_run',session_id='work',request_id='invalid',expected_revision=0,action=dict(type='undo'),error='HISTORY_BOUNDARY')
        self.cli('session.dry_run',session_id='work',request_id='expired',expected_revision=0,action=dict(type='snapshot',name='saved'),control=dict(timeout_ms=0),error='TIMEOUT')
        self.assertEqual(self.files(),source)
        database=next(self.root.rglob('*.sqlite3'))
        with closing(sqlite3.connect(database)) as db:
            db.execute('BEGIN IMMEDIATE') # reserved writer can coexist with a genuinely read-only proposal
            self.proposal(dict(type='snapshot',name='saved'))
            db.rollback()
        self.assertEqual(self.files(),source)

    def test_mcp_preview_compact_commit_retry_and_concurrent_same_request(self):
        self.save();action=dict(type='edit',operations=[dict(op='add',item=box())])
        with closing(Client(('--tools','core'),workspace=self.root)) as c:
            c.initialize()
            response=c.tool('session.dry_run',session_id='work',request_id='propose',expected_revision=0,action=action,options=dict(preview=True),response_format='preview')
            self.assertFalse(response['isError'],response)
            predicted=restore(response)['result']
            self.assertEqual(predicted,self.proposal(action,preview=True))
            proposal=predicted['proposal']
            def commit(_):return self.cli('session.apply_proposal',proposal=proposal,action=action,response_mode='compact')
            with ThreadPoolExecutor(max_workers=2) as pool: outcomes=list(pool.map(commit,range(2)))
            self.assertEqual(sorted(o['replayed'] for o in outcomes),[False,True])
            self.assertEqual(outcomes[0]['receipt_summary'],outcomes[1]['receipt_summary'])
            self.assertEqual(outcomes[0]['document_ref']['revision'],1)
            c.success('session.apply',session_id='work',request_id='advance',expected_revision=1,action=dict(type='snapshot',name='later'))
            retry=c.success('session.apply_proposal',proposal=proposal,action=action,response_mode='compact',control=dict(timeout_ms=0))
            self.assertTrue(retry['replayed']);self.assertEqual(retry['document_ref']['revision'],1);self.assertEqual(retry['current_revision'],2)
            self.cli('session.dry_run',session_id='work',request_id='propose',expected_revision=0,action=action,error='REQUEST_ALREADY_COMMITTED')
            altered=dict(proposal,result_state_sha256='0'*64)
            self.cli('session.apply_proposal',proposal=altered,action=action,error='PROPOSAL_MISMATCH')
            self.assertEqual(self.cli('session.read',session_id='work')['current_revision'],2)
            self.assertEqual(len(json.dumps(retry).encode())<8192,True)


if __name__=='__main__':unittest.main()
