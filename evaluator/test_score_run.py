import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluator.score_run import load_rules, ppa_provenance_valid, ppa_score, score_run


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
        self.payload["ppa_measurement"].update(provenance)
        self.payload["ppa_reference"].update(provenance)

    def test_pending_baseline_blocks_ppa_and_time(self):
        scored = score_run(self.payload, self.rules)
        self.assertEqual(scored["functional_total"], 75)
        self.assertEqual(scored["ppa_score"], 0)
        self.assertEqual(scored["ppa_rank_bucket"], 0)
        self.assertEqual(scored["time_score"], 0)

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
        self.assertEqual(scored["ppa_score"], 14)
        self.assertEqual(scored["time_score"], 2.5)

    def test_ppa_provenance_requires_common_1ghz_period(self):
        self.assertTrue(ppa_provenance_valid("T01", self.payload["ppa_measurement"],
                                             self.payload["ppa_reference"]))
        self.payload["ppa_measurement"]["parameter_set"]["period_ps"] = 500
        self.assertFalse(ppa_provenance_valid("T01", self.payload["ppa_measurement"],
                                              self.payload["ppa_reference"]))

    def test_ppa_provenance_rejects_bad_seed_measurement(self):
        self.payload["ppa_measurement"]["per_seed"][1]["drc_violations"] = 1
        self.assertFalse(ppa_provenance_valid("T01", self.payload["ppa_measurement"],
                                              self.payload["ppa_reference"]))

    def test_t06_provenance_requires_frozen_asynchronous_clock_pair(self):
        parameter_set = {"platform": "ASAP7_7p5t_RVT_NLDM", "period_ps": 1000,
                         "corner": "WC", "utilization": 10, "density": 0.6,
                         "seeds": [11, 29, 47],
                         "clock_periods_ps": {"wr_clk": 1000, "rd_clk": 1000},
                         "asynchronous_clock_groups": [["wr_clk", "rd_clk"]]}
        measurement = dict(self.payload["ppa_measurement"], task_id="T06",
                           parameter_set=parameter_set)
        reference = dict(self.payload["ppa_reference"], task_id="T06",
                         parameter_set=parameter_set)
        self.assertTrue(ppa_provenance_valid("T06", measurement, reference))
        measurement["parameter_set"] = dict(parameter_set,
                                              clock_periods_ps={"wr_clk": 1000, "rd_clk": 1250})
        self.assertFalse(ppa_provenance_valid("T06", measurement, reference))

    def test_reference_ppa_formula(self):
        self.assertEqual(ppa_score(self.payload["ppa_measurement"],
                                   self.payload["ppa_reference"]), 14)

    def test_half_credit_excludes_ppa(self):
        self.groups["AC-02"]["cases_passed"] = 2
        scored = score_run(self.payload, self.rules)
        self.assertEqual(scored["functional_total"], 55)
        self.assertEqual(scored["ppa_score"], 0)
        self.assertEqual(scored["time_score"], 0)

    def test_safety_violation_gets_no_credit(self):
        self.groups["AC-02"]["cases_passed"] = 2
        self.groups["AC-02"]["safety_violation"] = True
        self.assertEqual(score_run(self.payload, self.rules)["functional_total"], 35)

    def test_missing_group_is_error(self):
        del self.groups["AC-04"]
        with self.assertRaises(ValueError):
            score_run(self.payload, self.rules)

    def test_invalid_route_gets_no_ppa_or_time(self):
        self.payload["ppa_measurement"]["routed"] = False
        scored = score_run(self.payload, self.rules)
        self.assertEqual(scored["ppa_score"], 0)
        self.assertEqual(scored["time_score"], 0)

    def test_route_or_hold_violation_gets_no_ppa(self):
        self.payload["ppa_measurement"]["drc_violations"] = 1
        self.assertEqual(score_run(self.payload, self.rules)["ppa_score"], 0)
        self.payload["ppa_measurement"]["drc_violations"] = 0
        self.payload["ppa_measurement"]["hold_worst_slack_ns"] = -0.001
        self.assertEqual(score_run(self.payload, self.rules)["ppa_score"], 0)

    def test_pilot_or_mismatched_workload_gets_no_ppa(self):
        self.payload["ppa_measurement"]["measurement_status"] = "pilot"
        self.assertEqual(score_run(self.payload, self.rules)["ppa_score"], 0)
        self.payload["ppa_measurement"]["measurement_status"] = "three_seed"
        self.payload["ppa_measurement"]["workload_sha256"] = "b" * 64
        self.assertEqual(score_run(self.payload, self.rules)["ppa_score"], 0)

    def test_groups_have_equal_weight_in_half_credit(self):
        groups = {group: {"cases_passed": 1, "cases_total": 1}
                  for item in self.rules["tasks"]["T09"] for group in item["groups"]}
        groups["CPU-DIR-INT"] = {"cases_passed": 0, "cases_total": 1}
        groups["CPU-DIFF-INT"] = {"cases_passed": 100, "cases_total": 100}
        payload = dict(self.payload, task_id="T09", groups=groups)
        scored = score_run(payload, self.rules)
        item = next(x for x in scored["score_items"] if x["id"] == "F_INTEGER_CONTROL")
        self.assertEqual(item["points"], 12.5)

    def test_t02_qualified_groups_score_60_plus_15(self):
        counts = {"AC-05": 20, "AC-06": 8, "AC-07": 10,
                  "AC-08A": 8, "AC-08B": 6}
        groups = {group: {"cases_passed": count, "cases_total": count,
                          "safety_violation": False}
                  for group, count in counts.items()}
        scored = score_run(dict(self.payload, task_id="T02", groups=groups,
                                time_limit_seconds=5400), self.rules)
        self.assertEqual(scored["functional_basic"], 60)
        self.assertEqual(scored["functional_edges"], 15)
        self.assertTrue(scored["full_functional_pass"])

    def test_t10_cannot_receive_formal_score_before_qualification(self):
        groups = {group: {"cases_passed": 1, "cases_total": 1}
                  for item in self.rules["tasks"]["T10"] for group in item["groups"]}
        with self.assertRaisesRegex(ValueError, "design-only"):
            score_run(dict(self.payload, task_id="T10", groups=groups), self.rules)


if __name__ == "__main__":
    unittest.main()
