"""Original synthetic B19 client using only the supplied local command bridge."""
import base64
from pathlib import Path

from benchmark_recovery import authored
from benchmark_graphics import ORANGE
from workload_cases import save,save_json


def solve(root,send):
    root=Path(root)
    def call(step,command,expected_error=None,retry_of=None,**arguments):
        response=send(dict(step=step,command=command,arguments=arguments,expected_error=expected_error,retry_of=retry_of))
        if expected_error:
            assert response['ok'] is False and response['error']['code']==expected_error,response
            return response['error']
        assert response['ok'] is True,response
        return response['result']
    def control(step,name,**arguments):
        response=send(dict(step=step,control=name,arguments=arguments));assert response['ok'],response
    def terminal(request_id,state):
        for i in range(30):
            value=call(request_id+'-wait-'+str(i),'job.wait',request_id=request_id,wait_ms=1000)
            if value['state'] not in ('queued','running'):
                assert value['state']==state,value;return value
        raise RuntimeError('Recovery did not finish')
    asset=call('image','asset.import',source_path='original.png')['asset']
    saved=call('save','session.create',session_id='work',request_id='create',document=authored(asset),response_mode='compact')['document_ref']
    preview=call('preview','document.preview',document=saved,options=dict(focus=dict(type='region',bounds=[32,40,56,60])))
    save(root/'preview.png',base64.b64decode(preview['artifact']['data'],validate=True))
    control('cancel','cancel-active',document=saved,output=dict(file_name='cancelled.png',format='png'))
    attempts={};attempts['cancelled']=terminal('cancel','cancelled')
    attempts['cancel-resume']=call('cancel-resume','job.resume',request_id='cancel')
    attempts['cancel-error']=call('cancel-result','job.result',request_id='cancel',expected_error='JOB_NOT_COMPLETED')
    control('gate','hold-queue')
    args=dict(document=saved,output=dict(file_name='recovered.png',format='png'))
    call('recover-start','job.start',request_id='recover',**args)
    call('newer','session.apply',session_id='work',request_id='newer',expected_revision=0,response_mode='compact',
        action=dict(type='edit',operations=[dict(op='vector',id='badge',geometry=dict(shape='rect',x=32,y=40,width=24,height=20),fill=ORANGE)]))
    control('launch','interrupt-queued')
    attempts['interrupted-status']=call('interrupted-status','job.status',request_id='recover')
    attempts['interrupted-wait']=call('interrupted-wait','job.wait',request_id='recover',wait_ms=0)
    attempts['interrupted-error']=call('interrupted-result','job.result',request_id='recover',expected_error='JOB_NOT_COMPLETED')
    call('restart','job.resume',request_id='recover')
    attempts['completed']=terminal('recover','completed');attempts['receipt']=call('result','job.result',request_id='recover')
    call('editable','document.publish',document=dict(session_id='work',revision=1),output=dict(format='snapshot',file_name='editable.json'))
    attempts['start-replay']=call('start-replay','job.start',request_id='recover',retry_of='recover-start',**args)
    attempts['resume-completed']=call('resume-completed','job.resume',request_id='recover',retry_of='restart')
    attempts['result-replay']=call('result-replay','job.result',request_id='recover',retry_of='result')
    attempts['overwrite-error']=call('overwrite','document.publish',document=dict(session_id='work',revision=1),output=args['output'],expected_error='OUTPUT_EXISTS')
    call('verify-history','session.verify',session_id='work')
    save_json(root/'attempts.json',attempts)
