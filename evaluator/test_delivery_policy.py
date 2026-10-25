"""Delivery deductions preserve independent scores and never exceed ten."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluator.delivery_check import check, inspect_contract
from evaluator.delivery_policy import assessment, apply_to_score, deduction
from evaluator.score_with_power_budget import score_run
from evaluator.score_run import load_rules


def error(root, attribution="candidate"):
    return dict(root_cause=root, attribution=attribution, detail=root)


class DeliveryPolicyTest(unittest.TestCase):
    def test_tiers_and_cap(self):
        cases = [([], [], 0), (["README.md"], [], 5),
                 (["README.md", "run.sh"], [], 10),
                 (["README.md", "run.sh", "results.json"], [], 10),
                 ([], [error("entry")], 5),
                 ([], [error("entry"), error("result")], 10),
                 ([], [error(str(i)) for i in range(20)], 10),
                 (["README.md"], [error("entry")], 10)]
        for missing, errors, expected in cases:
            with self.subTest(missing=missing, errors=errors):
                self.assertEqual(deduction(assessment(missing, errors)), (expected, None))

    def test_repeated_root_and_infrastructure_do_not_add_penalties(self):
        self.assertEqual(deduction(assessment(errors=[error("entry"), error("entry"),
            error("host", "infrastructure")])), (5, None))
        self.assertEqual(deduction(assessment(errors=[error("host", "infrastructure")])), (0, None))
        self.assertEqual(deduction(assessment(["rtl/", "rtl/files.f"])), (5, None))

    def test_current_rules_cover_all_ten_tasks(self):
        rules = load_rules()
        for task, items in rules['tasks'].items():
            groups = {g: dict(cases_passed=item.get('required_cases_total', 1),
                              cases_total=item.get('required_cases_total', 1))
                      for item in items for g in item['groups']}
            payload = dict(task_id=task, groups=groups, delivery_qualified=False,
                           elapsed_seconds=1, time_limit_seconds=14400,
                           sustained_throughput_passed=True)
            for count, expected in ((1, 5), (2, 10), (20, 10)):
                with self.subTest(task=task, count=count):
                    result = score_run(dict(payload, candidate_delivery_error_count=count))
                    self.assertEqual(result['functional_total'], 50)
                    self.assertEqual(result['candidate_delivery_penalty'], expected)
                    self.assertEqual(result['display_score'],
                                     result['display_score_before_candidate_penalty'] - expected)

    def test_unresolved_attribution_remains_pending(self):
        for report in (assessment(errors=[error("entry", "pending")]),):
            penalty, reason = deduction(report)
            self.assertIsNone(penalty)
            self.assertTrue(reason)

    def test_two_missing_items_resolve_a_previously_pending_total(self):
        base = dict(functional_total=50, ppa_score=35, time_score=2.5,
                    display_score_before_candidate_penalty=87.5, display_score=None,
                    delivery_qualified=False, delivery_penalty_status="pending",
                    delivery_penalty_pending_reason="exactly_two_missing_items_requires_policy_decision")
        result = apply_to_score(base, dict(delivery_assessment=assessment(["run.sh", "README.md"])))
        self.assertEqual(result["candidate_delivery_penalty"], 10)
        self.assertEqual(result["display_score"], 77.5)
        self.assertEqual(result["delivery_penalty_status"], "adjudicated")
        self.assertNotIn("delivery_penalty_pending_reason", result)

    def test_current_score_caps_legacy_adjudicated_counts_and_preserves_components(self):
        base = dict(functional_total=50, ppa_score=35, time_score=2.5,
                    display_score_before_candidate_penalty=87.5, display_score=72.5,
                    delivery_qualified=False)
        payload = dict(task_id="T01", candidate_delivery_error_count=3)
        with patch("evaluator.score_with_power_budget.frozen_score_run", return_value=base):
            scored = score_run(payload)
        self.assertEqual(scored["display_score"], 77.5)
        self.assertEqual(scored["candidate_delivery_penalty"], 10)
        for field in ("functional_total", "ppa_score", "time_score"):
            self.assertEqual(scored[field], base[field])
        self.assertEqual(base["display_score"], 72.5)

    def test_floor_and_pending_keep_components(self):
        base = dict(functional_total=3, ppa_score=0, time_score=0,
                    display_score_before_candidate_penalty=3, delivery_qualified=False)
        result = apply_to_score(base, dict(delivery_assessment=assessment(errors=[error("entry")])))
        self.assertEqual(result["display_score"], 0)
        result = apply_to_score(base, dict(delivery_assessment=assessment(errors=[error("entry", "pending")])))
        self.assertIsNone(result["display_score"])
        self.assertEqual(result["functional_total"], 3)

    def test_invalid_assessments_are_rejected(self):
        for report in (None, [], assessment("run.sh"), assessment(errors=[{}]),
                       assessment(errors=[error("entry", "guess")])):
            with self.subTest(report=report), self.assertRaises(ValueError):
                deduction(report)


class DeliveryInventoryTest(unittest.TestCase):
    def test_inventory_reports_all_missing_items_without_cascading_directory_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = check("T01", root, 11, 600)
            report = result["delivery_assessment"]
            self.assertEqual(set(report["missing_deliverables"]),
                             {"rtl/", "verif/", "run.sh", "README.md", "results.json"})
            self.assertFalse(report["errors"])
            self.assertEqual(deduction(report), (10, None))

    def test_clean_replay_does_not_reuse_submitted_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rtl").mkdir()
            (root / "rtl/files.f").write_text("dut.sv\n")
            (root / "rtl/dut.sv").write_text("module dut; endmodule\n")
            (root / "verif").mkdir()
            (root / "verif/tb.py").write_text("# self-check\n")
            (root / "README.md").write_text("Run ./run.sh\n")
            data = '{"tests":[{"name":"self","passed":true,"seed":11}],"tool_versions":{"test":"1"},"elapsed_seconds":0}'
            (root / "results.json").write_text(data)
            script = root / "run.sh"
            script.write_text("#!/bin/sh\ntest ! -e results.json || exit 7\nprintf '%s' '" + data + "' > results.json\n")
            script.chmod(0o755)
            result = check("T01", root, 11, 600)
            self.assertTrue(result["delivery_qualified"], result)
            self.assertEqual(deduction(result["delivery_assessment"]), (0, None))
            (root / "results.json").unlink()
            result = check("T01", root, 11, 600)
            self.assertEqual(result["delivery_assessment"]["missing_deliverables"], ["results.json"])
            self.assertEqual(deduction(result["delivery_assessment"]), (5, None))


if __name__ == "__main__":
    unittest.main()
