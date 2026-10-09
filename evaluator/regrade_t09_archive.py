#!/usr/bin/env python3
"""Publish explicitly replayed T09 reports, preserving other tasks and raw RTL.

The plan lists model, origin, submission, report, elapsed, delivery, and optional
measurement paths. This does not run candidate scripts or any physical tools.
Without --write it validates and computes a dry run. Frozen inputs, a complete
22-case cycle inventory and PPA source binding are required before publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__:
    from .ppa_aggregate import source_hash
    from .public_check import sources_from_filelist
    from .score_run import load_rules, ppa_provenance_valid, score_run, weighted_suite_score
    from .t09_reference_freeze import TOTALS, publish_atomic
    from .t09_timing_check import apply_timing_groups
else:
    from ppa_aggregate import source_hash
    from public_check import sources_from_filelist
    from score_run import load_rules, ppa_provenance_valid, score_run, weighted_suite_score
    from t09_reference_freeze import TOTALS, publish_atomic
    from t09_timing_check import apply_timing_groups

ROOT = Path(__file__).resolve().parents[1]
POLICY = "t09_group_cycles10_v1"
SCORE_KEYS = ("functional_total", "full_functional_pass", "ppa_score", "time_score", "display_score")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def regrade_record(old: dict, grade: dict, entry: dict, reference: dict, rules: dict) -> dict:
    submission = Path(entry["submission"])
    digest = source_hash(submission)
    if grade.get("phase") != "scored" or grade.get("scoring_policy") != POLICY:
        raise ValueError("T09 replay did not finish under the current policy")
    groups = grade["groups"]
    if set(groups) != set(TOTALS) or any(groups[name].get("cases_total") != count
                                        for name, count in TOTALS.items()):
        raise ValueError("T09 replay inventory changed or incomplete")
    timing = grade["diagnostics"]["timing_cycles"]
    checked = {}
    apply_timing_groups(checked, timing)
    if checked["CPU-PIPE-CYCLES"] != groups["CPU-PIPE-CYCLES"]:
        raise ValueError("cycle-group totals differ from individual outcomes")
    actual_sources = {str(path.relative_to(submission/'rtl')): sha(path)
                      for path in sources_from_filelist(submission)}
    if timing.get("rtl_sha256") != actual_sources:
        raise ValueError("replay belongs to another RTL snapshot")
    if old.get("candidate_sha256") not in {None, digest}:
        raise ValueError("candidate differs from the archived answer")
    payload = {"task_id": "T09", "groups": groups,
               "elapsed_seconds": entry["elapsed"], "time_limit_seconds": old["time_limit_seconds"],
               "delivery_qualified": entry["delivery"],
               "candidate_delivery_error_count": old.get("candidate_delivery_error_count", 0)}
    measurement = read(Path(entry["measurement"])) if entry.get("measurement") else None
    if measurement is not None:
        if measurement.get("source_sha256") != digest or not ppa_provenance_valid("T09", measurement, reference):
            raise ValueError("PPA evidence does not match the answer or frozen workload")
        payload.update(ppa_measurement=measurement, ppa_reference=reference)
    score = score_run(payload, rules)
    if score["full_functional_pass"] and measurement is None and old.get("ppa_score") not in {0, 0.0}:
        raise ValueError("missing valid PPA evidence for a previously measured passing answer")
    result = dict(old)
    result.update(score)
    result.update(elapsed_seconds=entry["elapsed"], functional_groups=groups,
                  functional_possible=50, ppa_possible=50, time_possible=5, display_possible=105,
                  score_status="scored", grade_phase="regraded-current-t09-policy",
                  scoring_policy=POLICY, ranking_eligible=False,
                  candidate_sha256=digest,
                  cycle_cases_passed=groups["CPU-PIPE-CYCLES"]["cases_passed"], cycle_cases_total=22)
    if measurement is not None:
        result["ppa_measurement"] = measurement
    if not score["full_functional_pass"]:
        result["ppa_zero_reason"] = "Current T09 functional/cycle score is below 50; retained PPA measurements are diagnostic only."
    elif not score["ppa_eligible"]:
        result["ppa_zero_reason"] = old.get("ppa_failure_reason", "Preserved adjudicated candidate synthesis failure; no valid routed PPA measurement.")
    else:
        result.pop("ppa_zero_reason", None)
    result["t09_regrade"] = {
        "policy": POLICY, "original_submission": entry["origin"],
        "rtl_sha256": actual_sources, "source_sha256": digest,
        "original_elapsed_seconds_preserved": True,
        "prior_scores": {key: old.get(key) for key in SCORE_KEYS},
        "prior_scoring_policy": old.get("scoring_policy"),
        "ppa_reference_source_sha256": reference["source_sha256"],
        "physical_flow_rerun": False,
        "measurement_file": entry.get("measurement"),
    }
    return result


def refresh_summary(summary: dict, records: list[dict], updated: dict, rules: dict) -> dict:
    result = dict(summary)
    result["tasks"] = [dict(row, **{key: updated[key] for key in (
        *SCORE_KEYS, "delivery_qualified", "ppa_eligible", "ppa_rank_bucket", "elapsed_seconds",
        "candidate_delivery_error_count", "candidate_delivery_penalty", "display_score_before_candidate_penalty",
        "grade_phase", "score_status", "scoring_policy", "cycle_cases_passed", "cycle_cases_total")})
        if row["task_id"] == "T09" else row for row in summary["tasks"]]
    sums = {name: math.fsum(row[key] for row in records if row.get(key) is not None)
            for name, key in (("functional_score_sum", "functional_total"),
                              ("ppa_score_sum_for_available_tasks", "ppa_score"),
                              ("time_score_sum_for_available_tasks", "time_score"),
                              ("display_score_subtotal_with_unscored_components_omitted", "display_score"))}
    result.update(sums)
    for alias, canonical in (("functional_total_sum", "functional_score_sum"),
                              ("ppa_score_sum", "ppa_score_sum_for_available_tasks"),
                              ("time_score_sum", "time_score_sum_for_available_tasks"),
                              ("display_score_sum", "display_score_subtotal_with_unscored_components_omitted")):
        if alias in result:
            result[alias] = sums[canonical]
    weighted = weighted_suite_score({row["task_id"]: row.get("display_score") for row in records}, rules)
    result.update(task_weights=rules["task_weights"],
                  weighted_display_score_with_unscored_components_omitted=weighted["weighted_display_score"],
                  weighted_display_score_possible=weighted["weighted_display_possible"],
                  weighted_task_contributions=weighted["weighted_contributions"],
                  covered_task_weight=weighted["covered_task_weight"],
                  covered_display_possible=weighted["covered_display_possible"],
                  full_functional_task_count=sum(row.get("full_functional_pass") is True for row in records))
    for alias, value in (("weighted_display_score", weighted["weighted_display_score"]),
                          ("weighted_display_possible", weighted["weighted_display_possible"]),
                          ("weighted_contributions", weighted["weighted_contributions"])):
        if alias in result:
            result[alias] = value
    policies = dict(result.get("task_scoring_policies", {}))
    policies["T09"] = POLICY
    result["task_scoring_policies"] = policies
    result["t09_regrade"] = updated["t09_regrade"]
    return result


def run(plan: Path, results: Path, write: bool) -> list[dict]:
    entries = read(plan)["models"]
    if len({row["model"] for row in entries}) != len(entries):
        raise ValueError("duplicate model in regrade plan")
    reference = read(ROOT/"benchmark/ppa-baselines.json")["tasks"]["T09"]
    rules = load_rules()
    prepared, reports = [], []
    for entry in entries:
        folder = results/entry["model"]
        old, summary = read(folder/"T09.json"), read(folder/"summary.json")
        grade = read(Path(entry["report"]))
        updated = regrade_record(old, grade, entry, reference, rules)
        records = [updated if number == 9 else read(folder/f"T{number:02d}.json")
                   for number in range(1, 11)]
        refreshed = refresh_summary(summary, records, updated, rules)
        stamp = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
        updated["result_revision_date"] = refreshed["result_revision_date"] = stamp[:10]
        evidence = folder/"T09_regrade_20261009"
        if write and evidence.exists():
            raise ValueError("regrade evidence destination exists; do not overwrite historical evidence")
        updated["t09_regrade"].update(date=stamp, report=str(evidence/"functional.json"),
                                     report_sha256=sha(Path(entry["report"])),
                                     checker_sha256={name: sha(ROOT/'evaluator'/name) for name in (
                                         "t09_check.py", "t09_timing_check.py", "t09_timing_tb.sv",
                                         "score_run.py", "score_rules.json", "regrade_t09_archive.py")})
        prepared.append((folder, evidence, old, summary, Path(entry["report"]), updated, refreshed))
        reports.append({"model": entry["model"], "old_functional": old["functional_total"],
                        "cycles": updated["cycle_cases_passed"], "functional": updated["functional_total"],
                        "ppa": updated["ppa_score"], "time": updated["time_score"],
                        "display": updated["display_score"],
                        "weighted_total": refreshed["weighted_display_score_with_unscored_components_omitted"]})
    # Validate every replay before touching any model's authoritative records.
    if write:
        for folder, evidence, old, summary, grade_path, updated, refreshed in prepared:
            evidence.mkdir()
            for name, value in (("previous_T09.json", old), ("previous_summary.json", summary)):
                publish_atomic(evidence/name, json.dumps(value, indent=2, ensure_ascii=False)+'\n')
            shutil.copy2(grade_path, evidence/"functional.json")
            publish_atomic(folder/"T09.json", json.dumps(updated, indent=2, ensure_ascii=False)+'\n')
            publish_atomic(folder/"summary.json", json.dumps(refreshed, indent=2, ensure_ascii=False)+'\n')
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--results", type=Path, default=ROOT/"results")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.plan, args.results, args.write), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
