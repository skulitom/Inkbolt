"""Local synchronous command broker for the two B20 engines."""
import json
from pathlib import Path
import re
import threading

from benchmark_runtime import require,safe_name,strict_json
from benchmark_recovery_bridge import MAX_MESSAGE
from workload_cases import sha


class HandoffControl:
    def __init__(self,case,channel):
        self.case=case;self.channel=Path(channel);self.channel.mkdir()
        self.stop=threading.Event();self.thread=None;self.error=None;self.seen=set();self.bytes=0

    def dispatch(self,message):
        require(isinstance(message,dict) and set(message)<={'step','engine','command','arguments','expected_error','retry_of','preview'},
            'Unexpected handoff message fields')
        step=safe_name(message['step']);engine=message['engine'];command=message['command'];arguments=message.get('arguments',{})
        require(isinstance(command,str) and isinstance(arguments,dict),'Invalid handoff command')
        require('judge_workspace' not in arguments,'Clients cannot select a judge workspace')
        case=self.case;expected=message.get('expected_error');retry=message.get('retry_of')
        if engine=='inkbolt':
            require(case.arm=='model','Inkbolt is unavailable to the baseline arm')
            try:value=case.call(step,command,expected_error=expected,retry_of=retry,preview=message.get('preview',False),**arguments)
            except Exception:
                envelope=case.results.get(step,{})
                if expected is None and envelope.get('ok') is False:return envelope
                raise
        elif engine=='consumer':
            # Keep all consumer reads/writes within this newly owned workspace.
            root=case.root.resolve()
            for name in ('input_root','output_root','store_root','output'):
                if name in arguments:
                    value=Path(arguments[name])
                    if not value.is_absolute():value=root/value
                    require(value.resolve().is_relative_to(root),'Consumer path escapes the trial workspace')
                    arguments[name]=str(value.resolve())
            if 'store_root' in arguments:require(Path(arguments['store_root'])==root/'cutbolt-store','Unexpected consumer store')
            if 'output' in arguments:
                allowed=[root/name for name in ('original.mkv','revised.mkv','undone.mkv','delivery-0/compiled.mkv','delivery-1/compiled.mkv')]
                require(Path(arguments['output']) in allowed,'Unexpected consumer output')
            try:value=case.consumer.call(step,command,expected_error=expected,retry_of=retry,**arguments)
            except Exception:
                envelope=case.consumer.records.get(step,{}).get('response',{})
                if expected is None and envelope.get('ok') is False:return envelope
                raise
            if command=='scene.render' and expected is None:
                movie=Path(arguments['output']);folder=movie.parent
                require(folder in (root/'delivery-0',root/'delivery-1'),'Unexpected compiled delivery folder')
                entries=list(folder.iterdir());require(1<=len(entries)<=16,'Unexpected delivery inventory')
                identities={}
                for path in entries:
                    safe_name(path.name)
                    require(path.is_file() and not path.is_symlink() and path.stat().st_size<=16*1024*1024,'Invalid or oversized delivery file')
                    identities[str(path)]=sha(path.read_bytes())
                case.observe_delivery(identities)
        else:raise ValueError('Unknown handoff engine')
        return {'ok':False,'error':value} if expected else {'ok':True,'result':value}

    def run(self):
        try:
            while not self.stop.is_set():
                for path in sorted(self.channel.glob('*.request')):
                    if path.name in self.seen:continue
                    require(len(self.seen)<256 and re.fullmatch(r'[0-9a-f]{32}\.request',path.name) is not None and
                        path.is_file() and not path.is_symlink() and path.stat().st_size<=MAX_MESSAGE,'Invalid or excessive handoff requests')
                    raw=path.read_bytes();self.bytes+=len(raw);require(self.bytes<=64*1024*1024,'Handoff traffic exceeds its bound')
                    self.seen.add(path.name)
                    try:response=self.dispatch(strict_json(raw))
                    except Exception as error:
                        self.error=f'{type(error).__name__}: {error}'
                        response={'ok':False,'error':{'code':'BENCHMARK_CONTROL_ERROR','message':self.error}}
                    data=json.dumps(response,separators=(',',':')).encode();require(len(data)<=MAX_MESSAGE,'Handoff response exceeds its bound')
                    target=path.with_suffix('.response');temporary=path.with_suffix('.answer')
                    with temporary.open('xb') as stream:stream.write(data)
                    temporary.rename(target)
                self.stop.wait(.01)
        except Exception as error:self.error=f'{type(error).__name__}: {error}'

    def start(self):self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=self.case.timeout+10)
        require(self.thread is None or not self.thread.is_alive(),'Handoff controller did not stop')
