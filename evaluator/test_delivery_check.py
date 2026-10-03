#!/usr/bin/env python3
"""Regression tests for portable delivery staging."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evaluator.delivery_check import stage_submission


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


if __name__ == "__main__":
    unittest.main()
