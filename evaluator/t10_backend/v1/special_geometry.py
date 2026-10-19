"""Special-route metal/cuts for ECO clearance diagnostics, including PG rails."""


def special_shapes(net,region=None):
    for wire in net.getSWires():
        for box in wire.getWires():
            if region is not None and (box.xMin()>region[2] or box.xMax()<region[0] or
                                       box.yMin()>region[3] or box.yMax()<region[1]):
                continue
            if not box.isVia():
                layer=box.getTechLayer()
                if layer is not None:
                    yield dict(kind='special_segment',net=net.getName(),layer=layer.getName(),
                               bbox=(box.xMin(),box.yMin(),box.xMax(),box.yMax()))
                continue
            x,y=box.getViaXY()
            via=box.getTechVia() or box.getBlockVia()
            if via is None:
                raise ValueError('special route via has no definition')
            for part in via.getBoxes():
                layer=part.getTechLayer()
                if layer is not None:
                    yield dict(kind='special_via',net=net.getName(),layer=layer.getName(),
                               bbox=(x+part.xMin(),y+part.yMin(),x+part.xMax(),y+part.yMax()),
                               via=via.getName(),origin=(x,y))
