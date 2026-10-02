"""T10 gate workload must verify matrix values as well as completion markers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ppa_power_probe import check_t10_workload, instrument_testbench


class T10PowerWorkloadTest(unittest.TestCase):
    def test_power_copy_uses_one_ghz_clock(self):
        source = """`timescale 1ns/1ps
module tb_hidden_T10_stream;
  logic clk=0, rst_n=0;
  always #5 clk=~clk;
endmodule
"""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "tb.sv"
            output = root / "tb_power.sv"
            original.write_text(source)
            self.assertEqual(instrument_testbench("T10", original, output),
                             "tb_hidden_T10_stream")
            instrumented = output.read_text()
            self.assertIn("always #0.5 clk=~clk;", instrumented)
            self.assertNotIn("always #5 clk=~clk;", instrumented)

    def test_power_copy_rejects_ambiguous_clock(self):
        source = "module tb_hidden_T10_stream; logic rst_n; endmodule\n"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "tb.sv"
            original.write_text(source)
            with self.assertRaisesRegex(ValueError, "one 10 ns debug clock"):
                instrument_testbench("T10", original, root / "tb_power.sv")

    def test_complete_zero_workload_and_corrupt_lane(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            count = 10
            for name, width, lines in (("a", 256, count * 16),
                                       ("b", 256, count * 16),
                                       ("as", 64, count),
                                       ("bs", 64, count),
                                       ("reset", 1, count),
                                       ("phase", 1, count)):
                (root / f"{name}.mem").write_text(("0" * width + "\n") * lines)
            (root / "mode.mem").write_text("".join(f"{mode:x}\n" for mode in range(10)))
            entries = []
            for case in range(count):
                entries.extend(f"MM_ROW {case} {row} {'0' * 256}" for row in range(16))
                entries.append(f"MM_CASE {case} 1 1 1 16")
            log = ("\n".join(entries) +
                   f"\nMM_STREAM input_bubble_phases={'0' * 13} finished={count}\n")
            check_t10_workload(log, root, count)
            bubble = log.replace("input_bubble_phases=" + "0" * 13,
                                 "input_bubble_phases=" + "1" + "0" * 12, 1)
            with self.assertRaisesRegex(RuntimeError, "continuous workload"):
                check_t10_workload(bubble, root, count)
            corrupted = log.replace(f"MM_ROW 0 0 {'0' * 256}", "MM_ROW 0 0 1", 1)
            with self.assertRaisesRegex(RuntimeError, "numerical mismatch"):
                check_t10_workload(corrupted, root, count)
            duplicated = log.replace("MM_CASE 0 1 1 1 16\n", "MM_CASE 0 1 1 1 16\n" * 2, 1)
            with self.assertRaisesRegex(RuntimeError, "duplicated case marker"):
                check_t10_workload(duplicated, root, count)


if __name__ == "__main__":
    unittest.main()
