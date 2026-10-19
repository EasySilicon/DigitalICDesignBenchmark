"""Native regression: a floating RECT must not disappear from connectivity."""
from pathlib import Path
import sys

import odb

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'t10_backend/v1'))
from check_connectivity import components
from full_geometry import wire_shapes, path_shapes

database=odb.dbDatabase.create()
tech=odb.dbTech.create(database,'rectangle_probe')
layer=odb.dbTechLayer.create(tech,'M2','ROUTING')
layer.setWidth(18)
chip=odb.dbChip.create(database,tech)
block=odb.dbBlock.create(chip,'rectangle_probe')
for name,x,y,expected in (('attached',150,100,1),('floating',500,500,2)):
    net=odb.dbNet.create(block,name)
    wire=odb.dbWire.create(net)
    encoder=odb.dbWireEncoder(); encoder.begin(wire)
    encoder.newPath(layer,'ROUTED')
    encoder.addPoint(100,100); encoder.addPoint(200,100)
    encoder.newPath(layer,'ROUTED')
    encoder.addPoint(x,y); encoder.addRect(-9,-9,9,9)
    encoder.end()
    old=list(path_shapes(net)); full=list(wire_shapes(net))
    assert len(old)==1 and len(full)==2, (old,full)
    assert full[-1]['kind']=='route_patch' and full[-1]['bbox']==(x-9,y-9,x+9,y+9)
    assert components(old)==1 and components(full)==expected, (name,full)
print('RECT_PATCH_REGRESSION_PASS attached=connected floating=detected historical_iterator_misses_floating')
