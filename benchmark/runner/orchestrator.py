"""Suite-level orchestration with isolated development and grading workers."""

from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid
from typing import Any

import yaml

from .adapters import AdapterRuntime, AuditResult, make_adapter
from .config import RunnerConfig
from .container import docker_command
from .pipeline import DevelopmentGradingPipeline


SNAPSHOT_DIRS = ("benchmark", "evaluator", "env", "vendor")


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + str(uuid.uuid4()))
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def inventory(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): digest_bytes(path.read_bytes())
            for path in sorted(root.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"}


def disk_usage(root: Path) -> int:
    total = 0
    for directory, _, names in os.walk(root):
        for name in names:
            try:
                total += (Path(directory) / name).lstat().st_size
            except FileNotFoundError:
                pass
    return total


class SuiteRunner:
    def __init__(self, config: RunnerConfig):
        self.config = config
        self.root = config.trial_root
        self.frozen = self.root / "frozen/ic_bcmk"
        self.adapter = make_adapter(config)
        self._event_lock = threading.RLock()
        self._state: dict[str, dict[str, Any] | None] = {"development": None, "grading": None}
        self.manifest: dict[str, Any] | None = None
        self.tasks: tuple[dict[str, Any], ...] = ()

    def event(self, kind: str, **fields: Any) -> None:
        row = {"utc": utc(), "event": kind, **fields}
        with self._event_lock:
            print(json.dumps(row, ensure_ascii=False), flush=True)
            with (self.root / "events.jsonl").open("a") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            if kind.startswith(("AGENT_", "DEVELOPMENT_")):
                self._state["development"] = row
                atomic_json(self.root / "development_status.json", row)
            elif kind.startswith(("GRADE_", "GRADING_")):
                self._state["grading"] = row
                atomic_json(self.root / "grading_status.json", row)
            atomic_json(self.root / "status.json", {
                "utc": utc(), "event": "PIPELINE_RUNNING",
                "development": self._state["development"],
                "grading": self._state["grading"], "last_event": row,
            })

    def _freeze(self) -> None:
        if self.frozen.exists():
            return
        self.frozen.mkdir(parents=True)
        for name in SNAPSHOT_DIRS:
            source = self.config.repo_root / name
            if not source.is_dir():
                raise ValueError(f"repository snapshot source is missing: {source}")
            shutil.copytree(source, self.frozen / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    def initialize(self) -> None:
        if self.root.exists() and not self.root.is_dir():
            raise ValueError(f"trial_root is not a directory: {self.root}")
        self.root.mkdir(parents=True, exist_ok=True)
        self.config.private_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._freeze()
        manifest = yaml.safe_load((self.frozen / "benchmark/manifest.yaml").read_text())
        if manifest.get("token_usage_policy") != "record_only":
            raise ValueError("official runner requires record-only token accounting")
        hardware = manifest.get("hardware_limit", {})
        for key in ("vcpu", "ram_gib", "disk_gib"):
            if type(hardware.get(key)) is not int or hardware[key] <= 0:
                raise ValueError(f"invalid benchmark hardware limit: {key}")
        by_id = {task["id"]: task for task in manifest.get("tasks", [])}
        order = self.config.task_order or tuple(by_id)
        if any(task not in by_id for task in order):
            raise ValueError("task_order contains a task absent from the benchmark manifest")
        self.manifest = manifest
        self.tasks = tuple(by_id[task] for task in order)
        run_manifest = self.root / "run_manifest.json"
        config_sha = digest_bytes(self.config.path.read_bytes())
        frozen_inventory = inventory(self.frozen)
        frozen_sha = digest_bytes(json.dumps(frozen_inventory, sort_keys=True,
                                             separators=(",", ":")).encode())
        if run_manifest.is_file():
            existing = json.loads(run_manifest.read_text())
            if existing.get("config_sha256") != config_sha or existing.get("frozen_sha256") != frozen_sha:
                raise ValueError("trial configuration or frozen inputs changed after launch")
        else:
            try:
                commit = subprocess.check_output(
                    ["git", "-C", str(self.config.repo_root), "rev-parse", "HEAD"],
                    text=True, stderr=subprocess.DEVNULL).strip()
                dirty = bool(subprocess.check_output(
                    ["git", "-C", str(self.config.repo_root), "status", "--porcelain"],
                    text=True, stderr=subprocess.DEVNULL).strip())
            except (OSError, subprocess.CalledProcessError):
                commit, dirty = None, None
            atomic_json(self.root / "snapshot_inventory.json", frozen_inventory)
            atomic_json(run_manifest, {
                "schema_version": 1, "suite_id": manifest.get("suite_id"),
                "model": self.config.agent.model,
                "reasoning_effort": self.config.agent.reasoning_effort,
                "adapter": self.config.agent.adapter,
                "agent_binary": str(self.config.agent.binary),
                "agent_binary_sha256": digest_bytes(self.config.agent.binary.read_bytes())
                    if self.config.agent.binary.is_file() else None,
                "skills": self.config.agent.skills.__dict__,
                "tools": {"web": self.config.agent.tools.web,
                          "multi_agent": self.config.agent.tools.multi_agent,
                          "allowed": list(self.config.agent.tools.allowed)},
                "token_usage_policy": "record_only", "token_stop_enabled": False,
                "task_order": list(order), "hardware_limit": hardware,
                "config_sha256": config_sha, "frozen_sha256": frozen_sha,
                "source_commit": commit, "source_worktree_dirty": dirty,
                "started_utc": utc(),
            })

    def preflight(self) -> None:
        assert self.manifest is not None
        self.adapter.preflight()
        if not self.config.orfs_root and any(task["id"] in ("T08", "T09", "T10") for task in self.tasks):
            raise ValueError("T08/T09/T10 require orfs_root for the public EDA kit")
        if self.config.orfs_root is not None and not (self.config.orfs_root / "flow/Makefile").is_file():
            raise ValueError("orfs_root does not contain flow/Makefile")
        for mount in self.config.readonly_mounts:
            if not mount.source.exists():
                raise ValueError(f"configured tool mount is missing: {mount.source}")
            if mount.source == self.config.repo_root or mount.source.is_relative_to(self.config.repo_root):
                raise ValueError("the host repository must never be mounted into a candidate container")
        if not self.config.grader.lock.parent.exists():
            self.config.grader.lock.parent.mkdir(parents=True, exist_ok=True)

    def _prepare_task(self, task: dict[str, Any]) -> tuple[Path, AdapterRuntime]:
        task_id = task["id"]
        directory = self.root / "tasks" / task_id
        runtime_path = directory / "adapter_runtime.json"
        if directory.exists():
            if not runtime_path.is_file():
                clock = directory / "workspace/TRIAL_CLOCK.json"
                session = directory / "session.jsonl"
                if clock.exists() or (session.exists() and session.stat().st_size):
                    raise RuntimeError(f"{task_id} has an unclassified started attempt; refusing to replace it")
                archive = self.root / "infrastructure_failures" / f"{task_id}-{uuid.uuid4().hex[:8]}"
                archive.parent.mkdir(parents=True, exist_ok=True)
                directory.rename(archive)
                self.event("PRESTART_ATTEMPT_ARCHIVED", task=task_id, archive=str(archive))
            else:
                raw = json.loads(runtime_path.read_text())
                from .adapters import Mount
                mounts = tuple(Mount(Path(item["source"]), item["target"], item["readonly"])
                               for item in raw.get("mounts", []))
                runtime = AdapterRuntime(raw["shell"], mounts, tuple(raw.get("environment", [])),
                                         Path(raw["audit_home"]) if raw.get("audit_home") else None)
                # Mounts are reconstructed by prepare only for a fresh launch. Existing
                # attempts recover from their recorded docker command/manifest instead.
                return directory, runtime
        directory.mkdir(parents=True)
        for name in ("agent_home", "empty_skills", "tmp"):
            (directory / name).mkdir(mode=0o700)
        command = [sys.executable, str(self.frozen / "benchmark/prepare_trial.py"),
                   task_id, str(directory / "workspace")]
        if task_id in ("T08", "T09", "T10"):
            assert self.config.orfs_root is not None
            command += ["--orfs-root", str(self.config.orfs_root)]
        subprocess.run(command, cwd=self.frozen, check=True,
                       env=os.environ | {"PYTHONPATH": str(self.frozen)},
                       stdout=subprocess.DEVNULL)
        policy = self.config.agent.skills
        with (directory / "workspace/PROMPT.md").open("a") as stream:
            stream.write("\nTrial tool policy: official built-in Skills are " +
                         ("enabled" if policy.builtin else "disabled") +
                         "; user and external Skills are disabled. Direct web tools are " +
                         ("enabled" if self.config.agent.tools.web else "disabled") +
                         "; multi-Agent delegation is " +
                         ("enabled" if self.config.agent.tools.multi_agent else "disabled") + ".\n")
        private_dir = self.config.private_root / self.root.name / task_id
        if private_dir.exists():
            raise RuntimeError(f"private task state already exists without a recorded attempt: {private_dir}")
        private_dir.mkdir(parents=True, mode=0o700)
        runtime = self.adapter.prepare(directory, private_dir, int(task["time_limit_minutes"]) * 60)
        atomic_json(runtime_path, {"shell": runtime.shell,
                                  "mounts": [{"source": str(mount.source),
                                              "target": mount.target,
                                              "readonly": mount.readonly}
                                             for mount in runtime.mounts],
                                  "environment": list(runtime.environment),
                                  "audit_home": str(runtime.audit_home) if runtime.audit_home else None})
        return directory, runtime

    def _container_state(self, name: str) -> dict[str, Any] | None:
        result = subprocess.run(["docker", "inspect", "--format", "{{json .State}}", name],
                                capture_output=True, text=True)
        return json.loads(result.stdout) if result.returncode == 0 else None

    def _finalize_agent(self, task: dict[str, Any], directory: Path,
                        runtime: AdapterRuntime, state: dict[str, Any], elapsed: float,
                        *, recovered: bool = False) -> Path:
        task_id = task["id"]
        private_dir = self.config.private_root / self.root.name / task_id
        audit = self.adapter.audit(directory, runtime)
        if not audit.initialized or not audit.binding_verified:
            raise RuntimeError(f"{task_id} did not prove the requested model/effort binding")
        seconds = int(task["time_limit_minutes"]) * 60
        exit_code = int(state.get("ExitCode", -1))
        deadline = exit_code == 124 and elapsed >= seconds - 2
        if state.get("OOMKilled"):
            raise RuntimeError(f"{task_id} candidate container exceeded the benchmark RAM limit")
        if audit.failed and not deadline:
            raise RuntimeError(f"{task_id} Agent/API failed before the task deadline")
        if exit_code not in (0, 124) and not deadline:
            raise RuntimeError(f"{task_id} candidate exited unexpectedly: {exit_code}")
        self.adapter.finalize(directory, private_dir, runtime)
        submission = directory / "submission"
        if not submission.exists():
            shutil.copytree(directory / "workspace", submission, symlinks=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        record = {
            "task_id": task_id, "model": self.config.agent.model,
            "reasoning_effort": self.config.agent.reasoning_effort,
            "exit_code": exit_code, "elapsed_seconds": min(elapsed, seconds),
            "tokens": audit.tokens, "session_id": audit.session_id,
            "stop_reason": "development_time_limit" if deadline else None,
            "recovered_completed_attempt": recovered, "finished_utc": utc(),
        }
        atomic_json(directory / "container_exit.json", state)
        atomic_json(directory / "agent_result.json", record)
        self.event("AGENT_RECOVERED" if recovered else "AGENT_FINISH", **record)
        self._summary()
        return directory

    def _recover_agent(self, task: dict[str, Any], directory: Path,
                       runtime: AdapterRuntime) -> Path | None:
        if (directory / "agent_result.json").is_file():
            if not (directory / "submission").is_dir():
                raise RuntimeError(f"{task['id']} is marked complete without a submission")
            return directory
        run = directory / "run_manifest.json"
        clock_path = directory / "workspace/TRIAL_CLOCK.json"
        if not run.is_file() or not clock_path.is_file():
            return None
        metadata = json.loads(run.read_text())
        state = self._container_state(metadata["container"])
        if state is None:
            raise RuntimeError(f"{task['id']} started but its container evidence is missing")
        clock = json.loads(clock_path.read_text())
        deadline = float(clock["deadline_epoch"])
        while state.get("Running"):
            if time.time() > deadline + 30:
                subprocess.run(["docker", "stop", "--time", "10", metadata["container"]],
                               capture_output=True)
            time.sleep(2)
            state = self._container_state(metadata["container"])
            if state is None:
                raise RuntimeError("candidate container vanished during recovery")
        recovered_log = directory / "session.recovered.jsonl"
        with recovered_log.open("w") as stream:
            subprocess.run(["docker", "logs", metadata["container"]], stdout=stream,
                           stderr=subprocess.STDOUT, text=True, check=False)
        session = directory / "session.jsonl"
        if session.is_file():
            shutil.copy2(session, directory / "session.before_recovery.jsonl")
        shutil.copy2(recovered_log, session)
        finished = dt.datetime.fromisoformat(state["FinishedAt"].replace("Z", "+00:00")).timestamp()
        elapsed = max(0.0, finished - float(clock["started_epoch"]))
        return self._finalize_agent(task, directory, runtime, state, elapsed, recovered=True)

    def develop(self, task: dict[str, Any]) -> Path:
        task_id = task["id"]
        directory, runtime = self._prepare_task(task)
        recovered = self._recover_agent(task, directory, runtime)
        if recovered is not None:
            return recovered
        private_dir = self.config.private_root / self.root.name / task_id
        container = f"ic-bcmk-{self.config.agent.adapter}-{self.root.name[-8:]}-{task_id.lower()}-{uuid.uuid4().hex[:6]}"
        hardware = self.manifest["hardware_limit"]  # type: ignore[index]
        command = docker_command(self.config, directory, runtime, container,
                                 cpus=hardware["vcpu"], memory_gib=hardware["ram_gib"])
        atomic_json(directory / "command.json", command)
        atomic_json(directory / "run_manifest.json", {
            "task_id": task_id, "model": self.config.agent.model,
            "reasoning_effort": self.config.agent.reasoning_effort,
            "adapter": self.config.agent.adapter, "container": container,
            "time_limit_seconds": int(task["time_limit_minutes"]) * 60,
            "token_usage_policy": "record_only", "token_stop_enabled": False,
            "resource_limits": hardware,
        })
        log_path = directory / "session.jsonl"
        process = None
        try:
            with log_path.open("w") as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                for _ in range(450):
                    if process.poll() is not None:
                        raise RuntimeError(f"{task_id} container failed before the start gate")
                    state = self._container_state(container)
                    if state and state.get("Running"):
                        break
                    time.sleep(0.1)
                else:
                    raise RuntimeError(f"{task_id} container did not become ready")
                started = time.time()
                seconds = int(task["time_limit_minutes"]) * 60
                atomic_json(directory / "workspace/TRIAL_CLOCK.json", {
                    "task_id": task_id, "model": self.config.agent.model,
                    "started_epoch": started, "deadline_epoch": started + seconds,
                    "started_utc": utc(), "time_limit_seconds": seconds,
                })
                (directory / "tmp/start_trial").touch()
                self.event("AGENT_START", task=task_id, model=self.config.agent.model,
                           reasoning_effort=self.config.agent.reasoning_effort,
                           limit_minutes=task["time_limit_minutes"], container=container)
                heartbeat = disk_sample = 0.0
                peak_disk = 0
                while process.poll() is None:
                    now = time.monotonic()
                    audit = self.adapter.audit(directory, runtime)
                    if now - disk_sample >= 10:
                        # Count candidate-writable state only. The read-only public EDA
                        # kit and host-side logs are infrastructure, not candidate disk.
                        current_disk = sum(disk_usage(directory / name)
                                           for name in ("workspace", "agent_home", "tmp"))
                        current_disk += disk_usage(private_dir)
                        peak_disk = max(peak_disk, current_disk)
                        if current_disk > hardware["disk_gib"] * 1024 ** 3:
                            subprocess.run(["docker", "stop", "--time", "10", container],
                                           capture_output=True)
                            raise RuntimeError(f"{task_id} exceeded the benchmark disk limit")
                        disk_sample = now
                    atomic_json(directory / "telemetry.json", {
                        "utc": utc(), "elapsed_seconds": time.time() - started,
                        "tokens": audit.tokens, "disk_bytes": current_disk,
                        "peak_disk_bytes": peak_disk,
                    })
                    if now - heartbeat >= 60:
                        self.event("AGENT_HEARTBEAT", task=task_id,
                                   elapsed_seconds=round(time.time() - started), tokens=audit.tokens)
                        heartbeat = now
                    time.sleep(1)
                process.wait(timeout=30)
                elapsed = time.time() - started
            state = self._container_state(container)
            if state is None:
                raise RuntimeError(f"{task_id} container evidence disappeared")
            return self._finalize_agent(task, directory, runtime, state, elapsed)
        finally:
            subprocess.run(["docker", "stop", "--time", "2", container], capture_output=True)
            if process is not None and process.poll() is None:
                process.wait(timeout=30)

    def _grader_command(self, task: dict[str, Any], directory: Path, output: Path) -> list[str]:
        result = json.loads((directory / "agent_result.json").read_text())
        values = {
            "task_id": task["id"], "trial_root": str(self.root),
            "task_root": str(directory), "submission": str(directory / "submission"),
            "grading": str(output), "repo_root": str(self.config.repo_root),
            "frozen_repo": str(self.frozen), "elapsed_seconds": str(result["elapsed_seconds"]),
        }
        try:
            return [item.format(**values) for item in self.config.grader.command]
        except KeyError as error:
            raise ValueError(f"unknown grader command placeholder: {error}") from error

    def grade(self, task: dict[str, Any], directory: Path) -> dict[str, Any]:
        task_id = task["id"]
        output = self.root / "grading" / task_id
        report_path = output / "report.json"
        if report_path.is_file():
            return json.loads(report_path.read_text())
        output.mkdir(parents=True, exist_ok=True)
        command = self._grader_command(task, directory, output)
        self.event("GRADE_QUEUED", task=task_id)
        request = output / "grade_job.json"
        atomic_json(request, {
            "command": command, "cwd": str(self.frozen),
            "driver_log": str(output / "driver.log"),
            "lock": str(self.config.grader.lock), "report": str(report_path),
            "status": str(output / "job_status.json"),
            "pythonpath": str(self.frozen),
        })
        self.event("GRADE_START", task=task_id)
        with (output / "grade_job.log").open("a") as job_log:
            process = subprocess.Popen(
                [sys.executable, str(self.frozen / "benchmark/runner/grade_job.py"), str(request)],
                stdout=job_log, stderr=subprocess.STDOUT)
            heartbeat = 0.0
            while process.poll() is None:
                now = time.monotonic()
                if now - heartbeat >= 60:
                    job_status = output / "job_status.json"
                    phase = "starting"
                    if job_status.is_file():
                        try:
                            phase = json.loads(job_status.read_text()).get("phase", phase)
                        except (OSError, json.JSONDecodeError):
                            pass
                    self.event("GRADE_HEARTBEAT", task=task_id, phase=phase,
                               log=str(output / "driver.log"))
                    heartbeat = now
                time.sleep(1)
            returncode = process.wait()
        if returncode or not report_path.is_file():
            raise RuntimeError(f"grader failed for {task_id} with exit {returncode}")
        report = json.loads(report_path.read_text())
        self.event("GRADE_FINISH", task=task_id, status=report.get("status"),
                   functional=report.get("functional_total"), ppa=report.get("ppa_score"),
                   display=report.get("display_score"))
        self._summary()
        return report

    def _summary(self) -> None:
        rows = []
        for task in self.tasks:
            report = self.root / "grading" / task["id"] / "report.json"
            agent = self.root / "tasks" / task["id"] / "agent_result.json"
            if report.is_file():
                rows.append(json.loads(report.read_text()))
            elif agent.is_file():
                rows.append({"task_id": task["id"], "status": "grading_queued",
                             "functional_total": None, "ppa_score": None,
                             "time_score": None, "display_score": None})
        scores = {row["task_id"]: row.get("display_score") for row in rows}
        try:
            from evaluator.score_run import weighted_suite_score
            aggregate = weighted_suite_score(scores)
        except (ImportError, ValueError, TypeError):
            aggregate = {}
        atomic_json(self.root / "summary.json", {
            "model": self.config.agent.model,
            "reasoning_effort": self.config.agent.reasoning_effort,
            "developed_tasks": sum((self.root / "tasks" / task["id"] / "agent_result.json").is_file()
                                   for task in self.tasks),
            "graded_tasks": sum((self.root / "grading" / task["id"] / "report.json").is_file()
                                for task in self.tasks),
            "tasks": rows, **aggregate,
        })

    def run(self) -> None:
        self.initialize()
        self.preflight()
        self._summary()
        pipeline = DevelopmentGradingPipeline(
            self.tasks, self.develop, self.grade,
            stopped=lambda: (self.root / "STOP").exists(), event=self.event)
        pipeline.run()
        self._summary()
        if (self.root / "STOP").exists():
            self.event("SUITE_STOPPED")
        else:
            self.event("SUITE_COMPLETE", model=self.config.agent.model,
                       developed_tasks=len(self.tasks), graded_tasks=len(self.tasks))

    def main(self, *, preflight_only: bool = False) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / "controller.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if preflight_only:
                self.initialize()
                self.preflight()
                self.event("PREFLIGHT_PASS")
            else:
                self.run()
