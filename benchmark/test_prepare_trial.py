from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from benchmark.prepare_trial import prepare


class PrepareTrialIsolationTest(unittest.TestCase):
    def prepare(self, task: str) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        destination = Path(temporary.name) / "submission"
        prepare(task, destination)
        return destination

    def assert_common_isolation(self, destination: Path, task: str) -> None:
        task_dirs = sorted(path.name for path in (destination / "benchmark/tasks").iterdir())
        self.assertEqual(task_dirs, [task])
        self.assertTrue((destination / f"benchmark/tasks/{task}/task.md").is_file())
        self.assertTrue((destination / f"benchmark/tasks/{task}/acceptance.md").is_file())
        self.assertTrue((destination / f"evaluator/public/tb_{task}.sv").is_file())
        self.assertTrue((destination / "evaluator/public_check.py").is_file())
        self.assertFalse((destination / "benchmark/manifest.yaml").exists())
        self.assertFalse((destination / "benchmark/ppa-baselines.json").exists())
        self.assertFalse((destination / "benchmark/prepare_trial.py").exists())
        self.assertFalse((destination / "evaluator/README.md").exists())
        self.assertFalse((destination / "benchmark/report.schema.json").exists())
        rules = (destination / "benchmark/README.md").read_text()
        self.assertNotIn("tasks/T", rules)
        for name in ("rv32i_five_stage_cpu", "npu_systolic_matmul_16x16",
                     "serial_in_parallel_out_8bit", "synchronous_fifo"):
            self.assertNotIn(name, rules)
        self.assertNotIn("Kimi", rules)
        self.assertFalse(any(destination.rglob("SKILL.md")))

    def test_regular_task_contains_only_selected_task(self) -> None:
        destination = self.prepare("T03")
        self.assert_common_isolation(destination, "T03")
        self.assertFalse((destination / "benchmark/cpu").exists())
        self.assertFalse((destination / "benchmark/npu-validation.md").exists())

    def test_t09_keeps_only_required_cpu_public_artifacts(self) -> None:
        destination = self.prepare("T09")
        self.assert_common_isolation(destination, "T09")
        self.assertTrue((destination / "benchmark/cpu/act4/test_config.yaml").is_file())
        self.assertTrue((destination / "benchmark/sources.lock.yaml").is_file())
        self.assertTrue((destination / "evaluator/public/tb_cpu_elf.sv").is_file())
        self.assertTrue((destination / "evaluator/act4_elfs/MANIFEST.json").is_file())
        self.assertFalse((destination / "evaluator/t09_timing_check.py").exists())
        self.assertFalse((destination / "evaluator/t09_timing_tb.sv").exists())
        self.assertFalse((destination / "evaluator/t09_timing_qualification.json").exists())
        self.assertFalse((destination / "evaluator/reference").exists())
        self.assertFalse((destination / "benchmark/tasks/T09/FREEZE.json").exists())

    def test_t10_keeps_its_public_oracle_and_validation_contract(self) -> None:
        destination = self.prepare("T10")
        self.assert_common_isolation(destination, "T10")
        self.assertTrue(
            (destination / "benchmark/tasks/T10/public/matmul_oracle.py").is_file()
        )
        self.assertTrue((destination / "benchmark/npu-validation.md").is_file())

    def test_t08_initializes_only_buggy_public_starter(self) -> None:
        destination = self.prepare("T08")
        self.assert_common_isolation(destination, "T08")
        self.assertTrue((destination / "rtl/mac_1g_repair.sv").is_file())
        self.assertTrue((destination / "rtl/files.f").is_file())
        self.assertTrue((destination / "LICENSE.upstream").is_file())
        self.assertFalse((destination / "evaluator/t08_check.py").exists())
        self.assertFalse((destination / "evaluator/t08_mutation_check.py").exists())
        self.assertFalse((destination / "evaluator/test_t08_mutation_check.py").exists())
        self.assertFalse((destination / "evaluator/fixtures").exists())
        self.assertFalse((destination / "benchmark/test_t08_spec.py").exists())
        self.assertFalse((destination / "evaluator/t08_validation.json").exists())
        self.assertFalse((destination / "benchmark/tasks/T08/SPEC_CHANGELOG.md").exists())
        self.assertFalse((destination / "benchmark/tasks/T08/AUTHOR_GUIDE.md").exists())
        readme = (destination / "benchmark/tasks/T08/README.md").read_text()
        self.assertNotIn("t08_mutation_check", readme)
        self.assertNotIn("gpt-6.1-sol", readme)
        spec = (destination / "benchmark/tasks/T08/task.md").read_text()
        self.assertIn("Specification revision: 3.0-frame-transactions", spec)
        self.assertFalse((destination / "evaluator/t08_repair_qualification.py").exists())
        self.assertGreaterEqual(len(spec.splitlines()), 3000)
        prompt = (destination / "PROMPT.md").read_text()
        self.assertIn("no token hard limit", prompt)
        self.assertNotIn("1200000", prompt)
        self.assertIn("override shared rules", prompt)
        self.assertIn("Keep your session persistent", prompt)
        self.assertIn("Generic synthesizable", prompt)
        self.assertIn("manual macro instantiation or library downloads", prompt)
        for document in ("task.md", "task.yaml", "acceptance.md", "README.md"):
            self.assertIn("2.0-lambdapdk-tdp-1ghz",
                          (destination / "benchmark/tasks/T08" / document).read_text())
        self.assertFalse((destination / "evaluator/t11_sram.py").exists())
        self.assertFalse((destination / "evaluator/run_t08_sram_ppa.py").exists())
        self.assertFalse((destination / "vendor").exists())


if __name__ == "__main__":
    unittest.main()
