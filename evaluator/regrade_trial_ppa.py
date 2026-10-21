#!/usr/bin/env python3
"""Recompute trial PPA scores from explicit preserved measurement records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from score_run import load_rules, ppa_score
from power_compile_budget import POLICY_ID, TIMEOUT_STATUS, apply_to_scored_record


POLICY = "setup-frequency-power4-hold-continuous-drc-half-v6"


def assignments(values: list[str]) -> dict[str, str]:
    result = {}
    for value in values:
        task, separator, path = value.partition("=")
        if not separator or task not in {f"T{i:02d}" for i in range(1, 11)} or not path:
            raise ValueError(f"invalid TASK=VALUE assignment: {value}")
        result[task] = path
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial", type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--measurement", action="append", default=[], metavar="TASK=PATH")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    trial = args.trial.resolve(strict=True)
    summary = json.loads((trial / "summary.json").read_text())
    overrides = assignments(args.measurement)
    rules = load_rules()
    baselines = json.loads(
        (Path(__file__).resolve().parents[1] / "benchmark/ppa-baselines.json").read_text()
    )
    summary_rows = {row["task_id"]: row for row in summary.get("tasks", [])}
    rows = []
    for task in (f"T{i:02d}" for i in range(1, 11)):
        measurement_path = (Path(overrides[task]) if task in overrides else
                            trial / "grading" / task / "ppa" / "measurement.json")
        prior = summary_rows.get(task, {})
        row = {
            "task_id": task,
            "old_ppa_score": prior.get("ppa_score"),
            "measurement_file": str(measurement_path),
        }
        archive = trial / 'grading' / task / 'score.json'
        preserved = json.loads(archive.read_text()) if archive.is_file() else prior
        checked = apply_to_scored_record(dict(preserved, task_id=task))
        if checked.get('ppa_status') == TIMEOUT_STATUS:
            row.update(status=TIMEOUT_STATUS, ppa_score=0, time_score=0,
                       power_compile_policy=POLICY_ID,
                       power_compile_records=checked['power_compile_records'])
        elif not measurement_path.is_file():
            row.update({"status": "measurement_unavailable", "ppa_score": None})
        elif task not in baselines.get("tasks", {}):
            row.update({"status": "reference_unavailable", "ppa_score": None})
        else:
            measurement = json.loads(measurement_path.read_text())
            checked = apply_to_scored_record(dict(preserved, task_id=task, ppa_measurement=measurement))
            if checked.get('ppa_status') == TIMEOUT_STATUS:
                row.update(status=TIMEOUT_STATUS, ppa_score=0, time_score=0,
                           power_compile_policy=POLICY_ID,
                           power_compile_records=checked['power_compile_records'],
                           candidate_source_sha256=checked.get('candidate_source_sha256') or measurement['source_sha256'])
                rows.append(row)
                continue
            if measurement.get("measurement_status") != "three_seed":
                row.update({"status": "invalid_measurement", "ppa_score": None})
            else:
                score = ppa_score(
                    measurement, baselines["tasks"][task], rules["ppa_points"],
                    rules["ppa_reference_points"], rules["setup_violation_exponent"]
                )
                row.update({
                    "status": "scored",
                    "setup_worst_slack_ns": measurement["setup_worst_slack_ns"],
                    "hold_worst_slack_ns": measurement["hold_worst_slack_ns"],
                    "drc_violations": measurement["drc_violations"],
                    "ppa_score": score,
                })
        if checked.get('power_compile_policy') == POLICY_ID:
            row.update(power_compile_policy=POLICY_ID,power_compile_records=checked['power_compile_records'],
                       candidate_source_sha256=checked.get('candidate_source_sha256') or checked.get('candidate_sha256')
                           or checked.get('source_sha256') or checked.get('ppa_measurement',{}).get('source_sha256'))
        rows.append(row)

    report = {
        "schema_version": 1,
        "model": args.model,
        "source_trial": str(trial),
        "scoring_policy": POLICY + ('+' + POLICY_ID if any(row.get('power_compile_policy') == POLICY_ID for row in rows) else ''),
        "setup_violation_exponent": rules["setup_violation_exponent"],
        "scored_task_count": sum(row["status"] == "scored" for row in rows),
        "ppa_score_sum_for_available_tasks": sum(
            row["ppa_score"] for row in rows if row["ppa_score"] is not None
        ),
        "tasks": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
