"""Exercise sequential cell behavior used by gate-level activity probes."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SequentialModelsTest(unittest.TestCase):
    def test_latch_transparency_hold_and_existing_flop_reset_behavior(self):
        bench = r'''
`timescale 1ps/1ps
module tb_seq;
  logic clk = 0, d = 0, resetn = 1, setn = 1;
  wire q_latch, q_flop, qn_reset;
  DHLx1_ASAP7_75t_R latch_cell(q_latch, d, clk);
  DFFHQx4_ASAP7_75t_R flop_cell(q_flop, d, clk);
  DFFASRHQNx1_ASAP7_75t_R reset_cell(qn_reset, d, resetn, setn, clk);
  initial begin
    #1; resetn = 0;
    #1; if (qn_reset !== 1'b1) $fatal(1, "asynchronous reset");
    resetn = 1; clk = 1;
    #1; if (q_latch !== 0 || q_flop !== 0 || qn_reset !== 1) $fatal(1, "initial capture");
    d = 1;
    #1; if (q_latch !== 1 || q_flop !== 0 || qn_reset !== 1) $fatal(1, "latch transparency versus edge capture");
    clk = 0;
    #1; d = 0;
    #1; if (q_latch !== 1) $fatal(1, "closed latch holds data");
    d = 1;
    #1; clk = 1;
    #1; if (q_latch !== 1 || q_flop !== 1 || qn_reset !== 0) $fatal(1, "next rising edge");
    d = 0;
    #1; if (q_latch !== 0 || q_flop !== 1) $fatal(1, "open latch follows falling data");
    clk = 0; resetn = 0;
    #1; if (qn_reset !== 1) $fatal(1, "reset without clock");
    resetn = 1; setn = 0;
    #1; if (qn_reset !== 0) $fatal(1, "asynchronous set");
    $display("SEQ_MODELS_PASS");
    $finish;
  end
endmodule
'''
        with tempfile.TemporaryDirectory(prefix="asap7-seq-models-") as temporary:
            path = Path(temporary)
            (path / "tb_seq.sv").write_text(bench)
            command = ["verilator", "--binary", "--timing", "-Wno-fatal", "-j", "2",
                       "--top-module", "tb_seq", "--Mdir", str(path / "build"),
                       str(path / "tb_seq.sv"), str(ROOT / "env/asap7_seq_sim.v")]
            built = subprocess.run(command, capture_output=True, text=True, timeout=60,
                                   env=os.environ | {"OBJCACHE": ""})
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            result = subprocess.run([str(path / "build/Vtb_seq")], capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SEQ_MODELS_PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
