#!/usr/bin/env python3
"""Evaluator-owned RV32 ELF bus smoke runner; not an ISA differential scorer."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path

from elf_image import load_elf, write_hex_image
from public_check import ROOT, sources_from_filelist


def run(submission: Path, elf: Path, seed: int, max_cycles: int) -> dict:
    sources = sources_from_filelist(submission)
    image = load_elf(elf)
    elf_sha256 = hashlib.sha256(elf.read_bytes()).hexdigest()
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_cpu_elf_") as directory:
        work = Path(directory)
        image_path = work / "memory.hex"
        write_hex_image(image, image_path)
        command = [
            "verilator", "--binary", "--timing", "--assert", "-Wno-fatal",
            "-j", "4", "--top-module", "tb_cpu_elf", "--Mdir", str(work),
            f"-I{(submission / 'rtl').resolve()}",
            *map(str, sources), str(ROOT / "public" / "tb_cpu_elf.sv"),
        ]
        compiled = subprocess.run(command, text=True, capture_output=True,
                                  timeout=180, check=False)
        if compiled.returncode:
            return {"passed": False, "phase": "compile", "elf_sha256": elf_sha256,
                    "elapsed_seconds": round(time.monotonic() - start, 3),
                    "log_tail": (compiled.stdout + compiled.stderr)[-8000:]}
        binary = work / "Vtb_cpu_elf"
        executed = subprocess.run(
            [str(binary), f"+IMAGE={image_path}", f"+SEED={seed}",
             f"+MAX_CYCLES={max_cycles}"],
            text=True, capture_output=True, timeout=180, check=False)
        return {"passed": executed.returncode == 0 and
                "CPU_ELF_PASS" in executed.stdout, "phase": "run",
                "elf_sha256": elf_sha256, "seed": seed,
                "elapsed_seconds": round(time.monotonic() - start, 3),
                "log_tail": (executed.stdout + executed.stderr)[-8000:]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path)
    parser.add_argument("elf", type=Path)
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--max-cycles", type=int, default=100_000)
    args = parser.parse_args()
    if args.max_cycles <= 0:
        parser.error("--max-cycles must be positive")
    try:
        result = run(args.submission, args.elf, args.seed, args.max_cycles)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        result = {"passed": False, "phase": "infrastructure", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
