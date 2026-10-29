"""Crash-resilient host grading job.

The job process owns the physical-flow lock. If its parent controller dies, the
lock remains held until grading exits. A restarted controller may enqueue the
same request; after acquiring the lock it observes report.json and exits without
running the grader twice.
"""

from __future__ import annotations

import fcntl
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


STALE_GRADING_NAMES = {"delivery_sandbox", "mapped", "physical", "functional.json",
                       "functional_score.json", "score_input.json", "measurement.json"}


def _status(path: Path, phase: str, **fields: object) -> None:
    value = {"utc": dt.datetime.now(dt.timezone.utc).isoformat(),
             "pid": os.getpid(), "phase": phase, **fields}
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}-{uuid.uuid4().hex}")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def _final_report(path: Path) -> bool:
    """Return true only for a report that may safely suppress a retry."""
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    status = value.get("status")
    if not isinstance(status, str) or not status:
        return False
    lowered = status.lower()
    return "pending" not in lowered and not lowered.startswith("infrastructure")


def _archive_stale_output(output: Path, request_path: Path,
                          request: dict[str, object]) -> Path:
    """Move an interrupted attempt aside before invoking a fresh grader."""
    archive_root = output.parent / "_attempts"
    archive_root.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = archive_root / f"{output.name}-{timestamp}-{uuid.uuid4().hex[:8]}"
    output.rename(archive)
    output.mkdir(parents=True)
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    return archive


def run(request_path: Path) -> int:
    request = json.loads(request_path.read_text())
    allowed = {"command", "cwd", "driver_log", "lock", "report", "status", "pythonpath"}
    if set(request) != allowed:
        raise ValueError("invalid grading request fields")
    command = request["command"]
    if not isinstance(command, list) or not command or any(not isinstance(item, str) for item in command):
        raise ValueError("grading command must be an argv list")
    lock_path = Path(request["lock"])
    report = Path(request["report"])
    log = Path(request["driver_log"])
    status = Path(request["status"])
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    status.parent.mkdir(parents=True, exist_ok=True)
    output = report.parent
    stale_artifacts = any(child.name in STALE_GRADING_NAMES or child.name.startswith("seed")
                          for child in output.iterdir())
    _status(status, "waiting_for_global_lock")
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if report.is_file() and _final_report(report):
            _status(status, "skipped_existing_report", returncode=0)
            return 0
        archived = None
        if report.exists() or stale_artifacts:
            archived = _archive_stale_output(output, request_path, request)
            log.parent.mkdir(parents=True, exist_ok=True)
            status.parent.mkdir(parents=True, exist_ok=True)
        _status(status, "running_grader",
                archived_attempt=str(archived) if archived else None)
        with log.open("w") as stream:
            result = subprocess.run(command, cwd=request["cwd"], stdout=stream,
                                    stderr=subprocess.STDOUT,
                                    env=os.environ | {"PYTHONPATH": request["pythonpath"]})
        if result.returncode:
            _status(status, "grader_failed", returncode=result.returncode)
            return result.returncode
        if not report.is_file():
            _status(status, "missing_report", returncode=74)
            return 74
        if not _final_report(report):
            _status(status, "retryable_report", returncode=75)
            return 75
        code = 0
        _status(status, "complete", returncode=code)
        return code


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: grade_job.py REQUEST.json")
    return run(Path(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
