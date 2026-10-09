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
SHARED_BENCHMARK_FILES = {"candidate-rules.md": "README.md"}
TASK_BENCHMARK_FILES = {
    "T09": ("sources.lock.yaml",),
    "T10": ("npu-validation.md",),
}
# Fail closed: future author notes/private assets are not candidate inputs.
T08_PUBLIC_FILES = (
    "task.md", "task.yaml", "acceptance.md", "README.md", "PROVENANCE.md",
    "starter.sha256",
)


def copy_public_task_materials(task: str, destination: Path) -> None:
    """Copy only shared rules and the selected task's public materials."""
    benchmark = destination / "benchmark"
    benchmark.mkdir()
    for source_name, target_name in SHARED_BENCHMARK_FILES.items():
        shutil.copy2(ROOT / "benchmark" / source_name, benchmark / target_name)
    for name in TASK_BENCHMARK_FILES.get(task, ()):
        shutil.copy2(ROOT / "benchmark" / name, benchmark / name)

    tasks = benchmark / "tasks"
    tasks.mkdir()
    source = ROOT / "benchmark/tasks" / task
    target = tasks / task
    if task == "T08":
        target.mkdir()
        for name in T08_PUBLIC_FILES:
            shutil.copy2(source / name, target / name)
        (target / "starter").mkdir()
        shutil.copy2(source / "starter/LICENSE.upstream", target / "starter/LICENSE.upstream")
        (target / "starter/rtl").mkdir()
        for path in sorted((source / "starter/rtl").iterdir()):
            if path.suffix in {".v", ".sv"} or path.name == "files.f":
                if not path.is_file() or path.is_symlink():
                    raise ValueError(f"invalid public starter file: {path}")
                shutil.copy2(path, target / "starter/rtl" / path.name)
    else:
        shutil.copytree(source, target,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "FREEZE.json", "PPA_FREEZE.json", "AUTHOR_GUIDE.md"))

    if task == "T09":
        shutil.copytree(ROOT / "benchmark/cpu/act4", benchmark / "cpu/act4")


