#!/usr/bin/env python3
"""Recompute archived task and summary scores from preserved raw evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from score_run import load_rules, ppa_score, weighted_suite_score


POLICY = "functional50-ppa50-setup-frequency-power4-hold-continuous-drc-half-delivery-v6"


def dump(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def regrade_record(record: dict, rules: dict, baselines: dict) -> dict:
    record = dict(record)
    measurement = record.get("ppa_measurement")
    if isinstance(measurement, dict) and record.get("ppa_eligible"):
        reference = baselines.get("tasks", {}).get(record["task_id"])
        if isinstance(reference, dict):
            ppa = ppa_score(
                measurement, reference, rules["ppa_points"],
                rules["ppa_reference_points"], rules["setup_violation_exponent"]
            )
            duration = record["elapsed_seconds"]
            limit = record["time_limit_seconds"]
            timing = max(0.0, min(
                rules["time_points"],
                rules["time_points"] * (1.0 - duration / limit),
            )) if ppa > 0 else 0.0
            width = rules["ppa_bucket_width"]
            count = record.get("candidate_delivery_error_count", 0)
            penalty = count * rules["candidate_delivery_error_penalty"]
            before = record["functional_total"] + ppa + timing
            record.update({
                "ppa_score": ppa,
                "ppa_rank_bucket": min(
                    round(rules["ppa_points"] / width),
                    int(ppa / width + 0.5),
                ),
                "time_score": timing,
                "candidate_delivery_error_count": count,
                "candidate_delivery_penalty": penalty,
                "display_score_before_candidate_penalty": before,
                "display_score": max(0.0, before - penalty),
            })
    record["scoring_policy"] = POLICY
    return record


def regrade_directory(directory: Path, write: bool) -> list[dict]:
    rules = load_rules()
    baselines = json.loads(
        (Path(__file__).resolve().parents[1] / "benchmark/ppa-baselines.json").read_text()
    )
    rows = []
    task_records = []
    for path in sorted(directory.glob("T[0-9][0-9].json")):
        original = json.loads(path.read_text())
        record = regrade_record(original, rules, baselines)
        if write:
            dump(path, record)
        task_records.append(record)
        rows.append({"task_id": record["task_id"],
                     "old_ppa": original.get("ppa_score"),
                     "new_ppa": record.get("ppa_score")})

    if not task_records:
        raise ValueError("Regrading requires local raw task records; published summary-only results must not be overwritten")
    summary_path = directory / "summary.json"
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text())
        summary["scoring_policy"] = POLICY
        summary["ppa_score_sum_for_available_tasks"] = sum(
            row["ppa_score"] for row in task_records if row.get("ppa_score") is not None
        )
        summary["time_score_sum_for_available_tasks"] = sum(
            row["time_score"] for row in task_records if row.get("time_score") is not None
        )
        summary["display_score_subtotal_with_unscored_components_omitted"] = sum(
            row["display_score"] for row in task_records
            if row.get("display_score") is not None
        )
        weighted = weighted_suite_score(
            {row["task_id"]: row.get("display_score") for row in task_records},
            rules,
        )
        summary["task_weights"] = rules["task_weights"]
        summary["weighted_display_score_with_unscored_components_omitted"] = \
            weighted["weighted_display_score"]
        summary["weighted_display_score_possible"] = \
            weighted["weighted_display_possible"]
        summary["weighted_task_contributions"] = \
            weighted["weighted_contributions"]
        summary["tasks"] = [
            {key: row.get(key) for key in (
                "task_id", "functional_total", "ppa_score", "time_score",
                "display_score", "score_status"
            )}
            for row in task_records
        ]
        if write:
            dump(summary_path, summary)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    output = {}
    for directory in args.directories:
        output[str(directory)] = regrade_directory(directory, args.write)
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
