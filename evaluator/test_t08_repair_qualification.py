from __future__ import annotations

import unittest
from evaluator.t08_check import GROUPS
from evaluator.t08_repair_qualification import FAULTS, VARIANTS, inject


class T08RepairQualificationTest(unittest.TestCase):
    def source(self):
        # Anchor fixture, not a corrected RTL implementation.
        return ("\nwire [WIDTH-1:0] s_axis;\n"
                + "if (wr_ptr_update_reg == wr_ptr_update_ack_sync2_reg) begin\n" * 3
                + "wr_ptr_sync_commit_reg <= wr_ptr_commit_reg;\n"
                + "wr_ptr_temp = wr_ptr_commit_reg;\n" * 2
                + "wr_ptr_gray_reg <= bin2gray(wr_ptr_temp);\n"
                  "                    drop_frame_reg <= 1'b0;\n"
                  "                    overflow_reg <= 1'b1;\n"
                  "                end\n"
                  "bad_frame_reg <= 1'b1;\n                    end\n")

    def test_positive_control_only_changes_notification_scheduling(self):
        source = inject(self.source(), frozenset())
        self.assertEqual(source.count("if (commit_sync_ready) begin"), 3)
        self.assertIn("wr_ptr_sync_commit_reg <= wr_ptr_commit_reg;", source)
        self.assertEqual(source.count("wr_ptr_temp = wr_ptr_commit_reg;"), 2)
        self.assertNotIn("wr_ptr_update_valid_reg <= 1'b0;", source)

    def test_full_injection_covers_each_lifecycle_path(self):
        source = inject(self.source(), FAULTS)
        self.assertIn("wr_ptr_sync_commit_reg <= wr_ptr_reg;", source)
        self.assertEqual(source.count("wr_ptr_temp = wr_ptr_sync_commit_reg;"), 2)
        self.assertEqual(source.count("wr_ptr_update_valid_reg <= 1'b0;"), 2)

    def test_partial_repairs_have_scored_witnesses(self):
        inventory = {c for _, _, cases in GROUPS for c in cases}
        for faults, witnesses in VARIANTS.values():
            self.assertTrue(set(witnesses) <= inventory)
            inject(self.source(), faults)
        self.assertEqual(set(VARIANTS["wrap_checkpoint_truncated"][1]), {26, 27})

    def test_missing_ambiguous_or_unknown_mutations_fail_closed(self):
        with self.assertRaises(ValueError):
            inject("missing", FAULTS)
        with self.assertRaises(ValueError):
            inject(self.source() + "\nwire [WIDTH-1:0] s_axis;", FAULTS)
        with self.assertRaises(ValueError):
            inject(self.source(), frozenset({"unknown"}))


if __name__ == "__main__":
    unittest.main()
