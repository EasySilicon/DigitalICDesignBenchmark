import tempfile
import unittest
from pathlib import Path

import yaml

from benchmark.runner.config import load_config


def valid_config(root: Path) -> dict:
    repo = root / "repo"
    repo.mkdir(exist_ok=True)
    binary = root / "fake-agent"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    return {
        "schema_version": 1,
        "trial_root": str(root / "trial"),
        "repo_root": str(repo),
        "private_root": str(root / "private"),
        "image": "ubuntu:24.04",
        "task_order": ["T01", "T02"],
        "tool_path": "/usr/bin:/bin",
        "readonly_mounts": [],
        "agent": {
            "adapter": "fake", "model": "test-model", "reasoning_effort": "high",
            "binary": str(binary), "profile": None, "model_alias": None,
            "skills": {"builtin": False, "user": False, "external": False},
            "tools": {"web": False, "multi_agent": False, "allowed": []},
            "options": {},
        },
        "grader": {"command": ["python3", "grade.py", "{task_id}"],
                   "lock": str(root / "grade.lock")},
    }


class RunnerConfigTest(unittest.TestCase):
    def write(self, root: Path, value: dict) -> Path:
        path = root / "runner.yaml"
        path.write_text(yaml.safe_dump(value, sort_keys=False))
        return path

    def test_valid_config_has_no_local_resource_or_token_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = load_config(self.write(root, valid_config(root)))
            self.assertEqual(config.agent.model, "test-model")
            self.assertEqual(config.task_order, ("T01", "T02"))
            self.assertFalse(hasattr(config, "token_limit"))
            self.assertFalse(hasattr(config, "memory_gib"))

    def test_rejects_unapproved_token_or_turn_limits_even_in_options(self):
        for key in ("token_limit", "aggregate_token_cap", "max_turns", "max_budget_usd"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                value = valid_config(root)
                value["agent"]["options"] = {key: 1}
                with self.assertRaisesRegex(ValueError, "not an approved benchmark setting"):
                    load_config(self.write(root, value))

    def test_skill_and_tool_policy_must_be_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = valid_config(root)
            del value["agent"]["skills"]["builtin"]
            with self.assertRaisesRegex(ValueError, "explicitly true or false"):
                load_config(self.write(root, value))

    def test_trial_and_private_state_must_stay_outside_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = valid_config(root)
            value["trial_root"] = str(root / "repo/trial")
            with self.assertRaisesRegex(ValueError, "trial_root and repo_root must not overlap"):
                load_config(self.write(root, value))
            value = valid_config(root)
            value["private_root"] = str(root / "repo/private")
            with self.assertRaisesRegex(ValueError, "private_root and repo_root must not overlap"):
                load_config(self.write(root, value))

    def test_trial_or_private_root_cannot_be_an_ancestor_of_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = valid_config(root)
            value["trial_root"] = str(root)
            value["private_root"] = str(root.parent / (root.name + "-private"))
            with self.assertRaisesRegex(ValueError, "trial_root and repo_root must not overlap"):
                load_config(self.write(root, value))


if __name__ == "__main__":
    unittest.main()
