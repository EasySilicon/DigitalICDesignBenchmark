"""Scoring regressions for numerical errors outside the systolic group."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from evaluator.score_run import build_t10_score_input, load_rules, score_run
from evaluator.t10_score_evidence import systolic_passed


class T10ScoreEvidenceTest(unittest.TestCase):
    def report(self):
        groups = {group: {"cases_passed": 4, "cases_total": 4}
                  for item in load_rules()["tasks"]["T10"] for group in item["groups"]}
        groups["MM-PROTO"] = {"cases_passed": 5, "cases_total": 5}
        cases = sum(row["cases_total"] for row in groups.values()) - 1
        return dict(task_id="T10", phase="run", cases=cases, groups=groups,
                    structure={"passed": True}, reset_probe_passed=True, failures=[],
                    stream_line=f"MM_STREAM input_bubble_phases={'0' * 14} finished={cases}")

    def payload(self, report):
        return dict(task_id="T10", groups=report["groups"], elapsed_seconds=1,
                    time_limit_seconds=14400, delivery_qualified=True,
                    sustained_throughput_passed=False)

    def numerical_failure(self):
        report = self.report()
        report["groups"]["MM-F16"]["cases_passed"] -= 1
        report["failures"].append(dict(case=0, group="MM-F16", protocol=True,
                                       timing=True, output=True,
                                       errors=["got finite, expected +inf"]))
        return report

    def test_other_group_arithmetic_failure_preserves_systolic_points(self):
        report = self.numerical_failure()
        payload = self.payload(report)
        old = score_run(payload)
        corrected = score_run(build_t10_score_input(payload, report))
        self.assertAlmostEqual(corrected["functional_total"] - old["functional_total"], 50 / 3)
        self.assertEqual(corrected["functional_basic"], old["functional_basic"])
        self.assertFalse(corrected["full_functional_pass"])
        self.assertFalse(corrected["ppa_eligible"])
        self.assertEqual(corrected["ppa_score"], 0)
        self.assertEqual(corrected["time_score"], 0)
        self.assertFalse(next(row for row in corrected["score_items"]
                              if row["id"] == "P_SYSTOLIC")["safety_violation"])

    def test_complete_report_passes(self):
        self.assertTrue(systolic_passed(self.report()))

    def test_real_stream_and_structure_failures_remain_blocked(self):
        for name in ("bubble", "truncated", "structure", "reset", "simulation", "numeric_systolic"):
            with self.subTest(name=name):
                report = self.report()
                if name == "bubble":
                    report["stream_line"] = report["stream_line"].replace("0" * 14, "1" + "0" * 13)
                elif name == "truncated":
                    report["stream_line"] = report["stream_line"].replace(f'finished={report["cases"]}', "finished=1")
                elif name == "structure": report["structure"]["passed"] = False
                elif name == "reset": report["reset_probe_passed"] = False
                elif name == "simulation": report["phase"] = "simulation-failed"
                else: report["groups"]["MM-SYSTOLIC"]["cases_passed"] -= 1
                self.assertFalse(systolic_passed(report))

    def test_non_systolic_protocol_and_timing_failures_are_not_exonerated(self):
        for flag in ("protocol", "timing", "output"):
            with self.subTest(flag=flag):
                report = self.numerical_failure();report["failures"][0][flag] = False
                self.assertFalse(systolic_passed(report))

    def test_missing_duplicate_and_inconsistent_evidence_rejected(self):
        report = self.numerical_failure()
        variants = [deepcopy(report) for _ in range(5)]
        variants[0]["failures"] = []
        variants[1]["failures"] *= 2
        variants[2]["groups"]["MM-F16"]["cases_passed"] = 4
        variants[3]["failures"][0]["case"] = True
        variants[4]["cases"] -= 1
        with self.assertRaisesRegex(ValueError, "incomplete T10 failure evidence"):
            systolic_passed(variants[0])
        for candidate in variants[1:]:self.assertFalse(systolic_passed(candidate))
        bad_payload = self.payload(report);bad_payload["groups"] = {}
        with self.assertRaisesRegex(ValueError, "does not match"):
            build_t10_score_input(bad_payload, report)

    def test_truncated_numerical_details_require_replay_instead_of_zero_points(self):
        report = self.report()
        report["groups"]["MM-F16"] = {"cases_passed": 9, "cases_total": 60}
        report["cases"] = sum(row["cases_total"] for row in report["groups"].values()) - 1
        report["stream_line"] = f'MM_STREAM input_bubble_phases={"0" * 14} finished={report["cases"]}'
        report["failures"] = [dict(case=i, group="MM-F16", protocol=True, timing=True,
                                   output=True, errors=["numeric mismatch"]) for i in range(50)]
        with self.assertRaisesRegex(ValueError, "replay the original simulation log"):
            build_t10_score_input(self.payload(report), report)

    def test_malformed_reports_and_explicit_safety_failures_rejected(self):
        for field, value in [("structure", None), ("stream_line", []),
                             ("cases", True), ("failures", None)]:
            with self.subTest(field=field):
                report = self.report();report[field] = value
                self.assertFalse(systolic_passed(report))
        report = self.report();report["groups"]["MM-SYSTOLIC"]["safety_violation"] = True
        self.assertFalse(systolic_passed(report))
        self.assertFalse(systolic_passed(None))
        with self.assertRaisesRegex(ValueError, "must be objects"):
            build_t10_score_input({}, None)

    def test_cli_uses_same_evidence_gate(self):
        report = self.numerical_failure();payload = self.payload(report)
        with tempfile.TemporaryDirectory() as name:
            root = Path(name);(root / "report.json").write_text(json.dumps(report))
            (root / "input.json").write_text(json.dumps(payload))
            command = [sys.executable, str(Path(__file__).with_name("score_run.py")),
                       str(root / "input.json"), "--t10-functional-report", str(root / "report.json")]
            run = subprocess.run(command, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(run.stdout), score_run(build_t10_score_input(payload, report)))


if __name__ == "__main__":
    unittest.main()
