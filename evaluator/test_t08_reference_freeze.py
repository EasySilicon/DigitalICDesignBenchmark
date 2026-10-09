import copy
import unittest

from t08_reference_freeze import freeze_gate


class FreezeGateTest(unittest.TestCase):
    def setUp(self):
        self.functional = {"full_functional_pass": True, "functional_total": 50,
                           "cases": {str(index): {"runs": [{"passed": True}] * 3}
                                     for index in range(37)}}
        self.stress = {"full_pass": True, "run_count": 270, "passed_count": 270}
        self.ppa = {"measurement_status": "three_seed", "routed": True,
                    "area_um2": 100.0, "delay_ns": 0.9, "energy_per_op_pj": 1.0,
                    "setup_worst_slack_ns": 0.001, "hold_worst_slack_ns": 0.001,
                    "drc_violations": 0, "annotation_fraction": 0.99,
                    "parameter_set": {"clock_periods_ps": {clock: 1000 for clock in
                                      ("logic_clk", "tx_clk", "rx_clk")}},
                    "per_seed": [{"layout_seed": seed} for seed in (11, 29, 47)]}

    def test_fully_qualified_reference_passes(self):
        freeze_gate(self.functional, self.stress, self.ppa)

    def test_physical_failures_do_not_freeze_a_reference(self):
        for field, value in (("setup_worst_slack_ns", -0.001), ("hold_worst_slack_ns", -0.001),
                             ("drc_violations", 1), ("annotation_fraction", 0.94),
                             ("measurement_status", "pilot")):
            ppa = copy.deepcopy(self.ppa)
            ppa[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                freeze_gate(self.functional, self.stress, ppa)

    def test_incomplete_functional_or_stress_checks_are_not_frozen(self):
        with self.assertRaises(ValueError):
            freeze_gate({**self.functional, "functional_total": 49}, self.stress, self.ppa)
        with self.assertRaises(ValueError):
            freeze_gate(self.functional, {**self.stress, "run_count": 269}, self.ppa)

    def test_nonfinite_measurements_cannot_freeze(self):
        for field in ("setup_worst_slack_ns", "hold_worst_slack_ns", "annotation_fraction",
                      "area_um2", "delay_ns", "energy_per_op_pj"):
            ppa = {**self.ppa, field: float("nan")}
            with self.subTest(field=field), self.assertRaises(ValueError):
                freeze_gate(self.functional, self.stress, ppa)


if __name__ == "__main__":
    unittest.main()
