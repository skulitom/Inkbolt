"""Import, edit and undo an original labeled SVG with an explicitly licensed local font."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from xml.sax.saxutils import escape


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--font',required=True,type=Path);parser.add_argument('--license',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--label',default='Agent graphic');parser.add_argument('--replacement',default='Ready to export')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1];exe=root/'target/debug/inkbolt.exe'
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    def call(**q):
        p=subprocess.run([str(exe)],input=json.dumps(q).encode(),capture_output=True,check=False)
        result=json.loads(p.stdout)
        if p.returncode or not result['ok']:raise RuntimeError(result)
        return result['result']
    def save(name,v):
        with (output/name).open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(v,indent=2)+'\n')
    font=call(command='font.import',source_path=str(args.font.resolve()),license_path=str(args.license.resolve()),store_root=str(output/'fonts'))
    source=f'''<svg xmlns="http://www.w3.org/2000/svg" width="320" height="96">
<defs><linearGradient id="panel"><stop offset="0" stop-color="#204060"/><stop offset="1" stop-color="#406080"/></linearGradient></defs>
<rect x="8" y="8" width="304" height="80" fill="url(#panel)"/>
<text id="label" x="19" y="58" font-family="Label Face" font-size="20" fill="white">{escape(args.label)}</text>
</svg>'''
    path=output/'source.svg'
    with path.open('x',encoding='utf8',newline='\n') as f:f.write(source)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    request=dict(command='svg.import',id='svg-label',source=dict(kind='file',source_path=str(path)),font_bindings=[dict(family='Label Face',font_id='label-font',font=font)],font_root=str(output/'fonts'))
    save('request.json',request);imported=call(**request);save('import.json',imported)
    label=next(m['item_id'] for m in imported['mapping'] if m['source_id']=='label')
    original_text=next(i['content']['frame']['text'] for i in imported['document']['items'] if i['id']==label)
    common=dict(session_root=str(output/'sessions'),session_id='label')
    call(command='session.create',**common,request_id='create',document=imported['document'],resources=dict(font_root=str(output/'fonts')))
    def publish(prefix,revision):
        for fmt,suffix in [('snapshot','json'),('png','png'),('svg','svg')]:
            save(prefix+'-'+fmt+'-receipt.json',call(command='session.publish',**common,expected_revision=revision,output=dict(output_root=str(output),file_name=prefix+'.'+suffix,format=fmt)))
    publish('before',0)
    save('edit.json',call(command='session.apply',**common,request_id='edit',expected_revision=0,action=dict(type='edit',operations=[dict(op='text_range',id=label,start=0,end=len(original_text),text=args.replacement)])))
    publish('edited',1)
    save('difference.json',call(command='session.diff',**common,from_revision=0,to_revision=1,compare_pixels=True))
    save('undo.json',call(command='session.apply',**common,request_id='undo',expected_revision=1,action=dict(type='undo')))
    save('undo-png-receipt.json',call(command='session.publish',**common,expected_revision=2,output=dict(output_root=str(output),file_name='undo.png',format='png')))
    assert (output/'before.png').read_bytes()==(output/'undo.png').read_bytes()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    print('Created editable SVG import, label edit, exports, difference and exact undo in '+str(output))


if __name__=='__main__':main()
