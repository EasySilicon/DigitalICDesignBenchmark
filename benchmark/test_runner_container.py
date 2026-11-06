import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch

import yaml

from benchmark.runner.adapters import AdapterRuntime, Mount
from benchmark.runner.config import load_config
from benchmark.runner.container import docker_command, validate_candidate_shell
from benchmark.test_runner_config import valid_config


class RunnerContainerTest(unittest.TestCase):
    def test_explicit_proxy_overrides_inherited_xray_for_every_proxy_variable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = replace(self.config(root), proxy_url="http://127.0.0.1:7897")
            with patch.dict("os.environ", {"HTTPS_PROXY": "http://127.0.0.1:20808"}):
                command = docker_command(config, self.task(root), AdapterRuntime("true"),
                                         "candidate", cpus=16, memory_gib=40)
            env = [command[i + 1] for i, arg in enumerate(command[:-1]) if arg == "-e"]
            for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
                self.assertIn(name + "=http://127.0.0.1:7897", env)
            self.assertIn("NO_PROXY=localhost,127.0.0.1,::1", env)
            self.assertNotIn("20808", " ".join(command))

    def config(self, root: Path):
        value = valid_config(root)
        path = root / "runner.yaml"
        path.write_text(yaml.safe_dump(value, sort_keys=False))
        return load_config(path)

    def task(self, root: Path) -> Path:
        task = root / "task"
        for name in ("workspace", "agent_home", "empty_skills", "tmp"):
            (task / name).mkdir(parents=True)
        return task

    def test_container_uses_manifest_resources_swap_and_no_extra_caps(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.config(root)
            binary_dir = root / "runtime"
            binary_dir.mkdir()
            binary = binary_dir / "agent"
            binary.write_text("x")
            runtime = AdapterRuntime("exec /opt/agent/bin/agent",
                                     (Mount(binary_dir, "/opt/agent/bin"),))
            command = docker_command(config, self.task(root), runtime, "candidate",
                                     cpus=16, memory_gib=40)
            self.assertEqual(command[command.index("--cpus") + 1], "16")
            self.assertEqual(command[command.index("--memory") + 1], "40g")
            self.assertEqual(command[command.index("--memory-swap") + 1], "-1")
            self.assertNotIn("--pids-limit", command)
            joined = " ".join(command)
            self.assertNotIn("MAX_OUTPUT_TOKENS", joined)
            self.assertNotIn("--max-budget-usd", joined)

    def test_rejects_hidden_candidate_limits_and_judge_mounts(self):
        for token in ("--max-budget-usd 1", "--max-turns 4", "TOKEN_LIMIT=10"):
            with self.subTest(token=token), self.assertRaises(ValueError):
                validate_candidate_shell("agent " + token)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.config(root)
            secret = root / "secret"
            secret.mkdir()
            runtime = AdapterRuntime("agent", (Mount(secret, "/grader"),))
            with self.assertRaisesRegex(ValueError, "unsafe|forbidden"):
                docker_command(config, self.task(root), runtime, "candidate", cpus=16, memory_gib=40)

    def test_adapter_cannot_mount_an_ancestor_of_repository_or_trial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.config(root)
            runtime = AdapterRuntime("agent", (Mount(root, "/opt/too-broad"),))
            with self.assertRaisesRegex(ValueError, "ancestor"):
                docker_command(config, self.task(root), runtime, "candidate", cpus=16, memory_gib=40)

    def test_configured_and_adapter_mounts_cannot_inject_workspace_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = valid_config(root)
            value["readonly_mounts"] = [{"source": str(root / "tool"),
                                           "target": "/workspace/hidden"}]
            (root / "tool").mkdir()
            path = root / "runner.yaml"
            path.write_text(yaml.safe_dump(value, sort_keys=False))
            config = load_config(path)
            task = self.task(root)
            with self.assertRaisesRegex(ValueError, "unsafe"):
                docker_command(config, task, AdapterRuntime("agent"), "candidate",
                               cpus=16, memory_gib=40)
            config = self.config(root)
            runtime = AdapterRuntime("agent", (Mount(root / "tool", "/workspace/hidden"),))
            with self.assertRaisesRegex(ValueError, "unsafe"):
                docker_command(config, task, runtime, "candidate", cpus=16, memory_gib=40)


if __name__ == "__main__":
    unittest.main()
