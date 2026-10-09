from __future__ import annotations

import unittest
from evaluator.t08_check import GROUPS
from evaluator.t08_mutation_check import MUTATIONS, UNIMPLEMENTED_WITNESSES, classify, mutate


class T08MutationQualificationTest(unittest.TestCase):
    def test_snapshot_witnesses_are_scored_without_changing_maximum(self):
        snapshot = next(cases for name, _, cases in GROUPS if name == "config_snapshot")
        self.assertEqual(snapshot, [14, 15, 19, 20, 21, 22, 30, 31])
        self.assertEqual(sum(points for _, points, _ in GROUPS), 50)
        inventory = {case for _, _, cases in GROUPS for case in cases}
        for _, _, witnesses in MUTATIONS.values():
            self.assertTrue(set(witnesses) <= inventory)
        self.assertTrue(set(UNIMPLEMENTED_WITNESSES) <= inventory)

    def test_mechanical_edit_requires_unique_anchor(self):
        name = "live_untagged_flag"
        old, new, _ = MUTATIONS[name]
        self.assertEqual(mutate("prefix " + old + " suffix", name), "prefix " + new + " suffix")
        for source in ("unrelated source", old + old):
            with self.assertRaises(ValueError):
                mutate(source, name)

    def test_compile_failure_is_not_detection(self):
        report = {"cases": {"21": {"passed": False,
                                  "runs": [{"passed": False, "error": "candidate compile failure"}]}}}
        self.assertFalse(classify(report, (21,))["detected"])

    def test_all_required_witnesses_must_fail(self):
        report = {"cases": {"19": {"passed": False, "runs": [{"exit_code": 1,"passed": False}]},
                            "20": {"passed": True, "runs": [{"exit_code": 0,"passed": True}]}}}
        self.assertTrue(classify(report, (19,))["detected"])
        self.assertFalse(classify(report, (19, 20))["detected"])
        self.assertFalse(classify(report, (21,))["detected"])

    def test_one_missed_seed_does_not_qualify(self):
        report = {"cases": {"19": {"passed": False, "runs": [
            {"seed":47,"exit_code":1,"passed":False},
            {"seed":91,"exit_code":0,"passed":True}]}}}
        self.assertFalse(classify(report, (19,))["detected"])

    def test_boundary_regressions_have_independent_scored_witnesses(self):
        self.assertEqual(MUTATIONS["first_last_old_snapshot"][2], (28, 31))
        self.assertEqual(MUTATIONS["first_last_stale_header"][2], (36,))
        self.assertEqual(MUTATIONS["bypass_short_rejected"][2], (29, 30))
        self.assertEqual(MUTATIONS["mac_bad_policy_double_counted"][2], (32,))

    def test_timeout_is_not_qualified_as_mutation_detection(self):
        report = {"cases": {"28": {"passed": False,
            "runs": [{"passed": False, "error": "candidate simulation timeout"}]}}}
        self.assertFalse(classify(report, (28,))["detected"])


if __name__ == "__main__":
    unittest.main()
