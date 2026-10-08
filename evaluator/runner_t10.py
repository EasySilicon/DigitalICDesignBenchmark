#!/usr/bin/env python3
"""Legacy single-block T10 generator/scorer; current pilot uses runner_t10_stream."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from t10_common import DEFAULT_BENCHMARK_ROOT, EVALUATOR_ROOT
from t10_structure_check import inspect as inspect_structure

sys.path.insert(0, str(DEFAULT_BENCHMARK_ROOT / "evaluator"))
from matmul_oracle import check_output  # noqa: E402
from public_check import sources_from_filelist  # noqa: E402

GROUP_COUNTS = {"MM-INT": 128, "MM-F16": 128, "MM-F8": 128,
                "MM-F4": 64, "MM-MX8": 128, "MM-MX4": 96,
                "MM-PROTO": 80, "MM-SYSTOLIC": 80, "MM-CORNER": 128}
GROUP_MODES = {"MM-INT": (0, 1), "MM-F16": (2, 3),
               "MM-F8": (4, 5), "MM-F4": (6,),
               "MM-MX8": (7, 8), "MM-MX4": (9,),
               "MM-PROTO": tuple(range(10)),
               "MM-SYSTOLIC": tuple(range(10)),
               "MM-CORNER": (2, 3, 4, 5, 7, 8, 9)}
WIDTH = {0: 8, 1: 16, 2: 16, 3: 16, 4: 8,
         5: 8, 6: 4, 7: 8, 8: 8, 9: 4}
CODES = {
    0: (0, 1, 0xFF, 0x80, 0x7F, 0x11, 0xE3),
    1: (0, 1, 0xFFFF, 0x8000, 0x7FFF, 0x07FF, 0xFC00),
    2: (0, 0x8000, 0x3C00, 0xBC00, 0x4000, 0x3800, 0x0001, 0x0400, 0x7BFF),
    3: (0, 0x8000, 0x3F80, 0xBF80, 0x4000, 0x3F00, 0x0001, 0x0080, 0x4100),
    4: (0, 0x80, 0x38, 0xB8, 0x40, 0x30, 0x01, 0x08, 0x7E),
    5: (0, 0x80, 0x3C, 0xBC, 0x40, 0x38, 0x01, 0x04, 0x7B),
    6: tuple(range(16)),
    7: (0, 0x80, 0x38, 0xB8, 0x40, 0x30, 0x01, 0x08, 0x7E),
    8: (0, 0x80, 0x3C, 0xBC, 0x40, 0x38, 0x01, 0x04, 0x7B),
    9: tuple(range(16)),
}
ONE = {0: 1, 1: 1, 2: 0x3C00, 3: 0x3F80, 4: 0x38,
       5: 0x3C, 6: 0x2, 7: 0x38, 8: 0x3C, 9: 0x2}
SPECIAL = {2: (0x7E00, 0x7C00), 3: (0x7FC0, 0x7F80),
           4: (0x7F,), 5: (0x7D, 0x7C),
           7: (0x7F,), 8: (0x7D, 0x7C)}
ROW_LINE = re.compile(r"^MM_ROW (\d+) (\d+) ([0-9a-fA-F]+)$", re.MULTILINE)
CASE_LINE = re.compile(r"^MM_CASE (\d+) ([01]) ([01]) ([01]) (\d+)$", re.MULTILINE)


@dataclass(frozen=True)
class Case:
    group: str
    mode: int
    a: tuple[int, ...]
    b: tuple[int, ...]
    a_scale: int
    b_scale: int
    pause: int
    stall: int
    reset_kind: int


def pack_rows(rows: list[list[int]], mode: int) -> tuple[int, ...]:
    width = WIDTH[mode]
    lanes = 64 // width
    beats = []
    for t in range(width):
        value = 0
        for vector in range(16):
            for lane in range(lanes):
                code = rows[vector][t * lanes + lane]
                value |= code << ((vector * lanes + lane) * width)
        beats.append(value)
    return tuple(beats)


def scale_bus(mode: int, rng: random.Random, index: int,
              extreme: bool) -> int:
    if mode not in (7, 8, 9):
        return 0
    value = 0
    # Extreme scales exercise both uniform/sparse and dense mixed-sign dots.
    boundary = (0, 126, 127, 128, 254) if extreme else (124, 125, 126, 127, 128, 129, 130)
    for vector in range(16):
        for block in range(2):
            # Other blocks use near-unity scales; selected blocks hit endpoints.
            code = boundary[(index + vector + block + rng.randrange(4)) % len(boundary)]
            value |= code << (8 * (2 * vector + block))
    return value


def generate_case(group: str, index: int, rng: random.Random) -> Case:
    modes = GROUP_MODES[group]
    mode = modes[index % len(modes)]
    codes = CODES[mode]
    kind = index % 8
    a = [[0] * 64 for _ in range(16)]
    b = [[0] * 64 for _ in range(16)]
    if kind == 0:
        for r in range(16):
            for k in range(64):
                a[r][k] = ONE[mode]
                b[r][k] = ONE[mode]
    elif kind == 1:
        a[15][63] = ONE[mode]
        b[15][63] = ONE[mode]
    elif kind == 2:
        # Deliberate cancellation and row/column asymmetry.
        for r in range(16):
            for k in range(64):
                a[r][k] = codes[(r + k) % len(codes)]
                b[r][k] = codes[(3 * r + 5 * k) % len(codes)]
    elif kind == 7:
        # Sample the complete legal element encoding space. The curated
        # boundary palette above alone misses many finite mantissa/exponent
        # combinations, especially in FP16, BF16, and both FP8 formats.
        for r in range(16):
            for k in range(64):
                a[r][k] = rng.randrange(1 << WIDTH[mode])
                b[r][k] = rng.randrange(1 << WIDTH[mode])
    else:
        for r in range(16):
            for k in range(64):
                a[r][k] = rng.choice(codes)
                b[r][k] = rng.choice(codes)
    ascale = scale_bus(mode, rng, index, kind in (0, 1))
    bscale = scale_bus(mode, rng, index + 3, kind in (5, 6))
    if group == "MM-CORNER":
        r, c, k = (index * 3) % 16, (index * 7) % 16, (index * 11) % 64
        a[r][k] = ONE[mode]
        b[c][k] = ONE[mode]
        if mode == 9 or index % 3 == 0 and mode in (7, 8):
            ascale &= ~(255 << (8 * (2 * r + k // 32)))
            ascale |= 255 << (8 * (2 * r + k // 32))
        elif mode in SPECIAL:
            a[r][k] = SPECIAL[mode][index % len(SPECIAL[mode])]
            if len(SPECIAL[mode]) == 2 and index % 4 == 3:
                b[c][k] = 0  # 0 * infinity => NaN.
    if ((group == "MM-MX8" and index in (120, 121)) or
            (group == "MM-MX4" and index == 88)):
        # A pair of products far above binary32 max cancels; block 1 leaves
        # exactly one. This rejects FP32 accumulation before the final dot.
        peak = {7: 0x7E, 8: 0x7B, 9: 0x7}[mode]
        a = [[0] * 64 for _ in range(16)]
        b = [[0] * 64 for _ in range(16)]
        for vector in range(16):
            a[vector][0], a[vector][1], a[vector][32] = (
                peak, peak | (1 << (WIDTH[mode] - 1)), ONE[mode])
            b[vector][0], b[vector][1], b[vector][32] = (
                peak, peak, ONE[mode])
        ascale = bscale = sum((254 if block % 2 == 0 else 127) << (8 * block)
                                for block in range(32))
    if ((group == "MM-MX8" and index in (122, 123)) or
            (group == "MM-MX4" and index == 89)):
        # Three 2^126 terms are finite; four must be +infinity. Rows of both
        # classes are checked in the same command at the exact FP32 boundary.
        a = [[0] * 64 for _ in range(16)]
        b = [[0] * 64 for _ in range(16)]
        for vector in range(16):
            for k in range(4):
                b[vector][k] = ONE[mode]
                if k < 3 + (vector & 1):
                    a[vector][k] = ONE[mode]
        ascale = bscale = sum(190 << (8 * block) for block in range(32))
    if group == "MM-CORNER" and index == 117:
        # A true negative infinity wins over an overflowing positive finite
        # partial sum, regardless of their order in the reduction.
        a = [[0] * 64 for _ in range(16)]
        b = [[0] * 64 for _ in range(16)]
        a[0][0], b[0][0] = 0x7B, 0x7B
        a[0][1], b[0][1] = 0xFC, ONE[mode]
        ascale = bscale = sum(254 << (8 * block) for block in range(32))
    pause = (1 << (index % WIDTH[mode])) if group == "MM-PROTO" else 0
    stall = (index % 31) if group == "MM-PROTO" else 0
    reset_kind = 1 + (index % 2) if group == "MM-PROTO" and index < 16 else 0
    return Case(group, mode, pack_rows(a, mode), pack_rows(b, mode),
                ascale, bscale, pause, stall, reset_kind)


def generate_cases(seed: int) -> list[Case]:
    rngs = [random.Random(seed + offset) for offset in range(3)]
    cases = []
    for group, count in GROUP_COUNTS.items():
        for index in range(count):
            cases.append(generate_case(group, index, rngs[index % 3]))
    if len(cases) > 1024:
        raise ValueError("SV harness MAX_CASES too small")
    return cases


def write_vectors(directory: Path, cases: list[Case]) -> None:
    data = {name: [] for name in ("a", "b", "as", "bs", "mode", "stall", "pause", "reset")}
    for case in cases:
        data["a"].extend(f"{value:0256x}" for value in (*case.a, *([0] * (16 - len(case.a)))))
        data["b"].extend(f"{value:0256x}" for value in (*case.b, *([0] * (16 - len(case.b)))))
        data["as"].append(f"{case.a_scale:064x}")
        data["bs"].append(f"{case.b_scale:064x}")
        data["mode"].append(f"{case.mode:x}")
        data["stall"].append(f"{case.stall:02x}")
        data["pause"].append(f"{case.pause:04x}")
        data["reset"].append(f"{case.reset_kind:x}")
    for name, values in data.items():
        (directory / f"{name}.mem").write_text("\n".join(values) + "\n")


def parse_output(log: str, cases: list[Case], structure: dict,
                 require_timing: bool = False,
                 numeric_checker=None) -> tuple[dict, list[dict]]:
    if numeric_checker is None:
        numeric_checker = check_output
    statuses = {int(i): (p == "1", t == "1", o == "1", int(n))
                for i, p, t, o, n in CASE_LINE.findall(log)}
    reset_results = {int(i): ok == "1" for i, ok in
                     re.findall(r"^MM_RESET (\d+) ([01])$", log, re.MULTILINE)}
    rows: dict[int, dict[int, int]] = {}
    for index, row, value in ROW_LINE.findall(log):
        rows.setdefault(int(index), {})[int(row)] = int(value, 16)
    totals = Counter(case.group for case in cases)
    counts = {group: {"cases_passed": 0, "cases_total": totals[group]}
              for group in GROUP_COUNTS}
    failures = []
    for index, case in enumerate(cases):
        protocol, timing, output, count = statuses.get(index, (False, False, False, 0))
        observed = rows.get(index, {})
        rows_complete = count == 16 and set(observed) == set(range(16))
        numeric_errors = ["missing/duplicate output rows"] if not rows_complete else \
            numeric_checker(list(case.a), list(case.b), case.a_scale, case.b_scale,
                            case.mode, [observed[r] for r in range(16)])
        # Every legal transaction must have correct data, including cases
        # primarily aimed at protocol or wavefront behavior. A numerical
        # failure must never qualify a submission for routed PPA scoring.
        passed = protocol and output and rows_complete and not numeric_errors
        if require_timing:
            passed = passed and timing
        if case.reset_kind:
            passed = passed and reset_results.get(index, False)
        if case.group == "MM-SYSTOLIC":
            passed = passed and timing and structure["passed"]
        if passed:
            counts[case.group]["cases_passed"] += 1
        elif len(failures) < 50 and not (case.group == "MM-SYSTOLIC" and
                                         structure.get("status") == "pending"):
            failures.append({"case": index, "group": case.group, "mode": case.mode,
                             "protocol": protocol, "timing": timing, "output": output,
                             "errors": numeric_errors[:3]})
    return counts, failures


def run(submission: Path, seed: int = 20260925,
        output_dir: Path | None = None) -> dict:
    submission = submission.resolve(strict=True)
    cases = generate_cases(seed)
    structure = inspect_structure(submission)
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_hidden_T10_") as temp:
        root = Path(temp)
        vectors = root / "vectors"
        vectors.mkdir()
        write_vectors(vectors, cases)
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "vector_sha256.json").write_text(json.dumps({
                name: hashlib.sha256((vectors / f"{name}.mem").read_bytes()).hexdigest()
                for name in ("a", "b", "as", "bs", "mode", "stall", "pause", "reset")}, indent=2))
        build = root / "build"
        command = ["verilator", "--binary", "--timing", "--assert", "-Wno-fatal",
                   "-j", "4", "--top-module", "tb_hidden_T10", "--Mdir", str(build),
                   *map(str, sources_from_filelist(submission)),
                   str(EVALUATOR_ROOT / "hidden/tb_hidden_T10.sv")]
        compiled = subprocess.run(command, text=True, capture_output=True,
                                  timeout=1200, check=False)
        if output_dir is not None:
            (output_dir / "compile.log").write_text(compiled.stdout + compiled.stderr)
        if compiled.returncode:
            return {"task_id": "T10", "phase": "compile-failed", "structure": structure,
                    "groups": {group: {"cases_passed": 0, "cases_total": count}
                               for group, count in GROUP_COUNTS.items()},
                    "log_tail": (compiled.stdout + compiled.stderr)[-8000:]}
        executed = subprocess.run([str(build / "Vtb_hidden_T10"),
                                   f"+VECTORS={vectors}", f"+CASE_COUNT={len(cases)}"],
                                  text=True, capture_output=True, timeout=900, check=False)
        if output_dir is not None:
            (output_dir / "simulation.log").write_text(executed.stdout + executed.stderr)
        groups, failures = parse_output(executed.stdout, cases, structure)
        return {"task_id": "T10", "phase": "run" if executed.returncode == 0 else "simulation-failed",
                "seed": seed, "cases": len(cases), "groups": groups,
                "structure": structure, "failures": failures,
                "log_tail": (executed.stdout + executed.stderr)[-8000:]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path)
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    try:
        result = run(args.submission, args.seed, args.output_dir)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        result = {"task_id": "T10", "phase": "infrastructure", "error": str(exc)}
    print(json.dumps(result, indent=2))
    return 0 if result.get("phase") == "run" else 1


if __name__ == "__main__":
    raise SystemExit(main())
