#!/usr/bin/env python3
"""Inspect a Yosys JSON netlist for direct two-flop T05 pointer synchronizers.

This checks destination-domain active-low asynchronous resets. It does not prove Gray coding, memory safety,
metastability MTBF, or physical CDC closure.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

FLOP_PREFIXES = ("$dff", "$adff", "$sdff", "$dffe", "$sdffe", "$aldff")


def inspect(module: dict, first_clock: str, second_clock: str, minimum: int) -> dict:
    ports = module["ports"]
    clocks = {}
    resets = {}
    for name in (first_clock, second_clock):
        bits = ports[name]["bits"]
        if len(bits) != 1:
            raise ValueError(f"clock port {name} is not one bit")
        clocks[bits[0]] = name
        reset_name = name.removesuffix("_clk") + "_rst_n"
        reset_bits = ports[reset_name]["bits"]
        if len(reset_bits) != 1:
            raise ValueError(f"reset port {reset_name} is not one bit")
        resets[name] = reset_bits
    cells = module["cells"]
    flops = {}
    q_owner = {}
    consumers = defaultdict(list)
    drivers = {}
    findings = []
    boundaries = set()

    for cell_name, cell in cells.items():
        conn = cell["connections"]
        directions = cell.get("port_directions", {})
        # Recent Yosys versions may retain hierarchy provenance as zero-port
        # $scopeinfo pseudo-cells after ``flatten``.  They are metadata rather
        # than netlist logic and therefore cannot participate in a crossing.
        if cell["type"] == "$scopeinfo" and not conn:
            continue
        if not directions and not cell["type"].startswith("$mem"):
            findings.append(f"{cell_name}: unknown port directions; crossing not classifiable")
        for port_name, bits in conn.items():
            direction = directions.get(port_name)
            for index, bit in enumerate(bits):
                if direction == "input":
                    consumers[bit].append((cell_name, port_name, index))
                elif direction == "output":
                    drivers[bit] = (cell_name, port_name)
        if cell["type"].startswith(FLOP_PREFIXES) and all(p in conn for p in ("CLK", "D", "Q")):
            clk_bit = conn["CLK"][0]
            domain = clocks.get(clk_bit)
            if domain is None:
                findings.append(f"{cell_name}: unrecognized clock {clk_bit}")
                continue
            clock_polarity = cell.get("parameters", {}).get("CLK_POLARITY")
            if clock_polarity is None or int(clock_polarity, 2) != 1:
                findings.append(f"{cell_name}: expected positive-edge clock")
            if len(conn["D"]) != len(conn["Q"]):
                findings.append(f"{cell_name}: D/Q width mismatch")
                continue
            flops[cell_name] = (cell, domain)
            for index, bit in enumerate(conn["Q"]):
                q_owner[bit] = (cell_name, index, domain)

    memo = {}

    def sources(bit: int | str, stack: frozenset) -> frozenset:
        if not isinstance(bit, int):
            return frozenset()
        if bit in q_owner:
            return frozenset((q_owner[bit],))
        if bit in memo:
            return memo[bit]
        if bit in stack:
            findings.append(f"combinational cycle reaching bit {bit}")
            return frozenset()
        driver = drivers.get(bit)
        if driver is None:
            return frozenset()
        cell_name, _ = driver
        cell = cells[cell_name]
        if cell["type"].startswith("$mem"):
            boundaries.add(cell_name)
            return frozenset()
        upstream = set()
        for port_name, bits in cell["connections"].items():
            if cell.get("port_directions", {}).get(port_name) == "input":
                for input_bit in bits:
                    upstream.update(sources(input_bit, stack | {bit}))
        memo[bit] = frozenset(upstream)
        return memo[bit]

    crossings = defaultdict(list)
    for cell_name, (cell, dst_domain) in flops.items():
        for bit_index, d_bit in enumerate(cell["connections"]["D"]):
            foreign = [src for src in sources(d_bit, frozenset()) if src[2] != dst_domain]
            if not foreign:
                continue
            if d_bit not in q_owner or len(foreign) != 1 or q_owner[d_bit] != foreign[0]:
                findings.append(f"{cell_name}.D[{bit_index}]: combinational or merged crossing "
                                f"from {[(src[0], src[2]) for src in foreign]}")
                continue
            src_name, src_index, src_domain = foreign[0]
            crossings[(src_domain, dst_domain)].append(
                (src_name, src_index, cell_name, bit_index)
            )

    chain_counts = defaultdict(int)
    output_bits = {bit for port in ports.values() if port["direction"] == "output"
                   for bit in port["bits"]}
    for (src_domain, dst_domain), entries in crossings.items():
        for src_name, src_index, first_name, first_index in entries:
            first, _ = flops[first_name]
            first_q = first["connections"]["Q"][first_index]
            uses = consumers[first_q]
            next_stages = [u for u in uses if u[1] == "D" and u[0] in flops
                           and flops[u[0]][1] == dst_domain]
            same_reset = False
            if len(next_stages) == 1:
                second, _ = flops[next_stages[0][0]]
                first_reset = first["connections"].get("ARST")
                second_reset = second["connections"].get("ARST")
                same_reset = (first_reset is not None and first_reset == second_reset and
                              first["parameters"].get("ARST_POLARITY") ==
                              second["parameters"].get("ARST_POLARITY") and
                              first["parameters"].get("CLK_POLARITY") ==
                              second["parameters"].get("CLK_POLARITY"))
            if len(uses) != 1 or len(next_stages) != 1 or not same_reset or first_q in output_bits:
                findings.append(
                    f"{src_name}.Q[{src_index}] {src_domain}->{dst_domain}: "
                    f"first stage {first_name}.Q[{first_index}] is not isolated "
                    "to one same-clock, same-reset second stage"
                )
            else:
                if (first["connections"].get("ARST") != resets[dst_domain] or
                    second["connections"].get("ARST") != resets[dst_domain] or
                    int(first["parameters"].get("ARST_POLARITY", "1"), 2) != 0 or
                    int(second["parameters"].get("ARST_POLARITY", "1"), 2) != 0):
                    findings.append(f"{first_name}/{next_stages[0][0]}: synchronizer reset "
                                    f"does not use active-low {dst_domain} local reset")
                    continue
                chain_counts[(src_domain, dst_domain)] += 1

    for direction in ((first_clock, second_clock), (second_clock, first_clock)):
        if chain_counts[direction] < minimum:
            findings.append(f"{direction[0]}->{direction[1]}: "
                            f"{chain_counts[direction]} verified chains, need >= {minimum}")

    # The ready/valid control outputs belong to their corresponding clock
    # domains. A direct foreign pointer feed can bypass all synchronizer
    # flops without ever appearing at a destination flop D pin.
    for output_name, domain in (("wr_ready", first_clock),
                                ("rd_valid", second_clock)):
        if output_name not in ports:
            continue
        for bit_index, bit in enumerate(ports[output_name]["bits"]):
            foreign = [src for src in sources(bit, frozenset()) if src[2] != domain]
            if foreign:
                findings.append(f"{output_name}[{bit_index}]: direct combinational "
                                f"foreign-domain source {[(x[0], x[2]) for x in foreign]}")

    return {
        "passed": not findings,
        "required_per_direction": minimum,
        "verified_chains": {f"{a}->{b}": chain_counts[(a, b)]
                            for a, b in ((first_clock, second_clock),
                                         (second_clock, first_clock))},
        "memory_boundaries_not_checked": sorted(boundaries),
        "findings": findings,
        "scope": "2FF chains and destination reset only; Gray/memory/RDC/MTBF not proven",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist", type=Path, help="Yosys write_json output")
    parser.add_argument("--top", default="asynchronous_fifo")
    parser.add_argument("--wr-clock", default="wr_clk")
    parser.add_argument("--rd-clock", default="rd_clk")
    parser.add_argument("--depth", type=int, choices=(8, 16), default=8)
    args = parser.parse_args()
    try:
        module = json.loads(args.netlist.read_text())["modules"][args.top]
        result = inspect(module, args.wr_clock, args.rd_clock,
                         (args.depth - 1).bit_length() + 1)
    except (OSError, ValueError, KeyError) as exc:
        result = {"passed": False, "findings": [f"analysis failed: {exc}"]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
