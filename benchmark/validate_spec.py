#!/usr/bin/env python3
"""Check the frozen v0.3 task inventory and physical reference contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "evaluator"))
PROJECT_NAME = "Digital IC Design Benchmark for Agents"


def fail(message: str) -> None:
    raise SystemExit(f"spec validation failed: {message}")


def validate_local() -> tuple[dict, dict]:
    manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text())
    sources = yaml.safe_load((ROOT / "sources.lock.yaml").read_text())
    readme = (ROOT / "README.md").read_text()

    if manifest.get("project_name") != PROJECT_NAME:
        fail("project name differs from the canonical name")
    if not readme.startswith(f"# {PROJECT_NAME}\n"):
        fail("benchmark overview title differs from the canonical project name")

    task_rows = manifest["tasks"]
    expected_ids = [f"T{index:02d}" for index in range(1, 11)]
    actual_ids = [row["id"] for row in task_rows]
    if actual_ids != expected_ids:
        fail(f"task IDs/order differ: {actual_ids}")
    expected_task_limits = {
        "T01": 30, "T02": 60, "T03": 90, "T04": 90,
        "T05": 120, "T06": 120, "T07": 120, "T08": 120, "T09": 120, "T10": 240,
    }
    actual_task_limits = {row["id"]: row["time_limit_minutes"] for row in task_rows}
    if actual_task_limits != expected_task_limits:
        fail("task time limits differ from the frozen v0.3 schedule")
    if sum(row["time_limit_minutes"] for row in task_rows) != 1110:
        fail("ten-task time budget must total 18 hours 30 minutes")

    scores = manifest["score"]
    if sum(scores[key] for key in ("functional", "ppa", "completion_time")) != 105:
        fail("suite display score does not sum to 105")
    if scores["functional_raw_basic_weight"] + scores["functional_raw_edge_weight"] != 75 or \
            scores["functional"] != 50 or scores["ppa"] != 50:
        fail("score allocation differs from normalized function 50 + PPA 50")
    if scores.get("candidate_delivery_error_penalty") != 5:
        fail("each candidate-caused fatal delivery error must deduct 5 display points")
    if scores.get("setup_violation_exponent") != 4:
        fail("setup violations must use the frozen fourth-power frequency penalty")
    if scores.get("task_raw_allocations") != {"T09": {"F": 48, "P": 27}}:
        fail("T09 must reserve 10 normalized points for the cycle group")
    expected_weights = {
        "T01": 0.03, "T02": 0.03, "T03": 0.06, "T04": 0.06, "T05": 0.06,
        "T06": 0.10, "T07": 0.10, "T08": 0.11, "T09": 0.20, "T10": 0.25,
    }
    if scores.get("task_weights") != expected_weights or \
            not math.isclose(sum(expected_weights.values()), 1.0):
        fail("task weights must match the frozen difficulty weighting and sum to one")
    if scores["rank_order"] != ["functional_total", "ppa_rank_bucket", "completion_time_seconds_ascending"]:
        fail("rank priority differs from function → PPA → time")
    if scores["suite_rank_order"] != ["full_functional_task_count", "functional_total_sum",
                                      "ppa_rank_bucket_sum", "normalized_completion_time_sum_ascending"]:
        fail("suite rank priority differs from function → PPA → time")
    if scores["ppa_rank_resolution_points"] <= 0:
        fail("PPA ranking resolution must be positive")
    if manifest["ppa_measurement"]["platform"] != sources["ppa"]["platform"]:
        fail("PPA platform differs between manifest and source lock")
    if manifest["ppa_measurement"]["flow"] != sources["ppa"]["flow"]:
        fail("PPA flow differs between manifest and source lock")
    baselines = json.loads((ROOT / "ppa-baselines.json").read_text())
    ppa_inventory = manifest["ppa_measurement"]
    calibrated = ppa_inventory["calibrated_baseline_tasks"]
    pending = ppa_inventory["pending_baseline_tasks"]
    if len(calibrated) != len(set(calibrated)) or len(pending) != len(set(pending)) or \
            set(calibrated).intersection(pending) or \
            set(calibrated).union(pending) != set(expected_ids) or \
            set(baselines["tasks"]) != set(calibrated):
        fail("PPA baseline scope must identify calibrated and pending tasks")
    expected_baseline_status = ("pending_1ghz_rebaseline" if not calibrated else
                                "qualified_1ghz" if not pending else
                                "partial_1ghz_qualified")
    if baselines["status"] != expected_baseline_status:
        fail("1 GHz PPA baseline status differs from calibrated task inventory")
    if baselines["score_bucket_width_points"] != scores["ppa_rank_resolution_points"]:
        fail("PPA baseline bucket width differs from manifest")
    t05_clocks = ppa_inventory.get("task_clock_contracts", {}).get("T05")
    t05_expected = {"wr_clk_period_ps": 1000, "rd_clk_period_ps": 1000,
                    "relationship": "asynchronous"}
    expected_parameter_status = ("target_1ghz_pending_physical_calibration"
                                 if not calibrated else
                                 "target_1ghz_calibrated" if not pending else
                                 "target_1ghz_partially_calibrated")
    expected_values_status = ("pending_rebaseline" if not calibrated else
                              "qualified" if not pending else "partial_rebaseline")
    if ppa_inventory["shared_clock_period_ps"] != 1000 or \
            t05_clocks != t05_expected or \
            baselines["parameter_set"].get("task_clock_contracts", {}).get("T05") != t05_expected or \
            ppa_inventory["parameter_set_status"] != expected_parameter_status or \
            ppa_inventory["baseline_values_status"] != expected_values_status or \
            baselines["parameter_set"]["period_ps"] != 1000:
        fail("1 GHz target differs from baseline records")
    common_parameters = {"platform": "ASAP7_7p5t_RVT_NLDM", "period_ps": 1000,
                         "corner": "WC", "utilization": 10, "density": 0.6,
                         "seeds": [11, 29, 47]}
    for task_id in calibrated:
        row = baselines["tasks"][task_id]
        parameters = dict(common_parameters)
        if task_id == "T05":
            parameters.update({"clock_periods_ps": {"wr_clk": 1000, "rd_clk": 1000},
                               "asynchronous_clock_groups": [["wr_clk", "rd_clk"]]})
        if task_id == "T08":
            from t11_sram import contract
            parameters.update(corner="mixed_WC_standard_cells_TT_SRAM",
                              clock_periods_ps={clock:1000 for clock in ("logic_clk","tx_clk","rx_clk")},
                              asynchronous_clock_groups=[["logic_clk","tx_clk","rx_clk"]],
                              ppa_policy_revision="2.0-lambdapdk-tdp-1ghz",
                              memory_mapping="lambdapdk_tdp_4096x32",sram_contract=contract(),
                              drc_scope=contract()["drc_scope"],lvs_performed=False)
        seeds = row.get("per_seed")
        hashes = (row.get("source_sha256", ""), row.get("workload_sha256", ""))
        if row.get("task_id") != task_id or \
                row.get("qualification_status") != "qualified_1ghz" or \
                row.get("measurement_status") != "three_seed" or \
                row.get("parameter_set") != parameters or \
                not row.get("routed") or row.get("drc_violations") != 0 or \
                row.get("setup_worst_slack_ns", -1) < 0 or \
                row.get("hold_worst_slack_ns", -1) < 0 or \
                row.get("annotation_fraction", 0) < ppa_inventory["minimum_activity_annotation"] or \
                any(len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
                    for value in hashes) or \
                any(not isinstance(row.get(key), (int, float)) or row[key] <= 0
                    for key in ("area_um2", "delay_ns", "average_power_mw",
                                "energy_per_op_pj")) or \
                not isinstance(seeds, list) or len(seeds) != 3 or \
                any(not isinstance(seed, dict) for seed in seeds) or \
                sorted(seed.get("layout_seed") for seed in seeds
                       if isinstance(seed, dict)) != [11, 29, 47] or \
                any(seed.get("drc_violations") != 0 or
                    seed.get("setup_worst_slack_ns", -1) < 0 or
                    seed.get("hold_worst_slack_ns", -1) < 0 or
                    seed.get("annotation_fraction", 0) < ppa_inventory["minimum_activity_annotation"] or
                    any(not isinstance(seed.get(key), (int, float)) or seed[key] <= 0
                        for key in ("area_um2", "delay_ns", "average_power_mw",
                                    "energy_per_op_pj", "ops")) or
                    any(len(seed.get(key, "")) != 64 or
                        any(character not in "0123456789abcdef" for character in seed.get(key, ""))
                        for key in ("config_sha256", "constraint_sha256",
                                    "finish_report_sha256", "drc_report_sha256",
                                    "power_report_sha256"))
                    for seed in seeds):
            fail(f"invalid qualified PPA baseline: {task_id}")
    for index, row in enumerate(task_rows, start=1):
        task_id = row["id"]
        task_dir = ROOT / "tasks" / task_id
        task_doc = task_dir / "task.md"
        acceptance_doc = task_dir / "acceptance.md"
        task_metadata = yaml.safe_load((task_dir / "task.yaml").read_text())
        if not task_doc.is_file() or not task_doc.read_text().startswith(f"# {task_id} ·"):
            fail(f"missing task-local task card: {task_id}")
        if not acceptance_doc.is_file() or not acceptance_doc.read_text().startswith(f"# {task_id}"):
            fail(f"missing task-local acceptance plan: {task_id}")
        if f"| {task_id} |" not in readme:
            fail(f"missing overview row: {task_id}")
        for key in ("id", "title", "level_hypothesis", "origin",
                    "time_limit_minutes", "same_model_token_cap"):
            if task_metadata.get(key) != row[key]:
                fail(f"task metadata differs from manifest: {task_id}/{key}")
        allocation = scores["task_raw_allocations"].get(task_id, {
            "F": scores["functional_raw_basic_weight"], "P": scores["functional_raw_edge_weight"]})
        if not math.isclose(sum(row["f_points"]), allocation["F"]):
            fail(f"F points do not sum to {allocation['F']}: {task_id}")
        if not math.isclose(sum(row["p_points"]), allocation["P"]):
            fail(f"P points do not sum to {allocation['P']}: {task_id}")
        if task_metadata.get("f_points") != row["f_points"] or task_metadata.get("p_points") != row["p_points"]:
            fail(f"task-local scoring weights differ from manifest: {task_id}")
        if row["level_hypothesis"] != index:
            fail(f"level hypothesis/order differs: {task_id}")
        if row["time_limit_minutes"] <= 0 or (row["same_model_token_cap"] is not None and row["same_model_token_cap"] <= 0):
            fail(f"invalid resource budget: {task_id}")

    if manifest["status"] != "design_only":
        fail("status cannot advance without the publication gates")
    for required in ("README.md", "README.en.md", "npu-validation.md"):
        if not (ROOT / required).is_file():
            fail(f"missing required document: {required}")
    for heading in ("## 共享任务规则", "## 通用验收规则", "## 验证与交付契约",
                    "## 评测与评分方法", "## PPA 测量与评分", "## 领域与难度覆盖"):
        if heading not in readme:
            fail(f"missing benchmark README section: {heading}")
    env_guide = ROOT.parent / "env" / "README.md"
    if not env_guide.is_file():
        fail("missing environment installation guide")
    guide_text = env_guide.read_text()
    if sources["ppa"]["flow_revision"] not in guide_text:
        fail("environment guide ORFS revision differs from source lock")
    if sources["riscv"]["arch_test_revision"] not in guide_text:
        fail("environment guide ACT4 revision differs from source lock")
    vendored_platform = ROOT.parent / sources["ppa"]["vendored_platform_path"]
    if not (vendored_platform / "config.mk").is_file():
        fail("vendored ASAP7 platform is missing")
    if not (ROOT.parent / sources["ppa"]["vendored_platform_hashes"]).is_file():
        fail("vendored ASAP7 hash manifest is missing")
    for task_id in expected_ids:
        if not (ROOT.parent / "evaluator" / "public" / f"tb_{task_id}.sv").is_file():
            fail(f"missing executable public testbench: {task_id}")
    if not (ROOT.parent / sources["riscv"]["act4_generated_elf_manifest"]).is_file():
        fail("missing generated ACT4 ELF inventory")
    cpu_plan = (ROOT / "tasks" / "T09" / "acceptance.md").read_text()
    if "CPU-PIPE-LAT" not in cpu_plan or "CPU-PIPE-THRU" in cpu_plan:
        fail("CPU structural timing gate must use per-instruction latency")
    if not (ROOT.parent / "evaluator" / "cpu_latency_check.py").is_file():
        fail("missing CPU latency trace checker")
    for name in ("t09_timing_check.py", "t09_timing_tb.sv"):
        if not (ROOT.parent / "evaluator" / name).is_file():
            fail(f"missing CPU cycle-performance checker: {name}")
    if "port_timing_v1" not in cpu_plan or "N + M×(response_cycles+ready_delay) + H" not in cpu_plan:
        fail("CPU cycle policy is missing its explicit workload budget")
    report_schema = json.loads((ROOT / "report.schema.json").read_text())
    if report_schema["properties"]["suite_id"]["const"] != manifest["suite_id"]:
        fail("report schema suite ID differs from manifest")
    if report_schema["properties"]["ppa_platform"]["const"] != sources["ppa"]["platform"]:
        fail("report schema PPA platform differs from source lock")
    if report_schema["properties"]["ppa_flow"]["const"] != sources["ppa"]["flow"]:
        fail("report schema PPA flow differs from source lock")
    if __package__:
        from .freeze_tasks import verify
    else:
        from freeze_tasks import verify
    try:
        for task_id in ("T08", "T09"):
            verify(task_id)
    except (OSError, ValueError, KeyError) as exc:
        fail(str(exc))
    return manifest, sources


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    manifest, sources = validate_local()
    print(json.dumps({"suite_id": manifest["suite_id"], "tasks": len(manifest["tasks"]),
                      "status": manifest["status"]}))


if __name__ == "__main__":
    main()
