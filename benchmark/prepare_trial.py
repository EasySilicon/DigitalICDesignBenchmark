#!/usr/bin/env python3
"""Create one blind, public-only contestant workspace for a benchmark task."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
CPU_PUBLIC = (
    "cpu_elf_check.py",
    "elf_image.py",
    "make_cpu_smoke.py",
    "cpu_latency_check.py",
    "verify_act4_artifacts.py",
)


def prepare(task: str, destination: Path) -> dict:
    manifest = yaml.safe_load((ROOT / "benchmark/manifest.yaml").read_text())
    row = next((item for item in manifest["tasks"] if item["id"] == task), None)
    if row is None:
        raise ValueError(f"unknown task {task}")
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "benchmark", destination / "benchmark",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    public = destination / "evaluator/public"
    public.mkdir(parents=True)
    for name in ("README.md", "public_check.py"):
        shutil.copy2(ROOT / "evaluator" / name, destination / "evaluator" / name)
    shutil.copy2(ROOT / "evaluator/public" / f"tb_{task}.sv", public / f"tb_{task}.sv")
    if task == "T09":
        shutil.copy2(ROOT / "evaluator/public/tb_cpu_elf.sv", public / "tb_cpu_elf.sv")
        for name in CPU_PUBLIC:
            shutil.copy2(ROOT / "evaluator" / name, destination / "evaluator" / name)
        shutil.copytree(ROOT / "evaluator/act4_elfs",
                        destination / "evaluator/act4_elfs")
    (destination / "rtl").mkdir()
    (destination / "verif").mkdir()
    elf_instruction = (
        " For T09, implement the required `run.sh --elf` mode and use the "
        "copied public ELF tools to exercise it." if task == "T09" else ""
    )
    prompt = f"""You are the sole candidate Agent for benchmark task {task}. This is a fresh conversation and an independent working directory. You have {row['time_limit_minutes']} minutes of wall clock time and an aggregate input-plus-output budget of {row['same_model_token_cap']} model tokens. Use only public materials copied into this directory and installed local tools. Do not inspect other repositories or directories for benchmark reference RTL, hidden tests, answers, or scoring code.

Read `benchmark/tasks/{task}/task.md`, `benchmark/tasks/{task}/acceptance.md`, the shared rules in `benchmark/tasks.md` and `benchmark/acceptance.md`, and the full `benchmark/verification-contract.md`. Deliver synthesizable RTL in `rtl/`, `rtl/files.f`, a self-checking verification environment in `verif/`, an executable `run.sh`, and `README.md` documenting tests, limitations, design choices, and a PPA optimization comparison with measured results or attempted tool commands. Correctness has priority over PPA, and PPA over completion time.

Build your own independent scoreboard, directed edge cases, and randomized checks appropriate to the task. The copied public evaluator is a smoke test only. Run `python3 evaluator/public_check.py {task} .` and your own checks. Make `run.sh` deterministic under `BENCH_SEED` and write `results.json` in the required contract format.{elf_instruction}

Finish by summarizing your deliverables, exact test results, and known limitations. Do not claim a formal benchmark score; the evaluator will score it separately.
"""
    (destination / "PROMPT.md").write_text(prompt)
    return {"task": task, "destination": str(destination),
            "time_limit_minutes": row["time_limit_minutes"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=[f"T{i:02d}" for i in range(1, 11)])
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(prepare(args.task, args.destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
