#!/usr/bin/env python3
"""Check T09 zero-stall fetch-to-retirement latency from evaluator-captured ports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

START_PC = 0x80000000
INSTRUCTION_COUNT = 64
EDGE_DELTA = 4  # request at n, WB observation after edge n+4


def check_trace(rows: list[dict]) -> dict:
    fetched: dict[int, int] = {}
    committed = 0
    prior_cycle: int | None = None
    for row in rows:
        cycle = row["cycle"]
        if not isinstance(cycle, int) or (prior_cycle is not None and cycle != prior_cycle + 1):
            return {"passed": False, "reason": f"nonconsecutive cycle at {cycle}"}
        prior_cycle = cycle
        if row["imem_valid_pre"]:
            pc = row["imem_addr_pre"]
            if START_PC <= pc < START_PC + 4 * INSTRUCTION_COUNT and (pc - START_PC) % 4 == 0:
                if pc in fetched:
                    return {"passed": False, "reason": f"duplicate fetch PC 0x{pc:08x} at {cycle}"}
                fetched[pc] = cycle
        if row["commit_valid_post"]:
            pc = row["commit_pc_post"]
            if committed == INSTRUCTION_COUNT:
                if pc in fetched:
                    return {"passed": False,
                            "reason": f"duplicate retirement of PC 0x{pc:08x} at {cycle}"}
                continue
            expected_pc = START_PC + 4 * committed
            if pc != expected_pc:
                return {"passed": False, "reason": f"commit {committed} at {cycle}: "
                        f"expected PC 0x{expected_pc:08x}, got 0x{pc:08x}"}
            if pc not in fetched:
                return {"passed": False, "reason": f"PC 0x{pc:08x} retired before fetch"}
            elapsed = cycle - fetched[pc]
            if elapsed != EDGE_DELTA:
                return {"passed": False, "reason": f"PC 0x{pc:08x}: "
                        f"fetch-to-retire edge delta {elapsed}, expected {EDGE_DELTA}"}
            committed += 1
    if len(fetched) != INSTRUCTION_COUNT or committed != INSTRUCTION_COUNT:
        return {"passed": False, "reason": f"incomplete: fetched={len(fetched)} "
                f"committed={committed}, need {INSTRUCTION_COUNT}"}
    return {"passed": True, "instructions": INSTRUCTION_COUNT,
            "edge_delta": EDGE_DELTA,
            "measurement": "imem request at rising edge n; commit_valid after rising edge n+4"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="one JSON object per sampled cycle")
    args = parser.parse_args()
    try:
        rows = [json.loads(line) for line in args.trace.read_text().splitlines() if line.strip()]
        result = check_trace(rows)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {"passed": False, "reason": f"invalid trace: {exc}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
