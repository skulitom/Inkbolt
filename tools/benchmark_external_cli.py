"""External arm orchestration, isolated from the scripted reference runner."""
import json
import os
import shutil
import subprocess
import traceback

from benchmark_driver import (config,driver_identity,read_json,run_external_task,model_run_complete,MIGRATED_TASKS)
from benchmark_baseline import tool_identity,file_hash
from benchmark_runtime import read_metadata_bytes, strict_json
from benchmark_tasks import TASKS,SUITE,CHECKS,check_class
from benchmark_consumer import tool_identities
from measure_workloads import ROOT,candidate_identity,release_build,save_json,sha
import measurement_host


def retained_engine(args, output, cohort=None):
    filename = 'evaluated-inkbolt.exe' if os.name == 'nt' else 'evaluated-inkbolt'
    if args.engine_from or args.import_engine:
        manifest = (cohort or args.engine_from or args.import_root) / 'inputs.json'
        manifest_bytes = read_metadata_bytes(manifest)
        original = strict_json(manifest_bytes)
        if args.engine_from:
            executable = args.engine_from / filename
            if (original.get('build') or {}).get('retained_file') != filename or executable.is_symlink() or not executable.is_file():
                raise ValueError('Expected the retained native executable alongside the model-run manifest')
        else:
            executable = args.import_engine
        executable = executable.resolve(strict=True)
        if original['arm']!='model' or file_hash(executable)!=original['build']['executable_sha256']:
            raise ValueError('Supplied engine differs from the original model run')
        build=dict(source='retained_engine' if args.engine_from else 'imported_engine',
                   original_commit=original['build'].get('original_commit',original['git_commit']),
                   executable_sha256=original['build']['executable_sha256'])
        if args.engine_from or cohort:
            build['source_inputs_sha256'] = sha(manifest_bytes)
    else:
        executable,build=release_build(output)
    retained=output/filename
    with executable.open('rb') as source, retained.open('xb') as destination:
        shutil.copyfileobj(source,destination)
    retained.chmod(retained.stat().st_mode | 0o100)
    if file_hash(retained)!=build['executable_sha256']:
        raise ValueError('Retained engine differs from the selected binary')
    if args.engine_from or cohort:
        with (output/'engine-inputs.json').open('xb') as source_inputs:
            source_inputs.write(manifest_bytes)
        executable = retained
    return executable,dict(build,retained_file=retained.name)


def cohort_sources(args, output, client, driver, baseline, consumer):
    """Validate the archive selection before opening the first judge workspace."""
    index_path = args.import_cohorts
    index_bytes = read_metadata_bytes(index_path)
    index = strict_json(index_bytes)
    if not isinstance(index, dict) or not index or set(index) - TASKS.keys():
        raise ValueError('Expected a nonempty map of known task IDs to archived run directories')
    selected = args.tasks or [task for task in TASKS if task in index]
    if not set(selected) <= index.keys():
        raise ValueError('A selected task has no archived cohort')
    sources, hashes = {}, {}
    engine = None
    for task in selected:
        if not isinstance(index[task], str) or not index[task].strip():
            raise ValueError(f'{task} needs an archived run directory')
        directory = (index_path.parent / index[task]).resolve(strict=True)
        if output.is_relative_to(directory):
            raise ValueError('Replay output must be outside each source archive')
        raw = read_metadata_bytes(directory / 'inputs.json')
        prior = strict_json(raw)
        expected = dict(schema_version=1, suite=SUITE, arm=args.arm, client=client['client'], model=client['model'],
                        driver_kind=client['kind'], driver=driver, repetitions=args.repetitions, baseline_tools=baseline)
        if task == 'B20':
            expected['consumer_tools'] = consumer
        if (not isinstance(prior, dict) or any(prior.get(k) != v for k, v in expected.items())
                or prior.get('benchmark_variant', 'standard') != args.variant
                or not isinstance(prior.get('selected_tasks'), list) or task not in prior['selected_tasks']):
            raise ValueError(f'{task} archive differs in task, repetition count, arm, variant or tool identities')
        if 'imported_cohorts' in prior:
            raise ValueError(f'{task} requires the underlying task archive, not a nested cohort report')
        if (not isinstance(prior.get('conditions'),str) or not prior['conditions'].strip()
                or not isinstance(prior.get('candidate_files'),dict) or not prior['candidate_files']
                or prior.get('candidate_sha256') != sha(json.dumps(prior['candidate_files'],sort_keys=True,separators=(',',':')).encode())):
            raise ValueError(f'{task} archive lacks its recorded conditions or candidate identity')
        if args.arm == 'model':
            digest = (prior.get('build') or {}).get('executable_sha256')
            if not isinstance(digest, str) or len(digest) != 64 or (engine is not None and digest != engine):
                raise ValueError(f'{task} archive has a missing or different engine identity')
            engine = digest
        sources[task] = directory
        hashes[task] = sha(raw)
    return sources, dict(index_sha256=sha(index_bytes), inputs_sha256=hashes, executable_sha256=engine)


