import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import yaml

from benchmark.runner.config import load_config
from benchmark.runner.orchestrator import SuiteRunner
from benchmark.runner.adapters import AdapterRuntime, AuditResult
from benchmark.test_runner_config import valid_config


class RunnerOrchestratorTest(unittest.TestCase):
    def test_successful_cli_delivery_after_child_oom_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = valid_config(root)
            config_path = root / "runner.yaml"
            config_path.write_text(yaml.safe_dump(value))
            runner = SuiteRunner(load_config(config_path))
            runner.config = replace(runner.config,
                                    agent=replace(runner.config.agent, adapter="claude"))
            directory = runner.root / "tasks/T01"
            (directory / "workspace").mkdir(parents=True)
            (directory / "workspace/delivery.txt").write_text("original delivery")
            (directory / "session.jsonl").write_text(json.dumps(
                dict(type="result", subtype="success", is_error=False)) + "\n")
            runner.adapter = Mock()
            runner.adapter.audit.return_value = AuditResult(True, False, "session", 123, True)
            runner.event = Mock()
            runner._summary = Mock()
            state = dict(OOMKilled=True, ExitCode=0)
            runner._finalize_agent(dict(id="T01", time_limit_minutes=3), directory,
                                   AdapterRuntime(""), state, 42)
            record = json.loads((directory / "agent_result.json").read_text())
            self.assertTrue(record["completed_after_child_oom"])
            self.assertTrue(record["container_oom_observed"])
            self.assertEqual(record["elapsed_seconds"], 42)
            self.assertEqual(json.loads((directory / "container_exit.json").read_text()), state)
            self.assertEqual((directory / "submission/delivery.txt").read_text(), "original delivery")

    def test_oom_without_successful_cli_delivery_still_stops_recovery(self):
        for code, success in ((137, True), (0, False)):
            with self.subTest(code=code, success=success), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                value = valid_config(root)
                config_path = root / "runner.yaml"
                config_path.write_text(yaml.safe_dump(value))
                runner = SuiteRunner(load_config(config_path))
                runner.config = replace(runner.config,
                                        agent=replace(runner.config.agent, adapter="claude"))
                directory = runner.root / "tasks/T01"
                directory.mkdir(parents=True)
                (directory / "session.jsonl").write_text(json.dumps(dict(
                    type="result", subtype="success" if success else "error",
                    is_error=not success)) + "\n")
                runner.adapter = Mock()
                runner.adapter.audit.return_value = AuditResult(True, False, "session", 123, True)
                with self.assertRaisesRegex(RuntimeError, "RAM limit"):
                    runner._finalize_agent(dict(id="T01", time_limit_minutes=3), directory,
                                           AdapterRuntime(""), dict(OOMKilled=True, ExitCode=code), 42)
                self.assertFalse((directory / "agent_result.json").exists())

    def test_pending_user_confirmation_blocks_model_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = valid_config(root)
            config_path = root / "runner.yaml"
            config_path.write_text(yaml.safe_dump(value, sort_keys=False))
            runner = SuiteRunner(load_config(config_path))
            runner.root.mkdir()
            (runner.root / "AWAITING_USER_CONFIRMATION").touch()
            with self.assertRaisesRegex(RuntimeError, "awaiting explicit user confirmation"):
                runner.run()
            self.assertFalse((runner.root / "run_manifest.json").exists())

    def test_initialization_freezes_inputs_and_reads_limits_only_from_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = valid_config(root)
            value["task_order"] = ["T01"]
            repo = Path(value["repo_root"])
            for name in ("benchmark", "evaluator", "env", "vendor"):
                (repo / name).mkdir(parents=True, exist_ok=True)
                (repo / name / "marker.txt").write_text(name)
            (repo / "benchmark/manifest.yaml").write_text(yaml.safe_dump({
                "suite_id": "test-suite", "token_usage_policy": "record_only",
                "hardware_limit": {"vcpu": 7, "ram_gib": 13, "disk_gib": 17},
                "tasks": [{"id": "T01", "time_limit_minutes": 3}],
            }, sort_keys=False))
            config_path = root / "runner.yaml"
            config_path.write_text(yaml.safe_dump(value, sort_keys=False))
            runner = SuiteRunner(load_config(config_path))
            runner.initialize()
            runner.preflight()
            manifest = json.loads((Path(value["trial_root"]) / "run_manifest.json").read_text())
            self.assertEqual(manifest["hardware_limit"],
                             {"vcpu": 7, "ram_gib": 13, "disk_gib": 17})
            self.assertEqual(manifest["token_usage_policy"], "record_only")
            self.assertFalse(manifest["token_stop_enabled"])
            self.assertTrue((Path(value["trial_root"]) /
                             "frozen/ic_bcmk/benchmark/manifest.yaml").is_file())

    def test_changed_config_cannot_resume_existing_trial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = valid_config(root)
            value["task_order"] = ["T01"]
            repo = Path(value["repo_root"])
            for name in ("benchmark", "evaluator", "env", "vendor"):
                (repo / name).mkdir(parents=True, exist_ok=True)
            (repo / "benchmark/manifest.yaml").write_text(yaml.safe_dump({
                "suite_id": "test", "token_usage_policy": "record_only",
                "hardware_limit": {"vcpu": 1, "ram_gib": 1, "disk_gib": 1},
                "tasks": [{"id": "T01", "time_limit_minutes": 1}],
            }))
            config_path = root / "runner.yaml"
            config_path.write_text(yaml.safe_dump(value, sort_keys=False))
            SuiteRunner(load_config(config_path)).initialize()
            value["agent"]["reasoning_effort"] = "max"
            config_path.write_text(yaml.safe_dump(value, sort_keys=False))
            with self.assertRaisesRegex(ValueError, "configuration or frozen inputs changed"):
                SuiteRunner(load_config(config_path)).initialize()


if __name__ == "__main__":
    unittest.main()
