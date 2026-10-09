#!/usr/bin/env python3
"""Regression tests for portable delivery staging."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evaluator.delivery_check import check_normal, stage_submission


class DeliveryStagingTests(unittest.TestCase):
    def test_staging_drops_generated_root_build_and_preserves_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            staged = root / "staged"
            (source / "rtl").mkdir(parents=True)
            (source / "verif").mkdir()
            (source / "build").mkdir()
            (source / "rtl" / "files.f").write_text("dut.sv\n")
            (source / "rtl" / "dut.sv").write_text("module dut; endmodule\n")
            (source / "verif" / "tb.py").write_text("# source\n")
            (source / "build" / "Vdut.mk").write_text("/workspace/verif/tb.cpp\n")
            run_sh = source / "run.sh"
            run_sh.write_text("#!/bin/sh\n")
            run_sh.chmod(0o755)

            stage_submission(source, staged)

            self.assertFalse((staged / "build").exists())
            self.assertEqual((staged / "rtl" / "dut.sv").read_text(),
                             "module dut; endmodule\n")
            self.assertEqual((staged / "verif" / "tb.py").read_text(), "# source\n")
            self.assertTrue((staged / "run.sh").stat().st_mode & 0o100)


class DeliveryResultTests(unittest.TestCase):
    @staticmethod
    def result(tests):
        return {
            "tests": tests,
            "tool_versions": {"verilator": "test-version"},
            "elapsed_seconds": 1.0,
        }

    def test_same_name_with_distinct_seeds_is_valid(self):
        rows = check_normal(self.result([
            {"name": "AC-01", "passed": True, "seed": 11},
            {"name": "AC-01", "passed": True, "seed": 29},
            {"name": "AC-01", "passed": True, "seed": 47},
        ]))
        self.assertEqual(len(rows), 3)

    def test_same_name_and_seed_is_duplicate(self):
        duplicate = {"name": "AC-01", "passed": True, "seed": 11}
        with self.assertRaisesRegex(ValueError, "name/seed"):
            check_normal(self.result([duplicate, dict(duplicate)]))


if __name__ == "__main__":
    unittest.main()
