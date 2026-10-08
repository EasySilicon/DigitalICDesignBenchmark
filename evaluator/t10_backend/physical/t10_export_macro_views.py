#!/usr/bin/env python3
"""Export LEF and extracted timing views from a routed T10 macro."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run(command: list[str], log: Path, env: dict[str, str] | None = None) -> None:
    with log.open("w") as output:
        subprocess.run(command, check=True, stdout=output, stderr=subprocess.STDOUT, env=env)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--variant-dir", required=True, type=Path)
    parser.add_argument("--scratch-dir", required=True, type=Path)
    parser.add_argument("--platform", required=True, type=Path)
    parser.add_argument("--openroad", default="openroad")
    args = parser.parse_args()

    scripts = Path(__file__).resolve().parent
    guarded = scripts / "t10_run_openroad_guarded.sh"
    args.scratch_dir.mkdir(parents=True, exist_ok=True)
    odb = args.variant_dir / "6_final.odb"
    sdc = args.variant_dir / "6_final.sdc"
    spef = args.variant_dir / "6_final.spef"
    for path in (odb, sdc, spef):
        if not path.is_file():
            parser.error(f"missing routed view: {path}")

    liberty = args.variant_dir / f"{args.design}_wc.lib"
    detailed = args.variant_dir / f"{args.design}_detailed.lef"
    macro_lef = args.variant_dir / f"{args.design}_m7.lef"
    pg = args.scratch_dir / f"{args.design}_m8_pg.txt"
    env = os.environ.copy()
    env.update(
        ASAP7_PLATFORM=str(args.platform),
        ODB_INPUT=str(odb),
        SDC_INPUT=str(sdc),
        SPEF_INPUT=str(spef),
        LIB_OUTPUT=str(liberty),
        LEF_OUTPUT=str(detailed),
        PG_OUTPUT=str(pg),
    )
    run(
        [str(guarded), args.openroad, "-exit",
         str(scripts / "t10_export_bank_timing.tcl")],
        args.scratch_dir / f"{args.design}_export_lib.log",
        env,
    )
    run(
        [str(guarded), args.openroad, "-exit",
         str(scripts / "t10_export_detailed_lef.tcl")],
        args.scratch_dir / f"{args.design}_export_lef.log",
        env,
    )
    run(
        [str(guarded), args.openroad, "-exit",
         str(scripts / "t10_extract_macro_pg.tcl")],
        args.scratch_dir / f"{args.design}_export_pg.log",
        env,
    )
    subprocess.run(
        [sys.executable, str(scripts / "t10_build_macro_lef.py"), str(detailed), str(pg), str(macro_lef)],
        check=True,
    )
    print(liberty)
    print(macro_lef)


if __name__ == "__main__":
    main()
