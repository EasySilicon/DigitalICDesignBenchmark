import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluator.score_run import (
    load_rules,
    ppa_provenance_valid,
    ppa_score,
    score_run,
    weighted_suite_score,
)


class ScoreRunTest(unittest.TestCase):
    def setUp(self):
        self.rules = load_rules()
        self.groups = {group: {"cases_passed": 4, "cases_total": 4}
                       for item in self.rules["tasks"]["T01"]
                       for group in item["groups"]}
        self.payload = {"task_id": "T01", "groups": self.groups,
                        "elapsed_seconds": 900, "time_limit_seconds": 1800,
                        "delivery_qualified": True,
                        "ppa_measurement": {"routed": True, "setup_worst_slack_ns": 0.1,
                                            "hold_worst_slack_ns": 0.05,
                                            "drc_violations": 0,
                                            "annotation_fraction": 0.98,
                                            "area_um2": 10, "delay_ns": 1,
                                            "energy_per_op_pj": 2},
                        "ppa_reference": {"area_um2": 10, "delay_ns": 1,
                                          "energy_per_op_pj": 2}}
        provenance = {"task_id": "T01", "measurement_status": "three_seed",
                      "workload_id": "T01-power-v1",
                      "workload_parameters": {"seed": 20260928},
                      "workload_sha256": "a" * 64,
                      "parameter_set": {"platform": "ASAP7_7p5t_RVT_NLDM",
                                        "period_ps": 1000, "corner": "WC",
                                        "utilization": 10, "density": 0.6,
                                        "seeds": [11, 29, 47]},
                      "per_seed": [{"layout_seed": seed, "drc_violations": 0,
                                    "setup_worst_slack_ns": 0.1,
                                    "hold_worst_slack_ns": 0.05,
                                    "annotation_fraction": 0.98,
                                    "area_um2": 10, "delay_ns": 1,
                                    "energy_per_op_pj": 2}
                                   for seed in (11, 29, 47)]}
        self.payload["ppa_measurement"].update(copy.deepcopy(provenance))
        self.payload["ppa_reference"].update(copy.deepcopy(provenance))

    def test_pending_baseline_blocks_ppa_and_time(self):
        scored = score_run(self.payload, self.rules)
        self.assertEqual(scored["functional_total"], 50)
        self.assertEqual(scored["ppa_score"], 0)
        self.assertEqual(scored["ppa_rank_bucket"], 0)
        self.assertEqual(scored["time_score"], 0)

    def test_task_weights_sum_to_one_and_mac_receives_eleven_percent(self):
        self.assertAlmostEqual(sum(self.rules["task_weights"].values()), 1.0)
        self.assertEqual(self.rules["task_weights"]["T08"], 0.11)
        self.assertEqual(self.rules["task_weights"]["T07"], 0.10)
        self.assertEqual(self.rules["task_weights"]["T06"], 0.10)

    def test_weighted_suite_score_is_not_renormalized_for_partial_results(self):
        scored = weighted_suite_score({"T01": 100, "T10": 80, "T09": None},
                                      self.rules)
        self.assertAlmostEqual(scored["weighted_display_score"], 23.0)
        self.assertAlmostEqual(scored["covered_task_weight"], 0.28)
        self.assertAlmostEqual(scored["covered_display_possible"], 29.4)

    def test_one_qualified_task_enables_ppa_before_full_suite(self):
        reference = copy.deepcopy(self.payload["ppa_reference"])
        reference["qualification_status"] = "qualified_1ghz"
        payload = copy.deepcopy(self.payload)
        payload["ppa_reference"] = reference
        with tempfile.TemporaryDirectory() as temporary:
            baseline_path = Path(temporary) / "baselines.json"
            baseline_path.write_text(json.dumps({
                "status": "partial_1ghz_qualified",
                "tasks": {"T01": reference},
            }))
            with patch("evaluator.score_run.BASELINES_PATH", baseline_path):
                scored = score_run(payload, self.rules)
        self.assertTrue(scored["ppa_eligible"])
        self.assertEqual(scored["ppa_score"], 35)
        self.assertEqual(scored["time_score"], 2.5)

    def test_candidate_delivery_error_costs_five_without_erasing_ppa_or_time(self):
        reference = copy.deepcopy(self.payload["ppa_reference"])
        reference["qualification_status"] = "qualified_1ghz"
        payload = copy.deepcopy(self.payload)
        payload.update({
            "delivery_qualified": False,
            "candidate_delivery_error_count": 1,
            "ppa_reference": reference,
        })
        with tempfile.TemporaryDirectory() as temporary:
            baseline_path = Path(temporary) / "baselines.json"
            baseline_path.write_text(json.dumps({
                "status": "partial_1ghz_qualified",
                "tasks": {"T01": reference},
            }))
            with patch("evaluator.score_run.BASELINES_PATH", baseline_path):
                scored = score_run(payload, self.rules)
        self.assertTrue(scored["ppa_eligible"])
        self.assertEqual(scored["ppa_score"], 35)
        self.assertEqual(scored["time_score"], 2.5)
        self.assertEqual(scored["candidate_delivery_penalty"], 5)
        self.assertEqual(scored["display_score_before_candidate_penalty"], 87.5)
        self.assertEqual(scored["display_score"], 82.5)

    def test_candidate_delivery_error_count_is_validated(self):
        for value in (-1, 1.5, True, "1"):
            with self.subTest(value=value), self.assertRaisesRegex(
                    ValueError, "candidate_delivery_error_count"):
                score_run(dict(self.payload, candidate_delivery_error_count=value), self.rules)

    def test_ppa_provenance_requires_common_1ghz_period(self):
        self.assertTrue(ppa_provenance_valid("T01", self.payload["ppa_measurement"],
                                             self.payload["ppa_reference"]))
        self.payload["ppa_measurement"]["parameter_set"]["period_ps"] = 500
        self.assertFalse(ppa_provenance_valid("T01", self.payload["ppa_measurement"],
                                              self.payload["ppa_reference"]))

    def test_ppa_provenance_rejects_malformed_seed_measurement(self):
        self.payload["ppa_measurement"]["per_seed"][1]["drc_violations"] = -1
        self.assertFalse(ppa_provenance_valid("T01", self.payload["ppa_measurement"],
                                              self.payload["ppa_reference"]))

    def test_t05_provenance_requires_frozen_asynchronous_clock_pair(self):
        parameter_set = {"platform": "ASAP7_7p5t_RVT_NLDM", "period_ps": 1000,
                         "corner": "WC", "utilization": 10, "density": 0.6,
                         "seeds": [11, 29, 47],
                         "clock_periods_ps": {"wr_clk": 1000, "rd_clk": 1000},
                         "asynchronous_clock_groups": [["wr_clk", "rd_clk"]]}
        measurement = dict(self.payload["ppa_measurement"], task_id="T05",
                           workload_id="T05-power-v1", parameter_set=parameter_set)
        reference = dict(self.payload["ppa_reference"], task_id="T05",
                         workload_id="T05-power-v1", parameter_set=parameter_set)
        self.assertTrue(ppa_provenance_valid("T05", measurement, reference))
        measurement["parameter_set"] = dict(parameter_set,
                                              clock_periods_ps={"wr_clk": 1000, "rd_clk": 1250})
        self.assertFalse(ppa_provenance_valid("T05", measurement, reference))

    def test_reference_ppa_formula(self):
        self.assertEqual(ppa_score(self.payload["ppa_measurement"],
                                   self.payload["ppa_reference"]), 35)

    def test_setup_violation_is_penalized_through_measured_delay(self):
        measurement = copy.deepcopy(self.payload["ppa_measurement"])
        measurement["setup_worst_slack_ns"] = -0.2
        measurement["delay_ns"] = 1.2
        for row in measurement["per_seed"]:
            row["setup_worst_slack_ns"] = -0.2
            row["delay_ns"] = 1.2
        self.assertTrue(ppa_provenance_valid(
            "T01", measurement, self.payload["ppa_reference"]
        ))
        score = ppa_score(measurement, self.payload["ppa_reference"])
        expected = 35 * (1 / 1.2) ** 0.35 * (1 / 1.2) ** 4
        self.assertAlmostEqual(score, expected)
        self.assertGreater(score, 0)
        self.assertLess(score, 35)

    def test_setup_penalty_uses_worst_slack_not_median_delay(self):
        measurement = copy.deepcopy(self.payload["ppa_measurement"])
        measurement["setup_worst_slack_ns"] = -0.1
        measurement["delay_ns"] = 0.99
        score = ppa_score(measurement, self.payload["ppa_reference"])
        base = 35 * (1 / 0.99) ** 0.35
        self.assertAlmostEqual(score, base * (1 / 1.1) ** 4)
        self.assertLess(score, base)

    def test_hold_violation_is_continuously_penalized(self):
        mild = copy.deepcopy(self.payload["ppa_measurement"])
        severe = copy.deepcopy(self.payload["ppa_measurement"])
        mild["hold_worst_slack_ns"] = -0.01
        severe["hold_worst_slack_ns"] = -0.20
        for measurement in (mild, severe):
            for row in measurement["per_seed"]:
                row["hold_worst_slack_ns"] = measurement["hold_worst_slack_ns"]
            self.assertTrue(ppa_provenance_valid(
                "T01", measurement, self.payload["ppa_reference"]
            ))
        mild_score = ppa_score(mild, self.payload["ppa_reference"])
        severe_score = ppa_score(severe, self.payload["ppa_reference"])
        self.assertGreater(mild_score, severe_score)
        self.assertGreater(severe_score, 0)

    def test_drc_violation_halves_ppa_score(self):
        measurement = copy.deepcopy(self.payload["ppa_measurement"])
        measurement["drc_violations"] = 3
        measurement["per_seed"][0]["drc_violations"] = 3
        self.assertTrue(ppa_provenance_valid(
            "T01", measurement, self.payload["ppa_reference"]
        ))
        self.assertEqual(
            ppa_score(measurement, self.payload["ppa_reference"]), 17.5
        )

    def test_drc_halves_after_ppa_cap(self):
        measurement = copy.deepcopy(self.payload["ppa_measurement"])
        measurement["area_um2"] = 5
        measurement["delay_ns"] = 0.5
        measurement["energy_per_op_pj"] = 1
        measurement["drc_violations"] = 1
        self.assertEqual(
            ppa_score(measurement, self.payload["ppa_reference"]), 25
        )

    def test_half_credit_excludes_ppa(self):
        self.groups["AC-06"]["cases_passed"] = 2
        scored = score_run(self.payload, self.rules)
        self.assertAlmostEqual(scored["functional_total"], 65 * 2 / 3)
        self.assertEqual(scored["ppa_score"], 0)
        self.assertEqual(scored["time_score"], 0)

    def test_safety_violation_gets_no_credit(self):
        self.groups["AC-06"]["cases_passed"] = 2
        self.groups["AC-06"]["safety_violation"] = True
        self.assertAlmostEqual(
            score_run(self.payload, self.rules)["functional_total"], 55 * 2 / 3)

    def test_missing_group_is_error(self):
        del self.groups["AC-08B"]
        with self.assertRaises(ValueError):
            score_run(self.payload, self.rules)

    def test_invalid_route_gets_no_ppa_or_time(self):
        self.payload["ppa_measurement"]["routed"] = False
        scored = score_run(self.payload, self.rules)
        self.assertEqual(scored["ppa_score"], 0)
        self.assertEqual(scored["time_score"], 0)

    def test_unrouted_measurement_gets_no_ppa(self):
        self.payload["ppa_measurement"]["routed"] = False
        self.assertEqual(score_run(self.payload, self.rules)["ppa_score"], 0)

    def test_pilot_or_mismatched_workload_contract_gets_no_ppa(self):
        self.payload["ppa_measurement"]["measurement_status"] = "pilot"
        self.assertEqual(score_run(self.payload, self.rules)["ppa_score"], 0)
        self.payload["ppa_measurement"]["measurement_status"] = "three_seed"
        self.payload["ppa_measurement"]["workload_id"] = "T01-power-v2"
        self.assertEqual(score_run(self.payload, self.rules)["ppa_score"], 0)

    def test_probe_maintenance_hash_change_keeps_same_workload_contract(self):
        self.payload["ppa_measurement"]["workload_sha256"] = "b" * 64
        self.assertTrue(ppa_provenance_valid(
            "T01", self.payload["ppa_measurement"], self.payload["ppa_reference"]))

    def test_workload_parameter_change_is_rejected(self):
        self.payload["ppa_measurement"]["workload_parameters"]["seed"] += 1
        self.assertFalse(ppa_provenance_valid(
            "T01", self.payload["ppa_measurement"], self.payload["ppa_reference"]))

    def test_groups_have_equal_weight_in_half_credit(self):
        groups = {group: {"cases_passed": 1, "cases_total": 1}
                  for item in self.rules["tasks"]["T09"] for group in item["groups"]}
        groups["CPU-DIR-INT"] = {"cases_passed": 0, "cases_total": 1}
        groups["CPU-DIFF-INT"] = {"cases_passed": 100, "cases_total": 100}
        groups["CPU-PIPE-CYCLES"] = {"cases_passed": 22, "cases_total": 22}
        payload = dict(self.payload, task_id="T09", groups=groups)
        scored = score_run(payload, self.rules)
        item = next(x for x in scored["score_items"] if x["id"] == "F_INTEGER_CONTROL")
        self.assertAlmostEqual(item["points"], 10 * 2 / 3)

    def t09_payload(self):
        groups = {group: {"cases_passed": 4, "cases_total": 4}
                  for item in self.rules["tasks"]["T09"] for group in item["groups"]}
        groups["CPU-PIPE-CYCLES"] = {"cases_passed": 22, "cases_total": 22}
        baseline_path = Path(__file__).resolve().parents[1]/"benchmark/ppa-baselines.json"
        reference = json.loads(baseline_path.read_text())["tasks"]["T09"]
        return dict(self.payload, task_id="T09", groups=groups,
                    ppa_reference=reference, ppa_measurement=copy.deepcopy(reference))

    def test_t09_cycle_group_scores_ten_five_zero(self):
        for passed, cycle_points, total in ((22, 10, 50), (21, 5, 45),
                                            (11, 5, 45), (10, 0, 40), (0, 0, 40)):
            payload = self.t09_payload()
            payload["groups"]["CPU-PIPE-CYCLES"]["cases_passed"] = passed
            scored = score_run(payload, self.rules)
            item = next(row for row in scored["score_items"] if row["id"] == "P_CYCLES")
            with self.subTest(passed=passed):
                self.assertEqual(item["points"], cycle_points)
                self.assertAlmostEqual(scored["functional_total"], total)
                self.assertEqual(scored["full_functional_pass"], passed == 22)
                if passed != 22:
                    self.assertFalse(scored["ppa_eligible"])
                    self.assertEqual(scored["ppa_score"], 0)
                    self.assertEqual(scored["time_score"], 0)
                else:
                    self.assertTrue(scored["ppa_eligible"])
                    self.assertAlmostEqual(scored["ppa_score"], 35)

    def test_any_single_cycle_failure_costs_five_not_five_per_case(self):
        from evaluator.t09_timing_check import apply_timing_groups, case_inventory
        names = ["continuous_addi", *(row[0] for row in case_inventory())]
        for failed in names:
            payload = self.t09_payload()
            report = {"phase": "run", "outcomes": [
                {"name": name, "passed": name != failed} for name in names]}
            apply_timing_groups(payload["groups"], report)
            with self.subTest(failed=failed):
                self.assertAlmostEqual(score_run(payload, self.rules)["functional_total"], 45)

    def test_t09_cycle_inventory_missing_or_wrong_count_rejected(self):
        for count in (1, 21, 23):
            payload = self.t09_payload()
            payload["groups"]["CPU-PIPE-CYCLES"] = {"cases_passed": count, "cases_total": count}
            with self.subTest(count=count), self.assertRaises(ValueError):
                score_run(payload, self.rules)
        payload = self.t09_payload()
        payload["groups"].pop("CPU-PIPE-CYCLES")
        with self.assertRaises(ValueError):
            score_run(payload, self.rules)

    def test_t09_other_groups_keep_old_scoring_after_proportional_resize(self):
        payload = self.t09_payload()
        payload["groups"]["CPU-DIR-INT"]["cases_passed"] = 3
        scored = score_run(payload, self.rules)
        self.assertAlmostEqual(scored["functional_total"], 50-20/3)
        cycles = next(row for row in scored["score_items"] if row["id"] == "P_CYCLES")
        self.assertEqual(cycles["points"], 10)

    def test_t01_qualified_groups_normalize_to_40_plus_10(self):
        counts = {"AC-05": 20, "AC-06": 8, "AC-07": 10,
                  "AC-08A": 8, "AC-08B": 6}
        groups = {group: {"cases_passed": count, "cases_total": count,
                          "safety_violation": False}
                  for group, count in counts.items()}
        scored = score_run(dict(self.payload, task_id="T01", groups=groups,
                                time_limit_seconds=5400), self.rules)
        self.assertEqual(scored["functional_basic"], 40)
        self.assertEqual(scored["functional_edges"], 10)
        self.assertTrue(scored["full_functional_pass"])

    def test_t10_pending_baseline_reports_function_but_blocks_ppa_and_time(self):
        groups = {group: {"cases_passed": 1, "cases_total": 1}
                  for item in self.rules["tasks"]["T10"] for group in item["groups"]}
        scored = score_run(dict(self.payload, task_id="T10", groups=groups,
                                sustained_throughput_passed=True), self.rules)
        self.assertEqual(scored["functional_total"], 50)
        self.assertTrue(scored["full_functional_pass"])
        self.assertFalse(scored["ppa_eligible"])
        self.assertEqual(scored["ppa_score"], 0)
        self.assertEqual(scored["time_score"], 0)

    def test_t10_sustained_gate_is_required_and_zeroes_systolic_item(self):
        groups = {group: {"cases_passed": 1, "cases_total": 1}
                  for item in self.rules["tasks"]["T10"] for group in item["groups"]}
        payload = dict(self.payload, task_id="T10", groups=groups)
        with self.assertRaisesRegex(ValueError, "sustained_throughput_passed"):
            score_run(payload, self.rules)
        scored = score_run(dict(payload, sustained_throughput_passed=False), self.rules)
        self.assertAlmostEqual(scored["functional_total"], 70 * 2 / 3)
        self.assertFalse(scored["full_functional_pass"])
        item = next(row for row in scored["score_items"] if row["id"] == "P_SYSTOLIC")
        self.assertEqual(item["points"], 0)
        self.assertTrue(item["safety_violation"])

    def test_t10_qualified_baseline_enables_official_ppa_and_time(self):
        groups = {group: {"cases_passed": 1, "cases_total": 1}
                  for item in self.rules["tasks"]["T10"] for group in item["groups"]}
        measurement = copy.deepcopy(self.payload["ppa_measurement"])
        reference = copy.deepcopy(self.payload["ppa_reference"])
        measurement["task_id"] = "T10"
        reference["task_id"] = "T10"
        measurement["workload_id"] = "T10-power-v1"
        reference["workload_id"] = "T10-power-v1"
        reference["qualification_status"] = "qualified_1ghz"
        payload = dict(self.payload, task_id="T10", groups=groups,
                       sustained_throughput_passed=True,
                       ppa_measurement=measurement, ppa_reference=reference,
                       elapsed_seconds=86400, time_limit_seconds=172800)
        with tempfile.TemporaryDirectory() as temporary:
            baseline_path = Path(temporary) / "baselines.json"
            baseline_path.write_text(json.dumps({
                "status": "partial_1ghz_qualified",
                "tasks": {"T10": reference},
            }))
            with patch("evaluator.score_run.BASELINES_PATH", baseline_path):
                scored = score_run(payload, self.rules)
        self.assertTrue(scored["ppa_eligible"])
        self.assertEqual(scored["ppa_score"], 35)
        self.assertEqual(scored["time_score"], 2.5)


if __name__ == "__main__":
    unittest.main()
