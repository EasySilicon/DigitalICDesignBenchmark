#!/usr/bin/env python3
"""Check the submission's own verification handoff; never use it as RTL oracle."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

if __package__:
    from .delivery_policy import assessment
    from .public_check import sources_from_filelist
else:
    from delivery_policy import assessment
    from public_check import sources_from_filelist


def read_result(path: Path) -> dict:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("results.json must contain an object")
    return data


# The agent runs inside a container at /workspace, while grading normally runs
# from a host path.  Simulator products often embed their build-time absolute
# path, so they are not part of a portable source handoff and must not be reused
# by the delivery check.
GENERATED_ROOT_ENTRIES = {
    ".git",
    "build",
    "obj_dir",
    "reports",
    "results.json",
}


def stage_submission(source: Path, destination: Path) -> None:
    """Copy a source handoff without root-level generated build products."""
    destination.mkdir()
    for entry in source.iterdir():
        if entry.name in GENERATED_ROOT_ENTRIES:
            continue
        target = destination / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target, symlinks=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif entry.is_file() or entry.is_symlink():
            shutil.copy2(entry, target, follow_symlinks=False)


def run_entry(submission: Path, args: list[str], seed: int, timeout: int) -> tuple[int, dict, str]:
    result_path = submission / "results.json"
    result_path.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment["BENCH_SEED"] = str(seed)
    finished = subprocess.run([str(submission / "run.sh"), *args], cwd=submission,
                              env=environment, text=True, capture_output=True,
                              timeout=timeout, check=False)
    output = (finished.stdout + finished.stderr)[-2000:]
    if not result_path.is_file():
        raise ValueError(f"run.sh did not create results.json; output tail:\n{output}")
    return (finished.returncode, read_result(result_path),
            output)


def check_normal(result: dict) -> list[tuple[str, bool, int]]:
    tests = result.get("tests")
    if not isinstance(tests, list) or not tests:
        raise ValueError("results.json needs a nonempty tests array")
    rows = []
    for item in tests:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or \
                not item["name"].strip() or not isinstance(item.get("passed"), bool) or \
                type(item.get("seed")) is not int:
            raise ValueError("test row must have name, boolean passed, and integer seed")
        rows.append((item["name"], item["passed"], item["seed"]))
    # A self-check may intentionally repeat the same named scenario under
    # several deterministic seeds.  The pair identifies a test instance;
    # rejecting a repeated name alone incorrectly penalizes multi-seed suites.
    if len({(row[0], row[2]) for row in rows}) != len(rows):
        raise ValueError("duplicate test name/seed pairs")
    if not all(row[1] for row in rows):
        raise ValueError("submission self-check failed")
    versions = result.get("tool_versions")
    if not isinstance(versions, dict) or not versions or not all(
            isinstance(name, str) and name and isinstance(version, str) and version
            for name, version in versions.items()):
        raise ValueError("tool_versions must contain named version strings")
    elapsed = result.get("elapsed_seconds")
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("elapsed_seconds must be finite and nonnegative")
    return rows


def inspect_contract(submission: Path) -> dict:
    """Inventory every required handoff item before attempting execution.

    A missing directory counts once; its absent children are not extra missing
    items. Runtime findings still require attribution before they cost points.
    """
    missing, errors = [], []
    def error(root, detail, attribution="candidate"):
        errors.append(dict(root_cause=root, detail=detail, attribution=attribution))
    rtl = submission / "rtl"
    if not rtl.is_dir() or not any(p.is_file() for p in rtl.rglob("*")):
        missing.append("rtl/")
    elif not (rtl / "files.f").is_file():
        missing.append("rtl/files.f")
    else:
        try:
            sources_from_filelist(submission)
        except ValueError as exc:
            error("rtl_filelist", str(exc))
        except FileNotFoundError as exc:
            error("rtl_filelist", str(exc))
        except OSError as exc:
            error("rtl_filelist", str(exc), "pending")
    run_sh = submission / "run.sh"
    if not run_sh.is_file():
        missing.append("run.sh")
    elif not os.access(run_sh, os.X_OK):
        error("run_sh_executable", "run.sh is not executable")
    verif = submission / "verif"
    if not verif.is_dir() or not any(p.is_file() for p in verif.rglob("*")):
        missing.append("verif/")
    readme = submission / "README.md"
    if not readme.is_file():
        missing.append("README.md")
    elif not readme.read_text().strip():
        error("readme_content", "README.md is empty")
    result = submission / "results.json"
    if not result.is_file():
        missing.append("results.json")
    else:
        try:
            check_normal(read_result(result))
        except (ValueError, json.JSONDecodeError) as exc:
            error("results_format", str(exc))
    return assessment(missing, errors)


def check(task: str, submission: Path, seed: int, timeout: int) -> dict:
    submission = submission.resolve(strict=True)
    report = inspect_contract(submission)
    rows = []
    root = "self_check_execution"
    attribution = "pending"
    try:
        run_sh = submission / "run.sh"
        if not run_sh.is_file() or not os.access(run_sh, os.X_OK):
            return delivery_report(task, report, rows)
        with tempfile.TemporaryDirectory(prefix=f"ic_bcmk_delivery_{task}_") as directory:
            staged = Path(directory) / "submission"
            stage_submission(submission, staged)
            for index in range(2):
                root, attribution = "self_check_execution", "pending"
                code, result, output = run_entry(staged, [], seed, timeout)
                if code != 0:
                    raise ValueError(
                        f"self-check run {index + 1} exited {code}; output tail:\n{output}")
                root, attribution = "results_format", "candidate"
                rows.append(check_normal(result))
            if rows[0] != rows[1]:
                root = "self_check_determinism"
                raise ValueError("same-seed self-check results changed")
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        if not any(e["root_cause"] == root for e in report["errors"]):
            report["errors"].append(dict(root_cause=root, detail=str(exc), attribution=attribution))
    return delivery_report(task, report, rows)


def delivery_report(task, report, rows):
    findings = [f"Missing deliverable: {name}" for name in report["missing_deliverables"]]
    findings += [e["detail"] for e in report["errors"]]
    return {"task_id": task, "delivery_qualified": not findings,
            "self_check_tests": len(rows[0]) if rows else 0,
            "findings": findings,
            "delivery_assessment": report,
            "note": "self-check validity only; RTL function is independently scored"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=[f"T{i:02d}" for i in range(1, 11)])
    parser.add_argument("submission", type=Path)
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    result = check(args.task, args.submission, args.seed, args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["delivery_qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
