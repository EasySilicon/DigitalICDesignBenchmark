#!/usr/bin/env python3
"""Qualify a hash-bound three-seed hierarchical T10 PPA measurement."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
from pathlib import Path

SEEDS = (11, 29, 47)
LEVELS = ("pe", "tile", "top")
PERIOD_PS = 1000.0
SHA_FIELDS = ("sha256", "bytes", "path")
REQUIRED_LEVEL_ARTIFACTS = ("odb", "sdc", "spef", "lef", "liberty",
                            "timing_report", "drc_report")
REQUIRED_POWER_ARTIFACTS = ("workload_manifest", "activity_audit",
                            "power_report")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finite_number(value: object, *, positive: bool = False) -> bool:
    return (type(value) in (int, float) and math.isfinite(value) and
            (value > 0 if positive else True))


def verify_artifact(record: object, root: Path, label: str,
                    failures: list[str]) -> None:
    if not isinstance(record, dict) or any(field not in record for field in SHA_FIELDS):
        failures.append(f"{label}: malformed artifact record")
        return
    path = Path(str(record["path"]))
    path = path if path.is_absolute() else root / path
    if not path.is_file():
        failures.append(f"{label}: artifact missing: {path}")
        return
    if type(record["bytes"]) is not int or record["bytes"] != path.stat().st_size:
        failures.append(f"{label}: byte count mismatch")
    observed = sha256(path)
    if record["sha256"] != observed:
        failures.append(f"{label}: SHA-256 mismatch")


def median(values: list[float]) -> float:
    return float(statistics.median(values))


def qualify(record: dict, root: Path) -> dict:
    failures: list[str] = []
    if record.get("schema_version") != 1 or record.get("task_id") != "T10":
        failures.append("wrong schema version or task ID")
    if record.get("measurement_status") != "three_seed_hierarchical":
        failures.append("measurement status is not three_seed_hierarchical")

    toolchain = record.get("toolchain", {})
    for field in ("yosys", "openroad", "orfs_revision"):
        if not isinstance(toolchain.get(field), str) or not toolchain[field].strip():
            failures.append(f"toolchain {field} is missing")
    for field in ("asap7_manifest_sha256", "evaluator_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(toolchain.get(field, ""))):
            failures.append(f"toolchain {field} is not a SHA-256")

    workload = record.get("workload", {})
    if workload.get("id") != "T10-power-v1" or workload.get("matrix_blocks") != 200:
        failures.append("wrong power workload ID or matrix-block count")
    for field in ("sha256", "oracle_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(workload.get(field, ""))):
            failures.append(f"workload {field} is not a SHA-256")

    params = record.get("parameter_set", {})
    expected = {
        "platform": "ASAP7_7p5t_RVT_NLDM",
        "corner": "WC",
        "period_ps": 1000,
        "signal_routing_layers": "M2-M7",
        "clock_routing_layers": "M6-M7",
        "seeds": list(SEEDS),
    }
    for field, value in expected.items():
        if params.get(field) != value:
            failures.append(f"parameter {field} must be {value!r}")

    source = record.get("source", {})
    for field in ("rtl_sha256", "filelist_sha256", "structure_report_sha256"):
        value = source.get(field)
        if not isinstance(value, str) or len(value) != 64:
            failures.append(f"source {field} is not a SHA-256")
    hierarchy = source.get("hierarchy", {})
    if hierarchy.get("tile_instances") != 16 or \
            hierarchy.get("pe_instances_per_tile") != 16 or \
            hierarchy.get("pe_instances_total") != 256:
        failures.append("source hierarchy is not 16 tiles x 16 PEs")

    seeds = record.get("per_seed")
    if not isinstance(seeds, list) or \
            [row.get("layout_seed") for row in seeds
             if isinstance(row, dict)] != list(SEEDS):
        failures.append("layout seeds must be exactly 11/29/47 in order")
        seeds = []

    areas: list[float] = []
    delays: list[float] = []
    energies: list[float] = []
    annotation: list[float] = []
    for seed_row in seeds:
        seed = seed_row.get("layout_seed")
        levels = seed_row.get("levels", {})
        level_slacks = []
        for level in LEVELS:
            data = levels.get(level, {}) if isinstance(levels, dict) else {}
            prefix = f"seed {seed} {level}"
            area = data.get("area_um2")
            setup = data.get("setup_worst_slack_ps")
            hold = data.get("hold_worst_slack_ps")
            drc = data.get("drc_violations")
            if not finite_number(area, positive=True):
                failures.append(f"{prefix}: invalid area")
            if not finite_number(setup) or setup < 0:
                failures.append(f"{prefix}: setup WNS is negative or invalid")
            if not finite_number(hold) or hold < 0:
                failures.append(f"{prefix}: hold WNS is negative or invalid")
            if type(drc) is not int or drc != 0:
                failures.append(f"{prefix}: detailed-route DRC is not zero")
            if finite_number(setup):
                level_slacks.append(float(setup))
            artifacts = data.get("artifacts", {})
            for name in REQUIRED_LEVEL_ARTIFACTS:
                verify_artifact(artifacts.get(name) if isinstance(artifacts, dict) else None,
                                root, f"{prefix} {name}", failures)
        top_area = levels.get("top", {}).get("area_um2") if isinstance(levels, dict) else None
        declared_area = seed_row.get("area_um2")
        declared_delay = seed_row.get("delay_ps")
        if finite_number(top_area, positive=True) and declared_area != top_area:
            failures.append(f"seed {seed}: area must equal complete-top area")
        if level_slacks:
            expected_delay = PERIOD_PS - min(level_slacks)
            if not finite_number(declared_delay, positive=True) or \
                    not math.isclose(declared_delay, expected_delay,
                                     rel_tol=0, abs_tol=1e-6):
                failures.append(f"seed {seed}: delay does not use worst hierarchical setup WNS")

        power = seed_row.get("power", {})
        blocks = power.get("matrix_blocks")
        fraction = power.get("activity_annotation_fraction")
        duration = power.get("vcd_window_seconds")
        total = power.get("total_power_w")
        energy = power.get("energy_j_per_block")
        if power.get("workload_id") != workload.get("id") or \
                power.get("workload_sha256") != workload.get("sha256"):
            failures.append(f"seed {seed}: workload identity differs from frozen workload")
        components = power.get("components_w", {})
        weights = power.get("instance_weights", {})
        if blocks != 200:
            failures.append(f"seed {seed}: power workload must contain 200 blocks")
        if not finite_number(fraction) or not 0.95 <= fraction <= 1.0:
            failures.append(f"seed {seed}: activity annotation is below 95%")
        if weights != {"top_shell": 1, "tile_shell": 16, "pe": 256}:
            failures.append(f"seed {seed}: hierarchical power weights are wrong")
        if not isinstance(components, dict) or any(
                not finite_number(components.get(name), positive=True)
                for name in ("top_shell", "tile_shell_sum", "pe_sum")):
            failures.append(f"seed {seed}: invalid hierarchical power components")
        elif not finite_number(total, positive=True) or not math.isclose(
                total, sum(components.values()), rel_tol=1e-9, abs_tol=1e-15):
            failures.append(f"seed {seed}: total power differs from component sum")
        if not all(finite_number(value, positive=True)
                   for value in (duration, total, energy)) or blocks != 200:
            failures.append(f"seed {seed}: invalid power duration/energy")
        elif not math.isclose(energy, total * duration / blocks,
                              rel_tol=1e-9, abs_tol=1e-18):
            failures.append(f"seed {seed}: energy per block is inconsistent")
        power_artifacts = power.get("artifacts", {})
        for name in REQUIRED_POWER_ARTIFACTS:
            verify_artifact(power_artifacts.get(name)
                            if isinstance(power_artifacts, dict) else None,
                            root, f"seed {seed} power {name}", failures)

        if finite_number(declared_area, positive=True):
            areas.append(float(declared_area))
        if finite_number(declared_delay, positive=True):
            delays.append(float(declared_delay))
        if finite_number(energy, positive=True):
            energies.append(float(energy) * 1e12)
        if finite_number(fraction):
            annotation.append(float(fraction))

    aggregate = record.get("aggregate", {})
    expected_aggregate = {}
    if len(areas) == 3:
        expected_aggregate["area_um2"] = median(areas)
    if len(delays) == 3:
        expected_aggregate["delay_ns"] = median(delays) / 1000.0
    if len(energies) == 3:
        expected_aggregate["energy_per_op_pj"] = median(energies)
    if len(annotation) == 3:
        expected_aggregate["annotation_fraction"] = min(annotation)
    for field, value in expected_aggregate.items():
        observed = aggregate.get(field)
        if not finite_number(observed) or not math.isclose(
                observed, value, rel_tol=1e-9, abs_tol=1e-12):
            failures.append(f"aggregate {field} is inconsistent")

    return {
        "task_id": "T10",
        "status": "qualified" if not failures else "failed",
        "failures": failures,
        "verified_layout_seeds": list(SEEDS) if not failures else [],
        "aggregate": expected_aggregate if not failures else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("measurement", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    measurement = args.measurement.resolve(strict=True)
    root = (args.artifact_root.resolve() if args.artifact_root else measurement.parent)
    result = qualify(json.loads(measurement.read_text()), root)
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")
    return 0 if result["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
