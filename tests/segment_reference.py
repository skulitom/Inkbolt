"""Original exhaustive labeling oracle, independent of graph/flow implementation."""
import itertools


def costs(pixels, width, height, options):
    features=[[(p[c]*p[3]+127)//255 for c in range(3)]+[p[3]] for p in pixels]
    distance=lambda a,b:sum((x-y)**2 for x,y in zip(a,b))
    seeds=[[y*width+x for x,y in options[k]] for k in ['foreground','background']]
    unary=[[min(distance(p,features[i]) for i in s) for s in seeds] for p in features]
    pair=[];strength=options.get('smoothness',4096);scale=options.get('edge_scale',4096)
    for y in range(height):
        for x in range(width):
            u=y*width+x
            for nx,ny in [(x+1,y),(x,y+1)]:
                if nx<width and ny<height:
                    v=ny*width+nx;pair.append((u,v,strength*scale//(scale+distance(features[u],features[v]))))
    hard=1+sum(max(c) for c in unary)+sum(w for _,_,w in pair)
    for i in seeds[0]:unary[i][1]=hard
    for i in seeds[1]:unary[i][0]=hard
    return unary,pair,hard,seeds


def exhaustive(pixels, width, height, options):
    unary,pairs,hard,seeds=costs(pixels,width,height,options)
    best=None;intersection=None;count=0
    fixed={i:True for i in seeds[0]}|{i:False for i in seeds[1]}
    free=[i for i in range(len(pixels)) if i not in fixed]
    for choices in itertools.product([False,True],repeat=len(free)):
        labels=dict(fixed)|dict(zip(free,choices));count+=1
        value=sum(c[0 if labels[i] else 1] for i,c in enumerate(unary))+sum(w for u,v,w in pairs if labels[u]!=labels[v])
        fg={i for i in labels if labels[i]}
        if best is None or value<best:best,intersection=value,fg
        elif value==best:intersection&=fg
    return best,bytes(255 if i in intersection else 0 for i in range(len(pixels))),count


def original_document(pixels,width,height):
    return dict(schema_version=2,id='original-selection',kind='raster',width=width,height=height,color_space='srgb',items=[dict(id='pixels',content=dict(type='raster',width=width,height=height,rgba_hex=bytes(v for p in pixels for v in p).hex()))])
