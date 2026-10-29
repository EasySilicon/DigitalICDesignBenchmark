import tempfile
import unittest
from pathlib import Path

from t08_power_probe import (activity_window, checked_operations, checked_macro_power,
                             sanitize_openroad_vcd_identifiers)


class T08PowerTest(unittest.TestCase):
    def test_openroad_unsafe_vcd_identifier_is_remapped_without_changing_activity(self):
        source = """$timescale 1ps $end
$scope module tb_t08_power $end
$var real 64 #j phase $end
$scope module dut $end
$var wire 1 a logic_clk $end
$var wire 1 b tx_clk $end
$var wire 1 c rx_clk $end
$var wire 4 #v payload [3:0] $end
$upscope $end
$upscope $end
$enddefinitions $end
#10000
r0.17 #j
0a
0b
0c
b0000 #v
#10500
1a
1b
1c
b1010 #v
#11000
0a
0b
0c
#11500
1a
1b
1c
#12000
0a
0b
0c
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "activity.vcd"
            path.write_text(source)
            mapping = sanitize_openroad_vcd_identifiers(path)
            self.assertEqual(set(mapping), {"#j", "#v"})
            result = path.read_text()
            self.assertNotIn("#j", result)
            self.assertNotIn("#v", result)
            self.assertIn("#10000", result)
            self.assertIn("#10500", result)
            self.assertIn("#11000", result)
            self.assertIn("r0.17 ORVCD", result)
            self.assertIn("b1010 ORVCD", result)
            # Remapping is idempotent and does not alter clock activity.
            self.assertEqual(sanitize_openroad_vcd_identifiers(path), {})
            end, periods = activity_window(path)
            self.assertAlmostEqual(end, 2e-9)
            self.assertEqual(periods, {"logic_clk": 1000.0,
                                       "tx_clk": 1000.0,
                                       "rx_clk": 1000.0})

    def test_macro_power_requires_each_instance_and_nonzero_active_power(self):
        row = "T08_SRAM_POWER name=rx.mem.0 internal=0.002 switching=0.001 leakage=0.0001 total=0.0031\n"
        good = row + row.replace("rx.mem.0", "tx.mem.0")
        self.assertEqual(len(checked_macro_power(good, 2)), 2)
        for bad in (row, row + row, good.replace("internal=0.002", "internal=0"),
                    good.replace("total=0.0031", "total=nan"), "fakeram7_tdp_4096x32"):
            with self.assertRaises(ValueError):
                checked_macro_power(bad, 2)

    def test_checked_completions_are_unique_and_byte_count_is_exact(self):
        log = "T08_POWER_PASS TX=3 RX=5 DROP=1 OPS=4296\nPOWER_OPS=4296\n"
        self.assertEqual(checked_operations(log), 4296)
        for bad in (log + log, log.replace("POWER_OPS=4296", "POWER_OPS=4295"),
                    log.replace("RX=5", "RX=4"), "POWER_OPS=4296\n"):
            with self.assertRaises(ValueError):
                checked_operations(bad)

    def test_activity_window_excludes_time_before_dump_start(self):
        header = ("$timescale 1ps $end\n$scope module tb_t08_power $end\n"
                  "$scope module dut $end\n$var wire 1 a logic_clk $end\n"
                  "$var wire 1 b tx_clk $end\n$var wire 1 c rx_clk $end\n"
                  "$upscope $end\n$upscope $end\n$enddefinitions $end\n")
        body = "#10000\n0a\n0b\n0c\n#10500\n1a\n1b\n1c\n#11000\n0a\n0b\n0c\n#11500\n1a\n1b\n1c\n#12000\n"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "activity.vcd"
            path.write_text(header + body)
            duration, clocks = activity_window(path)
            self.assertAlmostEqual(duration, 2e-9)
            self.assertEqual(clocks, {"logic_clk": 1000.0, "tx_clk": 1000.0, "rx_clk": 1000.0})
            path.write_text(header + body.replace("#11500", "#12500").replace("#12000", "#13000"))
            with self.assertRaisesRegex(ValueError, "1000 ps"):
                activity_window(path)


if __name__ == "__main__":
    unittest.main()
