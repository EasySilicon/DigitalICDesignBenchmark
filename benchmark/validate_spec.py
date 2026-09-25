#!/usr/bin/env python3
"""Check benchmark design consistency; optionally verify pinned CVDP rows."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

import yaml


ROOT = Path(__file__).resolve().parent


def fail(message: str) -> None:
    raise SystemExit(f"spec validation failed: {message}")


def validate_local() -> tuple[dict, dict]:
    manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text())
    sources = yaml.safe_load((ROOT / "sources.lock.yaml").read_text())
    tasks_doc = (ROOT / "tasks.md").read_text()
    readme = (ROOT / "README.md").read_text()

    task_rows = manifest["tasks"]
    expected_ids = [f"T{index:02d}" for index in range(1, 10)]
    actual_ids = [row["id"] for row in task_rows]
    if actual_ids != expected_ids:
        fail(f"task IDs/order differ: {actual_ids}")

    scores = manifest["score"]
    if sum(scores[key] for key in ("functional_basic", "functional_edges", "ppa", "completion_time")) != 100:
        fail("suite display score does not sum to 100")
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

    for index, row in enumerate(task_rows, start=1):
        task_id = row["id"]
        if f"## {task_id} ·" not in tasks_doc or f"| {task_id} |" not in readme:
            fail(f"missing task card or overview row: {task_id}")
        if sum(row["f_points"]) != scores["functional_basic"]:
            fail(f"F points do not sum to 60: {task_id}")
        if sum(row["p_points"]) != scores["functional_edges"]:
            fail(f"P points do not sum to 15: {task_id}")
        if row["level_hypothesis"] != index:
            fail(f"level hypothesis/order differs: {task_id}")
        if row["time_limit_minutes"] <= 0 or row["same_model_token_cap"] <= 0:
            fail(f"invalid resource budget: {task_id}")
        if row["origin"] == "cvdp" and task_id not in sources["cvdp"]["items"]:
            fail(f"missing CVDP source lock: {task_id}")

    if manifest["status"] != "design_only":
        fail("status cannot advance without the publication gates")
    for required in ("methodology.md", "ppa.md", "acceptance.md", "cpu-validation.md",
                     "coverage.md", "verification-contract.md"):
        if not (ROOT / required).is_file():
            fail(f"missing required document: {required}")
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
    cpu_plan = (ROOT / "cpu-validation.md").read_text()
    if "CPU-PIPE-LAT" not in cpu_plan or "CPU-PIPE-THRU" in cpu_plan:
        fail("CPU structural timing gate must use per-instruction latency")
    if not (ROOT.parent / "evaluator" / "cpu_latency_check.py").is_file():
        fail("missing CPU latency trace checker")
    report_schema = json.loads((ROOT / "report.schema.json").read_text())
    if report_schema["properties"]["suite_id"]["const"] != manifest["suite_id"]:
        fail("report schema suite ID differs from manifest")
    if report_schema["properties"]["ppa_platform"]["const"] != sources["ppa"]["platform"]:
        fail("report schema PPA platform differs from source lock")
    if report_schema["properties"]["ppa_flow"]["const"] != sources["ppa"]["flow"]:
        fail("report schema PPA flow differs from source lock")
    return manifest, sources


def verify_cvdp(sources: dict) -> None:
    cvdp = sources["cvdp"]
    url = (
        "https://huggingface.co/datasets/"
        f"{cvdp['repository']}/resolve/{cvdp['revision']}/{cvdp['file']}"
    )
    raw = urlopen(url, timeout=60).read()
    actual_file_hash = hashlib.sha256(raw).hexdigest()
    if actual_file_hash != cvdp["file_sha256"]:
        fail("CVDP file SHA-256 differs from lock")
    rows = {row["id"]: row for row in (json.loads(line) for line in raw.splitlines())}
    for task_id, locked in cvdp["items"].items():
        row = rows.get(locked["id"])
        if row is None:
            fail(f"CVDP row missing: {task_id}")
        prompt_hash = hashlib.sha256(row["input"]["prompt"].encode()).hexdigest()
        if prompt_hash != locked["prompt_sha256"] or row["categories"] != locked["categories"]:
            fail(f"CVDP prompt/category differs: {task_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-source", action="store_true", help="download pinned CVDP file")
    args = parser.parse_args()
    manifest, sources = validate_local()
    if args.verify_source:
        verify_cvdp(sources)
    print(json.dumps({"suite_id": manifest["suite_id"], "tasks": len(manifest["tasks"]),
                      "status": manifest["status"], "source_verified": args.verify_source}))


if __name__ == "__main__":
    main()
