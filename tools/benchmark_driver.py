"""External-client and transcript-import lifecycle; client data never supplies a verdict."""
import json
import math
from pathlib import Path
import shutil
import traceback

from benchmark_runtime import Trial, require, safe_name, strict_json
from benchmark_tasks import TASKS, CHECKS, BASELINE_NOT_APPLICABLE
import benchmark_diagram
import benchmark_icons
import benchmark_large_layout
import benchmark_svg
import benchmark_palette
import benchmark_flow
import benchmark_typography
import benchmark_mask
import benchmark_retouch
import benchmark_photo
import benchmark_mixed
import benchmark_variants
import benchmark_screen
import benchmark_print
import benchmark_resources
import benchmark_repair
import benchmark_retry
import benchmark_conflict
import benchmark_recovery_external
from benchmark_baseline import judge_diagram, file_hash
from benchmark_baseline_icons import judge_icons
from benchmark_baseline_large_layout import judge_large_layout
from benchmark_baseline_svg import judge_svg_artwork
from benchmark_baseline_palette import judge_palette
from benchmark_baseline_flow import judge_flow
from benchmark_baseline_typography import judge_typography
from benchmark_baseline_mask import judge_mask
from benchmark_baseline_retouch import judge_retouch
from benchmark_baseline_photo import judge_photo
from benchmark_baseline_mixed import judge_mixed
from benchmark_baseline_variants import judge_variants
from benchmark_baseline_screen import judge_screen
from benchmark_baseline_print import judge_print
from benchmark_baseline_resources import judge_resources
from benchmark_baseline_repair import judge_repair
from workload_cases import save, save_json, sha
from verify_process import run as run_owned, unavailable_memory, MEMORY_SCOPE, MEMORY_METHOD
import measurement_host

MIGRATIONS = {'B01':(benchmark_diagram, judge_diagram), 'B02':(benchmark_icons, judge_icons),
              'B03':(benchmark_large_layout, judge_large_layout), 'B04':(benchmark_svg, judge_svg_artwork),
              'B05':(benchmark_palette, judge_palette), 'B06':(benchmark_flow, judge_flow),
              'B07':(benchmark_typography, judge_typography), 'B08':(benchmark_mask, judge_mask),
              'B09':(benchmark_retouch, judge_retouch), 'B10':(benchmark_photo, judge_photo),
              'B11':(benchmark_mixed, judge_mixed), 'B12':(benchmark_variants, judge_variants),
              'B13':(benchmark_screen, judge_screen), 'B14':(benchmark_print, judge_print),
              'B15':(benchmark_resources, judge_resources), 'B16':(benchmark_repair, judge_repair),
              'B17':(benchmark_retry, None), 'B18':(benchmark_conflict, None), 'B19':(benchmark_recovery_external,None)}
MIGRATED_TASKS = tuple(MIGRATIONS)
MAX_METADATA = 1024*1024
MAX_TRANSCRIPT = 64*1024*1024


def read_json(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_METADATA,
            'Missing, linked or oversized driver metadata')
    return strict_json(path.read_bytes())


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def config(path):
    value = read_json(Path(path))
    require(set(value) == {'schema_version','kind','client','model','argv','driver_files','timeout_seconds'},
            'Unexpected or missing driver configuration fields')
    require(value['schema_version'] == 1 and value['kind'] in ('model','synthetic'), 'Invalid driver kind/version')
    require(set(value['client']) == {'id','version'} and all(isinstance(v,str) and v for v in value['client'].values()),
            'Declare the client id and version')
    require(set(value['model']) == {'id','settings'} and isinstance(value['model']['id'],str) and value['model']['id']
            and isinstance(value['model']['settings'],dict), 'Declare the model id and exact settings')
    require(isinstance(value['argv'],list) and all(isinstance(v,str) and v for v in value['argv']), 'Driver argv must be a string array')
    require(isinstance(value['driver_files'],list), 'Driver files must be an array of paths')
    seconds=value['timeout_seconds']
    require(type(seconds) in (int,float) and math.isfinite(seconds) and 0 < seconds <= 3600, 'Invalid driver deadline')
    return value


