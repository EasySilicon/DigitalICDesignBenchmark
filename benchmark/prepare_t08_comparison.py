#!/usr/bin/env python3
"""Freeze identical public T08 inputs and a host-only judge for supported CLIs.

Preparation only: this does not start an Agent, consume quota, copy credentials,
change host Skills, or start the 120-minute clock.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path

import yaml

from benchmark.prepare_trial import ROOT, prepare

MODELS = {
    "kimi-k3-256k": {"agent": "kimi", "model": "kimi-code/k3-256k"},
    "glm-5.3-flash": {"agent": "claude", "model": "glm-5.3-flash"},
    "deepseek-flash": {"agent": "claude", "model": "deepseek-flash"},
    "gpt-6-astra": {"agent": "codex", "model": "gpt-6-astra", "reasoning_effort": "high"},
    "gpt-6.1-sol": {"agent": "codex", "model": "gpt-6.1-sol", "reasoning_effort": "high"},
    "gpt-6-sol": {"agent": "codex", "model": "gpt-6-sol", "reasoning_effort": "high"},
}
DEFAULT_MODELS = ("kimi-k3-256k", "glm-5.3-flash")
JUDGE_FILES = (
    "evaluator/public_check.py",
    "evaluator/public/tb_T08.sv",
    "evaluator/t08_check.py",
    "evaluator/fixtures/t11_mac/tb_acceptance.sv",
    "evaluator/t08_stress_check.py",
    "evaluator/fixtures/t11_mac/tb_stress.sv",
    "benchmark/eda_time.py",
)
RUNNER_FILES = (
    "benchmark/run_t08_comparison.py",
    "benchmark/prepare_t08_comparison.py",
    "benchmark/prepare_trial.py",
)


def inventory(directory: Path) -> list[dict]:
    result = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlink is not a frozen input: {path}")
        if path.is_file():
            content = path.read_bytes()
            result.append({"path": path.relative_to(directory).as_posix(),
                           "sha256": hashlib.sha256(content).hexdigest(),
                           "bytes": len(content)})
    return result


def digest(records: list[dict]) -> str:
    return hashlib.sha256(json.dumps(records, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def copy_common_synthesis_maps(kit: Path, orfs: Path) -> None:
    """Ship required public ORFS technology maps, not any design worktree."""
    source = orfs / "flow/platforms/common/lcu_kogge_stone.v"
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"missing or unsafe ORFS synthesis map: {source}")
    target = kit / "flow/platforms/common/lcu_kogge_stone.v"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != source.read_bytes():
            raise ValueError("refusing to overwrite a different synthesis map")
        return
    shutil.copy2(source, target)


def prepare_public_eda(trial: Path, orfs: Path) -> None:
    """Copy an answer-free tool/technology kit, never the host ORFS worktree."""
    kit = trial / "public_eda"
    (kit / "flow").mkdir(parents=True)
    shutil.copy2(orfs / "flow/Makefile", kit / "flow/Makefile")
    for name in ("scripts", "util"):
        shutil.copytree(orfs / "flow" / name, kit / "flow" / name)
    copy_common_synthesis_maps(kit, orfs)
    for name in ("asap7", "lambdapdk_fakeram7"):
        shutil.copytree(ROOT / "vendor" / name, kit / name)
    for name in ("sram_libmap.txt", "sram_map.v", "sram_stub.v"):
        shutil.copy2(ROOT / "evaluator/fixtures/t11_mac" / name, kit / name)
    shutil.copy2(ROOT / "benchmark/t08_candidate_ppa.py", kit / "ppa.py")
    if any(kit.rglob("SKILL.md")) or any((kit / "flow" / name).exists()
            for name in ("designs", "logs", "results", "reports")):
        raise ValueError("unsafe public EDA kit")
    prompt = trial / "workspace/PROMPT.md"
    with prompt.open("a") as out:
        out.write("\nAn answer-free, read-only EDA kit is available at /opt/t08_eda. "
                  "It contains ORFS scripts, ASAP7 views, public SRAM views and generic "
                  "memory-mapping templates, not reference RTL or hidden tests. "
                  "For SRAM mapping only, run `python3 /opt/t08_eda/ppa.py --output "
                  "/workspace/ppa_map_1 --map-only`. For a seed11 physical iteration, "
                  "run `python3 /opt/t08_eda/ppa.py --output /workspace/ppa_iter_1`. "
                  "Use a new output directory each time. ASAP7 timing units are ps; "
                  "the target is 1000 ps / 1 GHz. Run one heavy EDA job at a time "
                  "with NUM_CORES=4. Optimize seed11 during development; the evaluator "
                  "measures the unchanged final RTL with seeds11/29/47 after submission. "
                  "Keep the task's FIFO capacities, behavior and constraints intact.\n")


def prepare_comparison(destination: Path, *, models: tuple[str, ...] | None = None,
                       time_limit_minutes: int | None = None,
                       orfs: Path | None = None) -> dict:
    names = DEFAULT_MODELS if models is None else tuple(models)
    if not names or len(set(names)) != len(names) or any(name not in MODELS for name in names):
        raise ValueError('select one or more distinct supported models')
    if time_limit_minutes is not None and (type(time_limit_minutes) is not int or time_limit_minutes <= 0):
        raise ValueError('time limit must be a positive whole number of minutes')
    selected = {name: MODELS[name] for name in names}
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    metadata = yaml.safe_load((ROOT / "benchmark/tasks/T08/task.yaml").read_text())
    minutes = metadata['time_limit_minutes'] if time_limit_minutes is None else time_limit_minutes
    start_gate = 'start_both' if len(selected) > 1 else 'start_single'
    for relative in RUNNER_FILES:
        target = destination / "frozen_runner" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    inventories = []
    for name, model in selected.items():
        trial = destination / name
        workspace = trial / "workspace"
        prepare("T08", workspace, time_limit_minutes=time_limit_minutes)
        if orfs is not None:
            prepare_public_eda(trial, orfs)
        # Validate that the delivered starting fixture matches its public lock.
        task = workspace / "benchmark/tasks/T08"
        for line in (task / "starter.sha256").read_text().splitlines():
            expected, relative = line.split()
            path = (task / relative).resolve(strict=True)
            if not path.is_relative_to(task) or path.is_symlink():
                raise ValueError(f"unsafe starter lock entry: {relative}")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f"starter lock mismatch: {relative}")
        records = inventory(workspace)
        if any(Path(record["path"]).name == "SKILL.md" for record in records):
            raise ValueError("Skill found in candidate package")
        inventories.append(records)
        write_json(trial / "starting_inventory.json", records)
        for folder in ("agent_home", "empty_skills", "tmp", "telemetry_eda", "grading"):
            (trial / folder).mkdir()
        judge = trial / "frozen_judge"
        for relative in JUDGE_FILES:
            target = judge / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        judge_inventory = inventory(judge)
        write_json(trial / "judge_inventory.json", judge_inventory)
        write_json(trial / "run_manifest.json", {
            "task": "T08", "experimental": True, **model,
            "spec_revision": metadata["spec_revision"],
            "starter_revision": metadata["starter_revision"],
            "judge_revision": metadata["judge_revision"],
            "time_limit_seconds": minutes * 60,
            "trial_time_limit_override": time_limit_minutes is not None,
            "start_gate": start_gate,
            "functional_max": metadata["functional_max"],
            "ppa_status": metadata["ppa_status"],
            "supplemental_checks": {"t08_concurrency": {
                "revision": "1.0-concurrency-progress", "scored": False,
                "expected_run_count": 270, "host_only": True}},
            "input_sha256": digest(records), "judge_sha256": digest(judge_inventory),
            "public_eda_sha256": digest(inventory(trial / "public_eda")) if orfs else None,
            "session_persistence": True, "aggregate_token_cap": None,
            "token_stop_enabled": False,
            "launch_policy": {
                "isolation": "separate Docker; only this workspace/home/tmp writable",
                "skills": "empty read-only skills; disable bundled/Skill tool",
                "direct_web_tools": "disabled",
                "normal_commands": "enabled; do not disable slash commands",
                "host_judge": "not mounted into candidate container",
                "eda_sampling_interval_seconds": 0.1,
                "eda_aggregation": "union busy intervals; preparation/judge excluded",
                "time_start": "after EDA monitor attachment, at start-gate release",
            },
        })
        write_json(trial / "status.json", {"status": "prepared", "started": False,
                                           "task": "T08", **model})
    if any(records != inventories[0] for records in inventories):
        raise ValueError("public inputs differ between models")
    judges = [inventory(destination / name / 'frozen_judge') for name in selected]
    if any(records != judges[0] for records in judges):
        raise ValueError("frozen judges differ between models")
    release = {
        "task": "T08", "status": "prepared_not_started", "experimental": True,
        "prepared_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "spec_revision": metadata["spec_revision"],
        "starter_revision": metadata["starter_revision"],
        "judge_revision": metadata["judge_revision"],
        "identical_public_inputs": True, "input_sha256": digest(inventories[0]),
        "identical_frozen_judges": True,
        "judge_sha256": digest(judges[0]),
        "models": selected, "credentials_copied": False,
        "runner_sha256": digest(inventory(destination / "frozen_runner")),
        "time_limit_seconds": minutes * 60,
        "trial_time_limit_override": time_limit_minutes is not None,
        "start_gate": start_gate,
        "functional_max": metadata["functional_max"], "ppa_status": metadata["ppa_status"],
    }
    write_json(destination / "release.json", release)
    return release


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="new, nonexistent host-only directory")
    parser.add_argument('--models', nargs='+', choices=tuple(MODELS))
    parser.add_argument('--time-limit-minutes', type=int)
    parser.add_argument('--orfs', type=Path, help='provide a sanitized public EDA kit')
    args = parser.parse_args()
    print(json.dumps(prepare_comparison(args.destination, models=args.models,
                    time_limit_minutes=args.time_limit_minutes, orfs=args.orfs), indent=2))


if __name__ == "__main__":
    main()
