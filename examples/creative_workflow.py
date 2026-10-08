"""Generate original charts and source-preserving creative treatments in a new folder."""
import argparse
import json
from pathlib import Path
import subprocess


OPERATORS = {
    'twist': dict(type='twist', center=[32,24], radius=29, angle=190),
    'relief': dict(type='relief', angle=35, distance=1.5, strength=3),
    'high-pass': dict(type='high_pass', sigma=2),
    'minimum': dict(type='extrema', radius=1, mode='minimum'),
    'maximum': dict(type='extrema', radius=1, mode='maximum'),
    'tone-fold': dict(type='tone_fold', threshold=.5),
    'edge-ink': dict(type='edge_ink', strength=2),
    'directional-marks': dict(type='stroke_rank', radius=3, angle=25, quantile=.3),
    'texture': dict(type='value_field', seed=1957, cell_size=16, octaves=3, origin=[0,0], low=[18,45,70], high=[242,200,139]),
    'field-repair': dict(type='field_repair', keep_parity=0),
}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--binary',type=Path,default=Path(__file__).resolve().parents[1]/'target/debug/inkbolt.exe')
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    def call(name,request):
        path=args.output/(name+'-request.json'); path.write_text(json.dumps(request,indent=2)+'\n')
        p=subprocess.run([str(args.binary.resolve()),str(path.resolve())],capture_output=True,text=True,check=True)
        response=json.loads(p.stdout); assert response['ok'],response
        (args.output/(name+'-response.json')).write_text(json.dumps(response,indent=2)+'\n')
        return response['result']
    d=call('create',dict(command='document.create',id='creative-example',kind='raster',width=64,height=48))
    values=[]
    for y in range(48):
        for x in range(64):
            ring=100<(x-32)**2+(y-24)**2<380
            color=(220,75,42) if ring else ((28,160,194) if (x//8+y//8)%2 else (238,209,124))
            values.extend(color+(255,))
    d=call('source',dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='add',item=dict(id='pixels',content=dict(type='raster',width=64,height=48,rgba_hex=bytes(values).hex())))]))['document']
    (args.output/'source.json').write_text(json.dumps(d,indent=2)+'\n')
    for name,op in OPERATORS.items():
        f=dict(id='treatment',operator=dict(type='creative',operator=op),border='reflect')
        out=call(name,dict(command='document.edit',document=d,expected_revision=d['revision'],operations=[dict(op='filters',id='pixels',filters=[f])]))['document']
        assert out['items'][0]['content']==d['items'][0]['content']
        (args.output/(name+'.json')).write_text(json.dumps(out,indent=2)+'\n')
        call(name+'-publish',dict(command='document.publish',document=out,output=dict(output_root=str(args.output.resolve()),file_name=name+'.png',format='png')))
    print(json.dumps(dict(output=str(args.output.resolve()),variants=len(OPERATORS),source_unchanged=True)))


if __name__=='__main__':main()
