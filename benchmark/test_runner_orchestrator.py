import json
import tempfile
import unittest
from pathlib import Path

import yaml

from benchmark.runner.config import load_config
from benchmark.runner.orchestrator import SuiteRunner
from benchmark.test_runner_config import valid_config


class RunnerOrchestratorTest(unittest.TestCase):
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
