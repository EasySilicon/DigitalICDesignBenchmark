"""Name-independent positive and defect tests for the automatic PE checker."""

import tempfile
import unittest
from pathlib import Path

from t10_structure_check import (_cone, _registered_d_cone,
                                 _registered_forward_d_cone,
                                 _reachable_instances,
                                 _shell_registered_meshes, inspect)


FIXTURE = Path(__file__).parent / "fixtures/t10_mesh_good"


class MeshStructureCheckTest(unittest.TestCase):
    @staticmethod
    def _shell_mesh_fixture(drop_edge: tuple[str, int, int] | None = None):
        connections = []
        for row in range(16):
            for col in range(16):
                index = row * 16 + col
                connections.append({
                    "left": list(range(100000 + index * 64,
                                       100000 + (index + 1) * 64)),
                    "top": list(range(200000 + index * 64,
                                      200000 + (index + 1) * 64)),
                })
        cells = {}
        for row in range(16):
            for col in range(15):
                source = row * 16 + col
                receiver = source + 1
                if drop_edge != ("left", source, receiver):
                    cells[f"left_{source}_{receiver}"] = {
                        "type": "$dff",
                        "connections": {"D": connections[source]["left"],
                                        "Q": connections[receiver]["left"]},
                    }
        for row in range(15):
            for col in range(16):
                source = row * 16 + col
                receiver = source + 16
                if drop_edge != ("top", source, receiver):
                    cells[f"top_{source}_{receiver}"] = {
                        "type": "$dff",
                        "connections": {"D": connections[source]["top"],
                                        "Q": connections[receiver]["top"]},
                    }
        return {"cells": cells}, connections

    def test_shell_registered_orthogonal_mesh_is_accepted(self) -> None:
        module, connections = self._shell_mesh_fixture()
        meshes = _shell_registered_meshes(module, connections, ["left", "top"])
        self.assertEqual([name for name, _ in meshes], ["left", "top"])
        self.assertTrue(all(len(paths) == 16 for _, paths in meshes))

    def test_shell_registered_mesh_with_missing_edge_is_rejected(self) -> None:
        module, connections = self._shell_mesh_fixture(("left", 17, 18))
        meshes = _shell_registered_meshes(module, connections, ["left", "top"])
        self.assertEqual([name for name, _ in meshes], ["top"])

    def test_complemented_registered_forward_is_accepted(self) -> None:
        pe = {"cells": {
            "input_invert": {"type": "$not",
                             "connections": {"A": [1], "Y": [2]},
                             "port_directions": {"A": "input", "Y": "output"}},
            "forward_ff": {"type": "$adff",
                           "connections": {"D": [2], "Q": [3]},
                           "port_directions": {"D": "input", "Q": "output"}},
            "output_invert": {"type": "$not",
                              "connections": {"A": [3], "Y": [4]},
                              "port_directions": {"A": "input", "Y": "output"}},
        }}
        self.assertIn(1, _registered_forward_d_cone(pe, [4], {1}))

    def test_registered_forward_with_input_bypass_is_rejected(self) -> None:
        pe = {"cells": {
            "forward_ff": {"type": "$dff",
                           "connections": {"D": [1], "Q": [2]},
                           "port_directions": {"D": "input", "Q": "output"}},
            "bypass": {"type": "$xor",
                       "connections": {"A": [2], "B": [1], "Y": [3]},
                       "port_directions": {"A": "input", "B": "input",
                                           "Y": "output"}},
        }}
        self.assertIsNone(_registered_forward_d_cone(pe, [3], {1}))

    def test_retained_child_result_must_be_registered(self) -> None:
        child = {"ports": {"din": {"direction": "input", "bits": [1]},
                           "dout": {"direction": "output", "bits": [2]}},
                 "cells": {"reg": {"type": "$dff",
                                   "connections": {"D": [1], "Q": [2]},
                                   "port_directions": {"D": "input", "Q": "output"}}}}
        pe = {"cells": {"result_stage": {
            "type": "postprocess", "connections": {"din": [101], "dout": [102]},
            "port_directions": {"din": "input", "dout": "output"}}}}
        self.assertIsNotNone(_registered_d_cone(pe, [102], {"postprocess": child}))
        child["cells"] = {"comb": {"type": "$not",
                                   "connections": {"A": [1], "Y": [2]},
                                   "port_directions": {"A": "input", "Y": "output"}}}
        self.assertIsNone(_registered_d_cone(pe, [102], {"postprocess": child}))

    def test_nested_registered_bank_is_traced_to_its_input(self) -> None:
        bank = {"ports": {"din": {"direction": "input", "bits": [1]},
                          "dout": {"direction": "output", "bits": [2]}},
                "cells": {"reg": {"type": "$dff",
                                  "connections": {"D": [1], "Q": [2]},
                                  "port_directions": {"D": "input", "Q": "output"}}}}
        top = {"cells": {"bank": {"type": "row_bank",
                                   "connections": {"din": [101], "dout": [102]},
                                   "port_directions": {"din": "input",
                                                       "dout": "output"}}}}
        self.assertNotIn(101, _cone(top, [102], include_registers=True))
        self.assertIn(101, _cone(top, [102], include_registers=True,
                                 modules={"row_bank": bank}))

    def test_renamed_pe_module_and_ports_pass(self) -> None:
        result = inspect(FIXTURE)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["pe_instances"], 256)

    def test_keep_hierarchy_wrapper_is_flattened_around_pe(self) -> None:
        source = (FIXTURE / "rtl/mesh.sv").read_text()
        source = source.replace(
            "module npu_systolic_matmul_16x16 (",
            '(* keep_hierarchy = "yes" *) module mesh_wrapper (', 1)
        source += r'''

module npu_systolic_matmul_16x16 (
    input  wire          clk,
    input  wire          rst_n,
    input  wire          in_valid,
    output wire          in_ready,
    input  wire          in_start,
    input  wire [15:0]   in_block_id,
    input  wire [3:0]    mode,
    input  wire [255:0]  a_scale,
    input  wire [255:0]  b_scale,
    input  wire [1023:0] a_data,
    input  wire [1023:0] b_data,
    input  wire          out_ready,
    output wire [3:0]    out_valid,
    output wire [63:0]   out_block_id,
    output wire [15:0]   out_row,
    output wire [4095:0] out_data
);
    (* keep_hierarchy = "yes" *) mesh_wrapper wrapper (
        .clk(clk), .rst_n(rst_n), .in_valid(in_valid), .in_ready(in_ready),
        .in_start(in_start), .in_block_id(in_block_id), .mode(mode),
        .a_scale(a_scale), .b_scale(b_scale), .a_data(a_data), .b_data(b_data),
        .out_ready(out_ready), .out_valid(out_valid),
        .out_block_id(out_block_id), .out_row(out_row), .out_data(out_data)
    );
endmodule
'''
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "rtl").mkdir()
            (root / "rtl/files.f").write_text("mesh.sv\n")
            (root / "rtl/mesh.sv").write_text(source)
            result = inspect(root)
        self.assertTrue(result["passed"], result)
        self.assertTrue(result["flattened_from_hierarchy"])
        self.assertEqual(result["pe_module"], "mesh_cell")
        self.assertEqual(result["pe_instances"], 256)

    def test_reachable_instance_count_uses_nested_multiplicity(self) -> None:
        modules = {
            "top": {"cells": {f"tile_{i}": {"type": "tile"}
                                for i in range(16)}},
            "tile": {"cells": {f"pe_{i}": {"type": "pe"}
                                 for i in range(16)}},
            "pe": {"cells": {}},
        }
        self.assertEqual(_reachable_instances(modules, "top", "pe"), 256)

    def test_broken_neighbor_is_rejected(self) -> None:
        self._reject_mutation("assign a_in = a_link[r][c-1];",
                              "assign a_in = a_data[r*64 +: 64];")

    def test_unregistered_forward_is_rejected(self) -> None:
        self._reject_mutation("right_data  <= left_data;",
                              "right_data  <= 64'b0;")

    def test_missing_local_feedback_is_rejected(self) -> None:
        self._reject_mutation("local_sum   <= local_sum + left_data * top_data;",
                              "local_sum   <= left_data * top_data;")

    def test_registered_output_after_local_accumulator_is_accepted(self) -> None:
        source = (FIXTURE / "rtl/mesh.sv").read_text()
        source = source.replace(
            "    output reg  [63:0] local_sum\n);",
            "    output reg  [63:0] local_sum\n);\n    reg [63:0] local_accum;", 1)
        source = source.replace(
            "            local_sum   <= 64'b0;",
            "            local_accum <= 64'b0;\n            local_sum <= 64'b0;", 1)
        source = source.replace(
            "            local_sum   <= local_sum + left_data * top_data;",
            "            local_accum <= local_accum + left_data * top_data;\n"
            "            local_sum <= local_accum;", 1)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "rtl").mkdir()
            (root / "rtl/files.f").write_text("mesh.sv\n")
            (root / "rtl/mesh.sv").write_text(source)
            result = inspect(root)
        self.assertTrue(result["passed"], result)

    def test_result_bit_compression_keeps_pe_contribution(self) -> None:
        source = (FIXTURE / "rtl/mesh.sv").read_text()
        old = "out_data[s*1024+c*64 +: 64] = sums[in_block_id[3:0]][c];"
        new = ("out_data[s*1024+c*64 +: 64] = "
               "{{26{sums[in_block_id[3:0]][c][63]}},"
               "sums[in_block_id[3:0]][c][37:0]};")
        self.assertIn(old, source)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "rtl").mkdir()
            (root / "rtl/files.f").write_text("mesh.sv\n")
            (root / "rtl/mesh.sv").write_text(source.replace(old, new, 1))
            result = inspect(root)
        self.assertTrue(result["passed"], result)

    def test_disconnected_pe_results_are_rejected(self) -> None:
        self._reject_mutation(
            "out_data[s*1024+c*64 +: 64] = sums[in_block_id[3:0]][c];",
            "out_data[s*1024+c*64 +: 64] = 64'b0;")

    def _reject_mutation(self, old: str, new: str) -> None:
        source = (FIXTURE / "rtl/mesh.sv").read_text()
        self.assertIn(old, source)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "rtl").mkdir()
            (root / "rtl/files.f").write_text("mesh.sv\n")
            (root / "rtl/mesh.sv").write_text(source.replace(old, new, 1))
            result = inspect(root)
        self.assertFalse(result["passed"], result)


if __name__ == "__main__":
    unittest.main()
