#!/usr/bin/env python3
"""Extend the legal T10 tile hook for the 38-bit final result hop.

The old stages remain in their measured row corridors. One new stage per
column is seeded beside its result bank, where detailed placement must still
check site legality. This script only generates a placement experiment; its
output is not a timing qualification.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("old_hook", type=Path)
    parser.add_argument("new_hook", type=Path)
    parser.add_argument("--unreset-valid", action="store_true")
    args = parser.parse_args()
    lines = args.old_hook.read_text().splitlines()
    assert lines[-1] == "remove_buffers"
    # The 39th result bit was provably redundant, so remove those placements.
    old = [line for line in lines[:-1] if not re.search(r"data_pipe\\\[\d+\\\]\\\[38\\\]", line)]
    assert len(lines[:-1]) - len(old) == 28
    assert len(old) == 1206  # 1204 placements and two comments
    if args.unreset_valid:
        old = [
            line.replace("$_DFF_PN0_", "$_DFF_P_")
            if ".valid_pipe" in line else line
            for line in old
        ]

    # The bank lies at x=1949.004. Its left halo ends near x=1937; seed four
    # legal site columns at x=1930.014..1934.874, using the already measured
    # row orientations. The 43 flops for each column occupy eleven site rows.
    row_valid_y = (1469.070, 1008.990, 551.070, 90.990)
    stage_by_column = (4, 3, 2, 2)
    added: list[str] = []
    for r in range(4):
        for c, stage in enumerate(stage_by_column):
            names = [
                ("data_pipe", bit, "$_DFF_P_") for bit in range(38)
            ] + [
                ("slot_pipe", bit, "$_DFF_P_") for bit in range(4)
            ] + [("valid_pipe", None,
                  "$_DFF_P_" if args.unreset_valid else "$_DFF_PN0_")]
            for index, (kind, bit, cell) in enumerate(names):
                suffix = f"\\[{bit}\\]" if bit is not None else ""
                name = (
                    f"result_row\\[{r}\\].result_cell\\[{c}\\]."
                    f"{kind}\\[{stage}\\]{suffix}{cell}"
                )
                x = 1930.014 + (index % 4) * 1.620
                y = row_valid_y[r] + 27.000 + c * 14.040 + (index // 4) * 0.270
                orientation = "MX" if (index // 4) % 2 == 0 else "R0"
                if kind == "valid_pipe":
                    # The routed 38-bit bank exposes write_valid[0] on its
                    # left, [1]/[2] on top, and [3] at the bottom. Place
                    # each final valid flop by its actual physical port.
                    bank_y = 1490.0 - r * 460.0
                    x, y = (
                        (1930.014, bank_y + 21.5),
                        (1971.8, bank_y + 73.9),
                        (1995.3, bank_y + 73.9),
                        (1996.1, bank_y - 6.0),
                    )[c]
                added.append(
                    f"place_inst -name {{{name}}} -location {{{x:.3f} {y:.3f}}} "
                    f"-orientation {orientation} -status PLACED"
                )
    assert len(added) == 688
    args.new_hook.write_text(
        "# Legacy row corridor placement plus one 38-bit final hop at each bank.\n"
        + "\n".join(old + added + ["remove_buffers", ""])
    )
    print(f"wrote {len(old)} prior and {len(added)} final-hop placements")


if __name__ == "__main__":
    main()
