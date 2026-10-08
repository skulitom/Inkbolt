"""Arrange an original icon sheet, inspect the proposal and publish new artifacts."""
import base64
import json
from pathlib import Path
import subprocess
import sys


def main():
    if len(sys.argv) != 3:
        raise SystemExit('Usage: python examples/assisted_layout.py PATH_TO_ENGINE NEW_OUTPUT_DIRECTORY')
    engine, output = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    output.mkdir(parents=True, exist_ok=False)

    def call(command, **values):
        result = subprocess.run([str(engine)], input=json.dumps(dict(command=command, **values)).encode(), capture_output=True, check=True)
        response = json.loads(result.stdout)
        assert response['ok'], response
        return response['result']

    sizes = [(40,18),(26,38),(38,38),(40,20),(28,24),(24,24)]
    colors = [[29,87,118,255],[30,115,101,255],[138,68,103,255],[116,92,43,255],[80,76,138,255],[45,102,139,255]]
    items=[]
    ids=[]
    for k, ((w,h), color) in enumerate(zip(sizes, colors)):
        id=f'icon-{k}';ids.append(id)
        items.append(dict(id=id, name=f'Original module {k+1}', transform=[1,0,0,1,4+k*12,7+k*10], content=dict(type='group')))
        items.append(dict(id=id+'-plate', parent=id, content=dict(type='vector', geometry=dict(shape='rect',x=0,y=0,width=w,height=h),fill=color)))
        items.append(dict(id=id+'-node', parent=id, content=dict(type='vector', geometry=dict(shape='ellipse',cx=7,cy=7,rx=3,ry=3),fill=[246,235,213,255])))
        items.append(dict(id=id+'-bar', parent=id, content=dict(type='vector', geometry=dict(shape='rect',x=14,y=5,width=w-18,height=4),fill=[246,235,213,255])))
        items.append(dict(id=id+'-status', parent=id, content=dict(type='vector', geometry=dict(shape='rect',x=4,y=h-5,width=w-8,height=2),fill=[156,205,197,255])))
    source=call('document.validate',document=dict(schema_version=2,id='module-sheet',kind='vector',width=128,height=128,color_space='srgb',items=items))
    options=dict(ids=ids,bounds=[8,8,120,120],gap=[6,8],horizontal='center',vertical='center')
    report=call('assist.layout',document=source,options=options)
    result=call('document.edit',document=source,expected_revision=source['revision'],operations=[dict(op='assist_layout',options=options)])
    arranged=result['document']
    for name,value in [('source.json',source),('arranged.json',arranged),('options.json',options),('proposal.json',report),('edit-receipt.json',result)]:
        with (output/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    for name,document,format in [('before.png',source,'png'),('after.png',arranged,'png'),('after.svg',arranged,'svg'),('after.pdf',arranged,'pdf')]:
        artifact=call('document.export',document=document,format=format)
        data=artifact['data'].encode() if format=='svg' else base64.b64decode(artifact['data'])
        with (output/name).open('xb') as f:f.write(data)
    print(json.dumps(dict(output=str(output),minimum_height=report['minimum_height'],row_ends=report['row_ends'],source_preserved=True)))


if __name__=='__main__':main()
