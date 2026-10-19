"""Physical flat names and zero activity survive explicit SAIF import."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

DIRECTORY = Path(__file__).parent/"t10_backend/v1"
sys.path.insert(0,str(DIRECTORY))
from saif_activity import export_scope
sys.path.pop(0)


class SaifActivityTest(unittest.TestCase):
    def export(self, name="impl.original_quad/_0000_", extra=""):
        source = "\n".join([
            '(SAIFILE','(TIMESCALE 1ps)','(DURATION 2000)',
            '(INSTANCE pe','(INSTANCE int_group\\[0\\].product_group','(NET',
            f'({name} (T0 500) (T1 1500) (TZ 0) (TX 0) (TB 0) (TC 0))',
            extra,')',')',')',')'])
        with tempfile.TemporaryDirectory() as temp:
            source_path=Path(temp)/'input.saif'
            target=Path(temp)/'nets.tsv'
            source_path.write_text(source)
            result=export_scope(source_path,['pe','int_group[0].product_group'],target)
            return result,target.read_text()

    def test_slash_flat_name_and_zero_toggles(self):
        result, data=self.export()
        self.assertEqual(result['activity_nets'],1)
        self.assertEqual(data,'{impl.original_quad/_0000_} 0 0.75\n')

    def test_bus_escapes_normalized_not_globbed(self):
        _,data=self.export(r'impl.product\[3\]')
        self.assertEqual(data,'{impl.product[3]} 0 0.75\n')

    def test_ambiguous_name_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            self.export('n', '(n (T0 500) (T1 1500) (TZ 0) (TX 0) (TB 0) (TC 0))')


if __name__=='__main__':
    unittest.main()
