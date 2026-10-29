"""Construct the isolated candidate container without hidden policy limits."""

from __future__ import annotations

import os
from pathlib import Path

from .adapters import AdapterRuntime, Mount
from .config import RunnerConfig


FORBIDDEN_CANDIDATE_LIMITS = (
    "--max-budget-usd", "--max-tokens", "--max-output-tokens", "--max-turns",
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS", "TOKEN_BUDGET", "TOKEN_LIMIT",
)
FORBIDDEN_TARGETS = ("/judge", "/grader", "/reference-rtl")
PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy",
              "all_proxy", "NO_PROXY", "no_proxy")


def validate_candidate_shell(shell: str) -> None:
    for token in FORBIDDEN_CANDIDATE_LIMITS:
        if token.lower() in shell.lower():
            raise ValueError(f"unapproved candidate limit in launch command: {token}")


def _mount_arg(mount: Mount) -> str:
    suffix = ":ro" if mount.readonly else ""
    return f"{mount.source}:{mount.target}{suffix}"


def _safe_target(target: str, *, adapter: bool = False) -> None:
    if target in ("/", "/workspace", "/home/benchmark", "/tmp") or any(
            target.startswith(base + "/") for base in ("/workspace", "/tmp")) or (
            not adapter and target.startswith("/home/benchmark/")) or any(
            target == forbidden or target.startswith(forbidden + "/") for forbidden in FORBIDDEN_TARGETS):
        raise ValueError(f"unsafe configured mount target: {target}")


def _verify_mount(mount: Mount) -> None:
    if not mount.source.exists():
        raise ValueError(f"mount source is missing: {mount.source}")
    if not mount.target.startswith("/"):
        raise ValueError(f"mount target is not absolute: {mount.target}")
    if any(mount.target == forbidden or mount.target.startswith(forbidden + "/")
           for forbidden in FORBIDDEN_TARGETS):
        raise ValueError(f"private judge/reference mount is forbidden: {mount.target}")


def docker_command(config: RunnerConfig, task_dir: Path, runtime: AdapterRuntime,
                   container: str, *, cpus: int, memory_gib: int) -> list[str]:
    validate_candidate_shell(runtime.shell)
    workspace = task_dir / "workspace"
    home = task_dir / "agent_home"
    empty_skills = task_dir / "empty_skills"
    temporary = task_dir / "tmp"
    for path in (workspace, home, empty_skills, temporary):
        if not path.is_dir():
            raise ValueError(f"candidate directory is missing: {path}")
    command = [
        "docker", "run", "--name", container, "--network", "host",
        "--user", f"{os.getuid()}:{os.getgid()}", "--cpus", str(cpus),
        "--memory", f"{memory_gib}g", "--memory-swap", "-1",
        "--security-opt", "no-new-privileges", "--read-only",
    ]
    for key in PROXY_KEYS:
        command += ["-e", key]
    command += ["-e", "HOME=/home/benchmark", "-e", f"PATH={config.tool_path}",
                "-e", "LANG=C.UTF-8", "-e", "LC_ALL=C.UTF-8", "-e", "CI=1"]
    base_mounts = [
        Mount(workspace, "/workspace", False), Mount(home, "/home/benchmark", False),
        Mount(empty_skills, "/empty_skills"), Mount(temporary, "/tmp", False),
    ]
    public_eda = task_dir / "public_eda"
    if public_eda.is_dir():
        destination = "/opt/benchmark_eda" if (public_eda / "task.json").is_file() else "/opt/t08_eda"
        base_mounts.append(Mount(public_eda, destination))
    configured = []
    for item in config.readonly_mounts:
        _safe_target(item.target)
        configured.append(Mount(item.source, item.target))
    for mount in configured:
        source = mount.source.resolve()
        if (config.trial_root.is_relative_to(source) or
                config.repo_root.is_relative_to(source) or
                config.private_root.is_relative_to(source)):
            raise ValueError(f"configured mount exposes an ancestor of private state, trial, or repository: {source}")
    for mount in runtime.mounts:
        _safe_target(mount.target, adapter=True)
        source = mount.source.resolve()
        if (config.trial_root.is_relative_to(source) or
                config.repo_root.is_relative_to(source) or
                config.private_root.is_relative_to(source)):
            raise ValueError(f"adapter mount exposes an ancestor of private state, trial, or repository: {source}")
    all_mounts = [*base_mounts, *configured, *runtime.mounts]
    seen_targets: set[str] = set()
    for mount in all_mounts:
        _verify_mount(mount)
        # Nested mounts are intentional for CLI credentials; exact duplicates are not.
        if mount.target in seen_targets:
            raise ValueError(f"duplicate mount target: {mount.target}")
        seen_targets.add(mount.target)
        command += ["-v", _mount_arg(mount)]
    for value in runtime.environment:
        if "=" not in value or value.split("=", 1)[0] in {"HOME", "PATH"}:
            raise ValueError(f"invalid adapter environment entry: {value}")
        command += ["-e", value]
    command += ["-w", "/workspace", config.image, "bash", "-lc", runtime.shell]
    return command
