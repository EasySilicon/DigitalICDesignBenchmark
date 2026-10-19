"""Integer-exact PE activity averaging and full-instance coverage checks."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

PATH = Path(__file__).parent / "t10_backend/v1/merge_pe_saif.py"
SPEC = importlib.util.spec_from_file_location("t10_merge_pe_saif", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PeSaifTest(unittest.TestCase):
    def source(self, count=2, missing_net=False, unknown=False):
        lines = ['(SAIFILE', '(TIMESCALE 1ps)', '(DURATION 1000)',
                 '(INSTANCE TOP', '(INSTANCE tb', '(INSTANCE dut']
        for index in range(count):
            lines += [f'(INSTANCE pe{index}', '(NET',
                      '(clk (T0 500) (T1 500) (TZ 0) (TX 0) (TB 0) (TC 2))']
            if not missing_net or index == 0:
                lines.append(f'(n (T0 {800-100*index}) (T1 {200+100*index}) (TZ 0) (TX {int(unknown)}) (TB 0) (TC {index+2}))')
            lines += [')', '(INSTANCE macro', '(NET',
                      '(x (T0 900) (T1 100) (TZ 0) (TX 0) (TB 0) (TC 4))', ')', ')', ')']
        return '\n'.join(lines + [')', ')', ')', ')'])+'\n'

    def merge(self, source):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.saif"
            output = Path(temporary) / "average.saif"
            path.write_text(source)
            result = MODULE.merge(path, {'pe0','pe1'}, {'macro':'synthetic_macro'}, output)
            return result, output.read_text()

    def test_exact_average_by_scaling_duration(self):
        result, merged = self.merge(self.source())
        self.assertEqual(result['pe_instances'], 2)
        self.assertEqual(result['duration_merged_ticks'], 2000)
        self.assertIn('(n (T0 1500) (T1 500) (TZ 0) (TX 0) (TB 0) (TC 5))', merged)
        self.assertEqual(result['clock_activity'], [1000,1000,4,2])
        self.assertEqual(result['scope_net_counts'], {'pe_shell':2,'macro':1})

    def test_incomplete_pe_set_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'incomplete SAIF'):
            self.merge(self.source(count=1))

    def test_net_missing_in_one_pe_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'net coverage'):
            self.merge(self.source(missing_net=True))

    def test_unknown_activity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unknown SAIF'):
            self.merge(self.source(unknown=True))

    def test_hierarchy_discovery_requires_exactly_256_pes(self):
        source = 'module npu_systolic_matmul_16x16();\n'
        source += ''.join(f' t10_reference_pe p{i} ();\n' for i in range(256))
        source += 'endmodule\n'
        self.assertEqual(len(MODULE.pe_paths(source)),256)
        with self.assertRaisesRegex(ValueError, '256 distinct'):
            MODULE.pe_paths(source.replace('t10_reference_pe p255 ();',''))


if __name__ == '__main__':
    unittest.main()