def driver_identity(configuration):
    paths=list(configuration['driver_files'])
    if configuration['argv']: paths.append(configuration['argv'][0])
    result={}
    for name in paths:
        path=Path(name)
        require(path.is_absolute() and path.is_file(), 'Driver files must be existing absolute regular files')
        result[str(path)]=dict(resolved_path=str(path.resolve()),sha256=file_hash(path))
    # Arguments remain in the owner's config; reports retain their identity.
    # Credentials belong only in the inherited environment, never in config.
    return dict(config_sha256=sha(canonical(configuration)),files=result)


def workspace_files(root):
    result={};total=0
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink() and path.resolve().is_relative_to(root.resolve()), 'Linked workspace entry')
        if path.is_dir(): continue
        require(path.is_file(), 'Nonregular workspace entry')
        total+=path.stat().st_size
        require(len(result)<65536 and total <= 8*1024**3, 'Benchmark workspace capture exceeds its bound')
        result[path.relative_to(root).as_posix()]=file_hash(path)
    return result


def transcript(evidence, name):
    safe_name(name)
    require(name not in ('driver-result.json','capture.json','request.json','mcp-config.json','execution.json'),
            'Transcript name collides with metadata')
    path=evidence/name
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= MAX_TRANSCRIPT,
            'Missing, linked, empty or oversized transcript')
    return path


def observations(result):
    value=result.get('observations')
    if value is None: return dict(token_usage=None,model_calls=None,agent_seconds=None)
    require(isinstance(value,dict) and value.get('source') == 'client_reported', 'Observations must be reported by the client')
    allowed={'source','token_usage','model_calls','agent_seconds','engine_commands','request_bytes','response_bytes',
             'invalid_calls','retries','first_preview_seconds','first_preview_sha256'}
    require(set(value)<=allowed, 'Unknown observation field')
    answer={key:None for key in ('token_usage','model_calls','agent_seconds','engine_commands','request_bytes','response_bytes','invalid_calls','retries')}
    for key in answer.keys()-{'token_usage'}:
        number=value.get(key)
        if number is not None:
            require(type(number) in ((int,float) if key=='agent_seconds' else (int,)) and math.isfinite(number)
                    and number>=0, 'Invalid observed '+key)
        answer[key]=number
    usage=value.get('token_usage')
    if usage is not None:
        require(isinstance(usage,dict) and bool(usage) and set(usage)<={'input_tokens','output_tokens','cached_input_tokens','reasoning_tokens'},
                'Unexpected token usage fields')
        require(all(type(v) is int and v>=0 for v in usage.values()), 'Invalid token usage')
        answer['token_usage']=usage
    if value.get('first_preview_seconds') is not None:
        seconds=value['first_preview_seconds']
        require(type(seconds) in (int,float) and math.isfinite(seconds) and seconds>=0 and
                (answer['agent_seconds'] is None or seconds<=answer['agent_seconds']), 'Invalid preview timestamp')
        require(isinstance(value.get('first_preview_sha256'),str) and len(value['first_preview_sha256'])==64,
                'Preview timing needs an artifact identity')
        answer.update(first_preview_seconds=seconds,first_preview_sha256=value['first_preview_sha256'])
    return answer


def execution_memory(execution):
    """Validate harness capture data, never client-reported observations.

    Older captures have no memory field. Import preserves their unknown value;
    the judge's own process cannot retroactively measure the original solve.
    """
    require(isinstance(execution,dict), 'Invalid captured execution')
    if 'memory' not in execution:
        return unavailable_memory('Capture has no owned-process memory observation')
    memory=execution['memory']
    require(isinstance(memory,dict) and set(memory)=={'available','scope','method',
            'peak_process_commit_bytes','peak_job_commit_bytes','reason'}, 'Invalid captured memory fields')
    require(type(memory['available']) is bool and memory['scope']==MEMORY_SCOPE and
            memory['method'] in (None,MEMORY_METHOD), 'Invalid captured memory scope or method')
    peaks=[memory['peak_process_commit_bytes'],memory['peak_job_commit_bytes']]
    if memory['available']:
        require(memory['method']==MEMORY_METHOD and memory['reason'] is None and
                all(type(v) is int and 0<v<2**64 for v in peaks), 'Invalid captured memory peaks')
    else:
        require(all(v is None for v in peaks) and isinstance(memory['reason'],str) and
                0<len(memory['reason'])<=512, 'Unavailable memory must have no numeric observations')
    return memory


