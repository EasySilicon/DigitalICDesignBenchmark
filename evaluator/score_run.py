#!/usr/bin/env python3
"""Deterministic functional/PPA/time score from evaluator-owned group results.

The input is produced by the independent hidden runner, never by a submission.
This module cannot turn public smoke-test PASS into an official score.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

RULES_PATH = Path(__file__).with_name("score_rules.json")
BASELINES_PATH = Path(__file__).resolve().parents[1] / "benchmark/ppa-baselines.json"


def load_rules() -> dict:
    rules = json.loads(RULES_PATH.read_text())
    if set(rules["tasks"]) != {f"T{i:02d}" for i in range(1, 11)}:
        raise ValueError("score rules must cover T01-T10")
    for task, items in rules["tasks"].items():
        for layer, required in (("F", 60), ("P", 15)):
            if sum(item["points"] for item in items if item["layer"] == layer) != required:
                raise ValueError(f"{task} {layer} points do not sum to {required}")
        ids = [item["id"] for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{task} has duplicate score item IDs")
        for item in items:
            if not item["groups"] or not set(item.get("critical_groups", [])).issubset(item["groups"]):
                raise ValueError(f"{task} {item['id']} has invalid group mapping")
    return rules


def score_functional(task: str, results: dict, rules: dict) -> tuple[float, float, list[dict]]:
    items = rules["tasks"][task]
    expected = {group for item in items for group in item["groups"]}
    if set(results) != expected:
        raise ValueError(f"group IDs mismatch; missing={sorted(expected-set(results))}; "
                         f"extra={sorted(set(results)-expected)}")
    awarded = []
    basic = edge = 0.0
    for item in items:
        passed = total = 0
        group_fractions = []
        safety = False
        critical_failed = False
        for group in item["groups"]:
            outcome = results[group]
            good = outcome["cases_passed"]
            count = outcome["cases_total"]
            if not isinstance(good, int) or not isinstance(count, int) or \
                    isinstance(good, bool) or isinstance(count, bool) or \
                    count <= 0 or good < 0 or good > count:
                raise ValueError(f"invalid case counts for {group}")
            if not isinstance(outcome.get("safety_violation", False), bool):
                raise ValueError(f"invalid safety_violation for {group}")
            passed += good
            total += count
            group_fractions.append(good / count)
            safety |= outcome.get("safety_violation", False)
            critical_failed |= group in item.get("critical_groups", []) and good != count
        if safety or critical_failed:
            points = 0.0
        elif all(fraction == 1.0 for fraction in group_fractions):
            points = float(item["points"])
        elif sum(group_fractions) * 2 >= len(group_fractions):
            points = item["points"] / 2
        else:
            points = 0.0
        awarded.append({"id": item["id"], "layer": item["layer"],
                        "points": points, "possible_points": item["points"],
                        "cases_passed": passed, "cases_total": total,
                        "safety_violation": safety or critical_failed})
        if item["layer"] == "F":
            basic += points
        else:
            edge += points
    return basic, edge, awarded


def ppa_score(measurement: dict, reference: dict) -> float:
    if not measurement.get("routed", False) or \
            measurement.get("setup_worst_slack_ns", -1) < 0 or \
            measurement.get("hold_worst_slack_ns", -1) < 0 or \
            measurement.get("drc_violations") != 0 or \
            measurement.get("annotation_fraction", 0) < 0.95:
        return 0.0
    factors = []
    for key, exponent in (("area_um2", 0.35), ("delay_ns", 0.35),
                          ("energy_per_op_pj", 0.30)):
        actual = measurement[key]
        baseline = reference[key]
        if not all(isinstance(value, (int, float)) and math.isfinite(value) and value > 0
                   for value in (actual, baseline)):
            raise ValueError(f"invalid positive PPA value: {key}")
        factors.append(min(2.0, max(0.5, baseline / actual)) ** exponent)
    return min(20.0, max(0.0, 14.0 * math.prod(factors)))


def ppa_provenance_valid(task: str, measurement: dict, reference: dict) -> bool:
    expected = {"platform": "ASAP7_7p5t_RVT_NLDM", "period_ps": 1000,
                "corner": "WC", "utilization": 10, "density": 0.6,
                "seeds": [11, 29, 47]}
    if task == "T06":
        expected["clock_periods_ps"] = {"wr_clk": 1000, "rd_clk": 1000}
        expected["asynchronous_clock_groups"] = [["wr_clk", "rd_clk"]]
    for record in (measurement, reference):
        rows = record.get("per_seed")
        if record.get("task_id") != task or \
                record.get("measurement_status") != "three_seed" or \
                record.get("parameter_set") != expected or \
                not isinstance(rows, list) or len(rows) != 3 or \
                any(not isinstance(row, dict) or type(row.get("layout_seed")) is not int
                    for row in rows) or \
                sorted(row["layout_seed"] for row in rows) != expected["seeds"] or \
                any(row.get("drc_violations") != 0 or
                    row.get("setup_worst_slack_ns", -1) < 0 or
                    row.get("hold_worst_slack_ns", -1) < 0 or
                    row.get("annotation_fraction", 0) < 0.95 or
                    any(not isinstance(row.get(key), (int, float)) or
                        not math.isfinite(row[key]) or row[key] <= 0
                        for key in ("area_um2", "delay_ns", "energy_per_op_pj"))
                    for row in rows):
            return False
    workload = measurement.get("workload_sha256")
    return isinstance(workload, str) and len(workload) == 64 and \
        workload == reference.get("workload_sha256")


def score_run(payload: dict, rules: dict | None = None) -> dict:
    rules = rules or load_rules()
    task = payload["task_id"]
    results = payload["groups"]
    if task == "T10":
        sustained = payload.get("sustained_throughput_passed")
        if not isinstance(sustained, bool):
            raise ValueError("T10 sustained_throughput_passed must be boolean")
        if not sustained:
            # The stream/structure gate is evaluator-owned and covers facts that
            # cannot be reconstructed from aggregate group counts alone.  Keep
            # the remaining functional diagnostics, but force P_SYSTOLIC to 0.
            results = dict(results)
            systolic = dict(results.get("MM-SYSTOLIC", {}))
            systolic["safety_violation"] = True
            results["MM-SYSTOLIC"] = systolic
    basic, edge, items = score_functional(task, results, rules)
    functional = basic + edge
    duration = payload["elapsed_seconds"]
    limit = payload["time_limit_seconds"]
    if not all(isinstance(value, (int, float)) and math.isfinite(value)
               for value in (duration, limit)) or duration < 0 or limit <= 0:
        raise ValueError("invalid elapsed/time-limit values")
    delivery = payload["delivery_qualified"]
    if not isinstance(delivery, bool):
        raise ValueError("delivery_qualified must be boolean")
    full = functional == rules["functional_total"]
    baselines = json.loads(BASELINES_PATH.read_text())
    official_reference = baselines.get("tasks", {}).get(task)
    baseline_ready = baselines.get("status") in {"partial_1ghz_qualified", "qualified_1ghz"} and \
        isinstance(official_reference, dict) and \
        official_reference.get("qualification_status") == "qualified_1ghz" and \
        payload.get("ppa_reference") == official_reference
    eligible = full and delivery and isinstance(payload.get("ppa_measurement"), dict) and \
        baseline_ready and \
        ppa_provenance_valid(task, payload["ppa_measurement"], payload["ppa_reference"])
    ppa = ppa_score(payload["ppa_measurement"], payload["ppa_reference"]) if eligible else 0.0
    ppa_valid = eligible and ppa > 0
    time = max(0.0, min(5.0, 5.0 * (1.0 - duration / limit))) if ppa_valid else 0.0
    width = rules["ppa_bucket_width"]
    bucket = min(round(20 / width), math.floor(ppa / width + 0.5)) if ppa_valid else 0
    return {"task_id": task, "functional_basic": basic, "functional_edges": edge,
            "functional_total": functional, "full_functional_pass": full,
            "delivery_qualified": delivery, "ppa_eligible": bool(eligible),
            "ppa_score": ppa, "ppa_rank_bucket": bucket,
            "time_score": time, "display_score": functional + ppa + time,
            "score_items": items,
            "rank_key": [functional, bucket, -duration if ppa_valid else 0]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path,
                        help="evaluator-owned group outcomes and PPA/time measurements")
    args = parser.parse_args()
    try:
        print(json.dumps(score_run(json.loads(args.results.read_text())),
                         ensure_ascii=False, indent=2))
    except (OSError, KeyError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
