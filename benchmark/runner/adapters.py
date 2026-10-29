"""Agent-CLI adapters for the common trial orchestration core."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shlex
import shutil
import tomllib
import uuid
from typing import Any

from .config import AgentConfig, RunnerConfig


@dataclass(frozen=True)
class Mount:
    source: Path
    target: str
    readonly: bool = True


@dataclass(frozen=True)
class AdapterRuntime:
    shell: str
    mounts: tuple[Mount, ...] = ()
    environment: tuple[str, ...] = ()
    audit_home: Path | None = None


@dataclass(frozen=True)
class AuditResult:
    initialized: bool
    failed: bool
    session_id: str | None
    tokens: int | None
    binding_verified: bool


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "{" + ", ".join(json.dumps(str(key)) + " = " + toml_value(child)
                                  for key, child in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(child) for child in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def _json_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(errors="replace") as stream:
        for line in stream:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = target.with_name(target.name + ".tmp-" + str(uuid.uuid4()))
    shutil.copy2(source, temporary)
    temporary.chmod(0o600)
    temporary.replace(target)


def _runtime_root(binary: Path) -> Path:
    """Return the smallest self-contained package root for a resolved CLI path."""
    for parent in binary.parents:
        if (parent / "package.json").is_file():
            return parent
        if parent.name == "node_modules":
            break
    return binary.parent


def _runtime_mount(binary: Path, target_root: str = "/opt/agent/runtime",
                   root: Path | None = None) -> tuple[Mount, str]:
    root = (root or _runtime_root(binary)).resolve()
    binary = binary.resolve()
    try:
        relative = binary.relative_to(root)
    except ValueError as error:
        raise ValueError(f"agent binary is outside its runtime root: {binary}") from error
    return Mount(root, target_root), target_root + "/" + relative.as_posix()


def _node_mount() -> tuple[Mount, str]:
    value = shutil.which("node")
    if not value:
        raise ValueError("this Agent CLI requires a host Node.js executable")
    node = Path(value).resolve()
    if not node.is_file():
        raise ValueError(f"Node.js executable is missing: {node}")
    return Mount(node, "/opt/agent-node/node"), "/opt/agent-node/node"


class Adapter:
    name = "base"

    def __init__(self, config: RunnerConfig):
        self.config = config
        self.agent = config.agent
        allowed_options = {"zcode": {"provider_config", "runtime_root"}}.get(self.name, set())
        unknown_options = sorted(set(self.agent.options) - allowed_options)
        if unknown_options:
            raise ValueError(f"unsupported {self.name} adapter options: {', '.join(unknown_options)}")
        if self.agent.skills.user or self.agent.skills.external:
            raise ValueError("user/external Skills require a separately reviewed adapter; "
                             "the official runner does not silently mount host Skills")
        if self.name in {"codex", "fake"} and self.agent.skills.builtin:
            raise ValueError(f"{self.name} adapter cannot prove a built-in Skill policy")
        if self.agent.tools.allowed and self.name not in {"kimi", "claude"}:
            raise ValueError(f"{self.name} adapter does not support a reviewed tool allowlist")
        if self.name != "kimi" and self.agent.model_alias is not None:
            raise ValueError(f"{self.name} adapter does not use agent.model_alias")

    def preflight(self) -> None:
        if not self.agent.binary.is_file():
            raise ValueError(f"agent binary is missing: {self.agent.binary}")

    def prepare(self, task_dir: Path, private_dir: Path, seconds: int) -> AdapterRuntime:
        raise NotImplementedError

    def audit(self, task_dir: Path, runtime: AdapterRuntime) -> AuditResult:
        raise NotImplementedError

    def finalize(self, task_dir: Path, private_dir: Path, runtime: AdapterRuntime) -> None:
        return None

    def _wrapped(self, invocation: str, seconds: int) -> str:
        return ("while [ ! -f /tmp/start_trial ]; do sleep 0.1; done; "
                f"exec timeout --signal=INT --kill-after=15s {seconds}s {invocation}")


class KimiAdapter(Adapter):
    name = "kimi"

    def preflight(self) -> None:
        super().preflight()
        if self.agent.profile is None or not (self.agent.profile / "config.toml").is_file():
            raise ValueError("Kimi adapter requires agent.profile with config.toml")
        if not self.agent.model_alias:
            raise ValueError("Kimi adapter requires agent.model_alias")
        if not (self.agent.profile / "credentials").is_dir():
            raise ValueError("Kimi profile is missing credentials/")
        credentials = self.agent.profile / "credentials/kimi-code.json"
        try:
            value = json.loads(credentials.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("Kimi OAuth credentials are unreadable") from error
        if not value.get("access_token") or not value.get("refresh_token"):
            raise ValueError("Kimi OAuth credentials are empty")

    def prepare(self, task_dir: Path, private_dir: Path, seconds: int) -> AdapterRuntime:
        profile = self.agent.profile
        assert profile is not None and self.agent.model_alias is not None
        host = tomllib.loads((profile / "config.toml").read_text())
        if self.agent.model_alias not in host.get("models", {}):
            raise ValueError(f"Kimi model alias is absent from profile: {self.agent.model_alias}")
        model = dict(host["models"][self.agent.model_alias])
        if model.get("model") != self.agent.model:
            raise ValueError("Kimi alias resolves to a different model")
        efforts = model.get("support_efforts", [])
        if efforts and self.agent.reasoning_effort not in efforts:
            raise ValueError("requested Kimi reasoning effort is not supported by the profile")
        provider_name = model.get("provider")
        provider = host.get("providers", {}).get(provider_name)
        if not isinstance(provider, dict) or not provider.get("oauth") or provider.get("api_key"):
            raise ValueError("Kimi runner accepts the managed OAuth profile, not embedded API keys")
        home = task_dir / "agent_home/.kimi-code"
        home.mkdir(parents=True, mode=0o700)
        (home / "credentials").mkdir(mode=0o700)
        if (profile / "oauth").is_dir():
            (home / "oauth").mkdir(mode=0o700)
        model["default_effort"] = self.agent.reasoning_effort
        disabled = []
        if not self.agent.tools.web:
            disabled += ["WebSearch", "FetchURL"]
        if not self.agent.tools.multi_agent:
            disabled += ["Agent", "AgentSwarm"]
        disabled.append("mcp__*")
        lines = [
            "default_model = " + json.dumps(self.agent.model_alias),
            "builtin_product_skills = " + toml_value(self.agent.skills.builtin),
            "[thinking]", "enabled = true",
            "effort = " + json.dumps(self.agent.reasoning_effort),
            "[models." + json.dumps(self.agent.model_alias) + "]",
        ]
        lines += [json.dumps(key) + " = " + toml_value(value) for key, value in model.items()]
        lines += ["[providers." + json.dumps(provider_name) + "]"]
        lines += [json.dumps(key) + " = " + toml_value(value) for key, value in provider.items()
                  if key in {"type", "base_url", "oauth"}]
        lines += ["[tools]", "disabled = " + toml_value(disabled)]
        config = home / "config.toml"
        config.write_text("\n".join(lines) + "\n")
        config.chmod(0o600)
        for name in ("device_id", "region"):
            if (profile / name).is_file():
                _copy_file(profile / name, home / name)
        agent_file = None
        if self.agent.tools.allowed:
            agents = home / "agents"
            agents.mkdir(mode=0o700)
            agent_file = agents / "benchmark.md"
            tools = ", ".join(self.agent.tools.allowed)
            agent_file.write_text(
                f"---\nname: benchmark\n"
                "description: Isolated benchmark task agent\n"
                f"tools: [{tools}]\n---\nFollow PROMPT.md.\n"
            )
            agent_file.chmod(0o600)
        binary_mount, binary_target = _runtime_mount(self.agent.binary)
        args = [binary_target, "-m", self.agent.model_alias,
                "--skills-dir", "/empty_skills", "--output-format", "stream-json",
                "--prompt", "$(< /workspace/PROMPT.md)"]
        invocation = " ".join(shlex.quote(arg) if not arg.startswith("$(<") else '"' + arg + '"'
                              for arg in args)
        if agent_file is not None:
            invocation += " --agent-file /home/benchmark/.kimi-code/agents/benchmark.md"
        mounts = [binary_mount,
                  # One shared mutable OAuth directory prevents divergent refresh-token copies.
                  Mount(profile / "credentials", "/home/benchmark/.kimi-code/credentials", False)]
        if (profile / "oauth").is_dir():
            mounts.append(Mount(profile / "oauth", "/home/benchmark/.kimi-code/oauth", False))
        return AdapterRuntime(
            shell=self._wrapped(invocation, seconds),
            mounts=tuple(mounts),
            environment=("KIMI_CODE_HOME=/home/benchmark/.kimi-code",),
            audit_home=task_dir / "agent_home",
        )

    def audit(self, task_dir: Path, runtime: AdapterRuntime) -> AuditResult:
        initialized = failed = binding = False
        session_id = None
        tokens = 0
        usage_records = 0
        for row in _json_rows(task_dir / "session.jsonl"):
            if row.get("role") == "assistant":
                initialized = True
            session_id = row.get("session_id") or session_id
        wires = list((task_dir / "agent_home/.kimi-code/sessions").glob("*/session_*/agents/main/wire.jsonl"))
        if len(wires) > 1:
            return AuditResult(initialized, True, session_id, None, False)
        for row in _json_rows(wires[0]) if wires else []:
            kind = row.get("type")
            if kind == "profile.bind":
                binding = (row.get("modelAlias") == self.agent.model_alias and
                           row.get("thinkingEffort") == self.agent.reasoning_effort)
                active = set(row.get("activeToolNames") or [])
                if self.agent.tools.allowed and not active <= set(self.agent.tools.allowed):
                    binding = False
                if not self.agent.tools.web and active & {"WebSearch", "FetchURL", "WebFetch"}:
                    binding = False
                if not self.agent.tools.multi_agent and active & {"Agent", "AgentSwarm", "Task"}:
                    binding = False
                session_id = wires[0].parents[2].name
            elif kind == "usage.record":
                initialized = True
                usage_records += 1
                usage = row.get("usage", {})
                tokens += sum(int(usage.get(key) or 0) for key in
                              ("inputOther", "output", "inputCacheRead", "inputCacheCreation"))
            elif kind == "turn.ended" and row.get("reason") not in ("completed", "interrupted"):
                failed = True
        return AuditResult(initialized, failed, session_id,
                           tokens if usage_records else None, binding)


class CodexAdapter(Adapter):
    name = "codex"

    def preflight(self) -> None:
        super().preflight()
        if self.agent.profile is None or not (self.agent.profile / "auth.json").is_file():
            raise ValueError("Codex adapter requires agent.profile with auth.json")

    def prepare(self, task_dir: Path, private_dir: Path, seconds: int) -> AdapterRuntime:
        assert self.agent.profile is not None
        private_home = private_dir / ".codex"
        private_home.mkdir(parents=True, mode=0o700)
        (task_dir / "agent_home/.codex").mkdir(parents=True, mode=0o700)
        chain = self.config.private_root / "auth_current/codex"
        chain.mkdir(parents=True, exist_ok=True, mode=0o700)
        source = chain / "auth.json"
        if not source.is_file():
            _copy_file(self.agent.profile / "auth.json", source)
        _copy_file(source, private_home / "auth.json")
        installation = self.agent.profile / "installation_id"
        if installation.is_file():
            _copy_file(installation, private_home / "installation_id")
        switches = ["--ignore-user-config", "--skip-git-repo-check"]
        if not self.agent.skills.user and not self.agent.skills.external:
            switches += ["--enable", "skip_host_skill_discovery", "--disable", "skill_search",
                         "--disable", "skill_mcp_dependency_install", "--disable", "plugins",
                         "--disable", "plugin_sharing"]
        if not self.agent.tools.multi_agent:
            switches += ["--disable", "multi_agent"]
        if not self.agent.tools.web:
            switches += ["-c", 'web_search="disabled"']
        binary_mount, binary_target = _runtime_mount(self.agent.binary)
        node_mount, node_target = _node_mount()
        args = [node_target, binary_target, "exec", "--json", *switches,
                "-m", self.agent.model, "-c", f'model_reasoning_effort="{self.agent.reasoning_effort}"',
                "--dangerously-bypass-approvals-and-sandbox", "-C", "/workspace",
                "--ephemeral", "--output-last-message", "/workspace/last_message.txt", "-"]
        invocation = shlex.join(args) + " < /workspace/PROMPT.md"
        return AdapterRuntime(
            shell=self._wrapped(invocation, seconds),
            mounts=(binary_mount, node_mount,
                    Mount(private_home, "/home/benchmark/.codex", False)),
            environment=("CODEX_HOME=/home/benchmark/.codex",), audit_home=private_dir)

    def audit(self, task_dir: Path, runtime: AdapterRuntime) -> AuditResult:
        initialized = failed = False
        session_id = None
        for row in _json_rows(task_dir / "session.jsonl"):
            if row.get("type") == "thread.started" and row.get("thread_id"):
                initialized = True
                session_id = row["thread_id"]
            elif row.get("type") == "turn.failed":
                failed = True
        return AuditResult(initialized, failed, session_id, None, initialized)

    def finalize(self, task_dir: Path, private_dir: Path, runtime: AdapterRuntime) -> None:
        source = private_dir / ".codex/auth.json"
        if source.is_file():
            _copy_file(source, self.config.private_root / "auth_current/codex/auth.json")


class ClaudeAdapter(Adapter):
    name = "claude"
    _allowed_env = {"ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"}

    def preflight(self) -> None:
        super().preflight()
        if self.agent.profile is None or not self.agent.profile.is_file():
            raise ValueError("Claude adapter requires agent.profile pointing to settings.json")

    def prepare(self, task_dir: Path, private_dir: Path, seconds: int) -> AdapterRuntime:
        assert self.agent.profile is not None
        host = json.loads(self.agent.profile.read_text())
        env = {key: value for key, value in host.get("env", {}).items() if key in self._allowed_env}
        for key in ("ANTHROPIC_MODEL", "ANTHROPIC_REASONING_MODEL",
                    "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
                    "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_FABLE_MODEL"):
            env[key] = self.agent.model
        private_home = private_dir / ".claude"
        private_home.mkdir(parents=True, mode=0o700)
        (task_dir / "agent_home/.claude").mkdir(parents=True, mode=0o700)
        deny = []
        if not self.agent.skills.builtin:
            deny.append("Skill")
        if not self.agent.tools.web:
            deny += ["WebSearch", "WebFetch"]
        settings = private_home / "settings.json"
        settings.write_text(json.dumps({
            "env": env,
            "disableBundledSkills": not self.agent.skills.builtin,
            "permissions": {"deny": deny},
            "hasCompletedOnboarding": True,
            "skipDangerousModePermissionPrompt": True,
        }, indent=2) + "\n")
        settings.chmod(0o600)
        session = str(uuid.uuid4())
        binary_mount, binary_target = _runtime_mount(self.agent.binary)
        args = [binary_target, "-p", "$(< /workspace/PROMPT.md)",
                "--model", self.agent.model, "--effort", self.agent.reasoning_effort,
                "--session-id", session,
                "--dangerously-skip-permissions", "--strict-mcp-config", "--mcp-config",
                '{"mcpServers":{}}', "--setting-sources", "user",
                "--output-format", "stream-json", "--verbose"]
        if deny:
            args += ["--disallowedTools", ",".join(deny)]
        if self.agent.tools.allowed:
            args += ["--allowedTools", ",".join(self.agent.tools.allowed)]
        invocation = " ".join(shlex.quote(arg) if not arg.startswith("$(<") else '"' + arg + '"'
                              for arg in args)
        return AdapterRuntime(self._wrapped(invocation, seconds),
            (binary_mount,
             Mount(private_home, "/home/benchmark/.claude", False)),
            audit_home=private_dir)

    def audit(self, task_dir: Path, runtime: AdapterRuntime) -> AuditResult:
        initialized = failed = binding = False
        session_id = None
        messages: dict[str, int] = {}
        for row in _json_rows(task_dir / "session.jsonl"):
            if row.get("type") == "system" and row.get("subtype") == "init":
                initialized = True
                session_id = row.get("session_id")
                binding = row.get("model") == self.agent.model
                skills = set(row.get("skills") or [])
                tools = set(row.get("tools") or [])
                if not self.agent.skills.builtin and skills:
                    binding = False
                if not self.agent.tools.web and tools & {"WebSearch", "WebFetch"}:
                    binding = False
                if not self.agent.tools.multi_agent and tools & {"Agent", "Task", "TeamCreate"}:
                    binding = False
            if row.get("type") == "result" and row.get("is_error"):
                failed = True
            message = row.get("message")
            if row.get("type") == "assistant" and isinstance(message, dict):
                usage = message.get("usage", {})
                messages[str(message.get("id", len(messages)))] = sum(
                    int(usage.get(key) or 0) for key in
                    ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
        return AuditResult(initialized, failed, session_id,
                           sum(messages.values()) if messages else None, binding)


class ZcodeAdapter(Adapter):
    name = "zcode"

    def _selection(self) -> dict[str, Any]:
        provider = Path(self.agent.options["provider_config"]).expanduser()
        if not provider.is_absolute():
            provider = self.config.path.parent / provider
        try:
            selected = json.loads(provider.read_text())["config"]["defaultModelSelection"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ValueError("ZCode provider configuration is unreadable") from error
        if not isinstance(selected, dict):
            raise ValueError("ZCode defaultModelSelection must be an object")
        return selected

    def preflight(self) -> None:
        super().preflight()
        provider = self.agent.options.get("provider_config")
        if not isinstance(provider, str):
            raise ValueError("ZCode adapter requires options.provider_config")
        path = Path(provider).expanduser()
        if not path.is_absolute():
            path = self.config.path.parent / path
        if not path.is_file():
            raise ValueError("ZCode adapter requires options.provider_config")
        selected = self._selection()
        if not isinstance(selected.get("providerId"), str) or not selected["providerId"]:
            raise ValueError("ZCode provider configuration has no providerId")
        if selected.get("modelId") != self.agent.model:
            raise ValueError("ZCode provider configuration selects a different model")
        options = selected.get("options") if isinstance(selected.get("options"), dict) else {}
        selected_effort = (options.get("reasoningLevel") or options.get("effort") or
                           selected.get("reasoningLevel") or selected.get("effort"))
        if selected_effort and selected_effort != self.agent.reasoning_effort:
            raise ValueError("ZCode provider configuration selects a different reasoning effort")
        if not selected_effort:
            raise ValueError("ZCode provider configuration does not prove the reasoning effort")
        runtime_root = self.agent.options.get("runtime_root")
        if runtime_root is not None:
            if not isinstance(runtime_root, str):
                raise ValueError("ZCode options.runtime_root must be a path string")
            root = Path(runtime_root).expanduser()
            if not root.is_absolute():
                root = self.config.path.parent / root
            root = root.resolve()
            if not self.agent.binary.is_relative_to(root):
                raise ValueError("ZCode binary must be inside options.runtime_root")

    def prepare(self, task_dir: Path, private_dir: Path, seconds: int) -> AdapterRuntime:
        config = task_dir / "agent_home/.zcode/cli/config.json"
        config.parent.mkdir(parents=True, mode=0o700)
        config.write_text(json.dumps({"features": {"skill": self.agent.skills.builtin,
                                                    "subagent": self.agent.tools.multi_agent,
                                                    "mcp": False},
                                      "skills": {"enabled": self.agent.skills.builtin, "roots": []}},
                                     indent=2) + "\n")
        provider = Path(self.agent.options["provider_config"]).expanduser()
        if not provider.is_absolute():
            provider = self.config.path.parent / provider
        provider = provider.resolve()
        runtime_root_value = self.agent.options.get("runtime_root")
        runtime_root = (Path(runtime_root_value).expanduser()
                        if runtime_root_value else _runtime_root(self.agent.binary))
        if not runtime_root.is_absolute():
            runtime_root = self.config.path.parent / runtime_root
        runtime_root = runtime_root.resolve()
        binary_mount, binary_target = _runtime_mount(
            self.agent.binary, "/opt/zcode-runtime", runtime_root)
        node_mount, node_target = _node_mount()
        selected = self._selection()
        model_selector = selected["providerId"] + "/" + selected["modelId"]
        denied = []
        if not self.agent.tools.multi_agent:
            denied += ["task", "delegate"]
        if not self.agent.tools.web:
            denied += ["websearch", "webfetch"]
        args = [node_target, binary_target,
                "--prompt", "$(< /workspace/PROMPT.md)",
                "--cwd", "/workspace", "--mode", "yolo", "--model", model_selector,
                "--json", "--no-color"]
        if denied:
            args += ["--disallowed-tools", ",".join(denied)]
        invocation = " ".join(shlex.quote(arg) if not arg.startswith("$(<") else '"' + arg + '"'
                              for arg in args)
        return AdapterRuntime(self._wrapped(invocation, seconds),
            (binary_mount, node_mount,
             Mount(provider, "/run/credentials/zcode-provider.json")),
            ("USERPROFILE=/home/benchmark", "ZCODE_DATA_BASE_DIR=/home/benchmark",
             "ZCODE_PERSONAL_PROVIDER_CONFIG_FILE=/run/credentials/zcode-provider.json"),
            task_dir / "agent_home")

    def audit(self, task_dir: Path, runtime: AdapterRuntime) -> AuditResult:
        initialized = failed = False
        binding: bool | None = None
        session_id = None
        tokens = None
        selected = self._selection()
        for row in _json_rows(task_dir / "session.jsonl"):
            if row.get("sessionId"):
                initialized = True
                session_id = row["sessionId"]
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            projection = row.get("projection") if isinstance(row.get("projection"), dict) else {}
            if row.get("type") == "turn.started":
                intent = payload.get("intent") if isinstance(payload.get("intent"), dict) else {}
                active = (intent.get("modelSelection")
                          if isinstance(intent.get("modelSelection"), dict) else {})
                active_options = (active.get("options")
                                  if isinstance(active.get("options"), dict) else {})
                active_effort = active_options.get("reasoningLevel") or active_options.get("effort")
                matches = (active.get("providerId") == selected.get("providerId") and
                           active.get("modelId") == self.agent.model and
                           active_effort == self.agent.reasoning_effort)
                binding = matches if binding is None else binding and matches
            usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
            total = usage.get("totalTokens") or projection.get("totalTokenCount")
            if isinstance(total, (int, float)):
                tokens = max(tokens or 0, int(total))
            if row.get("type") == "turn.failed" or projection.get("status") == "failed":
                failed = True
        return AuditResult(initialized, failed, session_id, tokens, binding is True)


class FakeAdapter(Adapter):
    """Test adapter; its executable receives model, effort and prompt path."""
    name = "fake"

    def prepare(self, task_dir: Path, private_dir: Path, seconds: int) -> AdapterRuntime:
        binary_mount, target = _runtime_mount(self.agent.binary)
        args = [target, "--model", self.agent.model, "--effort",
                self.agent.reasoning_effort, "--prompt", "/workspace/PROMPT.md"]
        return AdapterRuntime(self._wrapped(shlex.join(args), seconds),
                              (binary_mount,))

    def audit(self, task_dir: Path, runtime: AdapterRuntime) -> AuditResult:
        rows = _json_rows(task_dir / "session.jsonl")
        initialized = any(row.get("type") == "init" for row in rows)
        binding = any(row.get("type") == "init" and row.get("model") == self.agent.model and
                      row.get("effort") == self.agent.reasoning_effort for row in rows)
        failed = any(row.get("type") == "error" for row in rows)
        session_id = next((row.get("session_id") for row in rows if row.get("session_id")), None)
        tokens = sum(int(row.get("tokens", 0)) for row in rows if row.get("type") == "usage") or None
        return AuditResult(initialized, failed, session_id, tokens, binding)


ADAPTER_TYPES = {
    "kimi": KimiAdapter,
    "codex": CodexAdapter,
    "claude": ClaudeAdapter,
    "zcode": ZcodeAdapter,
    "fake": FakeAdapter,
}


def make_adapter(config: RunnerConfig) -> Adapter:
    return ADAPTER_TYPES[config.agent.adapter](config)