class ExternalTrial(Trial):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.driver_evidence=None
        self.driver_failure=None
        self.driver_execution={}
        self.setup=None

    def prefix(self, step):
        # Keep judge traffic outside the captured solver workspace, so importing
        # a completed trial does not mistake judge-generated logs for inputs.
        return self.judge_root/super().prefix(step).name

    def has_solve_evidence(self):
        return self.driver_evidence is not None and self.driver_failure is None

    def extra_results(self):
        evidence=self.driver_evidence or {}
        observed=evidence.get('observations',{})
        preview=None
        for check,filename in MIGRATIONS[self.task][0].PREVIEW_FILES.items():
            if any(c['name']==check and c['status']=='pass' for c in self.checks):
                path=self.root/filename
                if path.is_file() and observed.get('first_preview_sha256')==file_hash(path):
                    preview=observed.get('first_preview_seconds')
        return dict(driver=evidence,driver_failure=self.driver_failure,model_trials=evidence.get('kind')=='model',
            harness_setup=evidence.get('harness_setup',self.setup),
            token_usage=observed.get('token_usage'),model_calls=observed.get('model_calls'),
            agent_seconds=observed.get('agent_seconds'),scripted_wall_seconds=None,
            first_verified_preview_seconds=preview,
            engine_commands=observed.get('engine_commands'),request_bytes=observed.get('request_bytes'),
            response_bytes=observed.get('response_bytes'),invalid_calls=observed.get('invalid_calls'),
            retries=observed.get('retries'),engine_roundtrip_seconds=None,
            process_calls=None,protocol_requests=None,
            external_process_tree_memory=execution_memory(evidence.get('execution',self.driver_execution)),
            memory_complete=False,memory_scope='Engine-only memory was not separately observed',
            peak_commit_bytes=None,peak_working_set_bytes=None)


def contract(case, configuration, tools):
    value=dict(schema_version=1,task=case.task,repetition=case.repetition,arm=case.arm,
        prompt_sha256=case.prompt_sha256,fixtures=case.sources,client=configuration['client'],
        model=configuration['model'],kind=configuration['kind'],
        engine_sha256=file_hash(case.executable) if case.executable else None,
        baseline_tools=None if tools is None else {k:{a:b for a,b in v.items() if a!='path'} for k,v in tools.items()})
    adapter=MIGRATIONS[case.task][0]
    if hasattr(adapter,'control_identity'):value['control_files']=adapter.control_identity()
    return value


def setup_files(evidence,task):
    names=getattr(MIGRATIONS[task][0],'SETUP_FILES',())
    files={}
    for name in names:
        safe_name(name);path=evidence/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size<=MAX_METADATA,'Missing, linked or oversized harness setup evidence')
        files[name]=file_hash(path)
    return files


def validate_setup(evidence,task,value):
    files=setup_files(evidence,task)
    if not files:
        require(value is None,'Unexpected harness setup evidence');return None
    require(isinstance(value,dict) and set(value)=={'files','engine_commands','request_bytes','response_bytes','engine_roundtrip_seconds'} and
        value['files']==files,'Harness setup evidence identity mismatch')
    for key in ('engine_commands','request_bytes','response_bytes'):
        require(type(value[key]) is int and value[key]>0,'Invalid harness setup '+key)
    require(type(value['engine_roundtrip_seconds']) in (int,float) and math.isfinite(value['engine_roundtrip_seconds']) and
        value['engine_roundtrip_seconds']>=0,'Invalid harness setup duration')
    require(value['engine_commands']==MIGRATIONS[task][0].SETUP_COMMANDS,'Unexpected harness setup command count')
    return value


