"""Freeze drift, publication provenance, archive binding and blind packaging."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from benchmark import freeze_tasks as freeze
from benchmark.prepare_trial import prepare


class FreezeTasksTest(unittest.TestCase):
    def test_published_receipts_match_all_current_artifacts(self):
        for task in freeze.TASKS:
            receipt = freeze.verify(task)
            self.assertEqual(receipt["status"], "frozen")
            self.assertEqual(receipt["contracts"]["hardware_limit"]["ram_gib"], 40)
            self.assertEqual(receipt["contracts"]["token_usage_policy"], "record_only")
            self.assertNotIn("same_model_token_cap", receipt["contracts"]["task_metadata"])
            for name in (f"benchmark/tasks/{task}/task.md", f"benchmark/tasks/{task}/acceptance.md",
                         f"benchmark/tasks/{task}/task.yaml", f"evaluator/{task.lower()}_check.py",
                         "evaluator/score_run.py", "benchmark/prepare_trial.py"):
                self.assertIn(name, receipt["artifact_sha256"])

    def test_source_or_judge_drift_is_rejected(self):
        real_sha = freeze.sha
        for name in ("evaluator/reference/T09/rtl/ref.sv", "evaluator/t09_timing_check.py",
                     "benchmark/tasks/T08/starter/rtl/axis_async_fifo.v"):
            task = "T08" if "/T08/" in name else "T09"
            def corrupted(path):
                return "0" * 64 if str(path.relative_to(freeze.ROOT)) == name else real_sha(path)
            with patch.object(freeze, "sha", side_effect=corrupted), self.assertRaises(ValueError):
                freeze.verify(task)

    def test_missing_or_new_untracked_artifact_is_rejected(self):
        for change in ("delete", "add"):
            real_build = freeze.build
            def changed(task, root=freeze.ROOT):
                value = real_build(task, root)
                if change == "delete":
                    value["artifact_sha256"].pop("evaluator/t08_check.py")
                else:
                    value["artifact_sha256"]["benchmark/tasks/T08/secret.sv"] = "0" * 64
                return value
            with patch.object(freeze, "build", side_effect=changed), self.assertRaises(ValueError):
                freeze.verify("T08")

    def test_scoring_fragment_drift_is_rejected(self):
        real_read = freeze.read
        def changed(path, root=freeze.ROOT):
            result = real_read(path, root)
            if path == "evaluator/score_rules.json":
                result["tasks"]["T09"][-1]["points"] -= 1
            return result
        with patch.object(freeze, "read", side_effect=changed), self.assertRaises(ValueError):
            freeze.verify("T09")

    def test_process_reports_are_not_freeze_dependencies(self):
        for task in freeze.TASKS:
            names=freeze.file_inventory(task)
            self.assertFalse(any('/fixtures/t08_reference_' in p or '/fixtures/t09_cpu_' in p for p in names))
            self.assertIn(f'evaluator/{task.lower()}_qualification.json',names)

    def test_incomplete_recorded_qualification_is_rejected(self):
        real_read=freeze.read
        for task,key in [('T08','mapped_functional_runs'),('T09','killed_mutants')]:
            def changed(path,root=freeze.ROOT):
                value=real_read(path,root)
                if path==f'evaluator/{task.lower()}_qualification.json':value[key]-=1
                return value
            with self.subTest(task=task),patch.object(freeze,'read',side_effect=changed),self.assertRaises(ValueError):
                freeze.contracts(task)

    def test_both_candidate_packages_exclude_frozen_answers(self):
        for task in freeze.TASKS:
            with tempfile.TemporaryDirectory() as temp:
                target = Path(temp) / "trial"
                prepare(task, target)
                self.assertFalse(any(target.rglob("FREEZE.json")))
                self.assertFalse(any(target.rglob("PPA_FREEZE.json")))
                self.assertFalse(any(target.rglob("SKILL.md")))
                self.assertFalse((target / "evaluator/reference").exists())
                self.assertFalse((target / "evaluator/fixtures").exists())
                self.assertEqual([p.name for p in (target / "benchmark/tasks").iterdir()], [task])

    def test_final_summaries_validate_without_embedded_freeze_bookkeeping(self):
        schema=freeze.read('results/result.schema.json')
        paths=list((freeze.ROOT/'results').glob('*/summary.json'))
        self.assertGreaterEqual(len(paths),9)
        before={p:p.read_bytes() for p in paths}
        for path in paths:
            summary=json.loads(path.read_text())
            jsonschema.validate(summary,schema)
            self.assertNotIn('task_freeze_receipts',summary)
            for row in summary['tasks']:self.assertNotIn('benchmark_freeze',row)
        freeze.sync_results()
        self.assertEqual(before,{p:p.read_bytes() for p in paths})


if __name__ == "__main__":
    unittest.main()
