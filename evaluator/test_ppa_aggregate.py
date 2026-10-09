"""The PPA aggregator preserves timing misses and DRCs for score penalties."""

from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ppa_aggregate import aggregate


class PpaAggregatePhysicalGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        report = self.root / "reports" / "asap7" / "T10" / "6_final.rpt"
        report.parent.mkdir(parents=True)
        report.write_text("test report\n")
        result_dir = self.root / "results" / "asap7" / "T10"
        result_dir.mkdir(parents=True)
        self.route = {
            "task": "T10", "seed": 11, "exit_code": 0,
            "corner": "WC", "period_ps": 1000, "utilization": 10,
            "density": 0.6, "report": str(report),
            "cell_area_um2": 100.0, "critical_path_delay_ps": 990.0,
            "worst_slack_ps": 10.0, "hold_worst_slack_ps": 5.0,
            "drc_violations": 0,
        }
        self.power = {
            "task": "T10", "flow_result_dir": str(result_dir),
            "activity_annotation": 0.99, "ops": 200, "seed": 20260928,
            "workload_id": "T10-power-v1", "workload_parameters": {},
            "workload_sha256": "a" * 64,
            "energy_j_per_op": 1e-9, "power_w": {"total": 1.0},
        }
        self.route_file = self.root / "route.json"
        self.power_file = self.root / "power.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_aggregate(self) -> dict:
        self.route_file.write_text(json.dumps(self.route))
        self.power_file.write_text(json.dumps(self.power))
        with patch("ppa_aggregate.source_hash", return_value="b" * 64):
            return aggregate("T10", self.root,
                             [(self.route_file, self.power_file)], (11,))

    def test_accepts_zero_drc_nonnegative_setup_and_hold(self) -> None:
        result = self.run_aggregate()
        self.assertEqual(result["measurement_status"], "pilot")
        self.assertEqual(result["drc_violations"], 0)

    def test_accepts_setup_miss_and_records_longer_delay(self) -> None:
        self.route["worst_slack_ps"] = -20.0
        self.route["critical_path_delay_ps"] = 1020.0
        result = self.run_aggregate()
        self.assertEqual(result["setup_worst_slack_ns"], -0.02)
        self.assertEqual(result["delay_ns"], 1.02)

    def test_preserves_hold_and_drc_failures_for_scoring(self) -> None:
        for field, value in (("hold_worst_slack_ps", -0.01),
                             ("drc_violations", 1)):
            with self.subTest(field=field):
                original = self.route[field]
                self.route[field] = value
                result = self.run_aggregate()
                expected_key = ("hold_worst_slack_ns"
                                if field == "hold_worst_slack_ps" else field)
                expected_value = value / 1000 if field == "hold_worst_slack_ps" else value
                self.assertEqual(result[expected_key], expected_value)
                self.route[field] = original


class T08AggregateProvenanceTest(PpaAggregatePhysicalGateTest):
    def setUp(self):
        super().setUp()
        rtl = self.root / "rtl"
        rtl.mkdir()
        source = rtl / "mac.sv"
        source.write_text("module mac_1g_repair; endmodule\n")
        (rtl / "files.f").write_text("mac.sv\n")
        clocks = {clock: 1000 for clock in ("logic_clk", "tx_clk", "rx_clk")}
        self.route.update(task="T08", ppa_policy_revision="1.0-uniform-1ghz",
                          clock_relationship="asynchronous", clock_periods_ps=clocks,
                          source_sha256={"rtl/mac.sv": hashlib.sha256(source.read_bytes()).hexdigest()})
        self.power.update(task="T08", workload_id="T11-power-v1", vcd_clock_period_ps=clocks)

    def run_aggregate(self):
        self.route_file.write_text(json.dumps(self.route))
        self.power_file.write_text(json.dumps(self.power))
        return aggregate("T08", self.root, [(self.route_file, self.power_file)], (11,))

    def test_clock_and_source_identity_are_kept(self):
        result = self.run_aggregate()
        self.assertEqual(result["parameter_set"]["clock_periods_ps"], self.route["clock_periods_ps"])
        self.assertEqual(result["parameter_set"]["ppa_policy_revision"], "1.0-uniform-1ghz")

    def test_wrong_clock_or_source_is_rejected(self):
        original = dict(self.route)
        for field, value in (("clock_relationship", "synchronous"),
                             ("source_sha256", {}), ("clock_periods_ps", {"logic_clk": 8000})):
            self.route = {**original, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.run_aggregate()


if __name__ == "__main__":
    unittest.main()
