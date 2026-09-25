#!/usr/bin/env python3
"""Audit the frozen ACT4 ELF set and its 256 KiB memory mapping."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

try:
    from .elf_image import MEMORY_SIZE, TOHOST, load_elf
except ImportError:
    from elf_image import MEMORY_SIZE, TOHOST, load_elf

ROOT = Path(__file__).resolve().parent / "act4_elfs"
CONFIG = ROOT.parent.parent / "benchmark" / "cpu" / "act4"


def verify() -> dict:
    manifest = json.loads((ROOT / "MANIFEST.json").read_text())
    if manifest["memory_bytes"] != MEMORY_SIZE or int(manifest["tohost"], 0) != TOHOST:
        raise ValueError("ACT4 manifest differs from CPU memory contract")
    for name, expected in manifest["config_sha256"].items():
        if hashlib.sha256((CONFIG / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"ACT4 config hash mismatch: {name}")
    entries = manifest["elfs"]
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*.elf")}
    expected = {entry["path"] for entry in entries}
    if actual != expected or len(entries) != len(expected):
        raise ValueError("ACT4 ELF inventory mismatch")
    max_end = 0
    for entry in entries:
        path = ROOT / entry["path"]
        data = path.read_bytes()
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"ACT4 ELF hash mismatch: {entry['path']}")
        load_elf(path)
        max_end = max(max_end, entry["load_end_offset"])
    if max_end != manifest["max_load_end_offset"] or max_end >= TOHOST - 0x8000_0000:
        raise ValueError("ACT4 memory bound mismatch")
    return {"elf_count": len(entries), "max_load_end_offset": hex(max_end),
            "memory_bytes": MEMORY_SIZE, "tohost": hex(TOHOST)}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
