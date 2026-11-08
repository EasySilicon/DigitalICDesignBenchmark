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

    def test_t08_historical_report_bytes_are_anchored_to_original_freeze(self):
        base = freeze.ROOT / freeze.T08_EVIDENCE
        original = json.loads((base / "freeze.json").read_text())
        receipt = freeze.read("benchmark/tasks/T08/PPA_FREEZE.json")
        self.assertEqual(freeze.sha(base / "freeze.json"), receipt["freeze_evidence"]["freeze_manifest_sha256"])
        for path in base.rglob("*"):
            if path.is_file() and str(path.relative_to(base)) in original["artifact_sha256"]:
                self.assertEqual(freeze.sha(path), original["artifact_sha256"][str(path.relative_to(base))])

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

    def test_kimi_final_summary_preserves_scores_and_elapsed_time(self):
        summary=freeze.read("results/kimi-k3/summary.json")
        record = next(row for row in summary["tasks"]
                      if row["task_id"] == "T08")
        self.assertEqual(summary["trial_kind"], "pre_release_pilot")
        self.assertFalse(summary["ranking_eligible"])
        self.assertEqual(record["functional_total"], 50)
        self.assertAlmostEqual(record["ppa_score"], 33.78779834927204)
        self.assertAlmostEqual(record["time_score"], 0.5088926041126252)
        self.assertAlmostEqual(record["elapsed_seconds"], 8083.993312597275)
        self.assertAlmostEqual(record["display_score"], 84.29669095338467)

    def test_final_summaries_exclude_workflow_bookkeeping(self):
        for path in (freeze.ROOT / "results").glob("*/summary.json"):
            summary = json.loads(path.read_text())
            self.assertNotIn("t09_regrade", summary)
            for row in summary["tasks"]:
                for key in ("run_phase", "pilot_budget", "previous_trial",
                            "additional_phase_elapsed_seconds"):
                    self.assertNotIn(key, row)


if __name__ == "__main__":
    unittest.main()
