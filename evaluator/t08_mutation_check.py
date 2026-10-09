#!/usr/bin/env python3
"""Host-only T08 feature checker qualification, not candidate self-testing.

Pass an already-correct streaming-parser submission as --baseline. No corrected
RTL is bundled here. These anchors target the pilot parser; a structurally
different baseline needs explicit anchor updates, never a silent skipped mutant.
All edits are mechanical mutations of fresh temporary copies; the baseline is
never written. Compile failure is NOT a successful detection.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from evaluator.t08_check import evaluate

REPO = Path(__file__).resolve().parent.parent
MUTATIONS = {
    "reserved_admitted": ("tci_reg[11:0] == 12'hfff", "1'b0", (10,)),
    "invalid_slots_match": ("valid_reg[i] && tci_reg", "1'b1 && tci_reg", (9,)),
    "live_enable": (
        "wire frame_enable = in_frame ? enable_reg : cfg_enable;",
        "wire frame_enable = cfg_enable;", (14, 15)),
    "swapped_tci": (
        "terminal_tag ? tci_reg : 16'b0",
        "terminal_tag ? {tci_reg[7:0], tci_reg[15:8]} : 16'b0", (12,)),
    "terminal_header_ignored": (
        "offset == 5'd17 && tagged_reg",
        "offset == 5'd17 && tagged_reg && !s_last", (13,)),
    "mac_bad_cleared": (
        "s_bad | (terminal && policy_bad)", "(terminal && policy_bad)", (3,)),
    "header_wrap": ("if (offset < 5'd18)", "if (1'b1)", (9,)),
    "drop_event_missing": (
        "assign vlan_drop = terminal && policy_bad && !s_bad;",
        "assign vlan_drop = 1'b0;", (8,)),
    "live_list": (
        "valid_reg[i] && tci_reg[11:0] == vids_reg[12*i +: 12]",
        "cfg_valid[i] && tci_reg[11:0] == cfg_vids[12*i +: 12]", (19, 20)),
    "live_valid_mask": ("valid_reg[i] && tci_reg", "cfg_valid[i] && tci_reg", (20,)),
    "live_vids": ("== vids_reg[12*i +: 12]", "== cfg_vids[12*i +: 12]", (19,)),
    "live_untagged_flag": (
        "deny_now = !untagged_reg;", "deny_now = !cfg_accept_untagged;", (21,)),
    "live_priority_flag": (
        "deny_now = !priority_reg;", "deny_now = !cfg_accept_priority;", (22,)),
    "first_last_old_snapshot": (
        "wire frame_enable = in_frame ? enable_reg : cfg_enable;",
        "wire frame_enable = enable_reg;", (28, 31)),
    "first_last_stale_header": (
        "if (!in_frame) begin\n            tagged_now = 1'b0;\n            deny_now = 1'b1;",
        "if (!in_frame && !s_last) begin\n            tagged_now = 1'b0;\n            deny_now = 1'b1;", (36,)),
    "bypass_short_rejected": (
        "wire policy_bad = frame_enable && deny_now;",
        "wire policy_bad = deny_now;", (29, 30)),
    "mac_bad_policy_double_counted": (
        "assign vlan_drop = terminal && policy_bad && !s_bad;",
        "assign vlan_drop = terminal && policy_bad;", (32,)),
}
UNIMPLEMENTED_WITNESSES = (8, 9, 10, 11, 12, 13, 14, 15, 16, 19, 20, 21, 22)


def mutate(source: str, name: str) -> str:
    needle, replacement, _ = MUTATIONS[name]
    if source.count(needle) != 1:
        raise ValueError(f"mutation anchor is not unique: {name}")
    return source.replace(needle, replacement, 1)


def compiled(report: dict) -> bool:
    runs = [run for case in report["cases"].values() for run in case["runs"]]
    return bool(runs) and all("exit_code" in run and not run.get("error") for run in runs)


def classify(report: dict, witnesses: tuple[int, ...]) -> dict:
    records = report["cases"]
    failures = [int(case) for case, record in records.items() if not record["passed"]]
    is_compiled = compiled(report)
    witness_runs = [records.get(str(case), records.get(case, {})).get("runs", [])
                    for case in witnesses]
    expected_failures = all(runs and all(not run.get("passed", True) for run in runs)
                            for runs in witness_runs)
    return {"compiled": is_compiled, "detected": is_compiled and expected_failures,
            "failed_cases": sorted(failures), "expected_failure_cases": list(witnesses)}


def qualify(baseline: Path, output: Path, *, jobs: int = 1) -> dict:
    if not 1 <= jobs <= 4:
        raise ValueError("jobs must be between one and four")
    baseline = baseline.resolve()
    output = output.resolve()
    # Refuse a report destination inside the original candidate submission.
    if output == baseline or baseline in output.parents:
        raise ValueError("qualification output must be outside the baseline submission")
    output.mkdir(parents=True, exist_ok=True)
    positive = evaluate(baseline, output / "baseline.json")
    if not compiled(positive) or not positive["full_functional_pass"]:
        raise ValueError("baseline must compile and pass the complete current judge")
    source = (baseline / "rtl/rx_vlan_admission.sv").read_text()
    # Preflight every edit before spending time compiling variants.
    mutated = {name: mutate(source, name) for name in MUTATIONS}
    mutated["unimplemented"] = (REPO / "benchmark/tasks/T08/starter/rtl/rx_vlan_admission.sv").read_text()
    records = {}
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_t08_feature_mutants_") as temporary:
        root = Path(temporary)
        for name, feature_source in mutated.items():
            submission = root / name
            shutil.copytree(baseline / "rtl", submission / "rtl")
            (submission / "rtl/rx_vlan_admission.sv").write_text(feature_source)
        def check(name):
            report = evaluate(root / name, output / (name + ".json"))
            witnesses = UNIMPLEMENTED_WITNESSES if name == "unimplemented" else MUTATIONS[name][2]
            return name, classify(report, witnesses)
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            for future in as_completed([pool.submit(check, name) for name in mutated]):
                name, record = future.result()
                records[name] = record
                print(json.dumps({"variant": name, **record}), flush=True)
    result = {
        "task": "T08", "scope": "host-only independent checker qualification",
        "judge_revision": positive["judge_revision"],
        "completed_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "baseline_rtl_sha256": {str(path.relative_to(baseline / "rtl")):
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((baseline / "rtl").rglob("*")) if path.is_file()},
        "judge_sha256": {str(path.relative_to(REPO)):
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (REPO / "evaluator/t08_check.py", REPO / "evaluator/public/tb_T08.sv",
                         REPO / "evaluator/fixtures/t11_mac/tb_acceptance.sv")},
        "baseline_passed": True,
        "baseline_run_count": sum(len(c["runs"]) for c in positive["cases"].values()),
        "variant_count": len(records),
        "detected_count": sum(record["detected"] for record in records.values()),
        "passed": all(record["detected"] for record in records.values()),
        "variants": records,
        "limitations": ["Finite mutation set is not proof of detecting every possible RTL error.",
                       "Mutation anchors are specific to the qualified streaming parser.",
                       "Existing frozen trials and original submissions are unchanged."],
    }
    (output / "qualification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1,5), default=1)
    args = parser.parse_args()
    result = qualify(args.baseline, args.output_dir, jobs=args.jobs)
    print(json.dumps({"passed": result["passed"], "detected_count": result["detected_count"],
                      "variant_count": result["variant_count"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
