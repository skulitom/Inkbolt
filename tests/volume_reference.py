"""Original ray/plane reference for polygonal extrusions, independent of face ordering."""
import math


def dot(a,b):return sum(x*y for x,y in zip(a,b))
def matrix(angles):
    x,y,z=[math.radians(v) for v in angles];cx,sx=math.cos(x),math.sin(x);cy,sy=math.cos(y),math.sin(y);cz,sz=math.cos(z),math.sin(z)
    return [[cz*cy,cz*sy*sx-sz*cx,cz*sy*cx+sz*sx],
            [sz*cy,sz*sy*sx+cz*cx,sz*sy*cx-cz*sx],[-sy,cy*sx,cy*cx]]
def normalize(v):
    length=math.sqrt(dot(v,v));return [x/length for x in v]
def winding(loop,x,y):
    n=0
    for a,b in zip(loop,loop[1:]+loop[:1]):
        cross=(b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0])
        if a[1]<=y<b[1] and cross>0:n+=1
        if b[1]<=y<a[1] and cross<0:n-=1
    return n
def rgb(material,normal):
    color=[v/255 for v in material['color']]
    if material['type']=='unlit':return material['color']
    energy=material['ambient'][:]
    for light in material['lights']:
        amount=max(0,dot(normal,normalize(light['direction'])))*light['intensity']
        energy=[e+amount*c for e,c in zip(energy,light['color'])]
    result=[]
    for value,power in zip(color,energy):
        linear=value/12.92 if value<=.04045 else ((value+.055)/1.055)**2.4
        linear=max(0,min(1,linear*power));encoded=linear*12.92 if linear<=.0031308 else 1.055*linear**(1/2.4)-.055
        result.append(math.floor(encoded*255+.5))
    return result
def pixel(spec,loops,x,y):
    """Loops have positive outer and negative hole winding; each hit is tested in source 3D."""
    m=matrix(spec.get('rotation',[0,0,0]));inverse=list(zip(*m));pivot=spec.get('pivot',[0,0,0]);translation=spec.get('translation',[0,0,0]);camera=spec.get('camera',{'type':'orthographic'})
    if camera['type']=='orthographic':origin=[x,y,100000];direction=[0,0,-1]
    else:
        a,b=camera['principal'];origin=[a,b,camera['distance']];direction=[x-a,y-b,-camera['distance']]
    origin=[v-p-t for v,p,t in zip(origin,pivot,translation)];origin=[dot(row,origin)+p for row,p in zip(inverse,pivot)];direction=[dot(row,direction) for row in inverse]
    depth=spec['depth'];hits=[]
    if abs(direction[2])>1e-10:
        for z,normal in [(0,[0,0,1]),(-depth,[0,0,-1])]:
            t=(z-origin[2])/direction[2];px=origin[0]+direction[0]*t;py=origin[1]+direction[1]*t
            if t>=0 and sum(winding(c,px,py) for c in loops)!=0:hits.append((t,normal))
    if depth:
        for loop in loops:
            for a,b in zip(loop,loop[1:]+loop[:1]):
                edge=[b[0]-a[0],b[1]-a[1]];cross=direction[0]*edge[1]-direction[1]*edge[0]
                if abs(cross)<1e-10:continue
                offset=[a[0]-origin[0],a[1]-origin[1]]
                t=(offset[0]*edge[1]-offset[1]*edge[0])/cross
                u=(offset[0]*direction[1]-offset[1]*direction[0])/cross
                z=origin[2]+direction[2]*t
                if t>=0 and 0<=u<=1 and -depth<=z<=0:hits.append((t,normalize([edge[1],-edge[0],0])))
    if not hits:return [0,0,0,0]
    _,normal=min(hits,key=lambda v:v[0]);normal=[dot(row,normal) for row in m]
    return rgb(spec['material'],normal)+[255]
def pixels(spec,loops,width,height):return bytes(v for y in range(height) for x in range(width) for v in pixel(spec,loops,x+.5,y+.5))


def projected_contours(face):
    result=[]
    for command in face['geometry']['commands']:
        if command['verb']=='move':result.append([command['to']])
        elif command['verb']=='line':result[-1].append(command['to'])
        else:assert command['verb']=='close'
    return result
def segment_distance(p,a,b):
    v=[b[0]-a[0],b[1]-a[1]];w=[p[0]-a[0],p[1]-a[1]];n=dot(v,v)
    t=max(0,min(1,dot(w,v)/n)) if n else 0
    return math.hypot(w[0]-t*v[0],w[1]-t*v[1])
def projected(faces,width,height):
    """Interpret returned vector faces independently, retaining near-edge diagnostics."""
    paths=[(projected_contours(f),[math.floor(v*255+.5) for v in f['rgba']]) for f in faces]
    result=[];edge_distance=[]
    for y in range(height):
        for x in range(width):
            p=[x+.5,y+.5];color=[0,0,0,0];distance=float('inf')
            for contours,rgba in paths:
                if sum(winding(c,*p) for c in contours):color=rgba
                for c in contours:
                    for a,b in zip(c,c[1:]+c[:1]):distance=min(distance,segment_distance(p,a,b))
            result.extend(color);edge_distance.append(distance)
    return bytes(result),edge_distance
