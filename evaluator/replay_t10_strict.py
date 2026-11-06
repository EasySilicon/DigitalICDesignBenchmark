"""Score the strict corpus from an immutable, vector-verified RTL trace.

This does not compile RTL, invoke a model, or launch PPA. The retained trace
may include additional normal-domain diagnostics; the scored subsequence
must exactly equal the current strict generator, including its phase order.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import tempfile

from ppa_aggregate import source_hash
from runner_t10 import parse_output, write_vectors
from runner_t10_mma import mma_cases
from runner_t10_stream import functional_passed, stream_cases
from score_run import load_rules, score_functional
from t10_fast_oracle import check_output_fast
from t10_common import EVALUATOR_ROOT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_cases(provenance, seed):
    cases, phases = mma_cases(seed)
    with tempfile.TemporaryDirectory(prefix="t10-replay-vectors-") as temp:
        directory = Path(temp)
        write_vectors(directory, cases)
        (directory / "phase.mem").write_text("\n".join(f"{p:x}" for p in phases) + "\n")
        actual = {p.name: sha(p) for p in directory.glob("*.mem")}
    if actual != provenance["vector_sha256"]:
        raise ValueError("retained trace vectors differ from the regenerated corpus")
    selected = {i for i, c in enumerate(cases)
                if not (c.case_id or "").startswith("mma-normal-v1")}
    core, core_phases = stream_cases(seed)
    indices = sorted(selected)
    if ([cases[i] for i in indices] != core or
            [phases[i] for i in indices] != core_phases):
        raise ValueError("scored subsequence is not the exact strict corpus")
    return cases, selected


def run(submission: Path, trace: Path, structure_path: Path, output: Path):
    provenance = json.loads((trace / "provenance.json").read_text())
    old = json.loads((trace / "report.json").read_text())
    source = source_hash(submission)
    if source != provenance["candidate_source_sha256"] or source != old["candidate_source_sha256"]:
        raise ValueError("trace and submission source hashes differ")
    seed = provenance["seed"]
    oracle = EVALUATOR_ROOT.parent / "benchmark/tasks/T10/public/matmul_oracle.py"
    if sha(oracle) != provenance["legacy_oracle_sha256"]:
        raise ValueError("strict numerical oracle differs from the retained version")
    structure = json.loads(structure_path.read_text())
    if structure.get("candidate_source_sha256") != source:
        raise ValueError("structure evidence belongs to another submission")
    cases, selected = verified_cases(provenance, seed)
    simulation = trace / "simulation.log"
    log = simulation.read_text()

    @lru_cache(maxsize=8192)
    def numeric(a, b, a_scale, b_scale, mode, rows):
        return check_output_fast(list(a), list(b), a_scale, b_scale, mode, list(rows))

    def check(a, b, a_scale, b_scale, mode, rows):
        return numeric(tuple(a), tuple(b), a_scale, b_scale, mode, tuple(rows))

    groups, failures = parse_output(log, cases, structure,
                                    numeric_checker=check, selected_cases=selected)
    auxiliary = set(range(len(cases))) - selected
    aux_groups, aux_failures = parse_output(log, cases, structure,
                                           numeric_checker=check, selected_cases=auxiliary)
    reset_path = trace / "reset_simulation.log"
    reset_ok = bool(old["reset_probe_passed"] and "MM_RESET_STREAM PASS" in reset_path.read_text())
    groups["MM-PROTO"]["cases_total"] += 1
    groups["MM-PROTO"]["cases_passed"] += reset_ok
    if not reset_ok:
        failures.append(dict(group="MM-PROTO", case="stream_reset_probe", error="reset probe failed"))
    marker = re.findall(r"^MM_STREAM input_bubble_phases=[01]{14} finished=\d+$", log, re.M)
    report = dict(task_id="T10", policy_id="t10-strict-range-v1", numerical_profile="exact-dot-v1",
                  phase="run" if old["simulation_returncode"] == 0 else "simulation-failed",
                  seed=seed, cases=len(cases), scored_cases=len(selected),
                  groups=groups, failures=failures, structure=structure,
                  reset_probe_passed=reset_ok, stream_line=marker[0] if len(marker) == 1 else "",
                  additional_diagnostic_cases=len(auxiliary),
                  additional_diagnostic_groups=aux_groups,
                  additional_diagnostic_failures=aux_failures,
                  candidate_source_sha256=source,
                  evidence=dict(kind="retained RTL simulation; strict oracle replay",
                                trace_provenance_sha256=sha(trace / "provenance.json"),
                                trace_report_sha256=sha(trace / "report.json"),
                                simulation_sha256=sha(simulation), reset_sha256=sha(reset_path),
                                structure_sha256=sha(structure_path),
                                oracle_sha256=sha(oracle),
                                all_input_vectors_verified=True,
                                scored_subsequence_verified=True),
                  ppa_remeasured=False, model_session_started=False)
    report["full_functional_pass"] = functional_passed(report) and not aux_failures
    basic, edges, items = score_functional("T10", groups, load_rules())
    score = dict(task_id="T10", functional_basic=basic, functional_edges=edges,
                 functional_total=basic + edges, score_items=items,
                 full_functional_pass=report["full_functional_pass"])
    if source_hash(submission) != source:
        raise ValueError("submission changed during replay")
    output.mkdir(parents=True, exist_ok=False)
    (output / "functional.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "functional_score.json").write_text(json.dumps(score, indent=2) + "\n")
    return score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--structure", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.submission, args.trace, args.structure, args.output), indent=2))


if __name__ == "__main__":
    main()
