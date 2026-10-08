#!/usr/bin/env python3
"""Reject incomplete PE timing models before launching the 4x4 tile flow."""

from __future__ import annotations

import argparse
from pathlib import Path


ARC_MARKERS = (
    "timing_type : setup_rising",
    "timing_type : hold_rising",
    "timing_type : rising_edge",
    "timing_type : min_clock_tree_path",
    "timing_type : max_clock_tree_path",
)


def counts(text: str) -> dict[str, int]:
    return {marker: text.count(marker) for marker in ARC_MARKERS}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("context", type=Path)
    args = parser.parse_args()

    base = args.base.read_text()
    context = args.context.read_text()
    base_counts = counts(base)
    context_counts = counts(context)
    if context_counts != base_counts:
        raise ValueError(
            f"PE context timing arcs changed shape: base={base_counts}, "
            f"context={context_counts}"
        )
    if context_counts["timing_type : setup_rising"] != 184:
        raise ValueError(f"expected 184 PE input setup arcs: {context_counts}")
    if context_counts["timing_type : min_clock_tree_path"] != 1 or \
            context_counts["timing_type : max_clock_tree_path"] != 1:
        raise ValueError(f"PE clock-tree arcs are incomplete: {context_counts}")
    compact = context.replace(" ", "")
    if "cell(\"t10_reference_pe\")" not in compact and \
            "cell(t10_reference_pe)" not in compact:
        raise ValueError("context Liberty does not describe t10_reference_pe")
    print("T10_PE_CONTEXT_LIB_CHECK", context_counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
