#!/usr/bin/env python3
"""Pre-release T10 streaming-port scorer with continuous 4/8/16-cycle trains."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

from t10_common import EVALUATOR_ROOT
from runner_t10 import (Case, GROUP_COUNTS, ONE, WIDTH, generate_cases,
                        pack_rows, parse_output, write_vectors)
from t10_structure_check import inspect as inspect_structure
from t10_fast_oracle import check_output_fast


def compile_hierarchical(command: list[str], build: Path) -> tuple[subprocess.CompletedProcess, Path, str]:
    """Retry a known Verilator 5.051 empty VM_TRACE macro failure with tracing enabled."""
    compiled = subprocess.run(command, text=True, capture_output=True,
                              timeout=1200, check=False)
    transcript = compiled.stdout + compiled.stderr
    if compiled.returncode and "error: #if with no expression" in transcript and \
            "-DVM_TRACE=" in transcript:
        retry_build = build.with_name(build.name + "_trace")
        retry_command = command.copy()
        retry_command[retry_command.index("--Mdir") + 1] = str(retry_build)
        retry_command.insert(retry_command.index("--timing"), "--trace")
        compiled = subprocess.run(retry_command, text=True, capture_output=True,
                                  timeout=1200, check=False)
        transcript += "\nVERILATOR_EMPTY_VM_TRACE_RETRY\n" + compiled.stdout + compiled.stderr
        build = retry_build
    return compiled, build, transcript


def stream_cases(seed: int) -> tuple[list[Case], list[int]]:
    # The legacy generator's pause/stall/reset knobs belong to its single-
    # command harness. Numeric matrices are replayed as one continuous mixed
    # stream; streaming backpressure and reset are separate scenarios.
    cases = [replace(case, pause=0, stall=0, reset_kind=0)
             for case in generate_cases(seed)]
    phases = [0] * len(cases)
    for mode in range(10):
        width = WIDTH[mode]
        count = 256 if width == 4 else 64
        sign_bit = 1 << (width - 1)
        scale = sum(127 << (8 * index) for index in range(32))
        for index in range(count):
            last_only = bool(index & 1)
            a = [[0] * 64 for _ in range(16)]
            b = [[0] * 64 for _ in range(16)]
            for vector in range(16):
                negative = last_only and bool(vector & 1)
                code = ((1 << width) - 1 if mode < 2 else ONE[mode] | sign_bit) \
                    if negative else ONE[mode]
                for k in range(64):
                    if not last_only or k == 63:
                        a[vector][k] = code
                        b[vector][k] = code
            cases.append(Case("MM-SYSTOLIC", mode,
                              pack_rows(a, mode), pack_rows(b, mode),
                              scale, scale, 0, 0, 0))
            phases.append(mode + 1)
    # A separate, uninterrupted, fixed-seed mixed-format train exercises
    # block-boundary mode/scale changes while older blocks are still in flight.
    # The first four modes force both 4 -> 16 and 16 -> 4 transitions.
    rng = random.Random(seed ^ 0x10A7C0DE)
    source_by_mode = {
        mode: [case for case in cases[:sum(GROUP_COUNTS.values())]
               if case.mode == mode]
        for mode in range(10)
    }
    for index in range(512):
        mode = (6, 2, 9, 1)[index] if index < 4 else rng.randrange(10)
        source = rng.choice(source_by_mode[mode])
        cases.append(replace(source, group="MM-SYSTOLIC"))
        phases.append(12)
    # Output stalls last 32 cycles out of every 53. New blocks may wait for
    # credit, but an accepted block's remaining input beats may not stall.
    scale = sum(127 << (8 * index) for index in range(32))
    for index in range(128):
        mode = 9 if index & 1 else 0
        a = [[0] * 64 for _ in range(16)]
        b = [[0] * 64 for _ in range(16)]
        for vector in range(16):
            for k in range(64):
                # Distinct row groups make stalled local-gather selection
                # observable; constant rows masked a group-swap mutation.
                a[vector][k] = (vector + 1) if mode == 0 else (2, 3, 4, 5)[vector // 4]
                b[vector][k] = (vector + 1) if mode == 0 else (2 if vector % 2 == 0 else 3)
        cases.append(Case("MM-PROTO", mode,
                          pack_rows(a, mode), pack_rows(b, mode),
                          scale, scale, 0, 0, 0))
        phases.append(11)
    # A contiguous FP4 train forces the four-row-per-cycle output pipe to
    # fill during the periodic 32-cycle stall. The four row groups differ.
    for _ in range(128):
        mode = 9
        a = [[(2, 3, 4, 5)[row // 4]] * 64 for row in range(16)]
        b = [[2 if col % 2 == 0 else 3] * 64 for col in range(16)]
        cases.append(Case("MM-PROTO", mode,
                          pack_rows(a, mode), pack_rows(b, mode),
                          scale, scale, 0, 0, 0))
        phases.append(13)
    return cases, phases


def run(submission: Path, seed: int = 20260925,
        output_dir: Path | None = None,
        run_reset_probe: bool = True,
        mixed_backpressure: bool = False,
        first_latency_limit: int = 64,
        last_latency_limit: int = 80) -> dict:
    submission = submission.resolve(strict=True)
    cases, phases = stream_cases(seed)
    if len(cases) > 4096:
        raise ValueError("stream testbench MAX_CASES exceeded")
    structure = inspect_structure(submission)
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_T10_stream_") as temp:
        root = Path(temp)
        vectors = root / "vectors"
        vectors.mkdir()
        write_vectors(vectors, cases)
        (vectors / "phase.mem").write_text("\n".join(f"{phase:x}" for phase in phases) + "\n")
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "vector_sha256.json").write_text(json.dumps({
                name: hashlib.sha256((vectors / f"{name}.mem").read_bytes()).hexdigest()
                for name in ("a", "b", "as", "bs", "mode", "phase")}, indent=2) + "\n")
        build = root / "build"
        from runner_t10 import sources_from_filelist
        command = ["verilator", "--binary", "--hierarchical", "--timing", "--assert", "-Wno-fatal",
                   "-j", "4", "--top-module", "tb_hidden_T10_stream", "--Mdir", str(build),
                   *map(str, sources_from_filelist(submission)),
                   str(EVALUATOR_ROOT / "hidden/tb_hidden_T10_stream.sv")]
        compiled, build, compile_output = compile_hierarchical(command, build)
        if output_dir is not None:
            (output_dir / "compile.log").write_text(compile_output)
        if compiled.returncode:
            return {"task_id": "T10", "phase": "compile-failed", "structure": structure,
                    "log_tail": compile_output[-8000:]}
        executed = subprocess.run([str(build / "Vtb_hidden_T10_stream"),
                                   f"+VECTORS={vectors}", f"+CASE_COUNT={len(cases)}",
                                   f"+FIRST_LATENCY={first_latency_limit}",
                                   f"+LAST_LATENCY={last_latency_limit}",
                                   *(["+BP_MIXED"] if mixed_backpressure else [])],
                                  text=True, capture_output=True, timeout=1200,
                                  check=False)
        if output_dir is not None:
            (output_dir / "simulation.log").write_text(executed.stdout + executed.stderr)
        # Streaming timing and backpressure are required for every case, not
        # only for the historical MM-SYSTOLIC group.
        groups, failures = parse_output(executed.stdout, cases, structure,
                                        require_timing=True,
                                        numeric_checker=check_output_fast)
        stream_line = next((line for line in executed.stdout.splitlines()
                            if line.startswith("MM_STREAM ")), "")
        reset_ok = None
        if run_reset_probe:
            reset_build = root / "reset_build"
            reset_command = ["verilator", "--binary", "--hierarchical", "--timing", "--assert", "-Wno-fatal",
                             "-j", "4", "--top-module", "tb_hidden_T10_reset",
                             "--Mdir", str(reset_build),
                             *map(str, sources_from_filelist(submission)),
                             str(EVALUATOR_ROOT / "hidden/tb_hidden_T10_reset.sv")]
            reset_compile, reset_build, reset_compile_output = \
                compile_hierarchical(reset_command, reset_build)
            if output_dir is not None:
                (output_dir / "reset_compile.log").write_text(reset_compile_output)
            reset_run = None
            if reset_compile.returncode == 0:
                reset_run = subprocess.run([str(reset_build / "Vtb_hidden_T10_reset")],
                                           text=True, capture_output=True, timeout=120,
                                           check=False)
                if output_dir is not None:
                    (output_dir / "reset_simulation.log").write_text(
                        reset_run.stdout + reset_run.stderr)
            reset_ok = bool(reset_run is not None and reset_run.returncode == 0 and
                            "MM_RESET_STREAM PASS" in reset_run.stdout)
            groups["MM-PROTO"]["cases_total"] += 1
            if reset_ok:
                groups["MM-PROTO"]["cases_passed"] += 1
            else:
                failures.append({"group": "MM-PROTO", "case": "stream_reset_probe",
                                 "error": "reset probe failed to compile or pass"})
        return {"task_id": "T10", "phase": "run" if executed.returncode == 0
                else "simulation-failed", "status": "streaming_pre_release",
                "seed": seed, "cases": len(cases), "legacy_cases": sum(GROUP_COUNTS.values()),
                "mixed_backpressure": mixed_backpressure,
                "first_latency_limit": first_latency_limit,
                "last_latency_limit": last_latency_limit,
                "continuous_train_cases": len(cases) - sum(GROUP_COUNTS.values()),
                "groups": groups, "structure": structure, "stream_line": stream_line,
                "reset_probe_passed": reset_ok,
                "failures": failures,
                "log_tail": (executed.stdout + executed.stderr)[-4000:]}


def functional_passed(result: dict) -> bool:
    """Require numeric, protocol, reset, mesh and continuous-stream completion."""
    groups = result.get("groups", {})
    marker = re.fullmatch(
        r"MM_STREAM input_bubble_phases=([01]{14}) finished=(\d+)",
        result.get("stream_line", ""))
    return (result.get("phase") == "run" and
            result.get("structure", {}).get("passed") is True and
            result.get("reset_probe_passed") is True and
            set(groups) == set(GROUP_COUNTS) and
            all(row.get("cases_total", 0) > 0 and
                row.get("cases_passed") == row.get("cases_total")
                for row in groups.values()) and
            not result.get("failures") and marker is not None and
            marker.group(1) == "0" * 14 and
            int(marker.group(2)) == result.get("cases"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path)
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--mixed-backpressure", action="store_true",
                        help="also stall the 512-case mixed-format train")
    parser.add_argument("--first-latency-limit", type=int, default=64)
    parser.add_argument("--last-latency-limit", type=int, default=80)
    args = parser.parse_args()
    try:
        result = run(args.submission, args.seed, args.output_dir,
                     mixed_backpressure=args.mixed_backpressure,
                     first_latency_limit=args.first_latency_limit,
                     last_latency_limit=args.last_latency_limit)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        result = {"task_id": "T10", "phase": "infrastructure", "error": str(exc)}
    result["functional_passed"] = functional_passed(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["functional_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
