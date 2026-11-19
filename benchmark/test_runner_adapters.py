import json
import tempfile
import unittest
from pathlib import Path

import yaml

from benchmark.runner.adapters import ClaudeAdapter, CodexAdapter, KimiAdapter, ZcodeAdapter
from benchmark.runner.config import load_config
from benchmark.test_runner_config import valid_config


class RunnerAdapterTest(unittest.TestCase):
    def test_codex_terminal_completion_is_not_inferred_from_partial_messages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.configuration(root, {'adapter': 'codex'})
            adapter = CodexAdapter(config)
            for terminal, completed, failed in [
                ([], False, False),
                ([{'type': 'turn.completed'}], True, False),
                ([{'type': 'turn.failed'}], False, True),
                ([{'type': 'turn.completed'}, {'type': 'turn.started'}], False, False),
                ([{'type': 'turn.completed'}, {'type': 'turn.failed'}], False, True),
            ]:
                with self.subTest(terminal=terminal):
                    rows = [{'type': 'thread.started', 'thread_id': 'session'},
                            {'type': 'turn.started'}, *terminal]
                    (root / 'session.jsonl').write_text('\n'.join(map(json.dumps, rows)) + '\n')
                    result = adapter.audit(root, None)
                    self.assertEqual(result.completed, completed)
                    self.assertEqual(result.failed, failed)

    def test_claude_oauth_is_private_and_rotation_reaches_next_fresh_task(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            credentials = root / "oauth.json"
            credentials.write_text(json.dumps({"claudeAiOauth": {
                "accessToken": "private-access", "refreshToken": "private-refresh", "expiresAt": 100}}))
            settings = root / "settings.json"
            settings.write_text('{"env": {}, "enabledPlugins": {"external@example": true}}')
            config = self.configuration(root, {"adapter": "claude", "profile": str(settings)},
                                        options={"oauth_credentials": str(credentials)})
            adapter = ClaudeAdapter(config)
            adapter.preflight()
            task = root / "candidate"
            (task / "agent_home").mkdir(parents=True)
            private = root / "private-task"
            private.mkdir()
            runtime = adapter.prepare(task, private, 60)
            # A second task prepared before the first one refreshes must receive
            # the latest shared chain at launch, rather than its prepared copy.
            next_task = root / "next-candidate"
            (next_task / "agent_home").mkdir(parents=True)
            next_private = root / "next-private"
            next_private.mkdir()
            next_runtime = adapter.prepare(next_task, next_private, 60)
            for path in task.rglob("*"):
                if path.is_file():
                    self.assertNotIn("private-access", path.read_text())
            private_settings = (private / ".claude/settings.json").read_text()
            self.assertNotIn("external@example", private_settings)
            self.assertIn("TeamCreate", runtime.shell)
            renewed = private / ".claude/.credentials.json"
            renewed.write_text(json.dumps({"claudeAiOauth": {
                "accessToken": "rotated-access", "refreshToken": "rotated-refresh", "expiresAt": 200}}))
            adapter.finalize(task, private, runtime)
            self.assertEqual(json.loads(credentials.read_text())["claudeAiOauth"]["accessToken"], "rotated-access")
            # An older task must not overwrite newer shared credentials.
            renewed.write_text(json.dumps({"claudeAiOauth": {"expiresAt": 150}}))
            adapter.finalize(task, private, runtime)
            self.assertEqual(json.loads(credentials.read_text())["claudeAiOauth"]["expiresAt"], 200)
            adapter.before_start(next_task, next_private, next_runtime)
            self.assertEqual(json.loads((next_private / ".claude/.credentials.json").read_text())[
                "claudeAiOauth"]["accessToken"], "rotated-access")

    def configuration(self, root: Path, changes: dict, *, options=None):
        value = valid_config(root)
        value["agent"].update(changes)
        value["agent"]["options"] = options or {}
        path = root / "runner.yaml"
        path.write_text(yaml.safe_dump(value, sort_keys=False))
        return load_config(path)

    def test_kimi_uses_shared_oauth_without_copying_secrets_into_trial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = valid_config(root)
            profile = root / "kimi-profile"
            (profile / "credentials").mkdir(parents=True)
            (profile / "oauth").mkdir()
            (profile / "credentials/kimi-code.json").write_text(json.dumps({
                "access_token": "secret-access", "refresh_token": "secret-refresh"}))
            (profile / "config.toml").write_text("""
[models."kimi-code/test"]
model = "test-model"
provider = "managed"
support_efforts = ["high"]
[providers.managed]
type = "kimi"
base_url = "https://example.invalid"
oauth = true
""")
            value["agent"].update(adapter="kimi", profile=str(profile),
                                  model_alias="kimi-code/test")
            config_path = root / "runner.yaml"
            config_path.write_text(yaml.safe_dump(value, sort_keys=False))
            config = load_config(config_path)
            task = root / "candidate"
            (task / "agent_home").mkdir(parents=True)
            private = root / "private-task"
            private.mkdir()
            adapter = KimiAdapter(config)
            adapter.preflight()
            runtime = adapter.prepare(task, private, 60)
            self.assertFalse(any("secret-access" in path.read_text(errors="ignore")
                                 for path in task.rglob("*") if path.is_file()))
            targets = {mount.target: mount for mount in runtime.mounts}
            self.assertFalse(targets["/home/benchmark/.kimi-code/credentials"].readonly)
            self.assertEqual(targets["/home/benchmark/.kimi-code/credentials"].source,
                             profile / "credentials")
            rendered = (task / "agent_home/.kimi-code/config.toml").read_text()
            self.assertIn('effort = "high"', rendered)
            self.assertNotIn("secret-refresh", rendered)

    def test_codex_uses_private_auth_chain_without_candidate_limits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "codex-profile"
            profile.mkdir()
            (profile / "auth.json").write_text('{"token":"secret"}')
            config = self.configuration(root, {"adapter": "codex", "profile": str(profile)})
            task = root / "candidate"
            (task / "agent_home").mkdir(parents=True)
            private = root / "private-task"
            private.mkdir()
            adapter = CodexAdapter(config)
            adapter.preflight()
            runtime = adapter.prepare(task, private, 60)
            self.assertNotIn("secret", runtime.shell)
            self.assertNotIn("max_tokens", runtime.shell)
            self.assertNotIn("--ephemeral", runtime.shell)
            self.assertTrue((private / ".codex/auth.json").is_file())
            self.assertFalse((task / "agent_home/.codex/auth.json").exists())
            self.assertIn("--dangerously-bypass-approvals-and-sandbox", runtime.shell)

            # Retain this task's native history without carrying it into the
            # next task's fresh CLI home.
            history = private / ".codex/sessions/prior.jsonl"
            history.parent.mkdir()
            history.write_text('{"type":"token_count"}\n')
            next_task = root / "next-candidate"
            next_private = root / "next-private"
            next_runtime = adapter.prepare(next_task, next_private, 60)
            self.assertEqual(history.read_text(), '{"type":"token_count"}\n')
            self.assertFalse((next_private / ".codex/sessions").exists())
            self.assertEqual(next_runtime.audit_home, next_private)
            self.assertNotEqual(runtime.mounts[-1].source, next_runtime.mounts[-1].source)
            self.assertNotIn("resume", next_runtime.shell)
            self.assertNotIn("--ephemeral", next_runtime.shell)

    def test_codex_offline_tools_use_enforced_network_policy_without_bypass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profile"; profile.mkdir()
            (profile / "auth.json").write_text('{"token":"private"}')
            config = self.configuration(root, {"adapter": "codex", "profile": str(profile)},
                                        options={"network_access": False})
            task = root / "candidate"; (task / "agent_home").mkdir(parents=True)
            private = root / "private-task"; private.mkdir()
            runtime = CodexAdapter(config).prepare(task, private, 60)
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", runtime.shell)
            self.assertIn('permissions.benchmark-offline.network.enabled=false', runtime.shell)
            self.assertIn('approval_policy="never"', runtime.shell)
            self.assertIn('--enable use_legacy_landlock', runtime.shell)
            self.assertIn('--enable skip_host_skill_discovery', runtime.shell)
            self.assertIn('--disable multi_agent_v2', runtime.shell)
            for feature in ('apps', 'browser_use', 'computer_use', 'image_generation', 'remote_plugin'):
                self.assertIn('--disable ' + feature, runtime.shell)
            self.assertNotIn("private", " ".join(runtime.environment))

    def test_codex_rejects_invalid_or_contradictory_offline_policy(self):
        for access in (0, "false", None):
            with self.subTest(access=access), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                config = self.configuration(root, {"adapter": "codex"},
                                            options={"network_access": access})
                with self.assertRaisesRegex(ValueError, "boolean"):
                    CodexAdapter(config)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = valid_config(root)
            value["agent"].update(adapter="codex", options={"network_access": False})
            value["agent"]["tools"]["web"] = True
            path = root / "runner.yaml"; path.write_text(yaml.safe_dump(value))
            with self.assertRaisesRegex(ValueError, "tools.web=false"):
                CodexAdapter(load_config(path))

    def test_claude_keeps_provider_secret_outside_trial_and_adds_no_output_cap(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = root / "claude-settings.json"
            settings.write_text(json.dumps({"env": {"ANTHROPIC_AUTH_TOKEN": "secret-token",
                                                      "UNRELATED_SECRET": "forbidden",
                                                      "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "17"}}))
            config = self.configuration(root, {"adapter": "claude", "profile": str(settings)})
            task = root / "candidate"
            (task / "agent_home").mkdir(parents=True)
            private = root / "private-task"
            private.mkdir()
            adapter = ClaudeAdapter(config)
            adapter.preflight()
            runtime = adapter.prepare(task, private, 60)
            self.assertNotIn("secret-token", runtime.shell)
            self.assertNotIn("MAX_OUTPUT_TOKENS", " ".join(runtime.environment))
            self.assertIn("--effort high", runtime.shell)
            self.assertFalse(any("secret-token" in path.read_text(errors="ignore")
                                 for path in task.rglob("*") if path.is_file()))
            private_settings = (private / ".claude/settings.json").read_text()
            self.assertIn("secret-token", private_settings)
            self.assertNotIn("UNRELATED_SECRET", private_settings)
            self.assertNotIn("MAX_OUTPUT_TOKENS", private_settings)

    def test_claude_explicit_api_capabilities_and_automatic_reasoning(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = root / "settings.json"
            settings.write_text(json.dumps({"env": {
                "ANTHROPIC_AUTH_TOKEN": "private-token",
                "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "17"},
                "enabledPlugins": {"external@example": True}}))
            config = self.configuration(root, {"adapter": "claude", "profile": str(settings),
                "reasoning_effort": "auto"}, options={"provider_capabilities": {
                    "context_window": 524288, "response_window": 8192}})
            adapter = ClaudeAdapter(config)
            adapter.preflight()
            task, private = root / "candidate", root / "private-task"
            (task / "agent_home").mkdir(parents=True)
            private.mkdir()
            runtime = adapter.prepare(task, private, 60)
            rendered = json.loads((private / ".claude/settings.json").read_text())
            self.assertEqual(rendered["env"]["CLAUDE_CODE_MAX_CONTEXT_TOKENS"], "524288")
            self.assertEqual(rendered["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"], "8192")
            self.assertEqual(rendered["env"]["CLAUDE_CODE_AUTO_COMPACT_WINDOW"], "516096")
            self.assertFalse(rendered["alwaysThinkingEnabled"])
            self.assertNotIn("--effort", runtime.shell)
            self.assertNotIn("max-tokens", runtime.shell)
            self.assertNotIn("private-token", runtime.shell)
            self.assertNotIn("enabledPlugins", rendered)
            self.assertNotIn("oauth_credentials", config.agent.options)

    def test_claude_rejects_invalid_provider_capabilities(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = root / "settings.json"
            settings.write_text('{}')
            invalid = [None, {}, {"context_window": 1024},
                {"context_window": True, "response_window": 1},
                {"context_window": 1024, "response_window": -1},
                {"context_window": 1024, "response_window": 1024},
                {"context_window": 1024, "response_window": 2048},
                {"context_window": "1024", "response_window": 1},
                {"context_window": 1024, "response_window": 1, "extra": 1}]
            for capabilities in invalid:
                with self.subTest(capabilities=capabilities):
                    config = self.configuration(root, {"adapter": "claude", "profile": str(settings)},
                        options={"provider_capabilities": capabilities})
                    with self.assertRaises(ValueError):
                        ClaudeAdapter(config).preflight()
            config = self.configuration(root, {"adapter": "claude", "profile": str(settings),
                "reasoning_effort": "auto"})
            with self.assertRaises(ValueError):
                ClaudeAdapter(config).preflight()

    def test_zcode_validates_selected_model_and_effort(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_root = root / "zcode-source"
            binary = runtime_root / "dist/zcode.cjs"
            binary.parent.mkdir(parents=True)
            binary.write_text("// bundled")
            provider = root / "provider.json"
            provider.write_text(json.dumps({"config": {"defaultModelSelection": {
                "providerId": "test-provider", "modelId": "test-model",
                "options": {"reasoningLevel": "high"}},
                "apiKey": "secret-key"}}))
            config = self.configuration(root, {"adapter": "zcode", "binary": str(binary)},
                options={"provider_config": str(provider), "runtime_root": str(runtime_root)})
            task = root / "candidate"
            (task / "agent_home").mkdir(parents=True)
            private = root / "private-task"
            private.mkdir()
            adapter = ZcodeAdapter(config)
            adapter.preflight()
            runtime = adapter.prepare(task, private, 60)
            self.assertIn("/opt/zcode-runtime/dist/zcode.cjs", runtime.shell)
            self.assertIn("--model test-provider/test-model", runtime.shell)
            self.assertIn("--json", runtime.shell)
            self.assertNotIn("--output-format", runtime.shell)
            self.assertNotIn("secret-key", runtime.shell)
            self.assertEqual(next(mount for mount in runtime.mounts
                                  if mount.target == "/run/credentials/zcode-provider.json").source,
                             provider)

    def test_zcode_audit_proves_model_effort_and_counts_final_usage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_root = root / "zcode-source"
            binary = runtime_root / "zcode.cjs"
            runtime_root.mkdir()
            binary.write_text("// bundled")
            provider = root / "provider.json"
            provider.write_text(json.dumps({"config": {"defaultModelSelection": {
                "providerId": "test-provider", "modelId": "test-model",
                "options": {"reasoningLevel": "high"}}}}))
            config = self.configuration(root, {"adapter": "zcode", "binary": str(binary)},
                options={"provider_config": str(provider), "runtime_root": str(runtime_root)})
            task = root / "candidate"
            task.mkdir()
            (task / "session.jsonl").write_text("\n".join(json.dumps(row) for row in (
                {"type": "turn.started", "sessionId": "sess_test", "payload": {"intent": {
                    "modelSelection": {"providerId": "test-provider", "modelId": "test-model",
                                       "options": {"reasoningLevel": "high"}}}}},
                {"type": "turn.completed", "sessionId": "sess_test",
                 "payload": {"usage": {"totalTokens": 1234}}},
            )) + "\n")
            audit = ZcodeAdapter(config).audit(task, None)  # type: ignore[arg-type]
            self.assertTrue(audit.initialized)
            self.assertTrue(audit.binding_verified)
            self.assertEqual(audit.tokens, 1234)


if __name__ == "__main__":
    unittest.main()
