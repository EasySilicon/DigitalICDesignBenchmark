import json
import tempfile
import unittest
from pathlib import Path

import yaml

from benchmark.runner.adapters import ClaudeAdapter, CodexAdapter, KimiAdapter, ZcodeAdapter
from benchmark.runner.config import load_config
from benchmark.test_runner_config import valid_config


class RunnerAdapterTest(unittest.TestCase):
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
            self.assertTrue((private / ".codex/auth.json").is_file())
            self.assertFalse((task / "agent_home/.codex/auth.json").exists())

    def test_claude_keeps_provider_secret_outside_trial_and_adds_no_output_cap(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = root / "claude-settings.json"
            settings.write_text(json.dumps({"env": {"ANTHROPIC_AUTH_TOKEN": "secret-token",
                                                      "UNRELATED_SECRET": "forbidden"}}))
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
