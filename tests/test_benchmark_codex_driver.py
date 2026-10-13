"""Original event/argument controls; these never contact a model service."""
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import benchmark_codex_driver as driver


class Process:
    def __init__(self, events, code=0):
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(events)
        self.code = code
        self.killed = False

    def __enter__(self): return self
    def __exit__(self, *_): self.stdout.close()
    def wait(self): return self.code
    def kill(self): self.killed = True


class CodexDriverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root/'workspace'; self.workspace.mkdir()
        self.evidence = self.root/'evidence'; self.evidence.mkdir()
        self.prompt = b'Create the specified original artifact.\n'
        (self.workspace/'task.txt').write_bytes(self.prompt)
        (self.workspace/'source.json').write_bytes(b'{}')
        self.contract = dict(schema_version=1, arm='baseline', task='B02', repetition=1,
            kind='synthetic', client=dict(id='codex-cli',version='test-version'),
            model=dict(id='fixture-model-one', settings=dict(reasoning_effort='medium')),
            prompt_sha256=driver.digest(self.prompt), fixtures={'source.json':driver.digest(b'{}')},
            engine_sha256=None)
        self.request = dict(schema_version=1, contract=self.contract,
            workspace=str(self.workspace), prompt_path=str(self.workspace/'task.txt'),
            result_path=str(self.evidence/'driver-result.json'), transcript_directory=str(self.evidence),
            mcp_config=None, baseline_tools=dict(python=dict(path=sys.executable)),
            tool_policy='Use only the pinned baseline tools.')
        self.bind()

    def bind(self):
        self.request['contract_sha256'] = driver.digest(driver.canonical(self.contract))
        self.request_path = self.evidence/'request.json'
        self.request_path.write_bytes(driver.canonical(self.request))

    def invoke(self, events, code=0, version='codex-cli test-version'):
        process = Process(b''.join(driver.canonical(e)+b'\n' for e in events), code)
        with patch.object(driver.subprocess,'run',return_value=subprocess.CompletedProcess([],0,version.encode())), \
             patch.object(driver.subprocess,'Popen',return_value=process) as launch:
            driver.run(self.request_path, Path(sys.executable))
        return process, launch

    def test_model_is_explicit_and_passed_verbatim_without_shell_interpolation(self):
        for model in ('fixture-model-one','fixture-model-two','fixture $(not-a-shell)'):
            self.contract['model']['id'] = model; self.bind()
            argv, prompt, cwd = driver.prepare(self.request, Path(sys.executable))
            self.assertEqual(argv[argv.index('--model')+1], model)
            self.assertIn('model_reasoning_effort="medium"', argv)
            self.assertEqual(cwd, self.workspace)
            self.assertIn(self.prompt.decode(), prompt)
            self.assertNotIn(str(self.request_path), prompt)
        for value in ('', '  ', '-unexpected'):
            self.contract['model']['id'] = value; self.bind()
            with self.assertRaises(ValueError): driver.prepare(self.request, Path(sys.executable))

    def test_unknown_settings_cannot_be_silently_ignored(self):
        for settings in ({}, {'reasoning_effort':''}, {'reasoning_effort':'medium','temperature':1}):
            self.contract['model']['settings'] = settings; self.bind()
            with self.assertRaises(ValueError): driver.prepare(self.request, Path(sys.executable))

    def test_controlled_environment_and_no_engine_in_baseline(self):
        argv, prompt, _ = driver.prepare(self.request, Path(sys.executable))
        for flag in ('--ignore-user-config','--ephemeral','workspace-write','skip_host_skill_discovery'):
            self.assertIn(flag, argv)
        for setting in ('web_search="disabled"','project_doc_max_bytes=0','approval_policy="never"'):
            self.assertIn(setting, argv)
        self.assertFalse(any('mcp_servers.' in arg for arg in argv))
        self.assertNotIn('engine_executable', prompt)
        approved, _, _ = driver.prepare(self.request, Path(sys.executable), 'approve')
        self.assertEqual(approved, argv)  # Identical paired configuration grants no baseline engine.
        if sys.platform == 'win32': self.assertIn('windows.sandbox="elevated"',argv)
        for field in ('mcp_config', 'engine_executable'):
            bad = dict(self.request, **{field:'unexpected'})
            with self.assertRaises(ValueError): driver.prepare(bad, Path(sys.executable))

    def test_model_arm_pins_only_the_supplied_core_mcp_server(self):
        engine = Path(sys.executable).resolve()
        self.contract.update(arm='model', engine_sha256=driver.digest(engine.read_bytes()))
        self.request.update(baseline_tools=None, engine_executable=str(engine),
            mcp_config=str(self.evidence/'mcp-config.json'))
        mcp = dict(mcpServers=dict(inkbolt=dict(command=str(engine),
            args=['--workspace',str(self.workspace),'mcp','--tools','core'])))
        Path(self.request['mcp_config']).write_bytes(driver.canonical(mcp)); self.bind()
        argv, _, _ = driver.prepare(self.request, engine)
        self.assertIn('mcp_servers.inkbolt.required=true',argv)
        self.assertIn('mcp_servers.inkbolt.command='+json.dumps(str(engine)),argv)
        self.assertFalse(any('default_tools_approval_mode' in arg for arg in argv))
        approved, prompt, _ = driver.prepare(self.request, engine, 'approve')
        self.assertIn('mcp_servers.inkbolt.default_tools_approval_mode="approve"', approved)
        self.assertIn('approval_policy="never"', approved)
        self.assertIn('workspace-write', approved)
        self.assertEqual(prompt, driver.prepare(self.request, engine)[1])
        self.assertEqual(set(approved)-set(argv), {'mcp_servers.inkbolt.default_tools_approval_mode="approve"'})
        self.contract['engine_sha256'] = '0'*64; self.bind()
        with self.assertRaisesRegex(ValueError,'Engine executable identity'):
            driver.prepare(self.request, engine, 'approve')
        self.contract['engine_sha256'] = driver.digest(engine.read_bytes()); self.bind()
        mcp['mcpServers']['unexpected'] = {}; Path(self.request['mcp_config']).write_bytes(driver.canonical(mcp))
        with self.assertRaisesRegex(ValueError,'Unexpected MCP'): driver.prepare(self.request, engine, 'approve')

    def test_mcp_policy_is_explicit_on_the_command_line_and_unknown_modes_fail(self):
        with patch.object(driver, 'run') as run:
            self.assertEqual(driver.main(['--client-executable', sys.executable,
                '--mcp-approval-mode', 'approve', str(self.request_path)]), 0)
            run.assert_called_once_with(self.request_path, Path(sys.executable), 'approve')
        with self.assertRaisesRegex(ValueError,'Unknown MCP approval mode'):
            driver.prepare(self.request, Path(sys.executable), 'unexpected')

    def test_changed_prompt_fixture_and_contract_fail_before_client_execution(self):
        original = copy.deepcopy(self.request)
        self.request['contract_sha256'] = '0'*64
        with self.assertRaises(ValueError): driver.prepare(self.request, Path(sys.executable))
        self.request = original
        (self.workspace/'task.txt').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Prompt hash'): driver.prepare(self.request, Path(sys.executable))
        (self.workspace/'task.txt').write_bytes(self.prompt)
        (self.workspace/'source.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Fixture identity'): driver.prepare(self.request, Path(sys.executable))

    def test_real_event_usage_is_preserved_without_inventing_calls(self):
        events = [dict(type='thread.started',thread_id='synthetic'),dict(type='turn.started'),
            dict(type='item.completed',item=dict(type='agent_message',text='A synthetic result.')),
            dict(type='turn.completed',usage=dict(input_tokens=120,output_tokens=30,
                cached_input_tokens=90,reasoning_output_tokens=10))]
        _, launch = self.invoke(events)
        result = json.loads((self.evidence/'driver-result.json').read_bytes())
        self.assertEqual(result['kind'],'synthetic')
        self.assertEqual(result['model'],self.contract['model'])
        self.assertEqual(result['observations']['token_usage'],dict(input_tokens=120,output_tokens=30,
            cached_input_tokens=90,reasoning_tokens=10))
        self.assertIsNone(result['observations']['model_calls'])
        transcript = [json.loads(line) for line in (self.evidence/result['transcript']).read_bytes().splitlines()]
        self.assertEqual(transcript[1:],events)
        self.assertEqual(transcript[0]['contract_sha256'],self.request['contract_sha256'])
        self.assertNotIn('shell',launch.call_args.kwargs)
        self.assertEqual(launch.call_args.kwargs['cwd'],self.workspace)

    def test_missing_usage_stays_unknown(self):
        self.assertIsNone(driver.observed_usage([dict(type='turn.started'),dict(type='turn.completed')]))

    def test_failed_incomplete_duplicate_and_malformed_usage_cannot_pass(self):
        start = dict(type='turn.started'); done = dict(type='turn.completed',usage=dict(input_tokens=2))
        for events in ([start], [done], [start,done,done], [start,done,dict(type='error')],
                       [start,dict(type='turn.failed')],
                       [start,dict(type='turn.completed',usage=dict(input_tokens=True))],
                       [start,dict(type='turn.completed',usage=dict(output_tokens=-1))]):
            with self.subTest(events=events),self.assertRaises(ValueError): driver.observed_usage(events)

    def test_process_failure_keeps_raw_evidence_but_writes_no_success_result(self):
        with self.assertRaisesRegex(ValueError,'Client process failed'):
            self.invoke([dict(type='turn.started'),dict(type='turn.failed',error=dict(message='synthetic failure'))],code=2)
        self.assertFalse((self.evidence/'driver-result.json').exists())
        self.assertIn(b'synthetic failure',(self.evidence/'codex-events.jsonl').read_bytes())

    def test_version_mismatch_and_existing_result_refuse_before_launch(self):
        for version in ('codex-cli another-version','codex-cli test-version'):
            if version.endswith('test-version'): (self.evidence/'driver-result.json').write_bytes(b'original')
            with patch.object(driver.subprocess,'Popen') as launch, \
                 patch.object(driver.subprocess,'run',return_value=subprocess.CompletedProcess([],0,version.encode())):
                with self.assertRaises(ValueError): driver.run(self.request_path,Path(sys.executable))
            launch.assert_not_called()

    def test_transcript_bound_kills_client_and_never_writes_a_result(self):
        with patch.object(driver,'MAX_EVENT',8),self.assertRaisesRegex(ValueError,'exceeds its bound'):
            self.invoke([dict(type='turn.started')])
        self.assertFalse((self.evidence/'driver-result.json').exists())

    def test_bridge_metadata_is_available_without_direct_engine_configuration(self):
        self.contract.update(arm='model',engine_sha256='0'*64)
        self.request.update(baseline_tools=None,recovery_bridge=['python','original-bridge','channel'])
        self.bind()
        argv, prompt, _ = driver.prepare(self.request,Path(sys.executable))
        self.assertIn('original-bridge',prompt)
        self.assertFalse(any('mcp_servers.' in arg for arg in argv))


if __name__ == '__main__': unittest.main()
