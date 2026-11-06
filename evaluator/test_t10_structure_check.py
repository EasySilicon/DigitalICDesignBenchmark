"""Name-independent positive and defect tests for the automatic PE checker."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from t10_structure_check import (_cone, _control_cone, _operand_origins, _registered_d_cone,
                                 _registered_forward_d_cone,
                                 _reachable_instances,
                                 _shell_registered_meshes, inspect)


FIXTURE = Path(__file__).parent / "fixtures/t10_mesh_good"


class MeshStructureCheckTest(unittest.TestCase):
    @staticmethod
    def _packet_fixture(positions, defect=None):
        width = 83
        payload = {position: index for index, position in enumerate(positions)}
        metadata = {position: index for index, position in enumerate(
            i for i in range(width) if i not in payload)}
        def unpack(port):
            bits = [f"{port}[{i}]" for i in reversed(positions)]
            if defect == "missing_accumulator_bit" and port == "left_data":
                bits[-1] = "1'b0"
            return "{" + ",".join(bits) + "}"
        pe = f'''module mesh_cell (
 input wire clk, rst_n,
 input wire [{width-1}:0] left_data, top_data,
 output reg [{width-1}:0] right_data, bottom_data,
 output reg [63:0] local_sum);
 wire [63:0] x = {unpack('left_data')};
 wire [63:0] y = {unpack('top_data')};
 always @(posedge clk or negedge rst_n)
  if (!rst_n) begin right_data <= 0; bottom_data <= 0; local_sum <= 0; end
  else begin right_data <= left_data; bottom_data <= top_data;
   local_sum <= local_sum + x*y; end
endmodule
'''
        if defect == "unregistered_forward":
            pe = pe.replace("right_data <= 0;", "").replace("right_data <= left_data;", "")
            pe = pe.replace("endmodule", "always @* right_data = left_data;\nendmodule")
        if defect == "metadata_gated_forward":
            control = min(metadata)
            pe = pe.replace("right_data <=", "forward_q <=")
            pe = pe.replace("endmodule", f'''reg [{width-1}:0] forward_q;
 always @* right_data = left_data[{control}] ? forward_q : 0;
endmodule''')
        if defect == "shell_registers":
            for output, source in (("right_data", "left_data"), ("bottom_data", "top_data")):
                pe = pe.replace(f"{output} <= 0;", "").replace(f"{output} <= {source};", "")
                pe = pe.replace("endmodule", f"always @* {output} = {source};\nendmodule")
        top = "module npu_systolic_matmul_16x16" + (FIXTURE / "rtl/mesh.sv").read_text().split(
            "module npu_systolic_matmul_16x16", 1)[1]
        for name in ("a_link", "b_link", "a_in, b_in"):
            top = top.replace("wire [63:0] " + name, f"wire [{width-1}:0] " + name)
        def inject(axis, row, neighbor=False):
            fields = []
            for position in reversed(range(width)):
                if position in payload:
                    bit = payload[position]
                    if defect == "missing_injection_bit" and axis == "a" and bit == 0:
                        value = "1'b0"
                    else:
                        if defect == "duplicate_injection_bit" and axis == "a" and bit == 0:
                            bit = 1
                        index = "0" if defect == "duplicate_row" and axis == "a" else row
                        source = "a" if defect == "same_operand_axes" else axis
                        value = f"{source}_data[{index}*64+{bit}]"
                    if neighbor:
                        index = "r][c-1" if axis == "a" else "r-1][c"
                        value = f"{axis}_link[{index}][{position}]"
                else:
                    bit = metadata[position]
                    value = f"mode[{bit}]" if bit < 4 else f"in_block_id[{bit-4}]"
                    if defect == "metadata_gated_forward" and bit == 0:
                        value = "in_valid"
                fields.append(value)
            return "{" + ",".join(fields) + "}"
        for axis, condition, row in (("a", "c", "r"), ("b", "r", "c")):
            old = f"if ({condition} == 0) assign {axis}_in = {axis}_data[{row}*64 +: 64];"
            new = f'''if ({condition} == 0) begin
 reg [{width-1}:0] skew;
 always @(posedge clk or negedge rst_n)
  if (!rst_n) skew <= 0;
  else if (in_valid) skew <= {inject(axis, row)};
 assign {axis}_in = skew;
 end'''
            assert old in top
            top = top.replace(old, new)
            if defect == "metadata_shortcut":
                neighbor = "a_link[r][c-1]" if axis == "a" else "b_link[r-1][c]"
                top = top.replace(f"assign {axis}_in = {neighbor};",
                                  f"assign {axis}_in = {inject(axis, row, neighbor=True)};")
        if defect == "shell_registers":
            top = top.replace("mesh_cell cell_i (", f'''wire [{width-1}:0] forwarded_a, forwarded_b;
 reg [{width-1}:0] shell_a, shell_b;
 always @(posedge clk or negedge rst_n)
  if (!rst_n) begin shell_a <= 0; shell_b <= 0; end
  else begin shell_a <= forwarded_a; shell_b <= forwarded_b; end
 assign a_link[r][c] = shell_a;
 assign b_link[r][c] = shell_b;
 mesh_cell cell_i (''')
            top = top.replace(".right_data(a_link[r][c])", ".right_data(forwarded_a)")
            top = top.replace(".bottom_data(b_link[r][c])", ".bottom_data(forwarded_b)")
        return pe + top

    def _check_packet(self, positions, defect=None):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / "rtl").mkdir()
            (root / "rtl/files.f").write_text("mesh.sv\n")
            (root / "rtl/mesh.sv").write_text(self._packet_fixture(positions, defect))
            return inspect(root)

    def test_packed_payload_offset_and_interleaving_are_inferred(self):
        for positions in (list(range(64)), list(range(11, 75)),
                          [i + i // 4 for i in range(64)]):
            with self.subTest(positions=positions):
                result = self._check_packet(positions)
                self.assertTrue(result["passed"], result)
                self.assertEqual(set(result["packed_operand_sources"].values()), {"a_data", "b_data"})
                self.assertTrue(all(p == positions for p in result["operand_payload_positions"].values()))

    def test_packet_metadata_cannot_replace_missing_or_duplicated_operand_bits(self):
        for defect in ("missing_injection_bit", "duplicate_injection_bit",
                       "duplicate_row", "same_operand_axes"):
            with self.subTest(defect=defect):
                result = self._check_packet(list(range(11, 75)), defect)
                self.assertFalse(result["passed"], result)
                self.assertIn("operand", result["reason"])

    def test_packed_operand_links_may_be_registered_in_tile_shell(self):
        result = self._check_packet(list(range(11, 75)), "shell_registers")
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["link_register_placement"], "tile_shell")

    def test_packet_metadata_need_not_follow_registered_operand_mesh(self):
        result = self._check_packet(list(range(11, 75)), "metadata_shortcut")
        self.assertTrue(result["passed"], result)

    def test_packet_metadata_may_gate_an_already_registered_operand(self):
        result = self._check_packet(list(range(11, 75)), "metadata_gated_forward")
        self.assertTrue(result["passed"], result)

    def test_packed_forwarding_still_requires_a_register(self):
        result = self._check_packet(list(range(64)), "unregistered_forward")
        self.assertFalse(result["passed"], result)
        self.assertIn("not registered", result["reason"])

    def test_every_packed_operand_bit_must_reach_accumulator(self):
        result = self._check_packet(list(range(64)), "missing_accumulator_bit")
        self.assertFalse(result["passed"], result)
        self.assertIn("does not feed local accumulator", result["reason"])

    def test_operand_provenance_reaches_fixed_point_through_feedback(self):
        module = {"ports": {"a_data": {"bits": [1]}, "b_data": {"bits": [2]}},
                  "cells": {
                      "hold": {"type": "$mux", "connections": {
                          "A": [10], "B": [1], "S": [99], "Y": [11]},
                          "port_directions": {"A": "input", "B": "input", "S": "input", "Y": "output"}},
                      "ff": {"type": "$dff", "connections": {"D": [11], "Q": [10]},
                             "port_directions": {"D": "input", "Q": "output"}},
                      "next": {"type": "$dff", "connections": {"D": [10], "Q": [12]},
                               "port_directions": {"D": "input", "Q": "output"}}}}
        self.assertEqual(_operand_origins(module, [10, 12]), {10: 1, 12: 1})

    def test_arithmetic_is_not_mistaken_for_independent_packet_wiring(self):
        module = {"ports": {"a_data": {"bits": [1]}, "b_data": {"bits": [2]}},
                  "cells": {"add": {"type": "$add", "connections": {
                      "A": [1], "B": [2], "Y": [10, 11]},
                      "port_directions": {"A": "input", "B": "input", "Y": "output"}}}}
        self.assertEqual(_operand_origins(module, [10, 11]), {10: 3, 11: 3})

    def test_shared_register_controls_are_traced_once(self) -> None:
        module = {"cells": {
            "reset_gate": {
                "type": "$not", "connections": {"A": [2], "Y": [3]},
                "port_directions": {"A": "input", "Y": "output"}},
            **{f"ff_{i}": {"type": "$adff", "connections": {
                "CLK": [1], "ARST": [3], "D": [10 + i], "Q": [1000 + i]}}
               for i in range(100)},
            "sync_ff": {"type": "$sdff", "connections": {
                "CLK": [1], "SRST": [4], "D": [5], "Q": [6]}},
        }}
        expected = set().union(*(
            _cone(module, cell["connections"][pin])
            for cell in module["cells"].values() if cell["type"] in {"$adff", "$sdff"}
            for pin in ("CLK", "ARST", "SRST") if pin in cell["connections"]))
        with patch("t10_structure_check._cone", wraps=_cone) as trace:
            self.assertEqual(_control_cone(module), expected)
        self.assertEqual(expected, {1, 2, 3, 4})
        self.assertEqual(trace.call_count, 3)
        self.assertEqual(_control_cone({"cells": {}}), set())

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

    def test_shell_register_bus_may_share_a_cell_with_control_bits(self) -> None:
        module, connections = self._shell_mesh_fixture()
        for index, cell in enumerate(module["cells"].values()):
            cell["connections"]["D"] = ["0"] * 8 + cell["connections"]["D"]
            cell["connections"]["Q"] = list(range(900000 + index * 8,
                                                  900008 + index * 8)) + cell["connections"]["Q"]
        self.assertEqual(len(_shell_registered_meshes(
            module, connections, ["left", "top"])), 2)

    def test_shell_links_through_retained_identity_output_ports(self) -> None:
        module, connections = self._shell_mesh_fixture()
        for cell in module["cells"].values():
            cell["connections"]["D"] = [bit + 400000 for bit in cell["connections"]["D"]]
        for conn in connections:
            conn["left_out"] = [bit + 400000 for bit in conn["left"]]
            conn["top_out"] = [bit + 400000 for bit in conn["top"]]
        pe = {"ports": {
            "left": {"direction": "input", "bits": list(range(64))},
            "left_out": {"direction": "output", "bits": list(range(64))},
            "top": {"direction": "input", "bits": list(range(64, 128))},
            "top_out": {"direction": "output", "bits": list(range(64, 128))},
        }}
        self.assertEqual(len(_shell_registered_meshes(
            module, connections, ["left", "top"], pe)), 2)
        pe["ports"]["left_out"]["bits"].reverse()
        self.assertEqual([name for name, _ in _shell_registered_meshes(
            module, connections, ["left", "top"], pe)], ["top"])

    def test_shell_register_bus_may_be_split_between_cells(self) -> None:
        module, connections = self._shell_mesh_fixture()
        cells = {}
        for name, cell in module["cells"].items():
            for part in range(2):
                cells[f"{name}_{part}"] = {"type": "$dff", "connections": {
                    pin: bits[part * 32:(part + 1) * 32]
                    for pin, bits in cell["connections"].items()}}
        module["cells"] = cells
        self.assertEqual(len(_shell_registered_meshes(
            module, connections, ["left", "top"])), 2)

    def test_shell_register_partial_or_permuted_bus_is_rejected(self) -> None:
        for defect in ("missing", "swapped", "duplicate_driver", "two_stages"):
            with self.subTest(defect=defect):
                module, connections = self._shell_mesh_fixture()
                cell = module["cells"]["left_17_18"]
                if defect == "missing":
                    cell["connections"]["D"] = cell["connections"]["D"][:-1]
                elif defect == "swapped":
                    cell["connections"]["D"] = list(reversed(cell["connections"]["D"]))
                elif defect == "duplicate_driver":
                    module["cells"]["extra"] = cell
                else:
                    old_d = cell["connections"]["D"]
                    intermediate = list(range(900000, 900064))
                    cell["connections"]["D"] = intermediate
                    module["cells"]["extra"] = {"type": "$dff", "connections": {
                        "D": old_d, "Q": intermediate}}
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

    def test_slang_async_load_register_is_accepted_as_a_forward_stage(self) -> None:
        pe = {"cells": {
            "forward_ff": {"type": "$aldff",
                           "connections": {"D": [1], "Q": [2]},
                           "port_directions": {"D": "input", "Q": "output"}},
        }}
        self.assertIn(1, _registered_forward_d_cone(pe, [2], {1}))

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
