"""Recompute current strict scores and verify archived evidence identities."""
from pathlib import Path
import hashlib
import json
import math
import unittest

import jsonschema
from score_run import load_rules, score_functional, weighted_suite_score


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
read = lambda p: json.loads(p.read_text())


def unchanged_scores(rows):
    return [{k:v for k,v in row.items() if k != "benchmark_freeze"} for row in rows]


class StrictPublicationTest(unittest.TestCase):
    def test_strict_scores_match_evidence_and_preserve_other_tasks_and_ppa(self):
        receipt = read(RESULTS / "t10-strict-functional-retest-20261106.json")
        self.assertEqual(receipt["numerical_profile"], "exact-dot-v1")
        self.assertFalse(receipt["numerical_precision_relaxed"])
        self.assertEqual(receipt["functional_seed_count"], 1)
        self.assertEqual((receipt["strict_core_cases"], receipt["range_cases_added"]), (2898, 82))
        rules = load_rules()
        for model in receipt["models"]:
            name = model["model"]
            before = read(ROOT / model["previous_summary"]["path"])
            summary = read(RESULTS / name / "summary.json")
            task = read(RESULTS / name / "T10.json")
            report = read(ROOT / model["functional_report"]["path"])
            self.assertEqual(unchanged_scores(before["tasks"][:9]),
                             unchanged_scores(summary["tasks"][:9]), name)
            self.assertEqual(report["scored_cases"], 2898)
            self.assertEqual(report["candidate_source_sha256"], model["candidate_source_sha256"])
            basic, edges, items = score_functional("T10", report["groups"], rules)
            self.assertAlmostEqual(task["functional_total"], basic + edges)
            self.assertEqual(task["score_items"], items)
            self.assertEqual(task["full_functional_pass"], report["full_functional_pass"])
            current = summary["tasks"][-1]
            for key in ["functional_total", "ppa_score", "time_score", "display_score"]:
                self.assertEqual(current[key], task[key], (name,key))
            for key in ["ppa_score", "time_score"]:
                self.assertEqual(current[key], before["tasks"][-1][key], (name,key))
            penalty = task.get("candidate_delivery_penalty", 0)
            self.assertEqual(task["display_score"], max(0, basic + edges + task["ppa_score"] + task["time_score"] - penalty))
            weighted = weighted_suite_score({r["task_id"]:r["display_score"] for r in summary["tasks"]}, rules)
            self.assertAlmostEqual(summary["weighted_display_score"], weighted["weighted_display_score"], places=12)
            self.assertAlmostEqual(summary["functional_total_sum"], math.fsum(r["functional_total"] for r in summary["tasks"]))
            jsonschema.validate(task, read(RESULTS / "result.schema.json"))
        for name in ["gpt-6-astra", "gpt-6.1-sol", "gpt-6-sol", "kimi-k3.1-pro"]:
            self.assertEqual(read(RESULTS / name / "T10.json")["functional_total"], 50)
        self.assertLess(read(RESULTS / "claude-opus-5.5/T10.json")["functional_total"], 50)

    def test_all_current_and_pre_range_archive_indices_match_files(self):
        backup = RESULTS / "archive/t10-before-range-expansion-20261106"
        for root, manifest in [(backup, read(backup / "backup_manifest.json"))] + [
                (f.parent, read(f)) for f in RESULTS.glob("*/archive_manifest.json")]:
            for entry in manifest["files"]:
                file = root / entry["path"]
                self.assertEqual(file.stat().st_size, entry["bytes"], file)
                self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), entry["sha256"], file)

    def test_current_token_rows_use_max_trial_and_opus_records(self):
        records = {r["model"]:r for r in read(RESULTS / "token-usage.json")["models"]}
        max_record = records["kimi-k3.1-pro"]
        self.assertEqual(max_record["reasoning_effort"], "max")
        self.assertEqual(max_record["total_tokens"], 405087147)
        self.assertEqual(records["claude-opus-5.5"]["total_tokens"], 126636800)
        for model in records.values():
            self.assertEqual(model["total_tokens"], sum(row["tokens"] for row in model["tasks"]))
            for row in model["tasks"]:
                file = ROOT / row["source"]["path"]
                self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), row["source"]["sha256"])
                self.assertEqual(read(file)["tokens"], row["tokens"])
