#!/usr/bin/env python3
"""Hash every physical and timing input consumed by the T10 MCMM run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def artifact(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"missing input: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--odb", required=True, type=Path)
    parser.add_argument("--sdc", required=True, type=Path)
    parser.add_argument("--rcx-rules", required=True, type=Path)
    parser.add_argument("--setrc-tcl", required=True, type=Path)
    parser.add_argument("--wc-lib", action="append", required=True, type=Path)
    parser.add_argument("--bc-lib", action="append", required=True, type=Path)
    parser.add_argument("--wc-macro-lib", action="append", required=True, type=Path)
    parser.add_argument("--bc-macro-lib", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    expected_counts = {
        "--wc-lib": (len(args.wc_lib), 5),
        "--bc-lib": (len(args.bc_lib), 5),
        "--wc-macro-lib": (len(args.wc_macro_lib), 5),
        "--bc-macro-lib": (len(args.bc_macro_lib), 5),
    }
    for label, (observed, expected) in expected_counts.items():
        if observed != expected:
            parser.error(f"{label} count is {observed}, expected {expected}")

    roles: dict[str, Any] = {
        "odb": artifact(args.odb),
        "sdc": artifact(args.sdc),
        "rcx_rules": artifact(args.rcx_rules),
        "setrc_tcl": artifact(args.setrc_tcl),
        "wc_libs": [artifact(path) for path in args.wc_lib],
        "bc_libs": [artifact(path) for path in args.bc_lib],
        "wc_macro_libs": [artifact(path) for path in args.wc_macro_lib],
        "bc_macro_libs": [artifact(path) for path in args.bc_macro_lib],
    }
    all_paths = [
        record["path"]
        for value in roles.values()
        for record in (value if isinstance(value, list) else [value])
    ]
    if len(all_paths) != len(set(all_paths)):
        duplicates = sorted(path for path in set(all_paths) if all_paths.count(path) > 1)
        parser.error("an input appears in multiple roles: " + ", ".join(duplicates))

    result = {
        "schema_version": 1,
        "policy": "ordered, role-specific SHA-256 binding of every MCMM input",
        "roles": roles,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
