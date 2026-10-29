"""Strict configuration for the benchmark trial runner.

Resource and time limits intentionally do not live here.  The runner reads them
from benchmark/manifest.yaml so a local trial configuration cannot silently add
or tighten a benchmark limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ADAPTERS = {"kimi", "codex", "claude", "zcode", "fake"}
_FORBIDDEN_LIMIT_KEYS = {
    "token_limit", "token_cap", "max_tokens", "max_output_tokens",
    "turn_limit", "max_turns", "cost_limit", "max_budget_usd",
    "response_timeout", "model_timeout",
}


def _mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be a mapping")
    return value


def _only(data: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(f"unknown {where} keys: {', '.join(unknown)}")


def _required_string(data: dict[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}.{key} must be a nonempty string")
    return value


def _path(value: Any, base: Path, where: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where} must be a path string")
    path = Path(value).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def _reject_limits(value: Any, where: str = "agent.options") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _FORBIDDEN_LIMIT_KEYS or (
                    "token" in normalized and ("limit" in normalized or "cap" in normalized)):
                raise ValueError(f"{where}.{key} is not an approved benchmark setting")
            _reject_limits(child, f"{where}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_limits(child, f"{where}[{index}]")


@dataclass(frozen=True)
class SkillPolicy:
    builtin: bool
    user: bool
    external: bool


@dataclass(frozen=True)
class ToolPolicy:
    web: bool
    multi_agent: bool
    allowed: tuple[str, ...]


@dataclass(frozen=True)
class AgentConfig:
    adapter: str
    model: str
    reasoning_effort: str
    binary: Path
    profile: Path | None
    model_alias: str | None
    skills: SkillPolicy
    tools: ToolPolicy
    options: dict[str, Any]


@dataclass(frozen=True)
class GraderConfig:
    command: tuple[str, ...]
    lock: Path


@dataclass(frozen=True)
class MountConfig:
    source: Path
    target: str


@dataclass(frozen=True)
class RunnerConfig:
    path: Path
    trial_root: Path
    repo_root: Path
    orfs_root: Path | None
    private_root: Path
    image: str
    task_order: tuple[str, ...] | None
    tool_path: str
    readonly_mounts: tuple[MountConfig, ...]
    agent: AgentConfig
    grader: GraderConfig


def _skills(raw: Any) -> SkillPolicy:
    data = _mapping(raw, "agent.skills")
    _only(data, {"builtin", "user", "external"}, "agent.skills")
    for key in ("builtin", "user", "external"):
        if type(data.get(key)) is not bool:
            raise ValueError(f"agent.skills.{key} must be explicitly true or false")
    return SkillPolicy(data["builtin"], data["user"], data["external"])


def _tools(raw: Any) -> ToolPolicy:
    data = _mapping(raw, "agent.tools")
    _only(data, {"web", "multi_agent", "allowed"}, "agent.tools")
    for key in ("web", "multi_agent"):
        if type(data.get(key)) is not bool:
            raise ValueError(f"agent.tools.{key} must be explicitly true or false")
    allowed = data.get("allowed", [])
    if not isinstance(allowed, list) or any(not isinstance(item, str) or not item for item in allowed):
        raise ValueError("agent.tools.allowed must be a list of tool names")
    if len(allowed) != len(set(allowed)):
        raise ValueError("agent.tools.allowed contains duplicates")
    return ToolPolicy(data["web"], data["multi_agent"], tuple(allowed))


def load_config(path: Path) -> RunnerConfig:
    path = path.expanduser().resolve()
    data = _mapping(yaml.safe_load(path.read_text()), "configuration")
    _only(data, {"schema_version", "trial_root", "repo_root", "orfs_root",
                 "private_root", "image", "task_order", "tool_path",
                 "readonly_mounts", "agent", "grader"}, "configuration")
    if data.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    base = path.parent
    agent_raw = _mapping(data.get("agent"), "agent")
    _only(agent_raw, {"adapter", "model", "reasoning_effort", "binary", "profile",
                      "model_alias", "skills", "tools", "options"}, "agent")
    adapter = _required_string(agent_raw, "adapter", "agent")
    if adapter not in ADAPTERS:
        raise ValueError(f"unsupported agent adapter: {adapter}")
    options = agent_raw.get("options", {})
    _mapping(options, "agent.options")
    _reject_limits(options)
    profile = agent_raw.get("profile")
    alias = agent_raw.get("model_alias")
    if alias is not None and (not isinstance(alias, str) or not alias):
        raise ValueError("agent.model_alias must be a nonempty string")
    agent = AgentConfig(
        adapter=adapter,
        model=_required_string(agent_raw, "model", "agent"),
        reasoning_effort=_required_string(agent_raw, "reasoning_effort", "agent"),
        binary=_path(agent_raw.get("binary"), base, "agent.binary"),
        profile=_path(profile, base, "agent.profile") if profile is not None else None,
        model_alias=alias,
        skills=_skills(agent_raw.get("skills")),
        tools=_tools(agent_raw.get("tools")),
        options=dict(options),
    )
    grader_raw = _mapping(data.get("grader"), "grader")
    _only(grader_raw, {"command", "lock"}, "grader")
    command = grader_raw.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(item, str) or not item for item in command):
        raise ValueError("grader.command must be a nonempty argv list")
    if not any("{task_id}" in item for item in command):
        raise ValueError("grader.command must contain {task_id}")
    mounts_raw = data.get("readonly_mounts", [])
    if not isinstance(mounts_raw, list):
        raise ValueError("readonly_mounts must be a list")
    mounts: list[MountConfig] = []
    for index, item in enumerate(mounts_raw):
        item = _mapping(item, f"readonly_mounts[{index}]")
        _only(item, {"source", "target"}, f"readonly_mounts[{index}]")
        target = _required_string(item, "target", f"readonly_mounts[{index}]")
        if not target.startswith("/"):
            raise ValueError(f"readonly_mounts[{index}].target must be absolute")
        mounts.append(MountConfig(_path(item.get("source"), base,
                                               f"readonly_mounts[{index}].source"), target))
    task_order = data.get("task_order")
    if task_order is not None:
        if not isinstance(task_order, list) or not task_order or any(
                not isinstance(item, str) for item in task_order):
            raise ValueError("task_order must be a nonempty list")
        if len(task_order) != len(set(task_order)):
            raise ValueError("task_order contains duplicates")
        task_order = tuple(task_order)
    trial_root = _path(data.get("trial_root"), base, "trial_root")
    repo_root = _path(data.get("repo_root", "."), base, "repo_root")
    private_root = _path(data.get("private_root"), base, "private_root")
    if trial_root.is_relative_to(repo_root) or repo_root.is_relative_to(trial_root):
        raise ValueError("trial_root and repo_root must not overlap")
    if private_root.is_relative_to(trial_root) or trial_root.is_relative_to(private_root):
        raise ValueError("private_root and trial_root must not overlap")
    if private_root.is_relative_to(repo_root) or repo_root.is_relative_to(private_root):
        raise ValueError("private_root and repo_root must not overlap")
    image = data.get("image", "ubuntu:24.04")
    tool_path = data.get("tool_path", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    if not isinstance(image, str) or not image or not isinstance(tool_path, str) or not tool_path:
        raise ValueError("image and tool_path must be nonempty strings")
    orfs = data.get("orfs_root")
    return RunnerConfig(
        path=path,
        trial_root=trial_root,
        repo_root=repo_root,
        orfs_root=_path(orfs, base, "orfs_root") if orfs is not None else None,
        private_root=private_root,
        image=image,
        task_order=task_order,
        tool_path=tool_path,
        readonly_mounts=tuple(mounts),
        agent=agent,
        grader=GraderConfig(tuple(command), _path(grader_raw.get("lock"), base, "grader.lock")),
    )
