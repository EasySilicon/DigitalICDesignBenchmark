#!/usr/bin/env python3
"""Verify frozen T09 program/oracle manifests, hashes, and event counts."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
DATA = HERE / "t09_data"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl_count(path: Path) -> int:
    with gzip.open(path, "rt") as stream:
        return sum(1 for line in stream if isinstance(json.loads(line), dict))


def main() -> int:
    checked_files: set[Path] = set()
    act_root = DATA / "oracles" / "act4"
    act_rows = json.loads((act_root / "MANIFEST.json").read_text())["oracles"]
    if len(act_rows) != 45:
        raise SystemExit(f"ACT4 manifest has {len(act_rows)} entries, expected 45")
    for row in act_rows:
        elf = HERE / "act4_elfs" / row["elf_path"]
        oracle = act_root / row["oracle_path"]
        if digest(elf) != row["elf_sha256"] or digest(oracle) != row["oracle_sha256"]:
            raise SystemExit(f"ACT4 hash mismatch: {row['elf_path']}")
        if jsonl_count(oracle) != row["commits"]:
            raise SystemExit(f"ACT4 event count mismatch: {row['oracle_path']}")
        checked_files.update((elf, oracle))

    suite_counts = {}
    for suite, expected in (("directed", 108), ("random", 100)):
        root = DATA / "programs" / suite
        rows = json.loads((root / "MANIFEST.json").read_text())["cases"]
        if len(rows) != expected:
            raise SystemExit(f"{suite} manifest has {len(rows)} entries, expected {expected}")
        for row in rows:
            source, elf, oracle = (root / row[key] for key in ("source", "elf", "oracle"))
            if not source.is_file():
                raise SystemExit(f"missing source: {source}")
            if digest(elf) != row["elf_sha256"] or digest(oracle) != row["oracle_sha256"]:
                raise SystemExit(f"{suite} hash mismatch: {row['elf']}")
            if jsonl_count(oracle) != row["steps"]:
                raise SystemExit(f"{suite} event count mismatch: {row['oracle']}")
            checked_files.update((source, elf, oracle))
        suite_counts[suite] = len(rows)

    spec_root = DATA / "programs" / "spec"
    spec_rows = json.loads((spec_root / "MANIFEST.json").read_text())["cases"]
    if len(spec_rows) != 4:
        raise SystemExit(f"spec manifest has {len(spec_rows)} entries, expected 4")
    for row in spec_rows:
        source, elf = spec_root / row["source"], spec_root / row["elf"]
        if not source.is_file() or digest(elf) != row["elf_sha256"]:
            raise SystemExit(f"spec artifact mismatch: {row['case']}")
        checked_files.update((source, elf))

    for name in ("delivery_bad_tohost.S", "delivery_bad_tohost.elf"):
        path = DATA / "programs" / name
        if not path.is_file():
            raise SystemExit(f"missing delivery probe: {path}")
        checked_files.add(path)
    print(json.dumps({"status": "ok", "act4": len(act_rows),
                      "directed": suite_counts["directed"],
                      "random": suite_counts["random"], "spec": len(spec_rows),
                      "checked_files": len(checked_files)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
