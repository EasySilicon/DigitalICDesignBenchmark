#!/usr/bin/env python3
"""Assemble and strictly qualify the frozen three-seed T10 PPA record."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from pathlib import Path

from t10_ppa_qualify import qualify  # noqa: E402

SEEDS = (11, 29, 47)
LEVELS = ("pe", "tile", "top")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.resolve(strict=True).read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def output(command: list[str], cwd: Path | None = None) -> str:
    return subprocess.check_output(command, cwd=cwd, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True,
                        help="contains seed11/seed29/seed47 level and power JSON")
    parser.add_argument("--workload-manifest", type=Path, required=True)
    parser.add_argument("--hierarchy-report", type=Path, required=True)
    parser.add_argument("--rtl", type=Path, required=True)
    parser.add_argument("--filelist", type=Path, required=True)
    parser.add_argument("--asap7-manifest", type=Path, required=True)
    parser.add_argument("--orfs-root", type=Path, required=True)
    parser.add_argument("--yosys", default="yosys")
    parser.add_argument("--openroad", default="openroad")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--qualification-output", type=Path)
    args = parser.parse_args()

    root = args.evidence_root.resolve(strict=True)
    workload_path = args.workload_manifest.resolve(strict=True)
    workload = load(workload_path)
    if workload.get("task_id") != "T10" or workload.get("case_count") != 200:
        raise ValueError("workload manifest is not the frozen 200-block T10 workload")
    oracle_sha = workload.get("oracle_check", {}).get("oracle_sha256")
    if not isinstance(oracle_sha, str) or len(oracle_sha) != 64:
        raise ValueError("workload manifest has no oracle SHA-256")

    hierarchy_path = args.hierarchy_report.resolve(strict=True)
    hierarchy = load(hierarchy_path)
    result = hierarchy.get("result", {})
    expected_hierarchy = {
        "tile_instances": 16,
        "pe_instances_per_tile": 16,
        "pe_instances_total": 256,
    }
    if any(result.get(key) != value for key, value in expected_hierarchy.items()):
        raise ValueError("hierarchy report is not the required 16 x 16 structure")

    per_seed = []
    for seed in SEEDS:
        seed_root = root / f"seed{seed}"
        levels = {}
        setup_slacks = []
        for level in LEVELS:
            path = seed_root / f"{level}.json"
            data = load(path)
            if data.get("level") != level or data.get("layout_seed") != seed:
                raise ValueError(f"level identity mismatch: {path}")
            levels[level] = data
            setup_slacks.append(float(data["setup_worst_slack_ps"]))
        power = load(seed_root / "power.json")
        if power.get("layout_seed") not in (None, seed):
            raise ValueError(f"power seed mismatch: {seed_root / 'power.json'}")
        power.pop("layout_seed", None)
        per_seed.append({
            "layout_seed": seed,
            "levels": levels,
            "area_um2": levels["top"]["area_um2"],
            "delay_ps": 1000.0 - min(setup_slacks),
            "power": power,
        })

    areas = [float(row["area_um2"]) for row in per_seed]
    delays = [float(row["delay_ps"]) for row in per_seed]
    energies = [float(row["power"]["energy_j_per_block"]) * 1e12
                for row in per_seed]
    annotations = [float(row["power"]["activity_annotation_fraction"])
                   for row in per_seed]
    evaluator = Path(__file__).resolve().with_name("t10_ppa_qualify.py")
    record = {
        "schema_version": 1,
        "task_id": "T10",
        "measurement_status": "three_seed_hierarchical",
        "toolchain": {
            "yosys": output([args.yosys, "-V"]),
            "openroad": output([args.openroad, "-version"]),
            "orfs_revision": output(["git", "rev-parse", "HEAD"], args.orfs_root),
            "asap7_manifest_sha256": sha256(args.asap7_manifest.resolve(strict=True)),
            "evaluator_sha256": sha256(evaluator),
        },
        "workload": {
            "id": "T10-power-v1",
            "matrix_blocks": 200,
            "sha256": sha256(workload_path),
            "oracle_sha256": oracle_sha,
        },
        "parameter_set": {
            "platform": "ASAP7_7p5t_RVT_NLDM",
            "corner": "WC",
            "period_ps": 1000,
            "signal_routing_layers": "M2-M7",
            "clock_routing_layers": "M6-M7",
            "seeds": list(SEEDS),
        },
        "source": {
            "rtl_sha256": sha256(args.rtl.resolve(strict=True)),
            "filelist_sha256": sha256(args.filelist.resolve(strict=True)),
            "structure_report_sha256": sha256(hierarchy_path),
            "hierarchy": expected_hierarchy,
        },
        "per_seed": per_seed,
        "aggregate": {
            "area_um2": float(statistics.median(areas)),
            "delay_ns": float(statistics.median(delays)) / 1000.0,
            "energy_per_op_pj": float(statistics.median(energies)),
            "annotation_fraction": min(annotations),
        },
    }

    qualification = qualify(record, root)
    qualification_path = args.qualification_output
    if qualification_path:
        qualification_path.parent.mkdir(parents=True, exist_ok=True)
        qualification_path.write_text(json.dumps(qualification, indent=2) + "\n")
    if qualification["status"] != "qualified":
        print(json.dumps(qualification, indent=2), file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.replace(args.output)
    print(json.dumps(record["aggregate"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
