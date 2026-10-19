import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('t10_connectivity',Path(__file__).parent/'t10_backend/v1/check_connectivity.py')
MODULE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ConnectivityTest(unittest.TestCase):
    def shape(self,layer,box,group=None):
        return dict(layer=layer,bbox=box,group=group)

    def test_same_layer_edge_contact_connects(self):
        self.assertEqual(MODULE.components([self.shape('M2',(0,0,5,5)),self.shape('M2',(5,0,10,5))]),1)

    def test_different_layers_do_not_connect_without_via(self):
        self.assertEqual(MODULE.components([self.shape('M2',(0,0,5,5)),self.shape('M3',(0,0,5,5))]),2)

    def test_actual_via_connects_layers(self):
        self.assertEqual(MODULE.components([self.shape('M2',(0,0,5,5),('via',0)),self.shape('M3',(0,0,5,5),('via',0))]),1)

    def test_disjoint_floating_route_is_detected(self):
        self.assertEqual(MODULE.components([self.shape('M2',(0,0,5,5)),self.shape('M2',(6,0,10,5))]),2)

    def test_same_logical_pin_shapes_are_connected_inside_cell(self):
        self.assertEqual(MODULE.components([self.shape('M1',(0,0,2,2),('pin','A')),self.shape('M1',(6,0,8,2),('pin','A'))]),1)
