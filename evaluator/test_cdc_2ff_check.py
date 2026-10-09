#!/usr/bin/env python3
"""Regression for the T05 two-stage structural checker."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from evaluator.cdc_2ff_check import inspect


TOY = """
module cdc_toy(input logic wr_clk, rd_clk, wr_rst_n, rd_rst_n,
               input logic [3:0] wr_value, rd_value,
               output logic [3:0] wr_observed, rd_observed);
  logic [3:0] wr_source, rd_source;
  logic [3:0] wr_first, wr_second, rd_first, rd_second;
  always_ff @(posedge wr_clk or negedge wr_rst_n)
    if (!wr_rst_n) begin
      wr_source <= 0; wr_first <= 0; wr_second <= 0;
    end else begin
      wr_source <= wr_value;
      wr_first <= rd_source;
      wr_second <= {WR_SECOND};
    end
  always_ff @(posedge rd_clk or negedge rd_rst_n)
    if (!rd_rst_n) begin
      rd_source <= 0; rd_first <= 0; rd_second <= 0;
    end else begin
      rd_source <= rd_value;
      rd_first <= wr_source;
      rd_second <= {RD_SECOND};
    end
  assign wr_observed = wr_second;
  assign rd_observed = rd_second;
endmodule
"""


class TwoStageCheckerTest(unittest.TestCase):
    def elaborate(self, good: bool, packed: bool = False,
                  expose_first_stage: bool = False) -> dict:
        source = TOY.replace("{WR_SECOND}", "wr_first" if good else "rd_source")
        source = source.replace("{RD_SECOND}", "rd_first" if good else "wr_source")
        if packed:
            source = source.replace(
                "logic [3:0] wr_first, wr_second, rd_first, rd_second;",
                "logic [7:0] wr_sync, rd_sync;",
            )
            source = source.replace("wr_first <= 0; wr_second <= 0;", "wr_sync <= 0;")
            source = source.replace("rd_first <= 0; rd_second <= 0;", "rd_sync <= 0;")
            source = source.replace(
                "wr_first <= rd_source;\n      wr_second <= wr_first;",
                "wr_sync <= {wr_sync[3:0], rd_source};",
            )
            source = source.replace(
                "rd_first <= wr_source;\n      rd_second <= rd_first;",
                "rd_sync <= {rd_sync[3:0], wr_source};",
            )
            source = source.replace("assign wr_observed = wr_second;",
                                    "assign wr_observed = wr_sync[7:4];")
            source = source.replace("assign rd_observed = rd_second;",
                                    "assign rd_observed = rd_sync[7:4];")
        if expose_first_stage:
            source = source.replace("assign wr_observed = wr_second;",
                                    "assign wr_observed = wr_first;")
        with tempfile.TemporaryDirectory(prefix="ic_bcmk_cdc_test_") as temp:
            rtl = Path(temp) / "toy.sv"
            output = Path(temp) / "toy.json"
            rtl.write_text(source)
            cmd = [
                "yosys", "-Q", "-T", "-p",
                f"read_verilog -sv {rtl}; hierarchy -top cdc_toy; "
                f"proc; flatten; opt_clean; write_json {output}",
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return json.loads(output.read_text())["modules"]["cdc_toy"]

    def test_two_stage_pointer_crossing_passes(self) -> None:
        result = inspect(self.elaborate(True), "wr_clk", "rd_clk", 4)
        self.assertTrue(result["passed"], result["findings"])
        self.assertEqual(result["verified_chains"]["wr_clk->rd_clk"], 4)
        self.assertEqual(result["verified_chains"]["rd_clk->wr_clk"], 4)

    def test_yosys_scopeinfo_metadata_is_ignored(self) -> None:
        module = self.elaborate(True)
        module["cells"]["metadata_only"] = {
            "type": "$scopeinfo", "parameters": {}, "attributes": {},
            "port_directions": {}, "connections": {},
        }
        result = inspect(module, "wr_clk", "rd_clk", 4)
        self.assertTrue(result["passed"], result["findings"])

    def test_one_stage_pointer_crossing_fails(self) -> None:
        result = inspect(self.elaborate(False), "wr_clk", "rd_clk", 4)
        self.assertFalse(result["passed"])
        self.assertTrue(any("not isolated" in item for item in result["findings"]))

    def test_packed_shift_register_chain_passes(self) -> None:
        result = inspect(self.elaborate(True, packed=True), "wr_clk", "rd_clk", 4)
        self.assertTrue(result["passed"], result["findings"])

    def test_first_stage_output_fails(self) -> None:
        result = inspect(self.elaborate(True, expose_first_stage=True),
                         "wr_clk", "rd_clk", 4)
        self.assertFalse(result["passed"])

    def test_remote_reset_on_synchronizer_fails(self) -> None:
        module = self.elaborate(True)
        wr_reset = module["ports"]["wr_rst_n"]["bits"]
        rd_reset = module["ports"]["rd_rst_n"]["bits"]
        for cell in module["cells"].values():
            if cell["type"] == "$adff" and cell["connections"]["CLK"] == module["ports"]["wr_clk"]["bits"]:
                if cell["connections"]["ARST"] == wr_reset:
                    cell["connections"]["ARST"] = rd_reset
        result = inspect(module, "wr_clk", "rd_clk", 4)
        self.assertFalse(result["passed"])
        self.assertTrue(any("synchronizer reset" in item for item in result["findings"]))


if __name__ == "__main__":
    unittest.main()
