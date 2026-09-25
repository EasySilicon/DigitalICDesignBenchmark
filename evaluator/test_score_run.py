import unittest

from evaluator.score_run import load_rules, score_run


class ScoreRunTest(unittest.TestCase):
    def setUp(self):
        self.rules = load_rules()
        self.groups = {group: {"cases_passed": 4, "cases_total": 4}
                       for item in self.rules["tasks"]["T01"]
                       for group in item["groups"]}
        self.payload = {"task_id": "T01", "groups": self.groups,
                        "elapsed_seconds": 900, "time_limit_seconds": 1800,
                        "delivery_qualified": True,
                        "ppa_measurement": {"routed": True, "wns_ns": 0.1,
                                            "annotation_fraction": 0.98,
                                            "area_um2": 10, "delay_ns": 1,
                                            "energy_per_op_pj": 2},
                        "ppa_reference": {"area_um2": 10, "delay_ns": 1,
                                          "energy_per_op_pj": 2}}
        provenance = {"task_id": "T01", "measurement_status": "three_seed",
                      "workload_sha256": "a" * 64,
                      "parameter_set": {"platform": "ASAP7_7p5t_RVT_NLDM",
                                        "period_ps": 2500, "corner": "WC",
                                        "utilization": 10, "density": 0.6,
                                        "seeds": [11, 29, 47]},
                      "per_seed": [{"layout_seed": seed} for seed in (11, 29, 47)]}
        self.payload["ppa_measurement"].update(provenance)
        self.payload["ppa_reference"].update(provenance)

    def test_baseline_and_time(self):
        scored = score_run(self.payload, self.rules)
        self.assertEqual(scored["functional_total"], 75)
        self.assertEqual(scored["ppa_score"], 14)
        self.assertEqual(scored["ppa_rank_bucket"], 28)
        self.assertEqual(scored["time_score"], 2.5)

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


if __name__ == "__main__":
    unittest.main()
