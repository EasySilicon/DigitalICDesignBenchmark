#!/usr/bin/env python3
"""Independent behavioral and structural evaluator for T05."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path

from cdc_2ff_check import inspect
from public_check import ROOT, sources_from_filelist


PARAMETERS = ((8, 8), (8, 16), (32, 8), (32, 16))
BEHAVIOR_GROUPS = {f"AC-{index:02d}" for index in range(26, 31)}
EXPECTED_GROUPS = BEHAVIOR_GROUPS | {"AC-31"}
GROUP_LINE = re.compile(r"^IC_GROUP (AC-\d+) (\d+) (\d+)$", re.MULTILINE)


def structural_check(submission: Path, sources: list[Path], width: int,
                     depth: int, temporary: Path) -> dict:
    netlist = temporary / f"netlist_w{width}_d{depth}.json"
    script = temporary / f"elaborate_w{width}_d{depth}.ys"
    source_words = " ".join(str(path) for path in sources)
    script.write_text(
        f"read_verilog -sv -I{(submission / 'rtl').resolve()} {source_words}\n"
        f"chparam -set WIDTH {width} -set DEPTH {depth} asynchronous_fifo\n"
        "hierarchy -check -top asynchronous_fifo\n"
        # Flatten before the generic graph inspection so synchronizer stages
        # are visible as destination-domain flops rather than opaque module
        # ports.  Yosys may leave harmless $scopeinfo metadata behind; the
        # checker explicitly ignores those zero-port pseudo-cells.
        "proc\nflatten\nopt\nmemory_dff\nopt_clean\n"
        f"write_json {netlist}\n"
    )
    outcome = subprocess.run(["yosys", "-q", "-s", str(script)], text=True,
                             capture_output=True, timeout=180, check=False)
    if outcome.returncode:
        raise RuntimeError(f"Yosys structural elaboration failed for WIDTH={width} "
                           f"DEPTH={depth}: {(outcome.stdout + outcome.stderr)[-4000:]}")
    module = json.loads(netlist.read_text())["modules"]["asynchronous_fifo"]
    return inspect(module, "wr_clk", "rd_clk", math.ceil(math.log2(depth)) + 1)


def run(submission: Path, seed: int,
        parameters: tuple[tuple[int, int], ...] = PARAMETERS) -> dict:
    submission = submission.resolve()
    sources = sources_from_filelist(submission)
    aggregate = {group: {"cases_passed": 0, "cases_total": 0,
                         "safety_violation": False}
                 for group in EXPECTED_GROUPS}
    structural = {}
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_T05_hidden_") as temporary_name:
        temporary = Path(temporary_name)
        for index, (width, depth) in enumerate(parameters):
            build = temporary / f"build_{index}"
            command = ["verilator", "--binary", "--timing", "--assert", "-Wno-fatal",
                       "-j", "4", "--top-module", "tb_hidden_T05",
                       "--Mdir", str(build), f"-GWIDTH={width}", f"-GDEPTH={depth}",
                       f"-I{(submission / 'rtl').resolve()}", *map(str, sources),
                       str(ROOT / "t05_hidden_tb.sv")]
            compiled = subprocess.run(command, text=True, capture_output=True,
                                      timeout=180, check=False)
            if compiled.returncode:
                raise RuntimeError(f"compile failed for WIDTH={width} DEPTH={depth}: "
                                   f"{(compiled.stdout + compiled.stderr)[-4000:]}")
            executed = subprocess.run([str(build / "Vtb_hidden_T05"), f"+SEED={seed}"],
                                      text=True, capture_output=True, timeout=300,
                                      check=False)
            if executed.returncode:
                raise RuntimeError(f"simulation failed for WIDTH={width} DEPTH={depth}: "
                                   f"{(executed.stdout + executed.stderr)[-4000:]}")
            rows = GROUP_LINE.findall(executed.stdout)
            if len(rows) != len(BEHAVIOR_GROUPS) or {row[0] for row in rows} != BEHAVIOR_GROUPS:
                raise RuntimeError(f"malformed group output for WIDTH={width} DEPTH={depth}")
            for group, passed, total in rows:
                passed_i, total_i = int(passed), int(total)
                if total_i <= 0 or passed_i < 0 or passed_i > total_i:
                    raise RuntimeError(f"invalid group count for {group}")
                aggregate[group]["cases_passed"] += passed_i
                aggregate[group]["cases_total"] += total_i
                if group in {"AC-26", "AC-27"} and passed_i != total_i:
                    aggregate[group]["safety_violation"] = True
            result = structural_check(submission, sources, width, depth, temporary)
            structural[f"WIDTH={width},DEPTH={depth}"] = result
            aggregate["AC-31"]["cases_total"] += 1
            aggregate["AC-31"]["cases_passed"] += int(result["passed"])
            aggregate["AC-31"]["safety_violation"] |= not result["passed"]
    return {"task_id": "T05", "seed": seed,
            "groups": dict(sorted(aggregate.items())), "structural": structural}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", nargs="?", type=Path)
    parser.add_argument("--reference", action="store_true")
    parser.add_argument("--seed", type=int, default=20260928)
    args = parser.parse_args()
    if args.reference == (args.submission is not None):
        parser.error("select exactly one of SUBMISSION or --reference")
    submission = args.submission if args.submission is not None else ROOT / "reference/T05"
    try:
        result = run(submission, args.seed)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        result = {"task_id": "T05", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