def run_suite(args, output, aggregate):
    variant=getattr(args,'variant','standard')
    configuration=config(args.driver_config)
    driver=driver_identity(configuration)
    baseline_config=read_json(args.baseline_tools) if args.baseline_tools else None
    tools=tool_identity(baseline_config) if baseline_config else None
    consumer_tools={name:getattr(args,name).resolve() for name in ('cutbolt','ffmpeg','ffprobe') if getattr(args,name)}
    consumer_identity=tool_identities(consumer_tools) if consumer_tools else None
    candidates=candidate_identity();environment=measurement_host.identity()
    sources, archive = {}, None
    if args.import_cohorts:
        sources, archive = cohort_sources(args, output, configuration, driver, tools, consumer_identity)
    executable,build=retained_engine(args,output,next(iter(sources.values()),None)) if args.arm=='model' else (None,None)
    if archive and build and build['executable_sha256'] != archive['executable_sha256']:
        raise ValueError('Selected archive engine changed before replay')
    selected=tuple(args.tasks or sources or TASKS)
    identity=dict(schema_version=1,suite=SUITE,arm=args.arm,benchmark_variant=variant,client=configuration['client'],model=configuration['model'],
        driver_kind=configuration['kind'],driver=driver,baseline_tools=tools,consumer_tools=consumer_identity,build=build,environment=environment,
        conditions=args.conditions,candidate_files=candidates,candidate_sha256=sha(json.dumps(candidates,sort_keys=True,separators=(',',':')).encode()),
        selected_tasks=selected,repetitions=args.repetitions,
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
    if archive:
        identity['imported_cohorts'] = archive
        retained_inputs=output/'cohort-inputs'
        retained_inputs.mkdir()
        for task, directory in sources.items():
            raw=read_metadata_bytes(directory/'inputs.json')
            if sha(raw)!=archive['inputs_sha256'][task]:
                raise ValueError(f'{task} source inputs changed before capture')
            with (retained_inputs/(task+'.json')).open('xb') as stream:
                stream.write(raw)
    save_json(output/'inputs.json',identity)
    save_json(output/'tasks.json',dict(suite=SUITE,tasks=[dict(id=task,title=title,outcome=outcome,
        migrated=task in MIGRATED_TASKS,checks=[dict(name=name,check_class=check_class(task,name)) for name in CHECKS[task]])
        for task,(title,outcome) in TASKS.items()]))
    rows=[]
    for repetition in range(1,args.repetitions+1):
        offset=(repetition-1)%len(selected)
        for task in selected[offset:]+selected[:offset]:
            name=f'{repetition:02d}-{task}';base=output/name
            try:
                previous = sources.get(task) or args.import_root
                row=run_external_task(executable,base,task,repetition,args.arm,configuration,tools,
                    previous.resolve()/name if previous else None,args.prepare_only,consumer_tools=consumer_tools,variant=variant)
            except Exception as error:
                base.mkdir(exist_ok=True)
                row=dict(task=task,repetition=repetition,arm=args.arm,status='failed',model_trials=False,
                         error=f'{type(error).__name__}: {error}')
                save_json(base/'failure.json',row)
                (base/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
            rows.append(row)
            print(json.dumps(dict(task=task,repetition=repetition,arm=args.arm,status=row['status'])),flush=True)
    unchanged=(candidates==candidate_identity() and environment==measurement_host.identity() and
               driver==driver_identity(configuration) and (tools is None or tools==tool_identity(baseline_config)) and
               (executable is None or
                file_hash(executable)==build['executable_sha256']==file_hash(output/build['retained_file'])) and
               (not build or 'source_inputs_sha256' not in build or file_hash(output/'engine-inputs.json') == build['source_inputs_sha256']) and
               (not consumer_tools or consumer_identity==tool_identities(consumer_tools)))
    if archive:
        unchanged = (unchanged and sha(read_metadata_bytes(args.import_cohorts)) == archive['index_sha256']
                     and all(sha(read_metadata_bytes(path/'inputs.json')) == archive['inputs_sha256'][task]
                             for task, path in sources.items()))
    success=all(row['status'] in (('prepared','not_applicable') if args.prepare_only else ('passed','not_applicable')) for row in rows)
    report=dict(schema_version=2,suite=SUITE,arm=args.arm,transport='external-client',benchmark_variant=variant,
        selected_tasks=selected,all_tasks=list(TASKS),repetitions=args.repetitions,
        full_selection=set(selected)==set(TASKS),migrated_tasks=list(MIGRATED_TASKS),
        model_trials=any(row.get('model_trials') for row in rows),
        actual_model_benchmark_complete=model_run_complete(rows,selected,args.repetitions,unchanged),
        matched_cutbolt_comparison=False,complete_scripted_suite=False,inputs_unchanged=unchanged,
        rows=rows,aggregates=aggregate(rows),
        outcome='invalid_inputs_changed' if not unchanged else 'not_applicable' if all(row['status']=='not_applicable' for row in rows) else
            'prepared' if args.prepare_only and success else
            'selected_tasks_passed' if success else 'incomplete_or_failed',
        provenance=identity,
        limitations=['Only migrated tasks can be judged by external arms; the fixed twenty-task inventory remains visible.',
            'Client-reported usage is retained as observed data; missing observations remain null.',
            'The process owner applies deadlines and cleans up its process tree, but is not a filesystem/security sandbox.',
            'The configured client must enforce the supplied tool policy and retain a credential-free transcript.',
            'Captured hashes establish identity, not an authenticated attestation of the client or transcript.',
            'Synthetic drivers never count as actual model trials; complete-suite and matched-arm comparison remain separate gates.'])
    save_json(output/'report.json',report)
    print(str(output/'report.json'))
    return 0 if success and unchanged else 2
