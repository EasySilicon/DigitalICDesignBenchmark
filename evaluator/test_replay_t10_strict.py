"""Keep retained-trace reuse input-identical and strictly scored."""
from collections import Counter
import unittest

from replay_t10_strict import verified_cases
from runner_t10 import Case, parse_output
from t10_fast_oracle import check_output_fast
from t10_range_cases import range_stress_cases


VECTORS = {
    "phase.mem": "b3f704f66c7b1cb1e71a092a85a3630173d1a8b580991017afe91c408b5a5551",
    "a.mem": "9a155d6b834a436207f9cd46c47ca4baeb77fc4cc8b273e4ce807ac8347c8e01",
    "stall.mem": "80b59bbb321087e097172ec69756d14f257b4cb31a7defa1389dc0b455616efc",
    "b.mem": "f2ca1b905e339497405045b6cabc2f131f1bcf2147fd5ed66126699660f0427f",
    "as.mem": "75000bf9c36bf6f063604012dbf904cbfc94b903eacce506ad7af4dd37830103",
    "bs.mem": "25320a174f68a98e222c9957efa8a7bf3babcd856aa57c4d379bc4070aca4b2d",
    "pause.mem": "f64414b7e7f999ce03896e05a697228f930acdfaac735e099ed6da876c8fd114",
    "reset.mem": "f7ea948aa31ce42a591be1ba08a626c71c8424b117668478537780d854f0ac69",
    "mode.mem": "4c40083c94e108b56b07626375f90e7d88b493f7ebefed4198bb4b0cb50908a8",
}


class StrictReplayTest(unittest.TestCase):
    def test_archived_vectors_are_unchanged_and_strict_subset_is_exact(self):
        cases, selected = verified_cases({"vector_sha256": VECTORS}, 11)
        self.assertEqual((len(cases), len(selected)), (3154, 2898))
        self.assertEqual(Counter(c.group for c in range_stress_cases()),
                         {"MM-F16": 22, "MM-MX8": 44, "MM-MX4": 16})
        altered = dict(VECTORS, **{"a.mem": "0" * 64})
        with self.assertRaisesRegex(ValueError, "vectors differ"):
            verified_cases({"vector_sha256": altered}, 11)

    def test_selection_preserves_trace_indices_and_rejects_duplicate_reports(self):
        case = Case("MM-INT", 0, (0,) * 8, (0,) * 8, 0, 0, 0, 0, 0)
        log = "\n".join(f"MM_ROW 1 {row} 0" for row in range(16)) + "\nMM_CASE 1 1 1 1 16\n"
        for duplicate in ("", "MM_ROW 1 0 0\n", "MM_CASE 1 1 1 1 16\n"):
            groups, failures = parse_output(log + duplicate, [case, case], {"passed": True},
                                            numeric_checker=check_output_fast,
                                            selected_cases={1})
            self.assertEqual(groups["MM-INT"]["cases_total"], 1)
            self.assertEqual(groups["MM-INT"]["cases_passed"], int(not duplicate))
            self.assertEqual(bool(failures), bool(duplicate))
        with self.assertRaisesRegex(ValueError, "outside"):
            parse_output(log, [case], {"passed": True}, selected_cases={1})
