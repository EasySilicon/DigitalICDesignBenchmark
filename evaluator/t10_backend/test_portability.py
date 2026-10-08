"""Exercise relocated shell, Python, Tcl and Make entry points without EDA."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


BACKEND = Path(__file__).resolve().parent


class PortabilityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="t10_portability_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repository = self.root / "relocated_checkout"
        self.backend = self.repository / "evaluator/t10_backend"
        shutil.copytree(BACKEND, self.backend,
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.reference = self.repository / "evaluator/reference/T10/rtl/npu_systolic_matmul_16x16.sv"
        self.reference.parent.mkdir(parents=True)
        self.reference.write_text("module npu_systolic_matmul_16x16; endmodule\n")
        self.foreign = self.root / "unrelated_working_directory"
        self.foreign.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("T10_") and k not in ("PLATFORM_DIR", "TMPDIR")}

    def run_command(self, command, *, env=None):
        return subprocess.run(command, cwd=self.foreign,
                              env=self.env if env is None else env,
                              capture_output=True, text=True, timeout=20)

    def test_defaults_follow_relocated_checkout(self):
        run = self.run_command([sys.executable, str(self.backend / "doctor.py")])
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        paths = json.loads(run.stdout)["paths"]
        self.assertEqual(paths["T10_BACKEND_ROOT"], str(self.backend))
        self.assertEqual(paths["T10_REFERENCE_RTL"], str(self.reference))
        self.assertEqual(paths["T10_SCRATCH_ROOT"], str(self.repository / "work/t10_backend"))
        command = 'source "$1"; printf "%s\\n" "$T10_BACKEND_ROOT" "$T10_REPO_ROOT" "$T10_REFERENCE_RTL"'
        run = self.run_command(["bash", "-eu", "-c", command, "bash", str(self.backend / "env.sh")])
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.splitlines(), [str(self.backend), str(self.repository), str(self.reference)])

    def test_make_configs_and_copied_floorplan_config(self):
        recipe = 'paths: ; @printf "%s\\n" "$(T10_BACKEND_ROOT)" "$(VERILOG_FILES)" "$(PLATFORM_DIR)"'
        for config in self.backend.glob("physical/*/config*.mk"):
            with self.subTest(config=config):
                run = self.run_command(["make", "--no-print-directory", "-f", str(config),
                                        "--eval", recipe, "paths"])
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout.splitlines(), [str(self.backend), str(self.reference),
                                                          str(self.repository / "vendor/asap7")])
        copied = self.root / "floorplan_snapshot/config.mk"
        copied.parent.mkdir()
        shutil.copyfile(self.backend / "physical/t10_frozen_top/config.mk", copied)
        env = self.env | {"T10_BACKEND_ROOT": str(self.backend)}
        run = self.run_command(["make", "--no-print-directory", "-f", str(copied),
                                "--eval", recipe, "paths"], env=env)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.splitlines()[0], str(self.backend))

    def test_missing_inputs_and_qualification_are_explicit(self):
        missing = self.root / "missing macro.lef"
        run = self.run_command([sys.executable, str(self.backend / "doctor.py"),
                                "--input", str(missing)])
        self.assertEqual(run.returncode, 2)
        self.assertIn(str(missing), json.loads(run.stdout)["missing"])
        run = self.run_command([sys.executable,
                                str(self.backend / "physical/t10_qualify_transport_candidate.py")])
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("Set T10_QUALIFICATION_ROOT", run.stderr)
        self.assertNotIn("ModuleNotFoundError", run.stderr)

    def test_shell_runner_preserves_paths_with_spaces(self):
        # The fake executable records argv/environment. No OpenROAD is launched.
        platform = self.root / "ASAP7 platform"
        for relative in ["setRC.tcl", "rcx_patterns.rules",
                         "lib/NLDM/asap7sc7p5t_AO_RVT_SS_nldm_211120.lib.gz",
                         "lib/NLDM/asap7sc7p5t_INVBUF_RVT_SS_nldm_220122.lib.gz",
                         "lib/NLDM/asap7sc7p5t_OA_RVT_SS_nldm_211120.lib.gz",
                         "lib/NLDM/asap7sc7p5t_SEQ_RVT_SS_nldm_220123.lib",
                         "lib/NLDM/asap7sc7p5t_SIMPLE_RVT_SS_nldm_211120.lib.gz"]:
            path = platform / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n")
        fake = self.root / "tools with spaces/openroad"
        fake.parent.mkdir()
        fake.write_text(f'#!{sys.executable}\nimport json,os,sys\n'
                        'from pathlib import Path\n'
                        'Path(os.environ["RECORD_ARGV"]).write_text(json.dumps({'
                        '"args":sys.argv[1:],"input":os.environ["T10_INPUT_ODB"],'
                        '"platform":os.environ["T10_ASAP7_PLATFORM"]}))\n')
        fake.chmod(0o755)
        # Make resource admission deterministic without querying/signalizing jobs.
        pgrep = fake.parent / "pgrep"
        pgrep.write_text("#!/usr/bin/env bash\nexit 1\n")
        pgrep.chmod(0o755)
        recorded = self.root / "argv.json"
        input_odb = self.root / "input db.odb"
        input_sdc = self.root / "input constraints.sdc"
        input_odb.write_text("fixture\n")
        input_sdc.write_text("fixture\n")
        output = self.root / "result directory/block"
        env = self.env | {"T10_ASAP7_PLATFORM": str(platform),
                          "T10_OPENROAD_EXE": str(fake),
                          "T10_SCRATCH_ROOT": str(self.root / "scratch with spaces"),
                          "T10_MIN_AVAILABLE_GIB": "1", "RECORD_ARGV": str(recorded),
                          "PATH": str(fake.parent) + os.pathsep + self.env["PATH"]}
        run = self.run_command(["bash", str(self.backend / "physical/run_t10_finish_hier_block.sh"),
                                str(input_odb), str(input_sdc), str(output)], env=env)
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        result = json.loads(recorded.read_text())
        self.assertEqual(result["args"], ["-no_init", "-exit", str(self.backend / "physical/t10_finish_hier_block.tcl")])
        self.assertEqual(result["input"], str(input_odb))
        self.assertEqual(result["platform"], str(platform))

    def test_no_host_paths_in_runtime_sources(self):
        for path in self.backend.rglob("*"):
            if path.suffix not in {".py", ".sh", ".tcl", ".sdc", ".mk", ".cc"}:
                continue
            if path.name == Path(__file__).name:
                continue
            with self.subTest(path=path):
                self.assertNotRegex(path.read_text(), r"/(?:home|mnt)/")


if __name__ == "__main__":
    unittest.main()
