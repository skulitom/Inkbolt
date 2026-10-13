"""B19 broker for agent-selected commands with harness-owned fault boundaries."""
import json
from pathlib import Path
import re
import threading
import time

from benchmark_runtime import require,safe_name,strict_json
from benchmark_recovery_bridge import MAX_MESSAGE


class RecoveryControl:
    def __init__(self,case,channel):
        self.case=case;self.channel=Path(channel);self.channel.mkdir()
        self.stop=threading.Event();self.thread=None;self.error=None;self.gate=None
        self.seen=set();self.controls=[];self.checkpoints=set();self.bytes=0
        case.outputs=('cancelled.png','recovered.png')

    def checkpoint(self,label):
        if label not in self.checkpoints:
            self.case.output_checkpoint(label);self.checkpoints.add(label)

    def dispatch(self,message):
        require(isinstance(message,dict) and set(message)<={'step','command','arguments','expected_error','retry_of','preview','control'},
                'Unexpected recovery message fields')
        step=safe_name(message['step']);case=self.case
        if 'control' in message:
            require(set(message)<={'step','control','arguments'},'A fault control cannot also issue an arbitrary command')
            control=message['control'];args=message.get('arguments',{})
            require(isinstance(args,dict),'Control arguments must be an object')
            require(control not in self.controls,'Fault control was already used')
            if control=='cancel-active':
                require(set(args)=={'document','output'} and args['output']=={'file_name':'cancelled.png','format':'png'},'Unexpected cancellation destination')
                with case.launch_boundary(step+'-start','job.start','cancel',**args) as state:
                    case.event('cancel-requested',request_id='cancel',runner=state['runner'])
                    value=case.call(step+'-cancel','job.cancel',request_id='cancel')
            elif control=='hold-queue':
                require(not args and self.gate is None and 'cancel-active' in self.controls,'Queue gate follows active cancellation')
                deadline=time.monotonic()+5
                while case.snapshot()['runtime']['owner'] is not None:
                    require(time.monotonic()<deadline,'Cancelled queue did not become idle');time.sleep(.01)
                self.gate=case.blocked_queue();self.gate.__enter__();value={'held':True}
            elif control=='interrupt-queued':
                require(not args and self.gate is not None,'Interruption requires the owned queue gate')
                snapshot=case.snapshot();state=snapshot['jobs'].get('recover',{})
                require(state.get('phase')=='queued' and state.get('attempt')==0,'The recover request was not admitted while the queue was held')
                # Bind admission/edit ordering to actual observed calls, never
                # client declarations or overwritten database rows.
                starts=[r for r in case.calls if r['command']=='job.start' and r['step'] in case.results and
                        case.results[r['step']].get('result',{}).get('request_id')=='recover']
                def request_id(row):
                    value=case.results.get(row['step'],{}).get('result',{})
                    return value.get('receipt_summary',value.get('receipt',{})).get('request_id')
                edits=[r for r in case.calls if r['command']=='session.apply' and request_id(r)=='newer']
                require(len(starts)==len(edits)==1 and starts[0]['completed_task_seconds']<edits[0]['completed_task_seconds'],
                        'Admit the pinned recovery request before committing the newer edit')
                self.gate.__exit__(None,None,None);self.gate=None
                with case.launch_boundary(step,'job.resume','recover') as state:case.interrupt_supervisor(state)
                value={'interrupted':True,'request_id':'recover','attempt':1}
            else:raise ValueError('Unknown recovery control')
            self.controls.append(control)
            return {'ok':True,'result':value}
        command=message['command'];arguments=message.get('arguments',{})
        require(isinstance(command,str) and isinstance(arguments,dict),'Invalid engine command')
        require('judge_workspace' not in arguments,'Clients cannot select a judge workspace')
        expected=message.get('expected_error')
        try:value=case.call(step,command,expected_error=expected,retry_of=message.get('retry_of'),preview=message.get('preview',False),**arguments)
        except Exception:
            envelope=case.results.get(step,{})
            if expected is None and envelope.get('ok') is False:return envelope
            raise
        if command=='job.result' and arguments.get('request_id')=='recover':
            if expected=='JOB_NOT_COMPLETED' and 'interrupt-queued' in self.controls:self.checkpoint('after-inspection')
            elif expected is None:self.checkpoint('before-replays')
        if command=='document.publish' and expected=='OUTPUT_EXISTS' and arguments.get('output',{}).get('file_name')=='recovered.png':
            self.checkpoint('after-replays')
        return {'ok':False,'error':value} if expected else {'ok':True,'result':value}

    def run(self):
        try:
            while not self.stop.is_set():
                for path in sorted(self.channel.glob('*.request')):
                    if path.name in self.seen:continue
                    require(len(self.seen)<256 and re.fullmatch(r'[0-9a-f]{32}\.request',path.name) is not None and
                            path.is_file() and not path.is_symlink() and path.stat().st_size<=MAX_MESSAGE,'Invalid or excessive control requests')
                    raw=path.read_bytes();self.bytes+=len(raw);require(self.bytes<=64*1024*1024,'Recovery request traffic exceeds its bound')
                    self.seen.add(path.name)
                    try:response=self.dispatch(strict_json(raw))
                    except Exception as error:
                        # An invalid command remains a recorded failure. It
                        # cannot silently become successful fault evidence.
                        self.error=f'{type(error).__name__}: {error}'
                        response={'ok':False,'error':{'code':'BENCHMARK_CONTROL_ERROR','message':self.error}}
                    data=json.dumps(response,separators=(',',':')).encode();require(len(data)<=MAX_MESSAGE,'Recovery response exceeds its bound')
                    target=path.with_suffix('.response');temporary=path.with_suffix('.answer')
                    with temporary.open('xb') as stream:stream.write(data)
                    temporary.rename(target)
                self.stop.wait(.01)
        except Exception as error:self.error=f'{type(error).__name__}: {error}'
        finally:
            if self.gate is not None:self.gate.__exit__(None,None,None);self.gate=None

    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=self.case.timeout+10)
        require(self.thread is None or not self.thread.is_alive(),'Recovery controller did not stop')
