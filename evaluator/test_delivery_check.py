#!/usr/bin/env python3
"""Regression tests for portable delivery staging."""

from __future__ import annotations

import tempfile
import json
import unittest
from pathlib import Path

from evaluator.delivery_check import check, check_normal, check_seeds, stage_submission
from evaluator.delivery_policy import deduction


class CpuDeliveryTests(unittest.TestCase):
    def test_prime_seed_replays_cover_each_seed_twice_without_date_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "submission"
            (source / "rtl").mkdir(parents=True)
            (source / "verif").mkdir()
            (source / "rtl/files.f").write_text("dut.sv\n")
            (source / "rtl/dut.sv").write_text("module dut; endmodule\n")
            (source / "verif/test.py").write_text("# self-check\n")
            (source / "README.md").write_text("Run ./run.sh\n")
            result = dict(tests=[dict(name="self", passed=True, seed=11)],
                          tool_versions=dict(test="1"), elapsed_seconds=0)
            (source / "results.json").write_text(json.dumps(result))
            trace = root / "seeds.jsonl"
            script = source / "run.sh"
            script.write_text("#!/usr/bin/env python3\n"
                "import json, os, pathlib\n"
                "seed = int(os.environ['BENCH_SEED'])\n"
                "assert seed in (11, 29, 47)\n"
                f"trace = pathlib.Path({str(trace)!r})\n"
                "with trace.open('a') as stream: stream.write(str(seed) + '\\n')\n"
                f"result = {result!r}\n"
                "result['tests'][0]['seed'] = seed * 1000\n"
                "pathlib.Path('results.json').write_text(json.dumps(result))\n")
            script.chmod(0o755)
            report = check_seeds("T06", source)
            self.assertTrue(report["delivery_qualified"], report)
            self.assertEqual(report["delivery_seeds"], [11, 29, 47])
            self.assertEqual(trace.read_text().splitlines(), ["11", "11", "29", "29", "47", "47"])
            self.assertEqual(deduction(report["delivery_assessment"]), (0, None))

    def test_t09_uses_only_the_generic_self_test_contract(self):
        cases = (("pass", True, []),
                 ("failed_test", False, ["results_format"]),
                 ("nondeterministic", False, ["self_check_determinism"]))
        for scenario, qualified, roots in cases:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "rtl").mkdir()
                (root / "rtl/files.f").write_text("dut.sv\n")
                (root / "rtl/dut.sv").write_text("module dut; endmodule\n")
                (root / "verif").mkdir()
                (root / "verif/test.py").write_text("# self-test source\n")
                (root / "README.md").write_text("Run ./run.sh\n")
                result = dict(tests=[dict(name="self", passed=True, seed=11)],
                              tool_versions=dict(test="1"), elapsed_seconds=0)
                (root / "results.json").write_text(json.dumps(result))
                # Any candidate-specific ELF invocation fails. The only accepted
                # invocation is the ordinary zero-argument self-test.
                script = root / "run.sh"
                script.write_text("#!/usr/bin/env python3\n"
                    "import json, os, pathlib, sys\n"
                    "assert len(sys.argv) == 1\n"
                    f"result = {result!r}\n"
                    "result['tests'][0]['seed'] = int(os.environ['BENCH_SEED'])\n"
                    f"scenario = {scenario!r}\n"
                    "if scenario == 'failed_test': result['tests'][0]['passed'] = False\n"
                    "if scenario == 'nondeterministic':\n"
                    "    counter = pathlib.Path('counter')\n"
                    "    n = int(counter.read_text()) + 1 if counter.exists() else 1\n"
                    "    counter.write_text(str(n))\n"
                    "    result['tests'][0]['name'] = str(n)\n"
                    "pathlib.Path('results.json').write_text(json.dumps(result))\n")
                script.chmod(0o755)
                report = check("T09", root, 11, 30)
                self.assertEqual(report["delivery_qualified"], qualified, report)
                self.assertEqual([e["root_cause"] for e in
                    report["delivery_assessment"]["errors"]], roots)
                self.assertEqual(deduction(report["delivery_assessment"]),
                                 (0 if qualified else 5, None))


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
