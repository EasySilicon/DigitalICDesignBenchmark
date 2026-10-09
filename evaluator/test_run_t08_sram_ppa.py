"""Interrupted physical qualification must resume without throwing away evidence."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from run_t08_sram_ppa import reusable_route, run, validated_promotion
from t11_sram import contract
from ppa_aggregate import source_hash


class ResumeTest(unittest.TestCase):
    def fixture(self, root, seed):
        receipt = dict(policy=contract(), source_sha256={"rtl/top.v": "original"},
                       mapped_netlist_sha256="mapped", macro_count=2)
        report = root / f"flow/reports/asap7/mac/seed{seed}/6_finish.rpt"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("routed report")
        final = root / f"flow/results/asap7/mac/seed{seed}"
        final.mkdir(parents=True, exist_ok=True)
        for name in ("6_final.v", "6_final.odb", "6_final.sdc", "6_final.spef"):
            (final / name).write_text("routed artifact")
        route = dict(task="T08", exit_code=0, seed=seed, corner="WC", period_ps=1000,
                     utilization=10, density=0.6, report=str(report),
                     clock_periods_ps={c: 1000 for c in ("logic_clk", "tx_clk", "rx_clk")},
                     sram_contract=receipt["policy"], source_sha256=receipt["source_sha256"],
                     mapped_netlist_sha256="mapped", macro_count=2, disconnected_macro_inputs=0)
        record = root / f"seed{seed}/route/result.json"
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps(route))
        return receipt, record, route

    def test_completed_route_reuse_checks_provenance_and_actual_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            receipt, record, route = self.fixture(root, 11)
            self.assertEqual(reusable_route(record, receipt, 11), route)
            for field, value in (("period_ps", 2000), ("exit_code", 1), ("macro_count", 1),
                                 ("source_sha256", {}), ("mapped_netlist_sha256", "changed")):
                record.write_text(json.dumps({**route, field: value}))
                with self.subTest(field=field), self.assertRaises(ValueError):
                    reusable_route(record, receipt, 11)
            record.write_text(json.dumps(route))
            (root / "flow/results/asap7/mac/seed11/6_final.spef").unlink()
            with self.assertRaises(ValueError):
                reusable_route(record, receipt, 11)

    def test_resume_reuses_mapping_and_seed11_without_replaying_regressions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            receipt, record, route = self.fixture(root, 11)
            previous = dict(policy=contract(), submission=str(source), started_at="previous-start",
                            status="failed", error="missing dependency", elapsed_seconds=10, selected_seeds=[11])
            (root / "state.json").write_text(json.dumps(previous))
            (root / "macro_model_selftest.log").write_text("T11_SRAM_MODEL_PASS")
            calls = []
            def execute(command, **kwargs):
                calls.append(command)
                if Path(command[1]).name == "ppa_probe.py":
                    self.fixture(root, int(command[command.index("--seed") + 1]))
                return subprocess.CompletedProcess(command, 0)
            measured = dict(setup_worst_slack_ns=-.1, hold_worst_slack_ns=.01, drc_violations=0)
            with patch("run_t08_sram_ppa.validated_mapping", return_value=receipt), \
                 patch("run_t08_sram_ppa.subprocess.run", side_effect=execute), \
                 patch("run_t08_sram_ppa.aggregate", return_value=measured) as measurement, \
                 patch("builtins.print"):
                state = run(source, root, root / "flow", resume=True)
            layouts = [c for c in calls if Path(c[1]).name == "ppa_probe.py"]
            self.assertEqual(layouts, [])
            self.assertFalse(any("--binary" in c or "-m" in c for c in calls))
            self.assertEqual(state["reused_routes"], [11])
            self.assertEqual(state["completed_seeds"], [11])
            self.assertEqual(state["selected_seeds"], [11])
            self.assertEqual(state["status"], "single_seed_needs_optimization")
            self.assertEqual(measurement.call_args.args[-1], (11,))
            self.assertFalse(any(Path(c[1]).name == "t08_reference_freeze.py" for c in calls))
            self.assertTrue(list(root.glob("state.before_resume_*.json")))
            self.assertEqual(json.loads(record.read_text()), route)

    def test_promotion_requires_passing_same_source_seed11(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "rtl").mkdir()
            (root / "rtl/files.f").write_text("top.v\n")
            (root / "rtl/top.v").write_text("module mac_1g_repair; endmodule\n")
            pilot = dict(measurement_status="pilot", source_sha256=source_hash(root),
                         parameter_set={"seeds": [11]},
                         per_seed=[dict(route_record="route.json", power_record="power.json")],
                         setup_worst_slack_ns=.01, hold_worst_slack_ns=.01, drc_violations=0)
            evidence = root / "aggregate.json"
            evidence.write_text(json.dumps(pilot))
            with patch("run_t08_sram_ppa.aggregate", return_value=pilot):
                self.assertEqual(validated_promotion(root, evidence), (Path("route.json"), Path("power.json")))
            for field, value in (("setup_worst_slack_ns", -.001), ("hold_worst_slack_ns", -.001),
                                 ("drc_violations", 1), ("source_sha256", "changed")):
                bad = {**pilot, field: value}
                evidence.write_text(json.dumps(bad))
                with patch("run_t08_sram_ppa.aggregate", return_value=bad), self.subTest(field=field), self.assertRaises(ValueError):
                    validated_promotion(root, evidence)

    def test_missing_power_dependency_fails_before_starting_eda(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            failure = subprocess.CalledProcessError(1, ["power", "--help"])
            with patch("run_t08_sram_ppa.subprocess.run", side_effect=failure) as execute, patch("builtins.print"):
                with self.assertRaises(subprocess.CalledProcessError):
                    run(root / "source", root, root / "flow")
            self.assertEqual(execute.call_count, 1)
            self.assertIn("--help", execute.call_args.args[0])
            self.assertEqual(json.loads((root / "state.json").read_text())["status"], "failed")


if __name__ == "__main__":
    unittest.main()
