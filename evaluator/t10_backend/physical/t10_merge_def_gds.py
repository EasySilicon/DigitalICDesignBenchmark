#!/usr/bin/env python3
"""Create a hierarchical stream file from one routed DEF and its GDS views."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import klayout.db as kdb


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--def2stream", required=True, type=Path)
    parser.add_argument("--technology", required=True, type=Path)
    parser.add_argument("--def", dest="input_def", required=True, type=Path)
    parser.add_argument("--design-name", required=True)
    parser.add_argument("--input-gds", required=True, type=Path, action="append")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--layer-map", default="", type=Path)
    parser.add_argument("--allow-empty", default="")
    args = parser.parse_args()

    inputs = [args.def2stream, args.technology, args.input_def, *args.input_gds]
    missing = [str(path) for path in inputs if not path.is_file()]
    if missing:
        parser.error("missing input(s): " + ", ".join(missing))
    if any(" " in str(path) for path in args.input_gds):
        parser.error("def2stream accepts a space-separated file list; GDS paths may not contain spaces")

    spec = importlib.util.spec_from_file_location("orfs_def2stream", args.def2stream)
    if spec is None or spec.loader is None:
        parser.error(f"cannot load {args.def2stream}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = module.merge_gds(
        kdb,
        str(args.technology),
        str(args.layer_map) if str(args.layer_map) != "." else "",
        str(args.input_def),
        args.design_name,
        " ".join(str(path) for path in args.input_gds),
        "",
        str(args.output),
        args.allow_empty,
    )
    print(f"T10_GDS_MERGE_RC={result}")
    return int(result)


if __name__ == "__main__":
    raise SystemExit(main())
