#!/usr/bin/env python3
"""Run every locked ACT4 ELF on Sail and audit the architectural tohost write.

This establishes an ISA-reference baseline, not CPU RTL correctness or pipeline
acceptance. The sim stops at the instruction after the PASS store to avoid the
intentional infinite loop in RVMODEL_HALT_PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from elf_image import TOHOST

ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "act4_elfs" / "MANIFEST.json"
DEFAULT_CONFIG = ROOT.parent / "benchmark" / "cpu" / "act4" / "sail.json"
STORE_LINE = re.compile(r"mem\[W,0x([0-9A-Fa-f]+)\] <- 0x([0-9A-Fa-f]+)")
STEP_LINE = re.compile(r"^\[(\d+)\] \[M\]:")
SYMBOL_LINE = re.compile(r"^([0-9a-fA-F]+)\s+[a-zA-Z]\s+rvmodel_halt_pass$")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pass_stop_pc(nm: str, elf: Path) -> int:
    outcome = subprocess.run([nm, "-an", str(elf)], text=True,
                             capture_output=True, check=True, timeout=30)
    matches = [int(match.group(1), 16) for line in outcome.stdout.splitlines()
               if (match := SYMBOL_LINE.fullmatch(line))]
    if len(matches) != 1:
        raise ValueError(f"{elf.name}: expected one rvmodel_halt_pass symbol")
    return matches[0] + 12


def check_one(sail: str, nm: str, config: Path, elf: Path,
              expected_hash: str, instruction_limit: int) -> dict:
    if digest(elf) != expected_hash:
        raise ValueError(f"{elf.name}: ELF hash mismatch")
    stop_pc = pass_stop_pc(nm, elf)
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_sail_act4_") as temporary:
        trace = Path(temporary) / "trace.txt"
        command = [sail, "--config", str(config), "--stop-at-pc", hex(stop_pc),
                   "--inst-limit", str(instruction_limit), "--trace-output", str(trace),
                   "--trace-instr", "--trace-mem", str(elf)]
        outcome = subprocess.run(command, text=True, capture_output=True,
                                 timeout=120, check=False)
        stores = []
        steps = 0
        if trace.exists():
            for line in trace.read_text(errors="replace").splitlines():
                if match := STEP_LINE.match(line):
                    steps = max(steps, int(match.group(1)) + 1)
                if match := STORE_LINE.search(line):
                    address, value = (int(part, 16) for part in match.groups())
                    if address == TOHOST:
                        stores.append(value)
            trace_sha256 = digest(trace)
        else:
            trace_sha256 = None
    passed = (outcome.returncode == 0 and steps < instruction_limit and
              stores and stores[-1] == 1 and
              all(value in (0, 1) for value in stores))
    return {"path": str(elf), "elf_sha256": expected_hash,
            "stop_pc": f"0x{stop_pc:08x}", "steps": steps,
            "tohost_writes": stores, "trace_sha256": trace_sha256,
            "sail_exit_code": outcome.returncode, "passed": bool(passed),
            "log_tail": (outcome.stdout + outcome.stderr)[-1000:] if not passed else ""}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--sail", default="sail_riscv_sim")
    parser.add_argument("--nm", default="riscv32-unknown-elf-nm")
    parser.add_argument("--inst-limit", type=int, default=1_000_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.inst_limit <= 0:
        parser.error("--inst-limit must be positive")
    try:
        manifest = json.loads(args.manifest.read_text())
        expected_config_hash = manifest["config_sha256"]["sail.json"]
        if digest(args.config) != expected_config_hash:
            raise ValueError("Sail config hash does not match ACT4 manifest")
        root = args.manifest.parent
        results = []
        for row in manifest["elfs"]:
            result = check_one(args.sail, args.nm, args.config, root / row["path"],
                               row["sha256"], args.inst_limit)
            result["path"] = row["path"]
            results.append(result)
            print(f"{row['path']}: {'PASS' if result['passed'] else 'FAIL'} "
                  f"steps={result['steps']} tohost={result['tohost_writes']}")
        summary = {"schema_version": 1, "act4_revision": manifest["act4_revision"],
                   "sail_version": subprocess.run([args.sail, "--version"],
                                                   text=True, capture_output=True,
                                                   check=True, timeout=10).stdout.strip(),
                   "config_sha256": expected_config_hash,
                   "instruction_limit": args.inst_limit,
                   "total": len(results), "passed": sum(x["passed"] for x in results),
                   "results": results}
        if args.output:
            args.output.write_text(json.dumps(summary, indent=2) + "\n")
        else:
            print(json.dumps({key: value for key, value in summary.items()
                              if key != "results"}, indent=2))
        return 0 if summary["passed"] == summary["total"] else 1
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
