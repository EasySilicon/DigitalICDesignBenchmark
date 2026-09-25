#!/usr/bin/env python3
"""Check the submission's own verification handoff; never use it as RTL oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

if __package__:
    from .public_check import sources_from_filelist
else:
    from public_check import sources_from_filelist


def read_result(path: Path) -> dict:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("results.json must contain an object")
    return data


def run_entry(submission: Path, args: list[str], seed: int, timeout: int) -> tuple[int, dict, str]:
    result_path = submission / "results.json"
    result_path.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment["BENCH_SEED"] = str(seed)
    finished = subprocess.run([str(submission / "run.sh"), *args], cwd=submission,
                              env=environment, text=True, capture_output=True,
                              timeout=timeout, check=False)
    if not result_path.is_file():
        raise ValueError("run.sh did not create results.json")
    return (finished.returncode, read_result(result_path),
            (finished.stdout + finished.stderr)[-2000:])


def check_normal(result: dict, seed: int) -> list[tuple[str, bool, int]]:
    tests = result.get("tests")
    if not isinstance(tests, list) or not tests:
        raise ValueError("results.json needs a nonempty tests array")
    rows = []
    for item in tests:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or \
                not item["name"].strip() or not isinstance(item.get("passed"), bool) or \
                type(item.get("seed")) is not int or item["seed"] != seed:
            raise ValueError("test row must have name, boolean passed, and requested seed")
        rows.append((item["name"], item["passed"], item["seed"]))
    if len({row[0] for row in rows}) != len(rows):
        raise ValueError("duplicate test names")
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


def check_elf_result(result: dict, elf: Path, expected_success: bool, code: int) -> None:
    digest = hashlib.sha256(elf.read_bytes()).hexdigest()
    if result.get("elf_sha256") != digest:
        raise ValueError("ELF result SHA-256 mismatch")
    tohost = result.get("tohost")
    timed_out = result.get("timed_out")
    if type(tohost) is not int or not isinstance(timed_out, bool):
        raise ValueError("ELF result needs integer tohost and boolean timed_out")
    if expected_success:
        if code != 0 or tohost != 1 or timed_out:
            raise ValueError("positive ELF did not report successful tohost=1")
    elif code == 0 or tohost == 1 or not isinstance(result.get("failure_reason"), str) \
            or not result["failure_reason"].strip():
        raise ValueError("negative ELF was not rejected with a reason")


def check(task: str, submission: Path, seed: int, timeout: int,
          good_elf: Path | None = None, bad_elf: Path | None = None) -> dict:
    submission = submission.resolve(strict=True)
    findings = []
    try:
        sources_from_filelist(submission)
        run_sh = submission / "run.sh"
        if not run_sh.is_file() or not os.access(run_sh, os.X_OK):
            raise ValueError("run.sh missing or not executable")
        verif = submission / "verif"
        if not verif.is_dir() or not any(path.is_file() for path in verif.rglob("*")):
            raise ValueError("verif/ missing or empty")
        readme = submission / "README.md"
        if not readme.is_file() or not readme.read_text().strip():
            raise ValueError("README.md missing or empty")
        rows = []
        for index in range(2):
            code, result, _ = run_entry(submission, [], seed, timeout)
            if code != 0:
                raise ValueError(f"self-check run {index + 1} exited {code}")
            rows.append(check_normal(result, seed))
        if rows[0] != rows[1]:
            raise ValueError("same-seed self-check results changed")
        if task == "T09":
            if good_elf is None or bad_elf is None:
                raise ValueError("T09 requires evaluator-owned positive and negative ELF probes")
            with tempfile.TemporaryDirectory(prefix="ic_bcmk_delivery_elf_") as directory:
                for source, expected_success in ((good_elf, True), (bad_elf, False)):
                    elf = Path(directory) / f"program_{secrets.token_hex(8)}.elf"
                    shutil.copyfile(source, elf)
                    code, result, _ = run_entry(submission, ["--elf", str(elf)],
                                                seed, timeout)
                    check_elf_result(result, elf, expected_success, code)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        findings.append(str(exc))
    return {"task_id": task, "delivery_qualified": not findings,
            "self_check_tests": len(rows[0]) if "rows" in locals() and rows else 0,
            "findings": findings,
            "note": "self-check validity only; RTL function is independently scored"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=[f"T{i:02d}" for i in range(1, 10)])
    parser.add_argument("submission", type=Path)
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--good-elf", type=Path)
    parser.add_argument("--bad-elf", type=Path)
    args = parser.parse_args()
    result = check(args.task, args.submission, args.seed, args.timeout,
                   args.good_elf, args.bad_elf)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["delivery_qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
