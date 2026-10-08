"""Regression checks for T10 hidden MX overflow and cancellation vectors."""

import unittest
from copy import deepcopy
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from runner_t10 import GROUP_COUNTS, WIDTH, generate_cases, parse_output
from runner_t10_stream import compile_hierarchical, stream_cases, functional_passed
from matmul_oracle import MAX_F32, dot_terms, expected_dot
from grade_t10_pilot import summarize
from score_run import load_rules
from t10_structure_check import _paths
from t10_fast_oracle import check_output_fast
from runner_t10 import check_output
from make_t10_power_vectors import generate as generate_power_cases
from t10_mutation_regression import MUTATIONS, materialize


class T10ScaleGenerationTest(unittest.TestCase):
    def test_completed_simulation_is_not_sufficient_for_functional_pass(self) -> None:
        report = {"phase": "run", "cases": 2752,
                  "structure": {"passed": True}, "reset_probe_passed": True,
                  "groups": {group: {"cases_passed": count, "cases_total": count}
                             for group, count in GROUP_COUNTS.items()},
                  "failures": [],
                  "stream_line": "MM_STREAM input_bubble_phases=00000000000000 finished=2752"}
        self.assertTrue(functional_passed(report))
        wrong_numeric = deepcopy(report)
        wrong_numeric["groups"]["MM-MX8"]["cases_passed"] -= 1
        wrong_reset = deepcopy(report)
        wrong_reset["reset_probe_passed"] = False
        partial = deepcopy(report)
        partial["stream_line"] = "MM_STREAM input_bubble_phases=00000000000000 finished=2751"
        bubble = deepcopy(report)
        bubble["stream_line"] = "MM_STREAM input_bubble_phases=00000000000001 finished=2752"
        structure = deepcopy(report)
        structure["structure"]["passed"] = False
        for rejected in (wrong_numeric, wrong_reset, partial, bubble, structure):
            self.assertFalse(functional_passed(rejected), rejected)

    def test_scaled_functional_points_do_not_fail_full_score_gate(self) -> None:
        functional = {"groups": {"MM-SYSTOLIC": {"cases_passed": 1, "cases_total": 1}},
                      "phase": "run", "cases": 1, "structure": {"passed": True},
                      "stream_line": "MM_STREAM input_bubble_phases=00000000000000 finished=1"}
        with patch("grade_t10_pilot.load_rules", return_value={"functional_total": 50}), \
             patch("grade_t10_pilot.score_functional", return_value=(40.0, 9.999999999999993, [])):
            report = summarize({"delivery_qualified": True}, functional)
        self.assertEqual(report["functional_total"], 50.0)
        self.assertEqual(report["functional_possible"], 50)
        self.assertIsNone(report["ppa_score"])
        self.assertFalse(report["official_score_eligible"])

    def test_complemented_a_forward_mutation_materializes(self) -> None:
        mutation = next(row for row in MUTATIONS if row.name == "broken_a_forward")
        source = "always_ff @(posedge clk) a_out_n <= ~a_in;\n"
        with tempfile.TemporaryDirectory() as temp:
            submission = materialize(mutation, source, Path(temp), "reference.sv")
            mutated = (submission / "rtl" / "reference.sv").read_text()
        self.assertIn("a_out_n <= ~b_in;", mutated)
        self.assertNotIn("a_out_n <= ~a_in;", mutated)

    def test_hierarchical_compile_retries_empty_verilator_trace_macro(self) -> None:
        command = ["verilator", "--binary", "--hierarchical", "--timing",
                   "--Mdir", "/tmp/t10_build", "source.sv"]
        first = subprocess.CompletedProcess(command, 1, "-DVM_TRACE=\n",
                                            "error: #if with no expression")
        second = subprocess.CompletedProcess(command, 0, "compiled", "")
        with patch("runner_t10_stream.subprocess.run", side_effect=[first, second]) as run:
            result, build, transcript = compile_hierarchical(command, Path("/tmp/t10_build"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(build, Path("/tmp/t10_build_trace"))
        self.assertIn("--trace", run.call_args_list[1].args[0])
        self.assertIn("VERILATOR_EMPTY_VM_TRACE_RETRY", transcript)

    def test_automatic_mesh_topology(self) -> None:
        horizontal = {16 * row + col: 16 * row + col + 1
                      for row in range(16) for col in range(15)}
        self.assertEqual(len(_paths(horizontal)), 16)
        horizontal.pop(0)
        self.assertIsNone(_paths(horizontal))

    def test_automatic_structure_group_scores_without_review(self) -> None:
        groups = {group: {"cases_passed": count,
                          "cases_total": count}
                  for group, count in GROUP_COUNTS.items()}
        report = summarize({"delivery_qualified": True},
                           {"groups": groups, "phase": "run", "cases": 2624,
                            "stream_line": "MM_STREAM input_bubble_phases=00000000000000 finished=2624",
                            "structure": {"passed": True, "status": "qualified",
                                          "method": "yosys_netlist"}})
        self.assertAlmostEqual(report["functional_total"], load_rules()["functional_total"])
        self.assertTrue(report["sustained_throughput_passed"])
        systolic = next(item for item in report["score_items"]
                        if item["id"] == "P_SYSTOLIC")
        self.assertEqual(systolic["points"], systolic["possible_points"])

    def test_sustained_throughput_is_a_hard_eligibility_gate(self) -> None:
        groups = {group: {"cases_passed": count, "cases_total": count}
                  for group, count in GROUP_COUNTS.items()}
        report = summarize({"delivery_qualified": True},
                           {"groups": groups, "phase": "run", "cases": 2624,
                            "stream_line": "MM_STREAM input_bubble_phases=00000000000001 finished=2624",
                            "structure": {"passed": True}})
        self.assertAlmostEqual(report["functional_total"], load_rules()["functional_total"])
        self.assertFalse(report["sustained_throughput_passed"])
        self.assertEqual(report["ppa_score"], 0)
        self.assertEqual(report["time_score"], 0)

    def test_extreme_scales_cover_mixed_sign_cases(self) -> None:
        cases = generate_cases(20260925)
        counts = {0: 0, 254: 0, 255: 0}
        dense_extreme = 0
        for group in ("MM-MX8", "MM-MX4", "MM-CORNER"):
            subset = [case for case in cases if case.group == group]
            for index, case in enumerate(subset):
                if case.mode not in (7, 8, 9):
                    continue
                for bus in (case.a_scale, case.b_scale):
                    scales = [(bus >> (8 * block)) & 255 for block in range(32)]
                    for code in counts:
                        counts[code] += scales.count(code)
                    if index % 8 in (5, 6) and 254 in scales:
                        dense_extreme += 1
        for code in counts:
            self.assertGreater(counts[code], 0, code)
        self.assertGreater(dense_extreme, 0)

    def test_exact_dot_after_opposite_signed_term_overflow(self) -> None:
        case = generate_cases(20260925)[569]
        self.assertEqual((case.group, case.mode), ("MM-MX8", 8))
        terms = dot_terms(list(case.a), list(case.b), case.a_scale,
                          case.b_scale, case.mode, 1, 14)
        self.assertTrue(any(term > MAX_F32 for term in terms))
        self.assertTrue(any(term < -MAX_F32 for term in terms))
        self.assertEqual(expected_dot(terms)[0], "finite")

    def test_directed_mx_extremes(self) -> None:
        cases = generate_cases(20260925)
        for index in (568, 569, 664):
            case = cases[index]
            terms = dot_terms(list(case.a), list(case.b), case.a_scale,
                              case.b_scale, case.mode, 3, 4)
            self.assertTrue(any(term > MAX_F32 for term in terms))
            self.assertTrue(any(term < -MAX_F32 for term in terms))
            self.assertEqual(expected_dot(terms)[:2], ("finite", 1))
        for index in (570, 571, 665):
            case = cases[index]
            even = dot_terms(list(case.a), list(case.b), case.a_scale,
                             case.b_scale, case.mode, 0, 0)
            odd = dot_terms(list(case.a), list(case.b), case.a_scale,
                            case.b_scale, case.mode, 1, 0)
            self.assertEqual(expected_dot(even)[0], "finite")
            self.assertEqual(expected_dot(odd)[0], "+inf")
        case = cases[949]
        self.assertEqual(case.mode, 8)
        terms = dot_terms(list(case.a), list(case.b), case.a_scale,
                          case.b_scale, case.mode, 0, 0)
        self.assertEqual(expected_dot(terms)[0], "-inf")

    def test_protocol_group_also_requires_correct_data(self) -> None:
        case = generate_cases(20260925)[672]
        self.assertEqual(case.group, "MM-PROTO")
        log = "MM_CASE 0 1 1 1 16\n" + "".join(
            f"MM_ROW 0 {row} {0:0256x}\n" for row in range(16))
        with patch("runner_t10.check_output", return_value=["wrong C[0][0]"]):
            groups, _ = parse_output(log, [case], {"passed": True})
        self.assertEqual(groups["MM-PROTO"]["cases_passed"], 0)

    def test_stream_campaign_has_required_long_trains_and_backpressure(self) -> None:
        cases, phases = stream_cases(20260925)
        self.assertEqual(len(cases), 2752)
        self.assertEqual(len(phases), len(cases))
        self.assertEqual(phases.count(0), 960)
        self.assertEqual(phases.count(11), 128)
        self.assertEqual(phases.count(12), 512)
        self.assertEqual(phases.count(13), 128)
        fp4_stall = [case for case, phase in zip(cases, phases) if phase == 13]
        self.assertEqual({case.mode for case in fp4_stall}, {9})
        self.assertNotEqual(fp4_stall[0].a[0] & 15,
                            (fp4_stall[0].a[0] >> (4*64)) & 15)
        self.assertNotEqual(fp4_stall[0].b[0] & 15,
                            (fp4_stall[0].b[0] >> 64) & 15)
        mixed = [case for case, phase in zip(cases, phases) if phase == 12]
        self.assertEqual([case.mode for case in mixed[:4]], [6, 2, 9, 1])
        self.assertEqual({case.mode for case in mixed}, set(range(10)))
        for mode in range(10):
            self.assertEqual(phases.count(mode + 1),
                             256 if mode in (6, 9) else 64)
            self.assertEqual({cases[i].mode for i, p in enumerate(phases)
                              if p == mode + 1}, {mode})

    def test_stream_timing_failure_invalidates_protocol_case(self) -> None:
        case = next(case for case in generate_cases(20260925)
                    if case.group == "MM-PROTO")
        log = "MM_CASE 0 1 0 1 16\n" + "".join(
            f"MM_ROW 0 {row} {0:0256x}\n" for row in range(16))
        with patch("runner_t10.check_output", return_value=[]):
            groups, _ = parse_output(log, [case], {"passed": True},
                                     require_timing=True)
        self.assertEqual(groups["MM-PROTO"]["cases_passed"], 0)

    def test_partial_stream_report_survives_late_fatal(self) -> None:
        case = generate_cases(20260925)[0]
        log = "MM_CASE 0 1 1 1 16\n" + "".join(
            f"MM_ROW 0 {row} {0:0256x}\n" for row in range(16))
        log += "MM_STREAM input_bubble_phases=00000000000000 finished=1\n"
        log += "%Fatal: pre-backpressure phase did not drain\n"
        with patch("runner_t10.check_output", return_value=[]):
            groups, failures = parse_output(log, [case], {"passed": True},
                                             require_timing=True)
        self.assertEqual(groups["MM-INT"]["cases_passed"], 1)
        self.assertEqual(failures, [])

    def test_stream_testbench_reports_before_candidate_fatals(self) -> None:
        testbench = (Path(__file__).parent / "hidden" /
                     "tb_hidden_T10_stream.sv").read_text()
        for message in ("invalid block start", "missing in_start at block boundary",
                        "unknown output tag", "input deadlock",
                        "pre-backpressure phase did not drain"):
            report = testbench.index(f'emit_report("{message}")')
            fatal = testbench.index(f'$fatal(1,"{message}', report)
            self.assertLess(report, fatal, message)

    def test_power_workload_samples_steady_state_for_every_mode(self) -> None:
        cases, phases = generate_power_cases(20260925)
        self.assertEqual(len(cases), 200)
        self.assertEqual(phases.count(11), 32)
        for mode in range(10):
            selected = [case for case, phase in zip(cases, phases)
                        if phase == mode + 1]
            self.assertEqual(len(selected) * WIDTH[mode], 128)
            self.assertEqual({case.mode for case in selected}, {mode})

    def test_power_workload_all_output_points_are_finite(self) -> None:
        cases, _ = generate_power_cases(20260925)
        for case_index, case in enumerate(cases):
            for row in range(16):
                for col in range(16):
                    kind, _, _ = expected_dot(dot_terms(
                        list(case.a), list(case.b), case.a_scale,
                        case.b_scale, case.mode, row, col))
                    self.assertEqual(kind, "finite",
                                     (case_index, case.mode, row, col))

    def test_pilot_compile_failure_is_reported_without_scoring(self) -> None:
        report = summarize({"delivery_qualified": True},
                           {"phase": "compile-failed", "structure": {"passed": False}})
        self.assertEqual(report["functional_total"], 0)
        self.assertEqual(report["phase"], "compile-failed")

    def test_fast_exact_oracle_matches_fraction_oracle(self) -> None:
        cases = generate_cases(20260925)
        for index in (0, 128, 135, 256, 263, 384, 455, 512, 576, 583,
                      672, 679, 832, 949):
            case = cases[index]
            rows = [0] * 16
            args = (list(case.a), list(case.b), case.a_scale,
                    case.b_scale, case.mode, rows)
            slow = check_output(*args)
            fast = check_output_fast(*args)
            self.assertEqual({error.split(":")[0] for error in slow},
                             {error.split(":")[0] for error in fast}, index)


if __name__ == "__main__":
    unittest.main()
