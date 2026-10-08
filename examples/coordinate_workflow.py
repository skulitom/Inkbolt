"""Original fractional geometry retained through snapshot and SVG exchange."""
import argparse
import copy
import json
from pathlib import Path
from mask_workflow import invoke


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    d=invoke('document.create',id='fractional-layout',kind='vector',width=96,height=64)
    items=[dict(id='layout',transform=[1.125,.0625,-.03125,.875,28.123456789012345,22.987654321098765],content=dict(type='group')),
        dict(id='panel',parent='layout',content=dict(type='vector',geometry=dict(shape='rect',x=-15.146750185997725,y=-9.125,width=38.952095808383234,height=26.375),fill=[30,90,180,255])),
        dict(id='curve',parent='layout',transform=[1,0,0,1,4.375,3.125],content=dict(type='vector',geometry=dict(shape='path',commands=[dict(verb='move',to=[-8.123456789012345,-3.375]),dict(verb='cubic',control1=[-4.25,9.125],control2=[12.625,-7.75],to=[20.123456789012345,6.375]),dict(verb='line',to=[-8.123456789012345,9.125]),dict(verb='close')]),fill=[245,170,40,255]))]
    d=invoke('document.edit',document=d,expected_revision=0,operations=[dict(op='add',item=i) for i in items])['document'];original=copy.deepcopy(d)
    def save(name,v):
        with (out/name).open('x',encoding='utf8') as f:json.dump(v,f,indent=2);f.write('\n')
    save('original.json',d)
    for fmt in ['svg','png']:
        save(fmt+'-receipt.json',invoke('document.publish',document=d,output=dict(output_root=str(out),file_name='original.'+fmt,format=fmt,scale=4 if fmt=='png' else 1)))
    result=invoke('svg.import',id='exchanged-layout',source=dict(kind='file',source_path=str(out/'original.svg')))
    save('import-receipt.json',result);save('reimported.json',result['document'])
    save('reimported-png-receipt.json',invoke('document.publish',document=result['document'],output=dict(output_root=str(out),file_name='reimported.png',format='png',scale=4)))
    assert d==original and (out/'original.png').read_bytes()==(out/'reimported.png').read_bytes()
    print('Saved original fractional geometry, SVG, reimported snapshot and matching previews in '+str(out))


if __name__=='__main__':main()
