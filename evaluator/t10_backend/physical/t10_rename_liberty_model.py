#!/usr/bin/env python3
"""Rename exact Liberty library/cell declarations for a physical macro view."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rename_declaration(text: str, kind: str, old: str, new: str) -> str:
    pattern = re.compile(
        rf'(?m)^(\s*{kind}\s*\(\s*["\']?){re.escape(old)}(["\']?\s*\)\s*\{{\s*)$'
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one {kind} declaration for {old!r}, found {len(matches)}"
        )
    return pattern.sub(rf"\g<1>{new}\g<2>", text, count=1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--old-library")
    parser.add_argument("--new-library")
    parser.add_argument("--old-cell")
    parser.add_argument("--new-cell")
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"missing input: {args.input}")
    library_requested = args.old_library is not None or args.new_library is not None
    cell_requested = args.old_cell is not None or args.new_cell is not None
    if library_requested and not (args.old_library and args.new_library):
        parser.error("--old-library and --new-library must be given together")
    if cell_requested and not (args.old_cell and args.new_cell):
        parser.error("--old-cell and --new-cell must be given together")
    if not library_requested and not cell_requested:
        parser.error("request at least one library or cell rename")
    if library_requested and args.old_library == args.new_library:
        parser.error("old and new library names must differ")
    if cell_requested and args.old_cell == args.new_cell:
        parser.error("old and new cell names must differ")

    source = args.input.read_bytes()
    text = source.decode("utf-8")
    try:
        if library_requested:
            text = rename_declaration(
                text, "library", args.old_library, args.new_library
            )
        if cell_requested:
            text = rename_declaration(text, "cell", args.old_cell, args.new_cell)
    except ValueError as error:
        parser.error(str(error))
    renamed = text.encode("utf-8")
    if source == renamed:
        raise RuntimeError("rename produced no byte change")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(renamed)
    print(f"input_sha256={sha256(source)}")
    print(f"output_sha256={sha256(renamed)}")
    if library_requested:
        print(f"old_library={args.old_library}")
        print(f"new_library={args.new_library}")
    if cell_requested:
        print(f"old_cell={args.old_cell}")
        print(f"new_cell={args.new_cell}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
