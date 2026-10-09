"""Author-side concurrency matrix and negative-control guard regressions."""
from __future__ import annotations

import itertools
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from evaluator.t08_stress_check import CASES, CLOCKS, PHASES, SEEDS, evaluate
from evaluator.t08_stress_qualification import VARIANTS, classify, inject


class T08StressCheckTest(unittest.TestCase):
    def replay(self, failure=None):
        simulations = []

        def run(cmd, **kwargs):
            if cmd[0] == "verilator":
                return SimpleNamespace(returncode=int(failure == "compile"), stdout="compile", stderr="")
            args = dict(arg[1:].split("=", 1) for arg in cmd[1:])
            case, seed = int(args["STRESS_CASE"]), int(args["SEED"])
            simulations.append((case, seed, float(args["LOGIC_HALF_NS"]), float(args["RX_PHASE_NS"])))
            if failure and (case, seed) == (0, 47):
                if failure == "timeout":
                    raise subprocess.TimeoutExpired(cmd, 30, output=b"partial", stderr=b"diagnostic")
                if failure in ("marker", "metrics"):
                    stdout = ('STRESS_METRICS {"tx_frames":1}\n' if failure == "marker" else "STRESS_PASS T08 CASE=0\n")
                    return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
                return SimpleNamespace(returncode=1, stdout='STRESS_PASS T08 CASE=0\nSTRESS_METRICS {"tx_frames":1}\n', stderr="")
            return SimpleNamespace(returncode=0, stdout=f'STRESS_PASS T08 CASE={case}\nSTRESS_METRICS {{"tx_frames":1}}\n', stderr="")

        with tempfile.TemporaryDirectory(prefix="test_t08_stress_") as temp:
            output = Path(temp) / "report.json"
            with patch("evaluator.t08_stress_check.sources_from_filelist", return_value=[]), \
                 patch("evaluator.t08_stress_check.subprocess.run", side_effect=run), patch("builtins.print"):
                report = evaluate(Path(temp) / "original", output)
            self.assertEqual(json.loads(output.read_text()), json.loads(json.dumps(report)))
            return report, simulations

    def test_default_matrix_axes_are_independent(self):
        report, simulations = self.replay()
        self.assertTrue(report["full_pass"])
        self.assertEqual(report["run_count"], 270)
        self.assertEqual(set(simulations), set(itertools.product(CASES, SEEDS, CLOCKS.values(), PHASES)))
        self.assertEqual(len(simulations), len(set(simulations)))

    def test_zero_exit_needs_both_marker_and_metrics(self):
        for failure in ("marker", "metrics"):
            with self.subTest(failure=failure):
                report, _ = self.replay(failure)
                self.assertFalse(report["full_pass"])
                self.assertEqual(report["passed_count"], 255)

    def test_marker_cannot_override_nonzero_exit(self):
        report, _ = self.replay("nonzero")
        self.assertFalse(report["full_pass"])
        self.assertEqual(report["passed_count"], 255)

    def test_timeout_is_not_pass_and_does_not_skip_later_cases(self):
        report, simulations = self.replay("timeout")
        self.assertEqual(len(simulations), 270)
        self.assertFalse(report["full_pass"])
        self.assertTrue(all(run["passed"] for run in report["runs"] if run["case"] == 5))
        self.assertEqual(next(run["error"] for run in report["runs"] if not run["passed"]), "simulation timeout")

    def test_compile_error_is_not_a_functional_result(self):
        report, simulations = self.replay("compile")
        self.assertFalse(report["compiled"])
        self.assertEqual(simulations, [])
        self.assertEqual(report["passed_count"], 0)
        self.assertFalse(classify(report)["detected"])

    def test_reject_mutating_original_or_invalid_matrix(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for output in (root, root / "report.json"):
                with self.assertRaises(ValueError):
                    evaluate(root, output)
            for kwargs in ({"cases": ()}, {"cases": (99,)}, {"seeds": (47, 47)},
                           {"clocks": (200,)}, {"phases": (-1,)}, {"phases": (8,)}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    evaluate(root / "original", root / "report.json", **kwargs)

    def test_external_only_scoreboards_and_exercised_preconditions(self):
        root = Path(__file__).resolve().parent
        source = (root / "fixtures/t11_mac/tb_stress.sv").read_text()
        self.assertNotIn("tb.dut.", source)
        self.assertIn("TX prefix before accepted good terminal", source)
        self.assertIn("RX prefix before physical frame completion", source)
        self.assertIn("160 MHz TX pressure never exercised backpressure", source)
        self.assertIn("wire_concurrent_cycles==0", source)
        self.assertIn("epoch_abort=1", source)
        self.assertIn("pre-reset TX traffic escaped into new epoch", source)
        self.assertIn("pre-reset RX traffic escaped into new epoch", source)
        self.assertIn("reset stimulus failed to establish in-flight traffic", source)
        public = (root / "public/tb_T08.sv").read_text()
        self.assertNotIn("near_full_read_write", public)
        self.assertNotIn("rx_completed", public)


class T08StressQualificationTest(unittest.TestCase):
    def test_recorded_qualification_matches_current_checker(self):
        root = Path(__file__).resolve().parent.parent
        evidence = json.loads((root / "evaluator/fixtures/t11_mac/stress_qualification_v1.json").read_text())
        qualification = evidence["qualification"]
        self.assertTrue(qualification["passed"])
        self.assertEqual(qualification["detected_count"], len(VARIANTS))
        self.assertEqual(set(qualification["variants"]), set(VARIANTS))
        for relative, digest in qualification["checker_sha256"].items():
            self.assertEqual(hashlib.sha256((root / relative).read_bytes()).hexdigest(), digest)
        self.assertEqual(hashlib.sha256((root / "evaluator/t08_stress_qualification.py").read_bytes()).hexdigest(),
                         qualification["qualification_sha256"])
        for report in evidence["summaries"].values():
            self.assertTrue(report["compiled"])
            self.assertTrue(report["full_pass"])
            self.assertEqual(report["passed_count"], 270)
            self.assertEqual(report["checker_sha256"], qualification["checker_sha256"])
        self.assertEqual(evidence["summaries"]["control"]["rtl_sha256"], qualification["baseline_rtl_sha256"])
        self.assertEqual(sum(variant["assertion_witness_count"] for variant in qualification["variants"].values()), 144)

    def test_missing_or_ambiguous_anchor_fails_closed(self):
        for name in VARIANTS:
            with self.subTest(name=name), self.assertRaises(ValueError):
                inject("missing", name)
        with self.assertRaises(ValueError):
            inject("assign s_axis_tready = (\nassign s_axis_tready = (", "tx_full_stuck")
        with self.assertRaises(ValueError):
            inject("", "unknown")

    def test_injection_only_changes_targeted_behavior(self):
        tx = inject("assign s_axis_tready = (condition);", "tx_full_stuck")
        self.assertIn("if (s_rst) qualification_stuck <= 1'b0", tx)
        self.assertIn("!DROP_WHEN_FULL && full", tx)
        rx = inject("if ((full && DROP_WHEN_FULL) || (full_wr && DROP_OVERSIZE_FRAME) || drop_frame_reg) begin",
                    "rx_overflow_resurrection")
        self.assertNotIn("|| drop_frame_reg", rx)
        top = inject("wire [7:0]  tx_fifo_axis_tdata;\n.gmii_tx_en(gmii_tx_en),", "cross_channel_wire_gate")
        self.assertIn("qualification_tx_en && !gmii_rx_dv", top)
        reset = inject("wire [7:0]  tx_fifo_axis_tdata;\n.gmii_tx_en(gmii_tx_en),", "reset_wire_ghost")
        self.assertIn("qualification_ever_tx && !tx_rst", reset)

    def test_detection_needs_compiled_all_seed_phase_assertion_witnesses(self):
        report = {"compiled": True, "run_count": 1, "matrix": {},
                  "runs": [{"passed": False, "exit_code": -6, "log_tail": "%Fatal: RX mismatch"}]}
        self.assertTrue(classify(report)["detected"])
        for changed in ({"passed": True}, {"exit_code": 0}, {"log_tail": "timeout"},
                        {"log_tail": "%Fatal: testbench watchdog"}):
            failure = {**report, "runs": [{**report["runs"][0], **changed}]}
            self.assertFalse(classify(failure)["detected"])
        self.assertFalse(classify({**report, "compiled": False})["detected"])
        self.assertFalse(classify({**report, "runs": [], "run_count": 0})["detected"])


if __name__ == "__main__":
    unittest.main()
