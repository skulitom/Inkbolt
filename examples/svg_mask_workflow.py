"""Import a labeled diagram with a shared editable mask, revise it and undo.

Requires explicit local font/license paths and a new output directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--font',required=True,type=Path)
    parser.add_argument('--license',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--label',default='Shared reveal')
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (output/name).open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(value,indent=2)+'\n')
    font=invoke('font.import',source_path=str(args.font.resolve()),license_path=str(args.license.resolve()),store_root=str(output/'fonts'))
    panels=''.join(f'''<g id="panel-{n}" transform="translate({x},16)" mask="url(#reveal)" clip-path="url(#trim)">
<rect width="96" height="72" fill="#1f93db"/>
<rect x="24" y="24" width="48" height="24" fill="#f3a848"/>
<text x="12.5" y="60" font-family="Label Face" font-size="10" fill="white">{escape(args.label)}</text>
</g>''' for n,x in enumerate((12,124)))
    source=f'''<svg xmlns="http://www.w3.org/2000/svg" width="232" height="104" viewBox="0 0 232 104">
<defs>
<clipPath id="trim"><rect width="96" height="72"/></clipPath>
<mask id="reveal" maskContentUnits="objectBoundingBox" x="0" y="0" width="1" height="1">
<linearGradient id="fade"><stop offset="0" stop-color="black"/><stop offset="1" stop-color="white"/></linearGradient>
<rect width="1" height="1" fill="url(#fade)"/>
<rect id="window" x=".25" y=".25" width=".5" height=".5" fill="white"/>
</mask>
</defs>{panels}</svg>'''
    path=output/'source.svg'
    with path.open('x',encoding='utf8',newline='\n') as f:f.write(source)
    original=hashlib.sha256(path.read_bytes()).hexdigest()
    request=dict(command='svg.import',id='masked-diagrams',source=dict(kind='file',source_path=str(path)),font_root=str(output/'fonts'),font_bindings=[dict(family='Label Face',font_id='labels',font=font)])
    save('request.json',request);result=invoke(**request);save('import.json',result)
    window=next(v['item_id'] for v in result['mapping'] if v['source_id']=='window')
    common=dict(session_root=str(output/'sessions'),session_id='masked-diagrams')
    invoke('session.create',**common,request_id='create',document=result['document'],resources=dict(font_root=str(output/'fonts')))
    def publish(name,revision):
        for fmt,extension in [('snapshot','json'),('png','png'),('svg','svg')]:
            save(name+'-'+fmt+'-receipt.json',invoke('session.publish',**common,expected_revision=revision,output=dict(output_root=str(output),file_name=name+'.'+extension,format=fmt)))
    publish('before',0)
    save('edit.json',invoke('session.apply',**common,request_id='edit',expected_revision=0,action=dict(type='edit',label='Revise shared mask',operations=[dict(op='properties',id=window,opacity=.25),dict(op='transform',id=window,matrix=[1,0,0,1,.125,0])])))
    publish('edited',1)
    save('difference.json',invoke('session.diff',**common,from_revision=0,to_revision=1,compare_pixels=True))
    save('undo.json',invoke('session.apply',**common,request_id='undo',expected_revision=1,action=dict(type='undo')))
    save('undo-png-receipt.json',invoke('session.publish',**common,expected_revision=2,output=dict(output_root=str(output),file_name='undo.png',format='png')))
    assert (output/'before.png').read_bytes()==(output/'undo.png').read_bytes()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==original
    invoke('session.verify',**common)
    print('Created editable SVG masks, shared edit, exports and exact undo in '+str(output))


if __name__=='__main__':main()
