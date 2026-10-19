"""The native writer must measure the requested window, not time since zero."""
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location("t10_saif_window", HERE/"t10_backend/v1/saif_window.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SaifWindowTest(unittest.TestCase):
    def test_different_writer_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unreviewed"):
            MODULE.corrected("different writer")

    @unittest.skipUnless(os.environ.get("T10_TEST_NATIVE_SAIF") == "1",
                         "explicit opt-in for native Verilator integration")
    def test_delayed_open_constants_and_transitions(self):
        with tempfile.TemporaryDirectory(prefix="t10_saif_window_") as temp:
            out = Path(temp)
            fixture = (HERE/"fixtures/t10_v1_three_seed/tb_saif_window.sv").resolve()
            def run(command, log, cwd):
                with log.open("w") as stream:
                    subprocess.run(command, cwd=cwd, stdout=stream,
                                   stderr=subprocess.STDOUT, check=True)
            run(["verilator", "--binary", "--timing", "--assert", "--trace-saif",
                 "--top-module", "tb_saif_window", "--Mdir", str(out/"build"),
                 "-j", "2", str(fixture)], out/"compile.log", out)
            run([str(out/"build/Vtb_saif_window")], out/"native.log", out)
            native = (out/"window.saif").read_text()
            executable, metadata = MODULE.build(out, "tb_saif_window", run, out)
            self.assertEqual(metadata["native_sha256"], MODULE.NATIVE_SHA256)
            self.assertEqual(metadata["native_sha256"], MODULE.sha(metadata["native_source"]))
            run([str(executable)], out/"corrected.log", out)
            corrected = (out/"window.saif").read_text()
            self.assertIn("(DURATION 5100)", native)  # Verified negative control.
            self.assertIn("(DURATION 3000)", corrected)
            def stats(name):
                pattern = r"\("+name+r" \(T0 (\d+)\) \(T1 (\d+)\).*?\(TC (\d+)\)\)"
                return tuple(map(int,re.search(pattern,corrected).groups()))
            self.assertEqual(stats("high_bit"),(0,3000,0))
            self.assertEqual(stats("low_bit"),(3000,0,0))
            self.assertEqual(stats("clk"),(1500,1500,6))
            self.assertEqual(stats("data_bit"),(1000,2000,2))


if __name__ == "__main__":
    unittest.main()
