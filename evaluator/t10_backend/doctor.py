#!/usr/bin/env python3
"""Check backend paths and dependencies without launching an EDA process."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "physical"))
from t10_paths import backend_root, configured_path, repo_root, scratch_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("paths", "ppa", "qualification"),
                        default="paths")
    parser.add_argument("--input", type=Path, action="append", default=[],
                        help="also check a required generated ODB/LEF/Liberty/receipt")
    args = parser.parse_args()
    repository = repo_root()
    evaluator = configured_path("T10_EVALUATOR_ROOT", repository / "evaluator")
    reference = configured_path("T10_REFERENCE_ROOT", evaluator / "reference")
    paths = {
        "T10_BACKEND_ROOT": backend_root(),
        "T10_REPO_ROOT": repository,
        "T10_SCRATCH_ROOT": scratch_root(),
        "T10_ORFS_ROOT": configured_path("T10_ORFS_ROOT", repository / "third_party/OpenROAD-flow-scripts"),
        "T10_ASAP7_PLATFORM": configured_path("T10_ASAP7_PLATFORM", repository / "vendor/asap7"),
        "T10_REFERENCE_RTL": configured_path("T10_REFERENCE_RTL", reference / "T10/rtl/npu_systolic_matmul_16x16.sv"),
        "T10_QUALIFICATION_ROOT": configured_path("T10_QUALIFICATION_ROOT", evaluator),
    }
    missing = []

    def require(path: Path) -> None:
        if not path.is_file() or not path.stat().st_size:
            missing.append(str(path))

    require(paths["T10_REFERENCE_RTL"])
    require(paths["T10_BACKEND_ROOT"] / "env.sh")
    require(paths["T10_BACKEND_ROOT"] / "config.mk")
    tools = {}
    if args.profile == "ppa":
        require(paths["T10_ORFS_ROOT"] / "flow/Makefile")
        require(paths["T10_ASAP7_PLATFORM"] / "config.mk")
        require(paths["T10_ASAP7_PLATFORM"] / "setRC.tcl")
        for name in ("openroad", "yosys", "make", "flock"):
            executable = os.environ.get("T10_" + name.upper() + "_EXE", name)
            if name == "openroad":
                executable = os.environ.get("T10_OPENROAD_EXE", os.environ.get("T10_OPENROAD", name))
            resolved = shutil.which(executable)
            tools[name] = resolved
            if not resolved:
                missing.append(f"executable: {executable}")
    elif args.profile == "qualification":
        for name in ("runner_t10_stream.py", "runner_t10.py", "runner.py",
                     "t10_structure_check.py", "t10_fast_oracle.py",
                     "hidden/tb_hidden_T10_stream.sv", "hidden/tb_hidden_T10_reset.sv"):
            require(paths["T10_QUALIFICATION_ROOT"] / name)
    for path in args.input:
        require(path.expanduser().resolve())
    print(json.dumps({"profile": args.profile, "passed": not missing,
                      "paths": {k: str(v) for k, v in paths.items()},
                      "tools": tools, "missing": missing}, indent=2))
    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
