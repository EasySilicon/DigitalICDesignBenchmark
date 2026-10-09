"""Do not publish a reference that only passed the convenient subset of gates."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluator.t09_reference_freeze import HERE, REFERENCE, TOTALS, add_power_fields, publish_atomic, qualify, sha, verify_routes
from evaluator.ppa_probe import constraint_text
from evaluator.t09_timing_check import case_inventory


class T09FreezeTest(unittest.TestCase):
    def evidence(self):
        ppa = {"task_id": "T09", "measurement_status": "three_seed", "routed": True,
               "per_seed": [{"layout_seed": seed, "setup_worst_slack_ns": .01,
                             "hold_worst_slack_ns": .02, "drc_violations": 0}
                            for seed in (11,29,47)]}
        functional = {"phase": "scored", "score": {"full_functional_pass": True},
                      "groups": {name: {"cases_passed": total, "cases_total": total}
                                 for name, total in TOTALS.items()}}
        timing = {"phase": "run", "timing_policy": "port_timing_v1", "cases_passed": 22,
                  "cases_total": 22,
                  "outcomes": [{"name": name, "passed": True}
                               for name in ["continuous_addi", *(row[0] for row in case_inventory())]],
                  "diagnostic_probes": [{"name": name, "scored": False}
                                        for name in ("taken_bne", "not_taken_bne", "jal", "jalr")]}
        mutants = {"mutants": 21, "compilable": 21, "caught": 21,
                   "outcomes": [{"compilable": True, "caught": True} for _ in range(21)]}
        return ppa, functional, timing, mutants

    def test_all_gates_pass(self):
        qualify(*self.evidence())

    def test_each_physical_failure_blocks_freeze(self):
        for key, value in (("setup_worst_slack_ns", -.001), ("hold_worst_slack_ns", -.001),
                           ("drc_violations", 1)):
            records = self.evidence()
            records[0]["per_seed"][1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                qualify(*records)

    def test_missing_seed_blocks_freeze(self):
        records = self.evidence()
        records[0]["per_seed"].pop()
        with self.assertRaises(ValueError):
            qualify(*records)

    def test_old_merged_hazard_inventory_blocks_freeze(self):
        records = self.evidence()
        records[1]["groups"]["CPU-PIPE-HAZ"] = {"cases_passed": 29, "cases_total": 29}
        with self.assertRaises(ValueError):
            qualify(*records)

    def test_missing_cycle_score_group_blocks_freeze(self):
        records = self.evidence()
        records[1]["groups"].pop("CPU-PIPE-CYCLES")
        with self.assertRaises(ValueError):
            qualify(*records)

    def test_timing_failure_cannot_be_hidden_by_totals(self):
        records = self.evidence()
        records[2]["outcomes"][0]["passed"] = False
        with self.assertRaises(ValueError):
            qualify(*records)

    def test_mutation_survival_blocks_freeze(self):
        records = self.evidence()
        records[3]["outcomes"][0]["caught"] = False
        with self.assertRaises(ValueError):
            qualify(*records)

    def test_duplicate_timing_case_blocks_freeze(self):
        records = self.evidence()
        records[2]["outcomes"][1] = records[2]["outcomes"][0].copy()
        with self.assertRaises(ValueError):
            qualify(*records)

    def test_duplicate_control_probe_blocks_freeze(self):
        records = self.evidence()
        records[2]["diagnostic_probes"][1] = records[2]["diagnostic_probes"][0].copy()
        with self.assertRaises(ValueError):
            qualify(*records)


class RoutedProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ic_bcmk_t09_route_provenance_")
        self.addCleanup(self.directory.cleanup)
        work = Path(self.directory.name)
        source = work/"ref.sv"
        source.write_bytes((REFERENCE/"rtl/ref.sv").read_bytes())
        self.source = source
        self.config = work/"config.mk"
        self.config.write_text(f"export VERILOG_FILES = {source}\n")
        self.sdc = work/"constraint.sdc"
        self.sdc.write_text(constraint_text("rv32i_five_stage_cpu", ("clk",), 1000, .20))
        digest = hashlib.sha256(self.config.read_bytes()+self.sdc.read_bytes()+source.read_bytes()).hexdigest()
        variant = f"ic_probe_t09_wc_p1000_u10_d0.6_s11_{digest[:10]}"
        report = work/"flow/reports/asap7/rv32i_five_stage_cpu"/variant/"6_finish.rpt"
        report.parent.mkdir(parents=True)
        report.write_text("worst slack max 10\nclk_clock period_min = 990\n")
        report.with_name("5_route_drc.rpt").write_text("")
        logs = work/"flow/logs/asap7/rv32i_five_stage_cpu"/variant
        logs.mkdir(parents=True)
        self.metrics = logs/"6_report.json"
        self.metrics.write_text(json.dumps({"finish__design__instance__area__stdcell": 2500,
            "finish__timing__setup__ws": 10, "finish__timing__hold__ws": 30,
            "finish__timing__drv__setup_violation_count": 0,
            "finish__timing__drv__hold_violation_count": 0}))
        self.route = work/"route.json"
        self.route.write_text(json.dumps({"variant": variant, "report": str(report),
            "worst_slack_ps": 10, "critical_path_delay_ps": 990,
            "cell_area_um2": 2500, "hold_worst_slack_ps": 30,
            "setup_violations": 0, "hold_violations": 0, "drc_violations": 0,
            "minimum_period_ps": {"clk_clock": 990}}))
        self.power = work/"power.json"
        self.power.write_text(json.dumps({"vcd_clock_period_ps": {"clk": 1000},
            "workload_parameters": {"seed": 20260928,
                "elf_sha256": sha(HERE/"t09_data/programs/random/diff_mem_seed035_v0.elf")}}))
        self.ppa = {"per_seed": [{"layout_seed": 11,
                    "route_record": str(self.route), "power_record": str(self.power)}]}

    def test_matching_raw_evidence(self):
        verify_routes(self.ppa)

    def test_rtl_cannot_be_swapped(self):
        self.source.write_bytes(self.source.read_bytes()+b"\n// different source\n")
        with self.assertRaises(ValueError):
            verify_routes(self.ppa)

    def test_relaxed_sdc_is_rejected(self):
        self.sdc.write_text(constraint_text("rv32i_five_stage_cpu", ("clk",), 1100, .20))
        with self.assertRaises(ValueError):
            verify_routes(self.ppa)

    def test_json_cannot_override_actual_metrics(self):
        data = json.loads(self.metrics.read_text())
        data["finish__timing__setup__ws"] = -10
        self.metrics.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            verify_routes(self.ppa)

    def test_power_at_slower_clock_is_rejected(self):
        data = json.loads(self.power.read_text())
        data["vcd_clock_period_ps"]["clk"] = 1100
        self.power.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            verify_routes(self.ppa)

    def test_another_power_workload_is_rejected(self):
        data = json.loads(self.power.read_text())
        data["workload_parameters"]["elf_sha256"] = "0"*64
        self.power.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            verify_routes(self.ppa)


class AtomicPublicationTest(unittest.TestCase):
    def test_power_units_are_exported_for_each_seed_and_the_median(self):
        record = {"per_seed": [{"power_w": value} for value in (.00582, .006, .005)]}
        add_power_fields(record)
        self.assertEqual([row["average_power_mw"] for row in record["per_seed"]], [5.819999999999999, 6, 5])
        self.assertAlmostEqual(record["average_power_mw"], 5.82)

    def test_replacement_is_complete_and_preserves_permissions(self):
        with tempfile.TemporaryDirectory(prefix="ic_bcmk_t09_publish_") as directory:
            path = Path(directory)/"record.json"
            path.write_text("old")
            path.chmod(0o664)
            publish_atomic(path, '{"new": true}\n')
            self.assertEqual(json.loads(path.read_text()), {"new": True})
            self.assertEqual(path.stat().st_mode & 0o777, 0o664)
            self.assertEqual(list(path.parent.glob(".t09_publish_*")), [])

    def test_failed_replacement_keeps_old_record_and_cleans_only_own_temp(self):
        with tempfile.TemporaryDirectory(prefix="ic_bcmk_t09_publish_") as directory:
            path = Path(directory)/"record.json"
            path.write_text("old")
            with patch("evaluator.t09_reference_freeze.os.replace", side_effect=OSError("unavailable")):
                with self.assertRaises(OSError):
                    publish_atomic(path, "new")
            self.assertEqual(path.read_text(), "old")
            self.assertEqual(list(path.parent.glob(".t09_publish_*")), [])


if __name__ == "__main__":
    unittest.main()