def prepare(task: str, destination: Path, *, time_limit_minutes: int | None = None) -> dict:
    manifest = yaml.safe_load((ROOT / "benchmark/manifest.yaml").read_text())
    row = next((item for item in manifest["tasks"] if item["id"] == task), None)
    if row is None:
        raise ValueError(f"unknown task {task}")
    original_minutes = row['time_limit_minutes']
    if time_limit_minutes is not None:
        if task != 'T08' or type(time_limit_minutes) is not int or time_limit_minutes <= 0:
            raise ValueError('positive whole-minute trial overrides are supported only for T08')
        row = {**row, 'time_limit_minutes': time_limit_minutes}
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    copy_public_task_materials(task, destination)
    if task == 'T08' and time_limit_minutes is not None:
        public_task = destination / 'benchmark/tasks/T08'
        metadata_path = public_task / 'task.yaml'
        metadata = yaml.safe_load(metadata_path.read_text())
        metadata['time_limit_minutes'] = time_limit_minutes
        metadata['trial_time_limit_override'] = True
        metadata_path.write_text(yaml.safe_dump(metadata, sort_keys=False))
        replacements = {
            'task.md': [(f'Budget: {original_minutes} minutes', f'Budget: {time_limit_minutes} minutes'),
                        (f'{original_minutes}-minute budget', f'{time_limit_minutes}-minute budget')],
            'README.md': [(f'{original_minutes} 分钟', f'{time_limit_minutes} 分钟')],
            'acceptance.md': [(f'{original_minutes*60:,} seconds', f'{time_limit_minutes*60:,} seconds')],
        }
        for filename, changes in replacements.items():
            path = public_task / filename
            text = path.read_text()
            for old, new in changes:
                if old not in text:
                    raise ValueError(f'missing trial-budget anchor in {filename}: {old}')
                text = text.replace(old, new)
            path.write_text(text)
    public = destination / "evaluator/public"
    public.mkdir(parents=True)
    shutil.copy2(ROOT / "evaluator/public_check.py",
                 destination / "evaluator/public_check.py")
    shutil.copy2(ROOT / "evaluator/public" / f"tb_{task}.sv", public / f"tb_{task}.sv")
    if task == "T09":
        shutil.copy2(ROOT / "evaluator/public/tb_cpu_elf.sv", public / "tb_cpu_elf.sv")
        for name in CPU_PUBLIC:
            shutil.copy2(ROOT / "evaluator" / name, destination / "evaluator" / name)
        shutil.copytree(ROOT / "evaluator/act4_elfs",
                        destination / "evaluator/act4_elfs")
    if task == "T08":
        public_task = destination / "benchmark/tasks/T08"
        shutil.copytree(public_task / "starter/rtl", destination / "rtl")
        shutil.copy2(public_task / "starter/LICENSE.upstream",
                     destination / "LICENSE.upstream")
    else:
        (destination / "rtl").mkdir()
    (destination / "verif").mkdir()
    elf_instruction = (
        " For T09, implement the required `run.sh --elf` mode and use the "
        "copied public ELF tools to exercise it." if task == "T09" else ""
    )
    token_cap = row.get("same_model_token_cap")
    token_instruction = (
        f"and an aggregate input-plus-output budget of {token_cap} model tokens."
        if token_cap is not None else
        "with token usage recorded but no token hard limit."
    )
    prompt = f"""You are the sole candidate Agent for benchmark task {task}. This is a fresh conversation and an independent working directory. You have {row['time_limit_minutes']} minutes of wall clock time {token_instruction} Use only public materials copied into this directory and installed local tools. Do not inspect other repositories or directories for benchmark reference RTL, hidden tests, answers, or scoring code.

Read `benchmark/tasks/{task}/task.md`, `benchmark/tasks/{task}/acceptance.md`, and the shared task rules, acceptance rules, and full verification/delivery contract in `benchmark/README.md`. Deliver synthesizable RTL in `rtl/`, `rtl/files.f`, a self-checking verification environment in `verif/`, an executable `run.sh`, and `README.md` documenting tests, limitations, design choices, and a PPA optimization comparison with measured results or attempted tool commands. Correctness has priority over PPA, and PPA over completion time.

Build your own independent scoreboard, directed edge cases, and randomized checks appropriate to the task. The copied public evaluator is a smoke test only. Run `python3 evaluator/public_check.py {task} .` and your own checks. Make `run.sh` deterministic under `BENCH_SEED` and write `results.json` in the required contract format.{elf_instruction}

Finish by summarizing your deliverables, exact test results, and known limitations. Do not claim a formal benchmark score; the evaluator will score it separately.
"""
    if task == "T08":
        prompt += """
T08 is a frozen brownfield task: modify the supplied buggy RTL. Its
task.md and acceptance.md override shared rules. Functional maximum is 50;
routed PPA has a frozen three-seed 1 GHz reference and contributes up to 50 points.
Do not fabricate PPA points or an official /105 score. Attempt local synthesis
and document the actual results; the evaluator independently measures routed PPA.
Read task.md section 1.5 for the SRAM physical policy. Generic synthesizable
FIFO arrays are sufficient; manual macro instantiation or library downloads
are not required. Preserve capacity, read/valid alignment and stall retention.
The 1 GHz physical target does not replace the functional GMII clock profile.

No Agent Skills are supplied. Do not discover, load or install Skills. Direct
web-search/fetch tools are disabled; do not download this repository or upstream
answers through other tools. Use the copied self-contained specification and
local tools. Do not use other model Agents. Keep your session persistent.
The clock starts only when the runner releases the start gate. Read
TRIAL_CLOCK.json for the deadline and check remaining time periodically.
Your compilation/simulation/EDA wall time is recorded separately from total
elapsed time; host preparation and independent grading are excluded.
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
