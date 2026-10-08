#!/usr/bin/env python3
"""Copy VDD/VSS boundary geometry between equal-size hierarchical LEFs."""

from pathlib import Path
import re
import sys


def pin_block(text: str, pin: str) -> str:
    match = re.search(
        rf"(?ms)^  PIN {re.escape(pin)}\n.*?^  END {re.escape(pin)}\n", text
    )
    if not match:
        raise SystemExit(f"missing PIN {pin}")
    return match.group(0)


if len(sys.argv) != 4:
    raise SystemExit(f"usage: {sys.argv[0]} PG_SOURCE.lef SIGNAL_SOURCE.lef OUTPUT.lef")

pg_path, signal_path, output_path = map(Path, sys.argv[1:])
pg_text = pg_path.read_text()
signal_text = signal_path.read_text()

size_re = re.compile(r"(?m)^  SIZE .+ ;$")
pg_size = size_re.search(pg_text)
signal_size = size_re.search(signal_text)
if not pg_size or not signal_size or pg_size.group(0) != signal_size.group(0):
    raise SystemExit("LEF macro sizes differ; refusing PG geometry transfer")

merged = signal_text
for pin in ("VDD", "VSS"):
    merged = merged.replace(pin_block(merged, pin), pin_block(pg_text, pin), 1)

if merged == signal_text:
    raise SystemExit("PG merge did not change output")
output_path.write_text(merged)
print(f"T10_LEF_PG_MERGE size='{pg_size.group(0).strip()}' output={output_path}")
