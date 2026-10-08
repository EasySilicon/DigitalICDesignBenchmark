import argparse
import re
from pathlib import Path

SIZE = re.compile(r'(?m)^  SIZE ([\d.]+) BY ([\d.]+) ;$')
OBS = re.compile(r'(?ms)^  OBS\n(.*?)^  END\n')
RECT = re.compile(r'RECT\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)')
PIN = re.compile(r'(?ms)^  PIN ([^\n]+)\n(.*?)^  END \1\n')


def section(obs, layer):
    pat = re.compile(r'(?ms)(^    LAYER '+re.escape(layer)+r' ;\n)(.*?)(?=^    LAYER |\Z)')
    match = pat.search(obs)
    if match is None:
        raise ValueError('missing OBS layer '+layer)
    return match, [tuple(map(float, group)) for group in RECT.findall(match.group(2))]


def fmt(box):
    return '      RECT  '+' '.join(f'{v:.3f}'.rstrip('0').rstrip('.') if v else '0' for v in box)+' ;\n'


def overlaps(a, b):
    return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])


def pin_shapes(lef, layer):
    shapes = []
    for _, body in PIN.findall(lef):
        for pin_layer, geometry in re.findall(
                r'(?ms)LAYER (M\d+) ;\n\s*RECT\s+([\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+)', body):
            if pin_layer == layer:
                shapes.append(tuple(map(float, geometry.split())))
    return shapes

p = argparse.ArgumentParser()
p.add_argument('--base', type=Path, required=True)
p.add_argument('--detailed', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--layer-edge', action='append', required=True, help='M2:left or M3:bottom')
p.add_argument('--depth', type=float, default=.2)
a=p.parse_args()
base=a.base.read_text();detail=a.detailed.read_text()
bs=SIZE.search(base);ds=SIZE.search(detail)
assert bs and ds and bs.groups()==ds.groups()
w,h=map(float,bs.groups())
assert 0<a.depth<min(w,h)/10
bm=OBS.search(base);dm=OBS.search(detail)
assert bm and dm
new=bm.group(1)
for spec in a.layer_edge:
    layer,edge=spec.split(':')
    assert edge in ('left','bottom')
    bm_layer,old=section(new,layer)
    _,actual=section(dm.group(1),layer)
    assert len(old)==1 and old[0]==(0.0,0.0,w,h)
    if edge=='left':
        inner=(a.depth,0.0,w,h)
        edge_boxes=[box for box in actual if box[0]<a.depth]
    else:
        inner=(0.0,a.depth,w,h)
        edge_boxes=[box for box in actual if box[1]<a.depth]
    # Routed child geometries often continue directly from a LEF signal pin.
    # An OBS overlapping that pin blocks parent-router pin access, even when
    # the metal is legal in the child. Keep the pin geometry open in the edge
    # strip while retaining the child's unrelated obstructions.
    pins=pin_shapes(base,layer)
    edge_boxes=[box for box in edge_boxes if not any(overlaps(box,pin) for pin in pins)]
    new=new[:bm_layer.start(2)]+fmt(inner)+''.join(map(fmt,edge_boxes))+new[bm_layer.end(2):]
    print(layer,edge,'detailed edge OBS',len(edge_boxes))
a.output.write_text(base[:bm.start(1)]+new+base[bm.end(1):])
print(a.output)
