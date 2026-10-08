#!/usr/bin/env python3
"""Automatic T10 PE mesh check on a Yosys elaborated netlist."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections import Counter, defaultdict, deque
from pathlib import Path

from public_check import sources_from_filelist

TOP = "npu_systolic_matmul_16x16"
FLOP_TYPES = {"$dff", "$adff", "$sdff", "$dffe", "$adffe", "$sdffe"}
# The original controller/result-storage allowance is 262144 bits.  A shell
# registered 16x16 mesh needs exactly 240 horizontal and 240 vertical links,
# each carrying one 64-bit operand and one 28-bit token.
MAX_NON_PE_STATE_BITS = 262144 + 2 * 240 * (64 + 28)
STREAM_PORTS = {
    "clk": ("input", 1), "rst_n": ("input", 1),
    "in_valid": ("input", 1), "in_ready": ("output", 1),
    "in_start": ("input", 1), "in_block_id": ("input", 16),
    "mode": ("input", 4), "a_scale": ("input", 256),
    "b_scale": ("input", 256), "a_data": ("input", 1024),
    "b_data": ("input", 1024), "out_ready": ("input", 1),
    "out_valid": ("output", 4), "out_block_id": ("output", 64),
    "out_row": ("output", 16), "out_data": ("output", 4096),
}


def _paths(edges: dict[int, int], size: int = 256) -> list[list[int]] | None:
    if len(edges) != 240 or len(set(edges.values())) != 240:
        return None
    starts = set(range(size)) - set(edges.values())
    if len(starts) != 16:
        return None
    paths = []
    seen = set()
    for start in sorted(starts):
        path = []
        node = start
        while node not in seen:
            seen.add(node)
            path.append(node)
            if node not in edges:
                break
            node = edges[node]
        if len(path) != 16 or node in edges:
            return None
        paths.append(path)
    return paths if len(seen) == size else None


def _shell_registered_meshes(module: dict, connections: list[dict],
                              input_ports: list[str]) -> list[tuple[str, list[list[int]]]]:
    """Find PE-input chains advanced by one register in the enclosing mesh.

    A physical implementation may keep the wavefront register in the tile
    shell instead of inside the PE macro.  In that form each edge has the
    current PE input on a flop D pin and the adjacent PE input on its Q pin.
    Requiring exact vector equality on both sides rejects combinational
    forwarding, partial buses, fanout trees, and skipped PE stages.
    """
    flops = [cell for cell in module["cells"].values()
             if cell["type"] in FLOP_TYPES]
    meshes = []
    for input_port in input_ports:
        receivers = {tuple(conn[input_port]): index
                     for index, conn in enumerate(connections)}
        sources = {tuple(conn[input_port]): index
                   for index, conn in enumerate(connections)}
        edges = {}
        for flop in flops:
            d_bits = tuple(flop["connections"].get("D", ()))
            q_bits = tuple(flop["connections"].get("Q", ()))
            source = sources.get(d_bits)
            receiver = receivers.get(q_bits)
            if source is not None and receiver is not None and source != receiver:
                if source in edges and edges[source] != receiver:
                    edges[source] = -1
                else:
                    edges[source] = receiver
        edges = {source: receiver for source, receiver in edges.items()
                 if receiver >= 0}
        paths = _paths(edges)
        if paths is not None:
            meshes.append((input_port, paths))
    return meshes


def _cone(module: dict, target: list[int],
          include_registers: bool = False,
          modules: dict | None = None) -> set[int]:
    """Trace dependencies, including registered result memories, backward."""
    driver: dict[int, tuple[dict, str]] = {}
    memory_writes: dict[str, list[dict]] = defaultdict(list)
    for cell in module["cells"].values():
        if cell["type"] in {"$memwr", "$memwr_v2"}:
            memory_writes[cell["parameters"]["MEMID"]].append(cell)
        if (cell["type"] in FLOP_TYPES and not include_registers) or \
                (not cell["type"].startswith("$") and
                 (modules is None or cell["type"] not in modules)):
            continue
        for port, direction in cell["port_directions"].items():
            if direction == "output":
                for bit in cell["connections"][port]:
                    if isinstance(bit, int):
                        driver[bit] = (cell, port)
    visited_bits = set(target)
    visited_cells = set()
    todo = deque(target)
    while todo:
        bit = todo.popleft()
        driven = driver.get(bit)
        if driven is None or (id(driven[0]), driven[1]) in visited_cells:
            continue
        cell, driven_port = driven
        visited_cells.add((id(cell), driven_port))
        if modules is not None and cell["type"] in modules:
            child = modules[cell["type"]]
            child_cone = _cone(child, child["ports"][driven_port]["bits"],
                               include_registers=include_registers,
                               modules=modules)
            for port, description in child["ports"].items():
                if description["direction"] != "input" or not \
                        set(description["bits"]) & child_cone:
                    continue
                for source in cell["connections"][port]:
                    if isinstance(source, int) and source not in visited_bits:
                        visited_bits.add(source)
                        todo.append(source)
            continue
        if cell["type"] in {"$memrd", "$memrd_v2"}:
            for write in memory_writes.get(cell["parameters"]["MEMID"], []):
                for source in write["connections"]["DATA"]:
                    if isinstance(source, int) and source not in visited_bits:
                        visited_bits.add(source)
                        todo.append(source)
        for port, direction in cell["port_directions"].items():
            if direction == "input":
                for source in cell["connections"][port]:
                    if isinstance(source, int) and source not in visited_bits:
                        visited_bits.add(source)
                        todo.append(source)
    return visited_bits


def _registered_port(module: dict, bits: list[int]) -> dict | None:
    for cell in module["cells"].values():
        if cell["type"] in FLOP_TYPES and cell["connections"].get("Q") == bits:
            return cell
    return None


def _registered_forward_d_cone(module: dict, output_bits: list[int],
                               input_bits: set[int]) -> set[int] | None:
    """Trace a registered PE link through stateless output logic.

    A complementary state encoding may put a NOT after the generic FF even
    though the mapped technology FF drives the output from QN directly.
    Require every output bit to depend on FF state, and reject any direct
    combinational path from a PE data input to the link output.
    """
    flops = [cell for cell in module["cells"].values()
             if cell["type"] in FLOP_TYPES]
    selected: dict[int, dict] = {}
    for bit in output_bits:
        upstream = _cone(module, [bit])
        if input_bits & upstream:
            return None
        driving_flops = [cell for cell in flops
                         if set(cell["connections"]["Q"]) & upstream]
        if not driving_flops:
            return None
        for cell in driving_flops:
            selected[id(cell)] = cell
    sources = set()
    for cell in selected.values():
        sources.update(_cone(module, cell["connections"]["D"]))
    return sources


def _registered_d_cone(module: dict, bits: list[int], modules: dict,
                       visited: set[str] | None = None) -> set[int] | None:
    """Return the output register's D cone in the current module's bit space."""
    flop = _registered_port(module, bits)
    if flop is not None:
        return _cone(module, flop["connections"]["D"],
                     include_registers=True, modules=modules)
    visited = set() if visited is None else visited
    for cell in module["cells"].values():
        kind = cell["type"]
        if kind not in modules or kind in visited:
            continue
        child = modules[kind]
        for port, direction in cell["port_directions"].items():
            if direction != "output" or cell["connections"][port] != bits:
                continue
            child_bits = child["ports"][port]["bits"]
            child_cone = _registered_d_cone(child, child_bits,
                                            modules, visited | {kind})
            if child_cone is None:
                continue
            sources = []
            # A held output register feeds its own D mux. Preserve that
            # feedback when translating the child cone into parent bits.
            if set(child_bits) & child_cone:
                sources.extend(bits)
            for input_port, description in child["ports"].items():
                if description["direction"] == "input" and \
                        set(description["bits"]) & child_cone:
                    sources.extend(cell["connections"][input_port])
            return _cone(module, sources, include_registers=True,
                         modules=modules)
    return None


def _feedback_on_result_path(module: dict, bits: list[int], modules: dict,
                             visited: set[str] | None = None) -> bool:
    """Find a result-path register whose own Q contributes to its next D."""
    upstream = _cone(module, bits, include_registers=True)
    for cell in module["cells"].values():
        if cell["type"] in FLOP_TYPES:
            q = set(cell["connections"]["Q"])
            if q & upstream and q & _cone(module, cell["connections"]["D"],
                                           modules=modules):
                return True
    visited = set() if visited is None else visited
    for cell in module["cells"].values():
        kind = cell["type"]
        if kind not in modules or kind in visited:
            continue
        child = modules[kind]
        for port, direction in cell["port_directions"].items():
            if direction == "output" and set(cell["connections"][port]) & upstream:
                if _feedback_on_result_path(child, child["ports"][port]["bits"],
                                            modules, visited | {kind}):
                    return True
    return False


def _local_state_bits(module: dict) -> int:
    flop_bits = sum(len(cell["connections"]["Q"])
                    for cell in module["cells"].values()
                    if cell["type"] in FLOP_TYPES)
    declared_memories = sum(memory["width"] * memory["size"]
                            for memory in module.get("memories", {}).values())
    collected_memories = 0
    for cell in module["cells"].values():
        if cell["type"] == "$mem_v2":
            params = cell["parameters"]
            collected_memories += int(params["WIDTH"], 2) * int(params["SIZE"], 2)
    return flop_bits + max(declared_memories, collected_memories)


def _non_pe_state_bits(modules: dict, module_name: str, pe_kind: str) -> int:
    module = modules[module_name]
    state = _local_state_bits(module)
    for cell in module["cells"].values():
        if cell["type"] in modules and cell["type"] != pe_kind:
            state += _non_pe_state_bits(modules, cell["type"], pe_kind)
    return state


def inspect_netlist(design: dict) -> dict:
    modules = design["modules"]
    top = modules[TOP]
    reasons = []
    for name, (direction, width) in STREAM_PORTS.items():
        port = top["ports"].get(name)
        if port is None or port["direction"] != direction or len(port["bits"]) != width:
            reasons.append(f"stream port {name} must be {direction}[{width}]")
    if reasons:
        return {"passed": False, "reason": "; ".join(reasons),
                "status": "failed", "method": "yosys_netlist"}
    candidates = []
    for kind in {cell["type"] for cell in top["cells"].values()}:
        instances = [(name, cell) for name, cell in top["cells"].items()
                     if cell["type"] == kind]
        if len(instances) != 256 or kind not in modules:
            continue
        pe = modules[kind]
        ins = [port for port, data in pe["ports"].items()
               if data["direction"] == "input" and len(data["bits"]) == 64]
        outs = [port for port, data in pe["ports"].items()
                if data["direction"] == "output" and len(data["bits"]) == 64]
        if len(ins) >= 2 and len(outs) >= 3:
            candidates.append((kind, instances, pe, ins, outs))
    if len(candidates) != 1:
        return {"passed": False, "reason": "expected one 256-instance PE module type",
                "candidate_types": [row[0] for row in candidates]}
    kind, instances, pe, ins, outs = candidates[0]
    connections = [cell["connections"] for _, cell in instances]
    pe_input_bits = {bit for port in pe["ports"].values()
                     if port["direction"] == "input"
                     for bit in port["bits"] if isinstance(bit, int)}
    control_bits = set()
    for cell in pe["cells"].values():
        if cell["type"] not in FLOP_TYPES:
            continue
        for pin in ("CLK", "ARST", "SRST"):
            if pin in cell["connections"]:
                control_bits.update(_cone(pe, cell["connections"][pin]))
    pe_data_inputs = pe_input_bits - control_bits
    meshes = []
    for output_port in outs:
        for input_port in ins:
            receivers = {tuple(conn[input_port]): index
                         for index, conn in enumerate(connections)}
            edges = {index: receivers[tuple(conn[output_port])]
                     for index, conn in enumerate(connections)
                     if tuple(conn[output_port]) in receivers and
                     receivers[tuple(conn[output_port])] != index}
            paths = _paths(edges)
            if paths is not None:
                meshes.append((output_port, input_port, paths))
    matching = []
    for i, first in enumerate(meshes):
        for second in meshes[i + 1:]:
            if first[0] == second[0] or first[1] == second[1]:
                continue
            if all(len(set(a) & set(b)) == 1
                   for a in first[2] for b in second[2]):
                matching.append((first, second))
    link_placement = "pe_output"
    if len(matching) == 1:
        first, second = matching[0]
    else:
        shell_meshes = _shell_registered_meshes(top, connections, ins)
        shell_matching = []
        for i, first_shell in enumerate(shell_meshes):
            for second_shell in shell_meshes[i + 1:]:
                if all(len(set(a) & set(b)) == 1
                       for a in first_shell[1] for b in second_shell[1]):
                    shell_matching.append((first_shell, second_shell))
        if len(shell_matching) != 1:
            return {"passed": False,
                    "reason": "two orthogonal 16x16 registered PE links absent",
                    "pe_module": kind, "mesh_candidates": len(meshes),
                    "shell_mesh_candidates": len(shell_meshes)}
        shell_first, shell_second = shell_matching[0]
        paired = []
        used_outputs = set()
        for input_port, paths in (shell_first, shell_second):
            output_candidates = []
            for output_port in outs:
                sources = _cone(pe, pe["ports"][output_port]["bits"])
                data_sources = sources & pe_data_inputs
                registered_sources = _registered_forward_d_cone(
                    pe, pe["ports"][output_port]["bits"], pe_data_inputs)
                input_set = set(pe["ports"][input_port]["bits"])
                if data_sources == input_set or \
                        (registered_sources is not None and
                         input_set.issubset(registered_sources)):
                    output_candidates.append(output_port)
            if len(output_candidates) != 1 or output_candidates[0] in used_outputs:
                return {"passed": False,
                        "reason": f"PE forwarding output for {input_port} is ambiguous",
                        "pe_module": kind,
                        "forward_output_candidates": output_candidates}
            used_outputs.add(output_candidates[0])
            paired.append((output_candidates[0], input_port, paths))
        first, second = paired
        link_placement = "tile_shell"
    forwarding = (first, second)
    sum_ports = [port for port in outs if port not in (first[0], second[0])]
    if len(sum_ports) != 1:
        reasons.append("expected one local 64-bit accumulator output")
    else:
        sum_port = sum_ports[0]
        sum_bits = pe["ports"][sum_port]["bits"]
        influence = _registered_d_cone(pe, sum_bits, modules)
        if influence is None:
            reasons.append("local accumulator output is not registered")
        else:
            for port in (first[1], second[1]):
                if not set(pe["ports"][port]["bits"]).issubset(influence):
                    reasons.append(f"{port} does not feed local accumulator")
            if not _feedback_on_result_path(pe, sum_bits, modules):
                reasons.append("local accumulator lacks feedback")
            # A submission may place result registers in a reusable bank or
            # store a losslessly compressed result. Trace those modules, but
            # stop at PE output pins. Require a data dependency from every
            # PE; the independent port oracle checks the actual numeric bits.
            storage_modules = {name: body for name, body in modules.items()
                               if name not in (TOP, kind)}
            output_influence = _cone(top, top["ports"]["out_data"]["bits"],
                                     include_registers=True,
                                     modules=storage_modules)
            if any(not (set(conn[sum_port]) & output_influence)
                   for conn in connections):
                reasons.append("at least one PE accumulator does not reach output")
    for output_port, input_port, _ in forwarding:
        if link_placement == "tile_shell":
            sources = _cone(pe, pe["ports"][output_port]["bits"])
            registered_sources = _registered_forward_d_cone(
                pe, pe["ports"][output_port]["bits"], pe_data_inputs)
            input_set = set(pe["ports"][input_port]["bits"])
            if sources & pe_data_inputs != input_set and not \
                    (registered_sources is not None and
                     input_set.issubset(registered_sources)):
                reasons.append(f"{input_port} does not exclusively feed {output_port}")
        else:
            sources = _registered_forward_d_cone(
                pe, pe["ports"][output_port]["bits"], pe_data_inputs)
            if sources is None:
                reasons.append(f"{output_port} forwarding output is not registered")
            elif not set(pe["ports"][input_port]["bits"]).issubset(sources):
                reasons.append(f"{input_port} does not feed {output_port}")
    top_state = _non_pe_state_bits(modules, TOP, kind)
    if top_state > MAX_NON_PE_STATE_BITS:
        reasons.append(
            f"non-PE state exceeds {MAX_NON_PE_STATE_BITS} bits")
    return {"passed": not reasons, "reason": "; ".join(reasons) if reasons else None,
            "pe_module": kind, "pe_instances": 256,
            "mesh_paths": [len(first[2]), len(second[2])],
            "link_register_placement": link_placement,
            "top_state_bits": top_state,
            "checked_links": [(first[0], first[1]), (second[0], second[1])]}


def _pe_interface_candidates(modules: dict) -> list[str]:
    """Return modules with the minimum externally observable PE interface."""
    candidates = []
    for kind, body in modules.items():
        ins = sum(data["direction"] == "input" and len(data["bits"]) == 64
                  for data in body.get("ports", {}).values())
        outs = sum(data["direction"] == "output" and len(data["bits"]) == 64
                   for data in body.get("ports", {}).values())
        if ins >= 2 and outs >= 3:
            candidates.append(kind)
    return sorted(candidates)


def _reachable_instances(modules: dict, parent: str, target: str,
                         active: frozenset[str] = frozenset(),
                         memo: dict[str, int] | None = None) -> int:
    """Count target instances recursively below parent without flattening."""
    if parent in active:
        raise ValueError(f"recursive module hierarchy at {parent}")
    memo = {} if memo is None else memo
    if parent in memo:
        return memo[parent]
    total = 0
    kinds = Counter(cell["type"]
                    for cell in modules[parent].get("cells", {}).values())
    for kind, count in kinds.items():
        if kind == target:
            total += count
        elif kind in modules:
            total += count * _reachable_instances(
                modules, kind, target, active | {parent}, memo)
    memo[parent] = total
    return total


def _yosys_exact_module_selection(name: str) -> str:
    """Build a non-injectable exact module selection for a Yosys script."""
    if re.search(r"[\s;*?\[\]{}]", name):
        raise ValueError(f"unsupported PE module name: {name!r}")
    return f"={name}"


def inspect(submission: Path) -> dict:
    sources = sources_from_filelist(submission)
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_t10_struct_") as temp:
        output = Path(temp) / "elaborated.json"
        prefix = ("read_verilog -sv " + " ".join(map(str, sources)) +
                  f"; hierarchy -top {TOP}; proc; opt_clean")

        def elaborate(script: str) -> tuple[dict | None, str | None]:
            compiled = subprocess.run(["yosys", "-Q", "-T", "-p", script],
                                      capture_output=True, text=True,
                                      timeout=180)
            if compiled.returncode:
                return None, (compiled.stdout + compiled.stderr)[-4000:]
            return json.loads(output.read_text()), None

        design, error = elaborate(f"{prefix}; write_json {output}")
        if design is None:
            return {"passed": False, "status": "failed",
                    "method": "yosys_netlist",
                    "reason": "Yosys elaboration failed",
                    "yosys_log_tail": error}
        result = inspect_netlist(design)
        if not result["passed"] and result.get("reason") == \
                "expected one 256-instance PE module type":
            # A tile/wrapper hierarchy can group PE instances below the top.
            # Candidate-authored keep_hierarchy attributes must not prevent
            # this evaluator-owned structural view from being constructed.
            # Clear them globally, then protect only the candidate PE module.
            modules = design["modules"]
            interface_candidates = _pe_interface_candidates(modules)
            reachable = {}
            for kind in interface_candidates:
                try:
                    reachable[kind] = _reachable_instances(modules, TOP, kind)
                except ValueError as exc:
                    reachable[kind] = str(exc)
            candidates = [kind for kind in interface_candidates
                          if reachable[kind] == 256]
            attempts = {}
            passing = []
            for pe_kind in candidates:
                try:
                    selection = _yosys_exact_module_selection(pe_kind)
                except ValueError as exc:
                    attempts[pe_kind] = {"passed": False, "reason": str(exc)}
                    continue
                flattened, flatten_error = elaborate(
                    f"{prefix}; setattr -unset keep_hierarchy; "
                    f"setattr -mod -unset keep_hierarchy; "
                    f"setattr -mod -set keep_hierarchy 1 {selection}; "
                    # Limit flattening to the evaluator's top-level view.
                    # Processing every module would also expand arithmetic
                    # helpers inside the retained PE and can make cone tracing
                    # needlessly large on realistic implementations.
                    f"flatten ={TOP}; opt_clean; write_json {output}")
                if flattened is None:
                    attempts[pe_kind] = {
                        "passed": False,
                        "reason": "Yosys wrapper flattening failed",
                        "yosys_log_tail": flatten_error,
                    }
                    continue
                attempt = inspect_netlist(flattened)
                attempt["flattened_from_hierarchy"] = True
                attempts[pe_kind] = attempt
                if attempt["passed"]:
                    passing.append(pe_kind)
            if len(passing) == 1:
                result = attempts[passing[0]]
            elif len(candidates) == 1:
                # Preserve the detailed structural reason from the sole
                # plausible 256-instance PE instead of the generic first pass.
                result = attempts[candidates[0]]
            else:
                result["interface_candidates"] = interface_candidates
                result["reachable_instance_counts"] = reachable
                result["hierarchical_candidate_types"] = candidates
                result["flatten_attempts"] = attempts
                if len(passing) > 1:
                    result["reason"] = "multiple 256-instance PE module types pass"
                    result["passing_candidate_types"] = passing
        result["status"] = "qualified" if result["passed"] else "failed"
        result["method"] = "yosys_netlist"
        return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.submission), indent=2))
