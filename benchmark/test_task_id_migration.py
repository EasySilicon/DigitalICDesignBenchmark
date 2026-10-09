"""Protect task identity, immutable evidence and null-vs-zero during migration."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluator"))


class TaskIdMigrationTest(unittest.TestCase):
    def test_new_suite_contains_exactly_ten_non_cvdp_tasks(self):
        manifest = yaml.safe_load((ROOT / "benchmark/manifest.yaml").read_text())
        self.assertEqual(manifest["suite_id"], "ic-delivery-rtl-v0.3")
        self.assertEqual([row["id"] for row in manifest["tasks"]], [f"T{i:02d}" for i in range(1, 11)])
        self.assertEqual(manifest["tasks"][0]["title"], "serdes_rx_comma_aligner")
        self.assertEqual(manifest["tasks"][7]["title"], "mac_1gbe_bug_repair_vlan_admission")
        self.assertNotIn("cvdp", yaml.safe_load((ROOT / "benchmark/sources.lock.yaml").read_text()))
        self.assertFalse((ROOT / "benchmark/tasks/T11").exists())
        self.assertFalse((ROOT / "evaluator/reference/T01/rtl/serial_in_parallel_out_8bit.sv").exists())

    def test_frozen_mac_reference_identity_and_scoring_provenance(self):
        from ppa_aggregate import source_hash
        from evaluator.score_run import load_rules, ppa_provenance_valid, ppa_score, score_functional
        from evaluator.t08_check import GROUPS
        reference = json.loads((ROOT / "benchmark/ppa-baselines.json").read_text())["tasks"]["T08"]
        self.assertEqual(source_hash(ROOT / "evaluator/reference/T08"), reference["source_sha256"])
        self.assertTrue(ppa_provenance_valid("T08", reference, reference))
        self.assertAlmostEqual(ppa_score(reference, reference), 35)
        groups = {name:{"cases_passed":len(cases), "cases_total":len(cases)} for name,_,cases in GROUPS}
        basic, edge, _ = score_functional("T08", groups, load_rules())
        self.assertEqual(basic + edge, 50)
        # A scenario only counts once all three functional seeds pass.
        groups["metadata_headers"]["cases_passed"] -= 1
        basic, edge, _ = score_functional("T08", groups, load_rules())
        self.assertEqual(basic + edge, 49)
        bad = copy.deepcopy(reference)
        bad["parameter_set"]["sram_contract"]["contract_sha256"] = "0" * 64
        self.assertFalse(ppa_provenance_valid("T08", bad, reference))

    def test_historical_mutation_evidence_is_exact_relabel_not_new_run(self):
        legacy = ROOT / "evaluator/fixtures/t11_mac/legacy_judge_v31"
        pairs = [("t11_check.py", "evaluator/t08_check.py"),
                 ("tb_T11.sv", "evaluator/public/tb_T08.sv"),
                 ("tb_acceptance.sv", "evaluator/fixtures/t11_mac/tb_acceptance.sv"),
                 ("t11_stress_check.py", "evaluator/t08_stress_check.py"),
                 ("t11_stress_qualification.py", "evaluator/t08_stress_qualification.py"),
                 ("tb_stress.sv", "evaluator/fixtures/t11_mac/tb_stress.sv")]
        for name, relative in pairs:
            old = (legacy / name).read_text()
            normalized = old.replace("T11", "T08").replace("t11", "t08").replace("fixtures/t08_mac", "fixtures/t11_mac")
            if name == "t11_check.py":
                normalized = normalized.replace('"status":"experimental"', '"status":"frozen_task"')
                normalized = normalized.replace('"ppa_status":"pending_frozen_reference"', '"ppa_status":"candidate_measurement_pending"')
            self.assertEqual(normalized, (ROOT / relative).read_text(), relative)

    def test_six_models_have_consistent_summaries_and_nullable_not_run_records(self):
        from evaluator.score_run import weighted_suite_score
        schema = json.loads((ROOT / "results/result.schema.json").read_text())
        models = ("gpt-6-astra", "gpt-6-sol", "gpt-6.1-sol", "kimi-k3", "deepseek-flash", "glm-5.3-flash")
        for model in models:
            folder = ROOT / "results" / model
            summary = json.loads((folder / "summary.json").read_text())
            self.assertEqual(summary["suite_id"], "ic-delivery-rtl-v0.3")
            self.assertEqual([row["task_id"] for row in summary["tasks"]], [f"T{i:02d}" for i in range(1, 11)])
            score = weighted_suite_score({row["task_id"]:row["display_score"] for row in summary["tasks"]})
            self.assertAlmostEqual(score["weighted_display_score"], summary["weighted_display_score_with_unscored_components_omitted"])
            for row in summary["tasks"]:
                # Public checkout contains final summaries, never raw model archives.
                jsonschema.validate(row, {**schema, "required": [
                    "task_id", "functional_total", "ppa_score", "time_score", "display_score"]})
            if model.startswith("gpt-") or model == "deepseek-flash":
                self.assertIsNone(summary["tasks"][7]["functional_total"])

    def test_mac_candidate_package_excludes_freeze_and_reference(self):
        from benchmark.prepare_trial import prepare
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "task"
            prepare("T08", destination)
            self.assertEqual([path.name for path in (destination / "benchmark/tasks").iterdir()], ["T08"])
            self.assertFalse((destination / "evaluator/reference").exists())
            self.assertFalse((destination / "benchmark/tasks/T08/PPA_FREEZE.json").exists())
            self.assertFalse((destination / "vendor").exists())
            self.assertFalse((destination / "benchmark/task-id-migration.json").exists())
            self.assertIn("frozen brownfield task", (destination / "PROMPT.md").read_text())


if __name__ == "__main__":
    unittest.main()
