"""Judge orchestration and host-only boundary inventory regression tests."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from evaluator.t08_check import (
    BOUNDARY_CLOCKS, GROUPS, JUDGE_REVISION, NEW_CASES, SEEDS, evaluate, simulation_args,
)


class T08CheckTest(unittest.TestCase):
    def test_unique_scored_inventory_and_fixed_maximum(self):
        cases = [case for _, _, cases in GROUPS for case in cases]
        self.assertEqual(sorted(cases), list(range(37)))
        self.assertEqual(len(cases), len(set(cases)))
        self.assertEqual(sum(points for _, points, _ in GROUPS), 50)
        self.assertEqual(set(NEW_CASES), set(range(28, 37)))

    def test_all_boundary_clock_profiles_and_legacy_defaults(self):
        self.assertEqual(BOUNDARY_CLOCKS, ((6.25, 0.7), (5.0, 2.3), (3.125, 6.1)))
        for seed, (half, phase) in zip(SEEDS, BOUNDARY_CLOCKS):
            self.assertEqual(simulation_args(13, seed), ["+CASE=13", f"+SEED={seed}"])
            for case in NEW_CASES:
                self.assertEqual(simulation_args(case, seed), [f"+CASE={case}", f"+SEED={seed}",
                    f"+LOGIC_HALF_NS={half}", f"+RX_PHASE_NS={phase}"])

    def replay(self, failure=None):
        def run(cmd, **kwargs):
            if cmd[0] == "verilator":
                return SimpleNamespace(returncode=0, stdout="compiled", stderr="")
            case = int(next(arg.split("=", 1)[1] for arg in cmd if arg.startswith("+CASE=")))
            seed = int(next(arg.split("=", 1)[1] for arg in cmd if arg.startswith("+SEED=")))
            if failure and (case, seed) == (28, 47):
                if failure == "timeout":
                    raise subprocess.TimeoutExpired(cmd, 30, output=b"partial output", stderr=b"diagnostic")
                if failure == "missing_marker":
                    return SimpleNamespace(returncode=0, stdout="finished without pass witness", stderr="")
                return SimpleNamespace(returncode=1, stdout="ACCEPT_PASS T08 CASE=28", stderr="fatal")
            return SimpleNamespace(returncode=0, stdout=f"ACCEPT_PASS T08 CASE={case}\n", stderr="")

        with tempfile.TemporaryDirectory(prefix="test_t08_judge_") as temp:
            output = Path(temp) / "report.json"
            with patch("evaluator.t08_check.sources_from_filelist", return_value=[]), \
                 patch("evaluator.t08_check.subprocess.run", side_effect=run):
                report = evaluate(Path(temp), output)
            self.assertEqual(json.loads(json.dumps(report)), json.loads(output.read_text()))
            if failure == "timeout":
                self.assertEqual((Path(temp) / "report.case28.seed47.log").read_text(),
                                 "partial outputdiagnostic")
            return report

    def test_complete_positive_report(self):
        report = self.replay()
        self.assertEqual(report["judge_revision"], JUDGE_REVISION)
        self.assertTrue(report["full_functional_pass"])
        self.assertEqual(report["functional_total"], 50)
        self.assertEqual(sum(len(case["runs"]) for case in report["cases"].values()), 111)

    def test_zero_exit_without_pass_marker_is_not_pass(self):
        self.assertFalse(self.replay("missing_marker")["cases"][28]["passed"])

    def test_pass_marker_with_nonzero_exit_is_not_pass(self):
        self.assertFalse(self.replay("nonzero_exit")["cases"][28]["passed"])

    def test_timeout_is_recorded_and_remaining_cases_still_run(self):
        report = self.replay("timeout")
        self.assertFalse(report["full_functional_pass"])
        self.assertEqual(report["cases"][28]["runs"][1]["error"], "candidate simulation timeout")
        self.assertTrue(report["cases"][36]["passed"])
        self.assertEqual(report["functional_total"], 49)

    def test_boundary_stimulus_and_error_monitors_remain_host_only(self):
        root = Path(__file__).resolve().parent
        public = (root / "public/tb_T08.sv").read_text()
        private = (root / "fixtures/t11_mac/tb_acceptance.sv").read_text()
        self.assertNotIn("policy_oracle", public)
        self.assertNotIn("boundary_rx_check", public)
        self.assertNotIn("tb.dut.", private)
        self.assertIn("tb.gmii_rx_er=gmii_error && i==body.size()/2", private)
        self.assertIn("if(!tb.logic_rst && tb.rx_error_bad_fcs)", private)


if __name__ == "__main__":
    unittest.main()
