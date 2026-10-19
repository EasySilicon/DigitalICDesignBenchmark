"""Read-only geometry around markers from an actual DRT/native DRC report."""
import argparse
import json
from pathlib import Path
import re
import sys

import odb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'physical'))
from t10_manual_v15_inspect import fixed_shapes, gap
from full_geometry import POLICY, wire_shapes
from special_geometry import special_shapes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('odb')
    parser.add_argument('report', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--halo-dbu', type=int, default=100)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('inspection output exists; preserve earlier observations')
    database = odb.dbDatabase.create()
    odb.read_db(database, args.odb)
    block = database.getChip().getBlock()
    dbu = block.getDbUnitsPerMicron()
    records = []
    for match in re.finditer(r'violation type: ([^\n]+)\n\s*srcs: ([^\n]+)\n\s*bbox = \(([-\d.]+), ([-\d.]+)\) - \(([-\d.]+), ([-\d.]+)\) on Layer (\S+)', args.report.read_text()):
        records.append(dict(kind=match[1], sources=match[2],
                            bbox=[round(float(match[i])*dbu) for i in range(3,7)],
                            layer=match[7], shapes=[]))
    if not records:
        raise ValueError('no parsed DRC markers')
    regions=[]
    for record in records:
        x0,y0,x1,y1=record['bbox']; halo=args.halo_dbu
        box=(x0-halo,y0-halo,x1+halo,y1+halo)
        while True:
            matches=[region for region in regions if gap(box,region)==0]
            if not matches:
                break
            for region in matches:
                regions.remove(region)
                box=(min(box[0],region[0]),min(box[1],region[1]),max(box[2],region[2]),max(box[3],region[3]))
        regions.append(box)
    def collect(shapes):
        for shape in shapes:
            if not any(gap(shape['bbox'],region)==0 for region in regions):
                continue
            for record in records:
                distance = gap(shape['bbox'], record['bbox'])
                if distance <= args.halo_dbu:
                    record['shapes'].append(dict(shape, gap_dbu=distance))
    for net in block.getNets():
        collect(wire_shapes(net))
        collect(special_shapes(net))
    for inst in block.getInsts():
        collect(fixed_shapes(inst))
    for record in records:
        record['shapes'].sort(key=lambda item: (item['gap_dbu'], item['layer'], item['kind']))
        print('MARKER', record['kind'], record['layer'], record['bbox'])
        for shape in record['shapes']:
            if shape['layer']==record['layer'] or (shape['kind']=='route_via' and shape.get('net') in record['sources']):
                print(json.dumps(shape, separators=(',',':')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(odb=args.odb, report=str(args.report),wire_iterator_policy=POLICY,special_routes_included=True,
                                          dbu_per_micron=dbu, markers=records), indent=2)+'\n')


if __name__=='__main__':
    main()
