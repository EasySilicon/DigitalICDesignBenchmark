#!/usr/bin/env python3
"""Separate T10 MMA-inspired functional audit; does not score or launch PPA."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from ppa_aggregate import source_hash
from public_check import sources_from_filelist
from runner_t10 import CASE_LINE, ROW_LINE, write_vectors
from runner_t10_stream import compile_hierarchical, stream_cases
from t10_common import EVALUATOR_ROOT
from t10_mma_cases import precision_cases, range_stress_cases
from t10_mma_oracle import PROFILE_ID, check_output_mma
from t10_structure_with_slang import inspect as inspect_structure


def save(path: Path, value: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


def mma_cases(seed: int = 11) -> tuple[list, list[int]]:
    cases, phases = stream_cases(seed)
    # The existing harness finishes with a backpressured train. Returning
    # from that train straight to unrestricted phase 0 would demand immediate
    # full input credit before its pending results have drained. Keep all new
    # arithmetic probes in the original, pre-backpressure numeric phase.
    boundary = next(i for i, phase in enumerate(phases) if phase != 0)
    extra = precision_cases(seed) + range_stress_cases()
    return (cases[:boundary] + extra + cases[boundary:],
            phases[:boundary] + [0] * len(extra) + phases[boundary:])


def evaluate(log: str, cases: list) -> dict:
    rows, row_counts = defaultdict(dict), Counter()
    for index, row, value in ROW_LINE.findall(log):
        rows[int(index)][int(row)] = int(value, 16)
        row_counts[int(index)] += 1
    flags, flag_counts = {}, Counter()
    for index, protocol, timing, output, count in CASE_LINE.findall(log):
        flags[int(index)] = (protocol == "1", timing == "1", output == "1", int(count))
        flag_counts[int(index)] += 1
    groups, details, failures, diagnostics = defaultdict(Counter), [], [], []
    mode_coverage, reasons = defaultdict(Counter), Counter()
    for index, case in enumerate(cases):
        group = groups[case.group]
        group["cases_total"] += 1
        observed = rows[index]
        protocol, timing, output, count = flags.get(index, (False, False, False, 0))
        complete = count == row_counts[index] == 16 and set(observed) == set(range(16))
        interface_ok = protocol and timing and output and complete and flag_counts[index] == 1
        numeric = check_output_mma(list(case.a), list(case.b), case.a_scale, case.b_scale,
                                   case.mode, [observed[r] for r in range(16)]) if complete else None
        errors = list(numeric.errors) if numeric else ["missing/duplicate output rows"]
        if not interface_ok:
            errors.append("protocol, latency, throughput, row or report completion check failed")
        diagnostic_lanes = numeric.diagnostic_lanes if numeric else 0
        checked_lanes = numeric.checked_lanes if numeric else 0
        verdict = "fail" if errors else "diagnostic" if diagnostic_lanes else "pass"
        group["cases_failed" if errors else "cases_with_diagnostics" if diagnostic_lanes
              else "cases_fully_checked_passed"] += 1
        group["checked_lanes"] += checked_lanes
        group["diagnostic_lanes"] += diagnostic_lanes
        if case.case_id and case.case_id.startswith("mma-normal-v1"):
            mode_coverage[case.mode]["cases_total"] += 1
            mode_coverage[case.mode]["fully_checked_passed"] += verdict == "pass"
        if numeric:
            reasons.update(numeric.reasons)
        detail = dict(index=index, case_id=case.case_id, mode=case.mode, group=case.group,
                      verdict=verdict, checked_lanes=checked_lanes,
                      diagnostic_lanes=diagnostic_lanes,
                      subnormal_affected_lanes=numeric.subnormal_affected_lanes if numeric else 0,
                      interface_passed=interface_ok, errors=errors[:3],
                      diagnostic_examples=numeric.diagnostics if numeric else [])
        details.append(detail)
        if errors:
            failures.append(detail)
        if diagnostic_lanes:
            diagnostics.append(detail)
    stream = re.findall(r"^MM_STREAM input_bubble_phases=([01]{14}) finished=(\d+)$", log, re.M)
    stream_ok = stream == [("0" * 14, str(len(cases)))]
    coverage_ok = set(mode_coverage) == set(range(2, 10)) and all(
        row["cases_total"] == row["fully_checked_passed"] == 32 for row in mode_coverage.values())
    unexpected = bool((set(rows) | set(flags)) - set(range(len(cases))))
    return dict(cases=len(cases), cases_fully_checked_passed=sum(x["verdict"] == "pass" for x in details),
                cases_with_diagnostics=len(diagnostics), cases_failed=len(failures),
                checked_lanes=sum(x["checked_lanes"] for x in details),
                diagnostic_lanes=sum(x["diagnostic_lanes"] for x in details),
                groups=dict(groups), normal_domain_coverage=dict(mode_coverage),
                normal_domain_coverage_passed=coverage_ok, stream_passed=stream_ok,
                unexpected_reports=unexpected, reason_counts=dict(reasons),
                numerical_and_interface_passed=not failures and stream_ok and coverage_ok and not unexpected,
                failures=failures, diagnostic_cases=diagnostics, case_results=details)


def run(submission: Path, output: Path, seed: int = 11,
        structure_evidence: Path | None = None) -> dict:
    submission = submission.resolve(strict=True)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    source = source_hash(submission)
    old_oracle = EVALUATOR_ROOT.parent / "benchmark/tasks/T10/public/matmul_oracle.py"
    legacy_hash = hashlib.sha256(old_oracle.read_bytes()).hexdigest()
    def progress(phase):
        save(output / "status.json", dict(phase=phase, profile=PROFILE_ID, seed=seed,
                                          candidate_source_sha256=source,
                                          wall_seconds=time.monotonic() - started))
    progress("generating_vectors")
    cases, phases = mma_cases(seed)
    original_count = len(cases) - 338
    if len(cases) > 4096:
        raise ValueError("stream testbench MAX_CASES exceeded")
    vectors = output / "vectors"
    vectors.mkdir()
    write_vectors(vectors, cases)
    (vectors / "phase.mem").write_text("\n".join(f"{phase:x}" for phase in phases) + "\n")
    provenance = dict(profile=PROFILE_ID, seed=seed, candidate_source_sha256=source,
                      original_stream_cases=original_count, added_normal_cases=256,
                      retained_range_probes=82, legacy_oracle_sha256=legacy_hash,
                      vector_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in vectors.glob("*.mem")},
                      evaluator_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in [Path(__file__), EVALUATOR_ROOT / "t10_mma_cases.py",
                                                  old_oracle.with_name("matmul_oracle_mma.py")]},
                      score_eligible=False, power_evaluation="not_requested_or_launched")
    if structure_evidence:
        evidence = json.loads(structure_evidence.read_text())
        structure = evidence.get("structure", evidence)
        bound_hash = structure.get("candidate_source_sha256", evidence.get("candidate_source_sha256"))
        if bound_hash != source or structure.get("passed") is not True:
            raise ValueError("structure evidence must be passed and bound to the same RTL hash")
        provenance["reused_structure_evidence"] = dict(
            path=str(structure_evidence.resolve()),
            sha256=hashlib.sha256(structure_evidence.read_bytes()).hexdigest())
    else:
        progress("checking_structure")
        structure = inspect_structure(submission)
    save(output / "provenance.json", provenance)
    save(output / "structure.json", structure)
    progress("compiling_functional_rtl")
    sources = list(map(str, sources_from_filelist(submission)))
    def compile_tb(top, build):
        command = ["verilator", "--binary", "--hierarchical", "--trace", "--timing", "--assert",
                   "-Wno-fatal", "-j", "4", "--top-module", top, "--Mdir", str(build),
                   *sources, str(EVALUATOR_ROOT / "hidden" / (top + ".sv"))]
        compiled, build, transcript = compile_hierarchical(command, build)
        (output / (top + "_compile.log")).write_text(transcript)
        if compiled.returncode:
            raise RuntimeError(f"{top} functional compilation failed; see retained log")
        return build / ("V" + top)
    binary = compile_tb("tb_hidden_T10_stream", output / "build")
    progress("simulating_functional_rtl")
    command = [str(binary), f"+VECTORS={vectors}", f"+CASE_COUNT={len(cases)}", "+BP_MIXED"]
    executed = subprocess.run(command, capture_output=True, text=True, timeout=1200, check=False)
    transcript = executed.stdout + executed.stderr
    (output / "simulation.log").write_text(transcript)
    progress("checking_mma_profile")
    result = evaluate(transcript, cases)
    progress("checking_runtime_reset")
    binary = compile_tb("tb_hidden_T10_reset", output / "reset_build")
    reset = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120, check=False)
    (output / "reset_simulation.log").write_text(reset.stdout + reset.stderr)
    reset_ok = reset.returncode == 0 and "MM_RESET_STREAM PASS" in reset.stdout
    if source_hash(submission) != source:
        raise RuntimeError("candidate RTL changed during the audit")
    if hashlib.sha256(old_oracle.read_bytes()).hexdigest() != legacy_hash:
        raise RuntimeError("legacy oracle changed during the audit")
    result.update(task_id="T10", profile=PROFILE_ID, seed=seed, candidate_source_sha256=source,
                  structure=structure, reset_probe_passed=reset_ok, score_eligible=False,
                  power_evaluation="not_requested_or_launched", source_unchanged=True,
                  legacy_oracle_unchanged=True, simulation_returncode=executed.returncode,
                  functional_passed=bool(result["numerical_and_interface_passed"] and
                                         structure.get("passed") is True and reset_ok and
                                         executed.returncode == 0),
                  acceptance_scope="MMA-inspired numerical envelope and unchanged T10 interfaces; "
                                   "diagnostic lanes are excluded, never counted as numerical passes",
                  wall_seconds=time.monotonic() - started)
    save(output / "report.json", result)
    progress("finished")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True, help="new directory for retained evidence")
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--structure-evidence", type=Path)
    args = parser.parse_args()
    try:
        result = run(args.submission, args.output_dir, args.seed, args.structure_evidence)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result = dict(task_id="T10", profile=PROFILE_ID, phase="infrastructure",
                      functional_passed=False, error=str(exc), score_eligible=False)
        if args.output_dir.exists() and not (args.output_dir / "report.json").exists():
            save(args.output_dir / "error.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in
                     ("case_results", "diagnostic_cases", "failures")}, indent=2))
    return 0 if result["functional_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
