"""Port timing checker regressions; enable RTL probes with T09_TIMING_RTL_TESTS=1."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from evaluator.t09_timing_check import (
    PC, addi, apply_timing_groups, case_inventory, check_continuous, compare_pair,
    decode_trace, oracle, program, run, validate_trace,
)


class TimingCheckerTest(unittest.TestCase):
    def test_inventory_is_fixed_and_unique(self):
        names = [row[0] for row in case_inventory()]
        self.assertEqual(len(names), 21)
        self.assertEqual(len(set(names)), 21)
        self.assertEqual(sum(name.startswith("load_") for name in names), 15)

    def trace(self, spacing=1, delay=4):
        return [{"kind": "fetch", "pc": PC+4*i, "cycle": spacing*i} for i in range(64)] + \
            [{"kind": "commit", "pc": PC+4*i, "cycle": spacing*i+delay} for i in range(64)]

    def test_continuous_stream_passes(self):
        self.assertEqual(check_continuous(self.trace())["steady_state_ipc"], 1.0)

    def test_throttled_four_cycle_latency_stream_fails(self):
        with self.assertRaisesRegex(ValueError, "bubble"):
            check_continuous(self.trace(spacing=2))

    def test_early_and_late_commits_fail(self):
        for delay in (3, 5):
            with self.subTest(delay=delay), self.assertRaisesRegex(ValueError, "four cycles"):
                check_continuous(self.trace(delay=delay))

    def test_missing_commit_and_duplicate_fetch_fail(self):
        with self.assertRaises(ValueError):
            check_continuous(self.trace()[:-1])
        rows = self.trace()
        rows[1]["pc"] = PC
        with self.assertRaises(ValueError):
            check_continuous(rows)

    def metrics(self, gap, span):
        return {"commit_cycles": {str(PC): 10, str(PC+4): 10+gap},
                "retirement_span_cycles": span}

    def test_one_load_dependency_bubble_passes(self):
        row = compare_pair(self.metrics(1, 19), self.metrics(2, 20), PC, PC+4, 1, 19)
        self.assertTrue(row["passed"])

    def test_two_dependency_bubbles_fail(self):
        row = compare_pair(self.metrics(1, 19), self.metrics(3, 21), PC, PC+4, 1, 19)
        self.assertFalse(row["dependency_penalty_passed"])

    def test_registered_alu_forwarding_bubble_fails(self):
        self.assertFalse(compare_pair(self.metrics(1, 18), self.metrics(2, 19), PC, PC+4, 0, 18)["passed"])

    def test_common_avoidable_stalls_do_not_cancel(self):
        row = compare_pair(self.metrics(2, 23), self.metrics(3, 24), PC, PC+4, 1, 19)
        self.assertTrue(row["dependency_penalty_passed"])
        self.assertFalse(row["workload_budget_passed"])
        self.assertFalse(row["passed"])

    def test_hiding_bubble_by_delaying_producer_does_not_pass(self):
        row = compare_pair(self.metrics(1, 19), self.metrics(2, 22), PC, PC+4, 1)
        self.assertFalse(row["passed"])

    def test_load_memory_and_branch_oracles(self):
        for kind in ("load_rs1", "load_rs2", "load_both", "load_store", "load_branch"):
            for dependent in (False, True):
                code, producer, consumer = program(kind, dependent)
                rows = oracle(code)
                self.assertEqual(next(row for row in rows if row["pc"] == producer)["data"], 0x12345678)
                use = next(row for row in rows if row["pc"] == consumer)
                if kind == "load_store":
                    self.assertEqual(use["mem_data"], 0x12345678 if dependent else 11)
                elif kind == "load_branch":
                    self.assertNotIn(consumer+4, [row["pc"] for row in rows])
                elif kind == "load_both":
                    self.assertEqual(use["data"], 0x2468acf0 if dependent else 22)
                else:
                    self.assertEqual(use["data"], 0x12345683 if dependent else 22)

    def test_correct_cycle_count_cannot_hide_wrong_commit(self):
        code = [addi(1, 0, 1)]
        rows = [{"kind": "commit", "cycle": 4, **oracle(code)[0]},
                {"kind": "done", "memory_104": 0}]
        validate_trace(code, rows, 1)
        rows[0]["data"] = 2
        with self.assertRaisesRegex(ValueError, "data"):
            validate_trace(code, rows, 1)

    def test_missing_or_duplicate_memory_transactions_fail(self):
        code, _, _ = program("load_rs1", True)
        commits = [{"kind": "commit", "cycle": i, **row} for i, row in enumerate(oracle(code))]
        done = {"kind": "done", "memory_104": 0}
        with self.assertRaisesRegex(ValueError, "request/response"):
            validate_trace(code, [*commits, done], 1)

    def test_trace_hex_fields_decode(self):
        row = decode_trace('noise\nTIMING {"kind":"commit","pc":"80000000","data":"12345678"}\n')[0]
        self.assertEqual(row["pc"], PC)
        self.assertEqual(row["data"], 0x12345678)

    def report(self):
        return {"phase": "run", "outcomes": [{"name": name, "passed": True}
                    for name in ["continuous_addi", *(row[0] for row in case_inventory())]]}

    def groups(self):
        return {"CPU-PIPE-LAT": {"cases_passed": 64, "cases_total": 64},
                "CPU-PIPE-HAZ": {"cases_passed": 8, "cases_total": 8}}

    def test_cycle_checks_get_separate_group_without_double_debit(self):
        groups, report = self.groups(), self.report()
        report["outcomes"][1]["passed"] = False
        apply_timing_groups(groups, report)
        self.assertEqual(groups["CPU-PIPE-CYCLES"], {"cases_passed": 21, "cases_total": 22})
        self.assertEqual(groups["CPU-PIPE-HAZ"], {"cases_passed": 8, "cases_total": 8})
        self.assertEqual(groups["CPU-PIPE-LAT"]["cases_passed"], 64)

    def test_throughput_failure_only_debits_cycle_group(self):
        groups, report = self.groups(), self.report()
        report["outcomes"][0]["passed"] = False
        apply_timing_groups(groups, report)
        self.assertEqual(groups["CPU-PIPE-CYCLES"], {"cases_passed": 21, "cases_total": 22})
        self.assertEqual(groups["CPU-PIPE-LAT"]["cases_passed"], 64)

    def test_non_boolean_outcome_cannot_be_scored_as_pass(self):
        for value in (1, 0, "false", None):
            report = self.report()
            report["outcomes"][0]["passed"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                apply_timing_groups(self.groups(), report)

    def test_missing_duplicate_or_changed_inventory_rejected(self):
        for mode in ("missing", "duplicate", "changed"):
            report = self.report()
            if mode == "missing":
                report["outcomes"].pop()
            elif mode == "duplicate":
                report["outcomes"][-1] = report["outcomes"][0]
            else:
                report["outcomes"][-1]["name"] = "unknown"
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                apply_timing_groups(self.groups(), report)


@unittest.skipUnless(os.environ.get("T09_TIMING_RTL_TESTS") == "1", "opt-in Verilator regression")
class RtlTimingRegressionTest(unittest.TestCase):
    def test_current_reference_and_two_bubble_load_mutation(self):
        reference = Path(__file__).resolve().parent/"reference/T09"
        result = run(reference)
        loads = [row for row in result["outcomes"] if row["name"].startswith("load_")]
        self.assertEqual(len(loads), 15)
        self.assertTrue(all(row["dependency_penalty_passed"] for row in loads))
        self.assertEqual(result["cases_passed"], 22)
        with tempfile.TemporaryDirectory(prefix="ic_bcmk_t09_timing_mutant_") as directory:
            candidate = Path(directory)
            shutil.copytree(reference/"rtl", candidate/"rtl")
            path = candidate/"rtl/ref.sv"
            source = path.read_text()
            for old, new in (
                ("logic load_dependency_stall, execute_start, pipeline_advance;",
                 "logic load_dependency_stall, execute_start, pipeline_advance;\n  logic timing_extra_hold;"),
                ("!memory_error && !load_dependency_stall && !trap_redirect;",
                 "!memory_error && !load_dependency_stall && !trap_redirect && !timing_extra_hold;"),
                ("mem_accepted <= 0;\n      ex_forward1 <= 0;",
                 "mem_accepted <= 0;\n      timing_extra_hold <= 0;\n      ex_forward1 <= 0;"),
                ("memwb <= '0;\n      if (hold_memory)",
                 "memwb <= '0;\n      timing_extra_hold <= memory_done && load_dependency_stall;\n      if (hold_memory)"),
            ):
                self.assertEqual(source.count(old), 1, old)
                source = source.replace(old, new)
            path.write_text(source)
            mutated = run(candidate)
            mutant_loads = [row for row in mutated["outcomes"] if row["name"].startswith("load_")]
            self.assertEqual(mutated["phase"], "run")
            self.assertTrue(all("error" not in row for row in mutant_loads))
            self.assertTrue(all(not row["dependency_penalty_passed"] for row in mutant_loads))


if __name__ == "__main__":
    unittest.main()
