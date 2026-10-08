#!/usr/bin/env python3
"""Create an execution-parameter-only copy of the locked ASAP7 KLayout deck."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import re
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument(
        "--tile-um",
        type=float,
        help="optionally change only the DRC tile size; rule expressions remain unchanged",
    )
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"missing input: {args.input}")
    if args.threads < 1:
        parser.error("--threads must be positive")
    if args.tile_um is not None and args.tile_um <= 0:
        parser.error("--tile-um must be positive")

    source_bytes = args.input.read_bytes()
    source = source_bytes.decode("utf-8")
    pattern = re.compile(r"(?m)^(\s*)threads\(\d+\)(\s*)$")
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        parser.error(f"expected exactly one threads(...) statement, found {len(matches)}")
    replacement = rf"\g<1>threads({args.threads})\g<2>"
    prepared = pattern.sub(replacement, source, count=1)
    if args.tile_um is not None:
        tile_pattern = re.compile(r"(?m)^(\s*)tiles\([^\n]+\)(\s*)$")
        tile_matches = list(tile_pattern.finditer(prepared))
        if len(tile_matches) != 1:
            parser.error(f"expected exactly one tiles(...) statement, found {len(tile_matches)}")
        tile_text = f"{args.tile_um:g}"
        prepared = tile_pattern.sub(rf"\g<1>tiles({tile_text}.um)\g<2>", prepared, count=1)
    prepared_bytes = prepared.encode("utf-8")

    diff = list(
        difflib.unified_diff(
            source.splitlines(),
            prepared.splitlines(),
            fromfile=str(args.input),
            tofile=str(args.output),
            lineterm="",
        )
    )
    changed_lines = [line for line in diff if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
    expected_changed_lines = 4 if args.tile_um is not None else 2
    if len(changed_lines) != expected_changed_lines or not all(
        "threads(" in line or "tiles(" in line for line in changed_lines
    ):
        raise RuntimeError(
            "deck preparation changed text outside the threads(...) and optional tiles(...) statements"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(prepared_bytes)
    print(f"input_sha256={digest(source_bytes)}")
    print(f"output_sha256={digest(prepared_bytes)}")
    print("changed_lines=" + repr(changed_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