def validate_result(evidence, request_contract, capture, files):
    result=read_json(evidence/'driver-result.json')
    require(set(result)=={'schema_version','contract_sha256','kind','client','model','transcript','observations'},
            'Unexpected or missing driver result fields')
    require(result['schema_version']==1 and result['contract_sha256']==sha(canonical(request_contract)), 'Driver input identity mismatch')
    for key in ('kind','client','model'):
        require(result[key]==request_contract[key], 'Driver changed '+key)
    raw=transcript(evidence,result['transcript'])
    observed=observations(result)
    require(capture['workspace_files']==files and capture['contract']==request_contract and
            capture['result_sha256']==file_hash(evidence/'driver-result.json') and
            capture['transcript_sha256']==file_hash(raw), 'Captured evidence identity mismatch')
    execution_memory(capture['execution'])
    setup=validate_setup(evidence,request_contract['task'],capture.get('harness_setup'))
    validated=dict(kind=result['kind'],client=result['client'],model=result['model'],observations=observed,
        transcript_sha256=capture['transcript_sha256'],result_sha256=capture['result_sha256'],
        workspace_sha256=sha(canonical(files)),contract_sha256=sha(canonical(request_contract)),
        original_host=capture['host'],execution=capture['execution'],harness_setup=setup)
    adapter=MIGRATIONS[request_contract['task']][0]
    if hasattr(adapter,'validate_capture'):validated['harness_recovery']=adapter.validate_capture(evidence,capture.get('harness_recovery'))
    return validated


def import_capture(source, case, evidence, expected):
    require(source.is_dir() and not source.is_symlink(), 'Missing imported trial')
    require(all((source/name).is_dir() and not (source/name).is_symlink() for name in ('workspace','evidence')),
            'Imported evidence/workspace must be regular directories')
    capture=read_json(source/'evidence/capture.json')
    files=workspace_files(source/'workspace')
    validated=validate_result(source/'evidence',expected,capture,files)
    for name,digest in files.items():
        target=case.root/name
        if target.exists():
            require(target.is_file() and file_hash(target)==digest, 'Imported fixture/prompt differs')
        else:
            target.parent.mkdir(parents=True,exist_ok=True)
            with (source/'workspace'/name).open('rb') as before, target.open('xb') as after:
                shutil.copyfileobj(before,after)
    require(workspace_files(case.root)==files and workspace_files(source/'workspace')==files, 'Import changed during copying')
    result=read_json(source/'evidence/driver-result.json')
    for name in ('driver-result.json','capture.json',result['transcript']):
        save(evidence/name,(source/'evidence'/name).read_bytes())
    for name in (validated['harness_setup'] or {}).get('files',{}):
        save(evidence/name,(source/'evidence'/name).read_bytes())
    validate_setup(evidence,expected['task'],validated['harness_setup'])
    if validated.get('harness_recovery'):
        for name in validated['harness_recovery']['files']:save(evidence/name,(source/'evidence'/name).read_bytes())
        MIGRATIONS[expected['task']][0].validate_capture(evidence,validated['harness_recovery'])
    validated['imported']=True
    return validated


