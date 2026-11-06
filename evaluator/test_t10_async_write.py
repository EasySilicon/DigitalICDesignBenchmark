"""Distinguish an unsupported reset-edge write from a harmless RTL rewrite."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

from slang_frontend import yosys_command


FIXTURES = Path(__file__).parent / "fixtures"
SOURCE = FIXTURES / "async_write_outside_reset.sv"


class AsyncWriteSemanticsTest(unittest.TestCase):
    def test_reset_edge_write_differs_from_clock_only_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary) / "build"
            result = subprocess.run([
                "verilator", "--binary", "--timing", "--assert", "-Wno-fatal",
                "-j", "2", "--top-module", "tb", "--Mdir", str(build),
                str(SOURCE), str(FIXTURES / "async_write_outside_reset_tb.sv")],
                capture_output=True, text=True, timeout=60,
                env=os.environ | {"OBJCACHE": ""})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(build / "Vtb")], capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("RESET_EDGE event_q=22 clock_q=11 clk=0", result.stdout)

    def test_both_frontends_reject_reset_edge_write_but_accept_clock_only(self):
        for frontend in ("native", "slang"):
            for top in ("reset_event_write", "clock_only_write"):
                with self.subTest(frontend=frontend, top=top):
                    script = (f"read_verilog -sv {SOURCE}; hierarchy -top {top}; proc"
                              if frontend == "native" else
                              f"read_slang --top {top} {SOURCE}; proc")
                    command = ["yosys"] if frontend == "native" else list(yosys_command())
                    result = subprocess.run([*command, "-Q", "-T", "-p", script],
                                            capture_output=True, text=True, timeout=30)
                    log = result.stdout + result.stderr
                    if top == "clock_only_write":
                        self.assertEqual(result.returncode, 0, log)
                    else:
                        self.assertNotEqual(result.returncode, 0, log)
                        expected = ("Multiple edge sensitive events" if frontend == "native"
                                    else "simple if-else pattern expected")
                        self.assertIn(expected, log)
