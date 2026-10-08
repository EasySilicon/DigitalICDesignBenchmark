#!/usr/bin/env python3
"""Evaluator-owned streaming T10 pilot; no routed PPA score until baseline qualification."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from t10_common import DEFAULT_BENCHMARK_ROOT
from runner_t10_stream import run

sys.path.insert(0, str(DEFAULT_BENCHMARK_ROOT / "evaluator"))
from delivery_check import check as check_delivery  # noqa: E402
from score_run import load_rules, score_functional  # noqa: E402


def sustained_pass(functional: dict) -> bool:
    if "groups" not in functional or "MM-SYSTOLIC" not in functional["groups"]:
        return False
    systolic = functional["groups"]["MM-SYSTOLIC"]
    stream_status = re.fullmatch(
        r"MM_STREAM input_bubble_phases=([01]{14}) finished=(\d+)",
        functional.get("stream_line", ""))
    return (functional.get("phase") == "run" and
            systolic["cases_passed"] == systolic["cases_total"] and
            functional.get("structure", {}).get("passed") is True and
            stream_status is not None and stream_status.group(1) == "0" * 14 and
            int(stream_status.group(2)) == functional.get("cases"))


def summarize(delivery: dict, functional: dict) -> dict:
    rules = load_rules()
    possible = rules["functional_total"]
    if "groups" not in functional:
        return {
            "task_id": "T10", "status": "streaming_functional_pilot_only",
            "phase": functional.get("phase", "infrastructure"),
            "functional_basic": 0, "functional_edges": 0,
            "functional_total": 0, "functional_possible": possible,
            "sustained_throughput_passed": False,
            "delivery_qualified": delivery["delivery_qualified"],
            "structure": functional.get("structure"), "score_items": [],
            "ppa_baseline_status": "pending_independent_reference_and_three_seed_route",
            "ppa_score": 0, "time_score": 0, "display_score": 0,
        }
    basic, edges, items = score_functional("T10", functional["groups"], rules)
    functional_total = basic + edges
    sustained = sustained_pass(functional)
    ppa_time_ineligible = functional_total < possible or not sustained
    result = {
        "task_id": "T10", "status": "streaming_functional_pilot_only",
        "functional_basic": basic, "functional_edges": edges,
        "functional_total": functional_total,
        "functional_possible": possible,
        "sustained_throughput_passed": sustained,
        "official_score_eligible": False,
        "delivery_qualified": delivery["delivery_qualified"],
        "structure": functional["structure"], "score_items": items,
        "ppa_baseline_status": "pending_independent_reference_and_three_seed_route",
        "ppa_score": 0 if ppa_time_ineligible else None,
        "time_score": 0 if ppa_time_ineligible else None,
        "display_score": functional_total if ppa_time_ineligible else None,
    }
    return result


def grade(submission: Path, output: Path, seed: int) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    delivery = check_delivery("T10", submission, seed, 600, None, None)
    (output / "delivery.json").write_text(json.dumps(delivery, indent=2) + "\n")
    functional = run(submission, seed, output / "functional_artifacts")
    (output / "functional.json").write_text(json.dumps(functional, indent=2) + "\n")
    result = summarize(delivery, functional)
    (output / "pilot_report.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=20260925)
    args = parser.parse_args()
    result = grade(args.submission, args.output_dir, args.seed)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