def run_external_task(executable, base, task, repetition, arm, configuration, tools=None, import_source=None, prepare=False):
    base.mkdir();evidence=base/'evidence';evidence.mkdir()
    if arm=='baseline' and task in BASELINE_NOT_APPLICABLE:
        row=dict(task=task,repetition=repetition,arm=arm,status='not_applicable',reason=BASELINE_NOT_APPLICABLE[task],model_trials=False)
        save_json(base/'result.json',row);return row
    if task not in MIGRATED_TASKS:
        row=dict(task=task,repetition=repetition,arm=arm,status='not_implemented',
            reason='The separated fixture, prompt and artifact judge are not migrated yet.',model_trials=False)
        save_json(base/'result.json',row);return row
    require(arm in ('model','baseline'), 'Invalid external arm')
    adapter,baseline_judge=MIGRATIONS[task]
    factory=getattr(adapter,'external_trial',ExternalTrial)
    case=factory(executable if arm=='model' else None,base/'workspace',task,repetition,'cli',CHECKS[task],arm=arm)
    case.judge_root=evidence
    case.result_path=base/'result.json'
    adapter.fixture(case);case.begin(adapter.PROMPT.read_text(encoding='utf-8'))
    expected=contract(case,configuration,tools)
    pinned=driver_identity(configuration)
    request=dict(schema_version=1,contract=expected,contract_sha256=sha(canonical(expected)),
        workspace=str(case.root.resolve()),prompt_path=str((case.root/'task.txt').resolve()),
        result_path=str((evidence/'driver-result.json').resolve()),transcript_directory=str(evidence.resolve()),
        baseline_tools=tools,mcp_config=None,
        tool_policy='Use only file writing, shell and the pinned baseline tools; Inkbolt is unavailable.' if arm=='baseline' else
            'Use the supplied Inkbolt executable or its MCP configuration; preserve all original inputs.')
    if arm=='model':
        save_json(evidence/'mcp-config.json',dict(mcpServers=dict(inkbolt=dict(command=str(case.executable.resolve()),
            args=['--workspace',str(case.root.resolve()),'mcp','--tools','core']))))
        request['mcp_config']=str((evidence/'mcp-config.json').resolve())
        request['engine_executable']=str(case.executable.resolve())
    if hasattr(adapter,'configure_request'):adapter.configure_request(case,request)
    save_json(evidence/'request.json',request)
    if not import_source and hasattr(adapter,'prepare_external'):
        adapter.prepare_external(case)
        rows=[row for row in case.calls if row['phase']=='setup']
        case.setup=dict(files=setup_files(evidence,task),engine_commands=len(rows),
            request_bytes=sum(row['request_bytes'] for row in rows),response_bytes=sum(row['response_bytes'] for row in rows),
            engine_roundtrip_seconds=sum(row['seconds'] for row in rows))
        validate_setup(evidence,task,case.setup)
    if prepare:
        row=dict(task=task,repetition=repetition,arm=arm,status='prepared',model_trials=False,
                 contract=expected,request=str(evidence/'request.json'),harness_setup=case.setup)
        save_json(base/'result.json',row);return row
    try:
        if import_source:
            case.driver_evidence=import_capture(import_source,case,evidence,expected)
        else:
            require(configuration['argv'], 'The external driver command is empty')
            if hasattr(adapter,'execute_client'):execution=adapter.execute_client(case,configuration,(evidence/'request.json').resolve())
            else:execution=run_owned(configuration['argv']+[str((evidence/'request.json').resolve())],case.root,
                                    configuration['timeout_seconds'],observe_memory=True)
            # Do not retain arbitrary console output: client credentials must
            # stay out of logs. The declared transcript is the evidence surface.
            execution.pop('output',None)
            case.driver_execution=execution
            save_json(evidence/'execution.json',execution)
            require(execution['status']=='passed', 'External client failed or exceeded its deadline')
            require(driver_identity(configuration)==pinned, 'Driver executable/configuration changed')
            result=read_json(evidence/'driver-result.json')
            raw=transcript(evidence,result['transcript'])
            files=workspace_files(case.root)
            capture=dict(schema_version=1,contract=expected,workspace_files=files,
                result_sha256=file_hash(evidence/'driver-result.json'),transcript_sha256=file_hash(raw),
                host=measurement_host.identity(),execution=execution,driver_identity=pinned)
            if case.setup is not None:capture['harness_setup']=case.setup
            if hasattr(case,'harness_recovery'):capture['harness_recovery']=case.harness_recovery
            save_json(evidence/'capture.json',capture)
            case.driver_evidence=validate_result(evidence,expected,capture,files)
    except Exception as error:
        case.driver_failure=f'{type(error).__name__}: {error}'
        case.error=case.driver_failure
    case.begin_judging()
    try:
        if arm=='baseline': baseline_judge(case,tools)
        else: adapter.judge(case)
    except Exception as error:
        case.error=case.error or f'{type(error).__name__}: {error}'
        (evidence/'judge-failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
    row=case.finish()
    return row


def model_run_complete(rows, selected, repetitions, inputs_unchanged):
    expected={(task,rep) for task in TASKS for rep in range(1,repetitions+1)}
    return (inputs_unchanged and set(selected)==set(TASKS) and repetitions>=5 and len(rows)==len(expected)
        and {(row['task'],row['repetition']) for row in rows}==expected and all(
            row.get('arm')=='model' and row.get('model_trials') is True and row.get('driver',{}).get('kind')=='model'
            and not row.get('driver_failure')
            and row.get('status') in ('passed','failed') and bool(row.get('driver',{}).get('transcript_sha256')) for row in rows))
