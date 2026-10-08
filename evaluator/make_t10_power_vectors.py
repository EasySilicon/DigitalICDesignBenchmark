#!/usr/bin/env python3
"""Freeze a balanced, finite, checked T10 gate-level power workload."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from t10_common import DEFAULT_BENCHMARK_ROOT
from runner_t10 import Case, WIDTH, pack_rows, write_vectors
from matmul_oracle import dot_terms, expected_dot

FINITE_CODES = {
    0: (1, 2, 3, 0x7f, 0xff, 0x80),
    1: (1, 2, 3, 0x7fff, 0xffff, 0x8000),
    2: (0x3c00, 0xbc00, 0x4000, 0x3800, 0x0400, 0x7bff),
    # Keep the high-dynamic-range sample large enough to toggle the BF16
    # exponent datapath while ensuring every 64-term dot product remains
    # finite in binary32. 0x7f7f is a finite BF16 input, but squaring it
    # overflows the required binary32 output and makes a poor power vector.
    3: (0x3f80, 0xbf80, 0x4000, 0x3f00, 0x0080, 0x4f7f),
    4: (0x38, 0xb8, 0x40, 0x30, 0x01, 0x7e),
    5: (0x3c, 0xbc, 0x40, 0x38, 0x01, 0x7b),
    6: (0x1, 0x2, 0x3, 0x9, 0xa, 0xb),
    7: (0x38, 0xb8, 0x40, 0x30, 0x01, 0x7e),
    8: (0x3c, 0xbc, 0x40, 0x38, 0x01, 0x7b),
    9: (0x1, 0x2, 0x3, 0x9, 0xa, 0xb),
}


def scale_bus(mode: int, index: int, offset: int) -> int:
    if mode not in (7,8,9):
        return 0
    result = 0
    for vector in range(16):
        for block in range(2):
            code = 124 + (index + offset + 3*vector + 5*block) % 7
            result |= code << (8*(2*vector+block))
    return result


def make_case(mode: int, index: int, rng: random.Random) -> Case:
    codes = FINITE_CODES[mode]
    a = [[rng.choice(codes) for _ in range(64)] for _ in range(16)]
    b = [[rng.choice(codes) for _ in range(64)] for _ in range(16)]
    return Case("MM-SYSTOLIC",mode,pack_rows(a,mode),pack_rows(b,mode),
                scale_bus(mode,index,0),scale_bus(mode,index,17),0,0,0)


def generate(seed: int) -> tuple[list[Case], list[int]]:
    rng = random.Random(seed)
    cases = []
    phases = []
    for mode in range(10):
        # Every mode contributes 128 uninterrupted input cycles. The hidden
        # monitor's steady window starts after cycle 64, so all ten formats
        # have a nonempty steady-state power sample.
        count = 128 // WIDTH[mode]
        for index in range(count):
            cases.append(make_case(mode,index,rng))
            phases.append(mode+1)
    for index in range(32):
        mode = 9 if index&1 else 0
        cases.append(make_case(mode,index,rng))
        phases.append(11)
    return cases, phases


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_oracle(cases: list[Case], phases: list[int]) -> dict:
    result_classes: Counter[str] = Counter()
    mode_output_points: Counter[int] = Counter()
    for case in cases:
        for row in range(16):
            for col in range(16):
                kind, _, _ = expected_dot(dot_terms(
                    list(case.a), list(case.b), case.a_scale,
                    case.b_scale, case.mode, row, col))
                result_classes[kind] += 1
                mode_output_points[case.mode] += 1
    if result_classes != {"finite": len(cases) * 16 * 16}:
        raise AssertionError(f"power workload contains nonfinite results: {result_classes}")
    oracle = (DEFAULT_BENCHMARK_ROOT / "benchmark" / "tasks" / "T10" /
              "public" / "matmul_oracle.py")
    return {
        "status": "pass",
        "matrix_blocks": len(cases),
        "output_points": len(cases) * 16 * 16,
        "result_classes": dict(sorted(result_classes.items())),
        "mode_output_points": {
            str(mode): mode_output_points[mode] for mode in range(10)
        },
        "phase_counts": {
            str(phase): count for phase, count in sorted(Counter(phases).items())
        },
        "oracle_path": "benchmark/tasks/T10/public/matmul_oracle.py",
        "oracle_sha256": sha256(oracle),
    }


def create(output: Path, seed: int = 20260925) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    cases, phases = generate(seed)
    write_vectors(output, cases)
    (output / "phase.mem").write_text("\n".join(f"{phase:x}" for phase in phases)+"\n")
    files = {path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
             for path in sorted(output.glob("*.mem"))}
    vector_sha256 = {
        name: files[f"{name}.mem"]["sha256"]
        for name in ("a", "b", "as", "bs", "mode", "phase")
    }
    record = {"task_id": "T10", "seed": seed, "case_count": len(cases),
              "mode_counts": {str(mode): sum(case.mode == mode for case in cases)
                              for mode in range(10)},
              "vector_sha256": vector_sha256,
              "oracle_check": check_oracle(cases, phases),
              "generator": {"path": Path(__file__).name,
                            "sha256": sha256(Path(__file__))},
              "files": files}
    (output / "manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=20260925)
    args = parser.parse_args()
    print(json.dumps(create(args.output, args.seed), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
