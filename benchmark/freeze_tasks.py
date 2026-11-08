#!/usr/bin/env python3
"""Publish/verify T08 and T09 task freeze receipts, without running physical EDA.

Receipts contain hashes and contracts, not a second PPA baseline. Default mode
is read-only. --write refreshes contracts for recorded reference qualifications.
Full raw-evidence verification is an explicit operation on an external directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluator"))
from ppa_aggregate import source_hash

TASKS = ("T08", "T09")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def read(path: str, root: Path = ROOT) -> dict:
    return json.loads((root / path).read_text())


def publish(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def verify_evidence(task: str, bundle: Path, root: Path = ROOT) -> None:
    """Audit explicitly supplied raw reports without copying them into the repo."""
    baseline = read("benchmark/ppa-baselines.json", root)["tasks"][task]
    if task == "T08":
        qualification = read("evaluator/t08_qualification.json", root)
        original = json.loads((bundle / "freeze.json").read_text())
        if sha(bundle / "freeze.json") != qualification["original_freeze_manifest_sha256"] or \
                original["source_sha256"] != baseline["source_sha256"] or \
                original["status"] != "frozen_reference_1ghz":
            raise ValueError("wrong or unqualified original T08 freeze evidence")
        names=[f"qualification/{name}.json" for name in
               ("functional","stress","mapped_functional","mapped_stress")]
        names += [f"seed{seed}/{name}" for seed in (11,29,47) for name in
                  ("route.json","power.json","6_finish.rpt","5_route_drc.rpt",
                   "power.log","simulation.log","6_final.sdc","power.tcl")]
        names += [f"mapped_reference/{name}" for name in
                  ("qualification.json","mapping.json","mapping.log")]
        for name in names:
            path=bundle/name
            if not path.is_file() or path.is_symlink() or sha(path)!=original["artifact_sha256"].get(name):
                raise ValueError(f"T08 original evidence missing/changed: {name}")
        for kind in ("functional", "mapped_functional"):
            evidence = json.loads((bundle / "qualification" / (kind + ".json")).read_text())
            cases = evidence["cases"]
            if evidence["full_functional_pass"] is not True or len(cases) != 37 or \
                    any(len(case["runs"]) != 3 or not all(r["passed"] is True for r in case["runs"])
                        for case in cases.values()):
                raise ValueError(f"T08 {kind} does not pass 111 runs")
        for kind in ("stress", "mapped_stress"):
            evidence = json.loads((bundle / "qualification" / (kind + ".json")).read_text())
            if evidence["full_pass"] is not True or evidence["passed_count"] != 270 or \
                    evidence["run_count"] != 270 or len(evidence["runs"]) != 270 or \
                    not all(row["passed"] is True for row in evidence["runs"]):
                raise ValueError(f"T08 {kind} does not pass 270 runs")
        for path in bundle.rglob("*"):
            name = str(path.relative_to(bundle))
            if path.is_file() and name in original["artifact_sha256"] and \
                    sha(path) != original["artifact_sha256"][name]:
                raise ValueError(f"T08 original evidence changed: {name}")
    elif task == "T09":
        qualification=read("evaluator/t09_qualification.json",root)
        for name,expected in qualification["reference_check_sha256"].items():
            if sha(bundle/name)!=expected:
                raise ValueError(f"T09 reference check changed: {name}")
        if sha(bundle/'ppa.json')!=qualification['evidence_record_sha256']:
            raise ValueError("T09 original PPA evidence changed")
        from t09_reference_freeze import qualify
        qualify(baseline, *(json.loads((bundle / (name + ".json")).read_text())
                            for name in ("functional", "timing", "mutations")))
    else:
        raise ValueError("unsupported evidence task")
    for seed in baseline["per_seed"]:
        directory = bundle / f"seed{seed['layout_seed']}"
        for name, field in (("6_finish.rpt", "finish_report_sha256"),
                            ("5_route_drc.rpt", "drc_report_sha256"),
                            ("power.log", "power_report_sha256")):
            if sha(directory / name) != seed[field]:
                raise ValueError(f"{task} report mismatch: {name}")
        route = json.loads((directory / "route.json").read_text())
        if route["period_ps"] != 1000 or route["seed"] != seed["layout_seed"] or \
                route["exit_code"] != 0 or route["corner"] != "WC":
            raise ValueError(f"{task} incorrect original route contract")
        if task == "T08" and (sha(directory / "config.mk") != seed["config_sha256"] or
                              sha(directory / "constraint.sdc") != route["constraint_sha256"]):
            raise ValueError("T08 input config/SDC differs from measured route")


def file_inventory(task: str, root: Path = ROOT) -> list[str]:
    """Scope all normative materials, actual judges, stimuli and transitive assets."""
    paths: set[Path] = set()
    directories = [f"benchmark/tasks/{task}", f"evaluator/reference/{task}", "vendor/asap7"]
    if task == "T08":
        directories += ["evaluator/fixtures/t11_mac", "vendor/lambdapdk_fakeram7"]
    else:
        directories += ["evaluator/t09_data", "evaluator/act4_elfs", "benchmark/cpu/act4"]
    for directory in directories:
        paths.update((root / directory).rglob("*"))
    names = ["benchmark/candidate-rules.md", "benchmark/prepare_trial.py",
             "benchmark/public_eda.py", "benchmark/candidate_ppa.py",
             "benchmark/README.md", "benchmark/README.en.md",
             "benchmark/report.schema.json", "results/result.schema.json",
             "benchmark/eda_time.py", "benchmark/freeze_tasks.py",
             "evaluator/public_check.py", "evaluator/delivery_check.py",
             "benchmark/delivery-policy.md", "evaluator/delivery_policy.py",
             "evaluator/slang_frontend.py", "evaluator/yosys_slang.py", "evaluator/route_with_slang.py",
             "benchmark/physical-runtime-policy.md", "evaluator/physical_budget.py",
             "benchmark/power-compile-policy.md",
             "evaluator/physical_grading.py", "evaluator/aggregate_with_power_budget.py",
             "evaluator/score_with_power_budget.py", "evaluator/power_compile_budget.py",
             "evaluator/score_run.py", "evaluator/ppa_aggregate.py",
             "evaluator/ppa_probe.py", "evaluator/ppa_power_probe.py",
             "env/asap7_seq_sim.v", "env/requirements-spec.txt",
             "vendor/asap7/SHA256SUMS", "env/orfs-26q2-compat.patch",
             "benchmark/tasks/T10/public/matmul_oracle.py"]
    if task == "T08":
        names += ["evaluator/t08_check.py", "evaluator/public/tb_T08.sv",
                  "evaluator/t08_stress_check.py", "evaluator/t08_mutation_check.py",
                  "evaluator/t08_repair_qualification.py", "evaluator/t08_stress_qualification.py",
                  "evaluator/t08_power_probe.py", "evaluator/t08_reference_freeze.py",
                  "evaluator/run_t08_sram_ppa.py", "evaluator/t11_sram.py",
                  "evaluator/t08_qualification.json"]
    else:
        names += [str(p.relative_to(root)) for p in (root / "evaluator").glob("t09_*.py")]
        names += ["evaluator/public/tb_T09.sv", "evaluator/public/tb_cpu_elf.sv",
                  "evaluator/t09_timing_tb.sv", "evaluator/t09_qualification.json",
                  "evaluator/t09_timing_qualification.json", "evaluator/cpu_elf_check.py",
                  "evaluator/cpu_latency_check.py",
                  "evaluator/elf_image.py", "evaluator/sail_commit.py",
                  "evaluator/verify_act4_artifacts.py", "evaluator/check_act4_sail.py",
                  "evaluator/make_cpu_smoke.py"]
    for name in names:
        path = root / name
        if not path.is_file():
            raise ValueError(f"required freeze dependency missing: {name}")
        paths.add(path)
    selected = []
    for path in paths:
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc" or path.name == "FREEZE.json":
            continue
        if path.is_symlink() and not (path.is_relative_to(root / "vendor/asap7") and
                                     path.resolve().is_relative_to(root / "vendor/asap7")):
            raise ValueError(f"unsafe freeze dependency symlink: {path}")
        selected.append(str(path.relative_to(root)))
    return sorted(selected)


def contracts(task: str, root: Path = ROOT) -> dict:
    manifest = yaml.safe_load((root / "benchmark/manifest.yaml").read_text())
    sources = yaml.safe_load((root / "benchmark/sources.lock.yaml").read_text())
    rules = read("evaluator/score_rules.json", root)
    row = next(row for row in manifest["tasks"] if row["id"] == task)
    metadata = yaml.safe_load((root / f"benchmark/tasks/{task}/task.yaml").read_text())
    if row.get("status") != "frozen" or metadata.get("status") != "frozen":
        raise ValueError(f"{task} status is not frozen")
    for key in ("title", "time_limit_minutes", "f_points", "p_points",
                "spec_revision", "judge_revision"):
        if row.get(key) != metadata.get(key):
            raise ValueError(f"{task} manifest/task metadata mismatch: {key}")
    baseline = read("benchmark/ppa-baselines.json", root)["tasks"][task]
    if baseline.get("qualification_status") != "qualified_1ghz" or \
            source_hash(root / f"evaluator/reference/{task}") != baseline["source_sha256"]:
        raise ValueError(f"{task} reference hash/qualification mismatch")
    seeds = baseline["per_seed"]
    if [r["layout_seed"] for r in seeds] != [11, 29, 47]:
        raise ValueError("freeze needs seeds 11/29/47")
    for seed in seeds:
        for key in ("setup_worst_slack_ns", "hold_worst_slack_ns", "area_um2", "delay_ns", "energy_per_op_pj"):
            value = seed[key]
            if not math.isfinite(value) or value < 0 or (key in ("area_um2", "delay_ns", "energy_per_op_pj") and value == 0):
                raise ValueError(f"{task} seed {seed['layout_seed']} fails {key}")
        if seed["drc_violations"] != 0 or seed["annotation_fraction"] < .95:
            raise ValueError(f"{task} invalid DRC/power qualification")
    qualification = read(f"evaluator/{task.lower()}_qualification.json", root)
    if qualification["source_sha256"] != baseline["source_sha256"] or \
            qualification["functional_total_normalized"] != 50:
        raise ValueError(f"{task} missing functional qualification")
    if task == "T08":
        ppa_receipt = read("benchmark/tasks/T08/PPA_FREEZE.json", root)
        for key in ("source_sha256", "workload_id", "workload_sha256", "parameter_set",
                    "area_um2", "delay_ns", "average_power_mw", "energy_per_op_pj",
                    "setup_worst_slack_ns", "hold_worst_slack_ns", "drc_violations"):
            if ppa_receipt[key] != baseline[key]:
                raise ValueError(f"T08 PPA receipt differs from sole baseline: {key}")
        expected_runs = {"functional_runs": 111, "mapped_functional_runs": 111,
                         "stress_runs": 270, "mapped_stress_runs": 270}
        if any(qualification.get(k) != v for k, v in expected_runs.items()) or \
                qualification["original_freeze_manifest_sha256"] != \
                ppa_receipt["freeze_evidence"]["freeze_manifest_sha256"]:
            raise ValueError("T08 recorded reference qualification mismatch")
        for path, expected in baseline["parameter_set"]["sram_contract"]["model_sha256"].items():
            if sha(root / path) != expected:
                raise ValueError(f"SRAM model contract drift: {path}")
    else:
        from t09_reference_freeze import TOTALS
        from t09_timing_check import apply_timing_groups
        expected_groups = {name: {"passed": count, "total": count} for name, count in TOTALS.items()}
        timing = read("evaluator/t09_timing_qualification.json", root)
        groups = {}
        apply_timing_groups(groups, timing)
        if qualification.get("reference_groups") != expected_groups or \
                qualification.get("eligible_mutants") != 21 or qualification.get("killed_mutants") != 21 or \
                groups["CPU-PIPE-CYCLES"] != {"cases_passed": 22, "cases_total": 22} or \
                timing.get("rtl_sha256") != {"ref.sv": sha(root / "evaluator/reference/T09/rtl/ref.sv")}:
            raise ValueError("T09 recorded reference qualification mismatch")
    # Freeze task-specific fragments, so completing T10 won't invalidate T08/T09.
    shared_rules = {k: v for k, v in rules.items() if k not in ("tasks", "task_weights", "task_raw_allocations")}
    shared_rules["task_weight"] = rules["task_weights"][task]
    shared_rules["task_raw_allocation"] = rules.get("task_raw_allocations", {}).get(task, {"F": 60, "P": 15})
    return {"suite_id": manifest["suite_id"], "task_metadata": row,
            "hardware_limit": manifest["hardware_limit"],
            "token_usage_policy": manifest["token_usage_policy"],
            "suite_score": manifest["score"], "score_policy": shared_rules,
            "score_items": rules["tasks"][task], "ppa_baseline_sha256": digest(baseline),
            "source_lock_ppa": {k: v for k, v in sources["ppa"].items()
                                if k not in ("finalized_parameter_set_status", "reference_values_status",
                                             "frozen_task_receipts", "pending_baseline_tasks")},
            "source_lock_riscv": sources["riscv"] if task == "T09" else None}


def build(task: str, root: Path = ROOT) -> dict:
    return {"schema_version": 1, "task_id": task, "status": "frozen",
            "publication_date": "2026-10-09", "resource_policy_revision": "2026-10-21",
            "scope": "task-level; not a suite-wide release",
            "baseline_authority": f"benchmark/ppa-baselines.json#tasks.{task}",
            "reference_source_sha256": source_hash(root / f"evaluator/reference/{task}"),
            "contracts": contracts(task, root),
            "artifact_sha256": {p: sha(root / p) for p in file_inventory(task, root)}}


def verify(task: str, root: Path = ROOT) -> dict:
    stored = read(f"benchmark/tasks/{task}/FREEZE.json", root)
    current = build(task, root)
    if stored != current:
        changed = [p for p in set(stored.get("artifact_sha256", {})) | set(current["artifact_sha256"])
                   if stored.get("artifact_sha256", {}).get(p) != current["artifact_sha256"].get(p)]
        raise ValueError(f"{task} freeze drift; changed artifacts={sorted(changed)}; contracts_changed={stored.get('contracts') != current['contracts']}")
    return stored


def sync_results(root: Path = ROOT) -> None:
    """Attach grading-contract identity to final summaries without changing scores."""
    receipts = {task: verify(task, root) for task in TASKS}
    for directory in sorted((root / "results").iterdir()):
        summary_path = directory / "summary.json"
        if not summary_path.is_file():
            continue
        summary = json.loads(summary_path.read_text())
        if summary.get('schema_version') == 4:
            # Final publication deliberately excludes operational provenance.
            # Verify the task contracts above; do not reinsert freeze receipts
            # into the public summary when this historical helper is invoked.
            import jsonschema
            jsonschema.validate(summary, read('results/result.schema.json', root))
            continue
        for task in TASKS:
            summary_row = next(row for row in summary["tasks"] if row["task_id"] == task)
            binding = {
                "receipt": f"benchmark/tasks/{task}/FREEZE.json",
                "receipt_sha256": sha(root / f"benchmark/tasks/{task}/FREEZE.json"),
                "reference_source_sha256": receipts[task]["reference_source_sha256"],
                "scope": "current grading contract"
            }
            summary_row["benchmark_freeze"] = binding
            summary.setdefault("task_freeze_receipts", {})[task] = binding
        publish(summary_path, summary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="explicitly publish qualified freeze receipts")
    parser.add_argument("--verify-t08-evidence", type=Path, help="audit external T08 reports without importing")
    parser.add_argument("--verify-t09-evidence", type=Path, help="audit external T09 reports without importing")
    parser.add_argument("--sync-results", action="store_true", help="bind current records to verified grading receipts; no score changes")
    args = parser.parse_args()
    try:
        for task, directory in (("T08", args.verify_t08_evidence), ("T09", args.verify_t09_evidence)):
            if directory:
                verify_evidence(task, directory.resolve())
        receipts = {task: build(task) if args.write else verify(task) for task in TASKS}
        if args.write:
            for task, receipt in receipts.items():
                publish(ROOT / f"benchmark/tasks/{task}/FREEZE.json", receipt)
        if args.sync_results:
            sync_results()
        for task, receipt in receipts.items():
            print(f"PASS {task}: frozen, {len(receipt['artifact_sha256'])} artifacts, recorded three-seed 1 GHz qualification")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"freeze validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
