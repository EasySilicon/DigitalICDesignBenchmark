#!/usr/bin/env python3
"""Aggregate evaluator-owned routed ASAP7 and checked TT power records."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

if __package__:
    from .public_check import sources_from_filelist
else:
    from public_check import sources_from_filelist

SEEDS = (11, 29, 47)
PERIOD_PS = 1000
POWER_SEEDS = {"T01": 20260927}


def source_hash(submission: Path) -> str:
    """Return a stable digest of the submitted RTL file list and contents."""
    submission = submission.resolve()
    digest = hashlib.sha256()
    for source in sources_from_filelist(submission):
        digest.update(source.relative_to(submission).as_posix().encode())
        digest.update(b"\0")
        digest.update(source.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def expected_result_dir(report: str) -> Path:
    parts = list(Path(report).resolve().parent.parts)
    if parts.count("reports") != 1:
        raise ValueError("route report does not have one ORFS reports component")
    parts[parts.index("reports")] = "results"
    return Path(*parts)


def aggregate(task: str, submission: Path,
              pairs: list[tuple[Path, Path]],
              expected_seeds: tuple[int, ...] = SEEDS) -> dict:
    routes = []
    workload_hashes = set()
    workload_ids = set()
    workload_parameters = []
    sram_policy = None
    t08_revision = None
    for route_file, power_file in pairs:
        route = json.loads(route_file.read_text())
        power = json.loads(power_file.read_text())
        if route.get("task") != task or power.get("task") != task or \
                route.get("exit_code") != 0 or route.get("corner") != "WC" or \
                route.get("period_ps") != PERIOD_PS or route.get("utilization") != 10 or \
                route.get("density") != 0.6:
            raise ValueError("route record has wrong task or common parameters")
        if task == "T08":
            revision = route.get("ppa_policy_revision")
            if t08_revision is not None and revision != t08_revision:
                raise ValueError("cannot mix T08 physical policy revisions")
            t08_revision = revision
            expected_clocks = {clock: 1000 for clock in ("logic_clk", "tx_clk", "rx_clk")}
            current_sources = {str(path.relative_to(submission.resolve())):
                               hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in sources_from_filelist(submission.resolve())}
            if revision not in ("1.0-uniform-1ghz", "2.0-lambdapdk-tdp-1ghz") or \
                    route.get("clock_relationship") != "asynchronous" or \
                    route.get("clock_periods_ps") != expected_clocks or \
                    power.get("vcd_clock_period_ps") != expected_clocks or \
                    route.get("source_sha256") != current_sources:
                raise ValueError("T08 clock policy or routed source provenance mismatch")
            if revision == "2.0-lambdapdk-tdp-1ghz":
                from t11_sram import contract, validated_mapping
                current = contract()
                receipt = validated_mapping(submission, Path(route["mapping_receipt"]).parent)
                if route.get("sram_contract") != current or power.get("sram_contract") != current or \
                        route.get("macro_count") != receipt["macro_count"] or \
                        power.get("macro_count") != receipt["macro_count"] or \
                        route.get("disconnected_macro_inputs") != 0 or \
                        route.get("mapped_netlist_sha256") != receipt["mapped_netlist_sha256"]:
                    raise ValueError("SRAM route/power/mapping contract mismatch")
                if route.get("macro_area_um2", 0) <= 0 or \
                        abs(route["cell_area_um2"] - route["standard_cell_area_um2"] -
                            route["macro_area_um2"]) > 1e-6:
                    raise ValueError("SRAM area omitted or inconsistent")
                final_netlist = expected_result_dir(route["report"]) / "6_final.v"
                if power.get("routed_netlist_sha256") != hashlib.sha256(final_netlist.read_bytes()).hexdigest():
                    raise ValueError("SRAM power measured on a different routed netlist")
                sram_policy = current
        if Path(power.get("flow_result_dir", "")).resolve() != expected_result_dir(route["report"]):
            raise ValueError("power record is not from this routed netlist")
        expected_power_seed = POWER_SEEDS.get(task, 20260928)
        if power.get("activity_annotation", 0) < 0.95 or \
                type(power.get("ops")) is not int or power["ops"] <= 0 or \
                power.get("seed") != expected_power_seed:
            raise ValueError("power workload or annotation invalid")
        workload_hash = power.get("workload_sha256")
        if not isinstance(workload_hash, str) or len(workload_hash) != 64:
            raise ValueError("power workload hash missing")
        workload_hashes.add(workload_hash)
        workload_id = power.get("workload_id")
        expected_workload = "T11-power-v1" if task == "T08" else f"{task}-power-v1"
        if workload_id != expected_workload:
            raise ValueError("power workload contract ID missing or incompatible")
        workload_ids.add(workload_id)
        parameters = power.get("workload_parameters")
        if not isinstance(parameters, dict):
            raise ValueError("power workload parameters missing")
        workload_parameters.append(parameters)
        area = route.get("cell_area_um2")
        delay = route.get("critical_path_delay_ps")
        wns = route.get("worst_slack_ps")
        hold_wns = route.get("hold_worst_slack_ps")
        drc_violations = route.get("drc_violations")
        energy = power.get("energy_j_per_op")
        if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
               for value in (area, delay, energy)) or \
                type(wns) not in (int, float) or not math.isfinite(wns) or \
                type(hold_wns) not in (int, float) or not math.isfinite(hold_wns) or \
                type(drc_violations) is not int or drc_violations < 0:
            raise ValueError("route or power has invalid measurements")
        # Setup misses remain in critical_path_delay_ps.  Hold misses and DRC
        # counts are retained for continuous penalties in the score function.
        routes.append({"layout_seed": route["seed"],
                       "area_um2": area,
                       "delay_ns": delay / 1000,
                       "setup_worst_slack_ns": wns / 1000,
                       "hold_worst_slack_ns": hold_wns / 1000,
                       "drc_violations": drc_violations,
                       "energy_per_op_pj": energy * 1e12,
                       "power_w": power["power_w"]["total"],
                       "ops": power["ops"],
                       "annotation_fraction": power["activity_annotation"],
                       "route_record": str(route_file.resolve()),
                       "power_record": str(power_file.resolve())})
        if task == "T08" and sram_policy:
            routes[-1].update(macro_count=route["macro_count"],
                             macro_area_um2=route["macro_area_um2"],
                             standard_cell_area_um2=route["standard_cell_area_um2"])
    routes.sort(key=lambda row: row["layout_seed"])
    if tuple(row["layout_seed"] for row in routes) != expected_seeds:
        raise ValueError(f"layout seeds must be {expected_seeds}")
    if len(workload_hashes) != 1:
        raise ValueError("power workload differs between layout seeds")
    if len(workload_ids) != 1:
        raise ValueError("power workload contract differs between layout seeds")
    if any(parameters != workload_parameters[0] for parameters in workload_parameters[1:]):
        raise ValueError("power workload parameters differ between layout seeds")
    parameter_set = {"platform": "ASAP7_7p5t_RVT_NLDM",
                     "period_ps": PERIOD_PS, "corner": "WC",
                     "utilization": 10, "density": 0.6,
                     "seeds": list(expected_seeds)}
    if task == "T05":
        parameter_set["clock_periods_ps"] = {"wr_clk": 1000, "rd_clk": 1000}
        parameter_set["asynchronous_clock_groups"] = [["wr_clk", "rd_clk"]]
    if task == "T08":
        parameter_set["ppa_policy_revision"] = t08_revision
        parameter_set["clock_periods_ps"] = {clock: 1000 for clock in ("logic_clk", "tx_clk", "rx_clk")}
        parameter_set["asynchronous_clock_groups"] = [["logic_clk", "tx_clk", "rx_clk"]]
        parameter_set["memory_mapping"] = "standard_cells; no reduced or mocked memory"
        if sram_policy:
            parameter_set.update(memory_mapping="lambdapdk_tdp_4096x32",
                                 sram_contract=sram_policy,
                                 corner="mixed_WC_standard_cells_TT_SRAM",
                                 drc_scope=sram_policy["drc_scope"], lvs_performed=False)
    return {"task_id": task, "source_sha256": source_hash(submission),
            "workload_id": workload_ids.pop(),
            "workload_parameters": workload_parameters[0],
            "workload_sha256": workload_hashes.pop(),
            "measurement_status": "three_seed" if expected_seeds == SEEDS else "pilot",
            "parameter_set": parameter_set,
            "routed": True,
            "setup_worst_slack_ns": min(row["setup_worst_slack_ns"] for row in routes),
            "hold_worst_slack_ns": min(row["hold_worst_slack_ns"] for row in routes),
            "drc_violations": max(row["drc_violations"] for row in routes),
            "annotation_fraction": min(row["annotation_fraction"] for row in routes),
            "area_um2": statistics.median(row["area_um2"] for row in routes),
            "delay_ns": statistics.median(row["delay_ns"] for row in routes),
            "energy_per_op_pj": statistics.median(row["energy_per_op_pj"] for row in routes),
            "per_seed": routes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=[f"T{i:02d}" for i in range(1, 12)])
    parser.add_argument("submission", type=Path)
    parser.add_argument("--pair", nargs=2, action="append", required=True,
                        metavar=("ROUTE_JSON", "POWER_JSON"))
    parser.add_argument("--pilot-one-seed", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    expected = (11,) if args.pilot_one_seed else SEEDS
    try:
        result = aggregate(args.task, args.submission,
                           [(Path(a), Path(b)) for a, b in args.pair], expected)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
