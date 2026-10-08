#!/usr/bin/env python3
"""Strictly qualify one completed T10 KLayout DRC run without waivers."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import klayout.db  # noqa: F401  # Register RDB geometry value types.
import klayout.rdb as rdb


def called(obj: object, name: str) -> Any:
    value = getattr(obj, name)
    return value() if callable(value) else value


def file_record(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def category_label(report: rdb.ReportDatabase, item: rdb.RdbItem) -> str:
    category = report.category_by_id(called(item, "category_id"))
    name = str(called(category, "name")).strip()
    description = str(called(category, "description")).strip()
    if name:
        return name
    if description:
        return description.split(":", 1)[0].strip()
    return str(called(category, "path")).strip("' ") or "<unnamed>"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gds", required=True, type=Path)
    parser.add_argument("--deck", required=True, type=Path)
    parser.add_argument("--expected-gds-sha256", required=True)
    parser.add_argument("--expected-deck-sha256", required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    exit_file = Path(f"{args.log}.exit")
    for path in (args.gds, args.deck, args.report, args.log, exit_file):
        if not path.is_file():
            parser.error(f"missing input: {path}")

    for label, digest in (
        ("--expected-gds-sha256", args.expected_gds_sha256),
        ("--expected-deck-sha256", args.expected_deck_sha256),
    ):
        if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            parser.error(f"{label} must be a 64-digit SHA-256")

    artifact_records = {
        "gds": file_record(args.gds),
        "deck": file_record(args.deck),
        "report": file_record(args.report),
        "log": file_record(args.log),
        "exit": file_record(exit_file),
    }
    failures: list[str] = []
    expected_hashes = {
        "gds": args.expected_gds_sha256.lower(),
        "deck": args.expected_deck_sha256.lower(),
    }
    for name, expected in expected_hashes.items():
        actual = artifact_records[name]["sha256"]
        if actual != expected:
            failures.append(
                f"{name} SHA-256 is {actual}, expected {expected}"
            )
    log = args.log.read_text(errors="replace")
    exit_text = exit_file.read_text().strip()
    if exit_text != "0":
        failures.append(f"KLayout runner exit status is {exit_text!r}, expected '0'")
    error_patterns = {
        "error line": r"(?m)^ERROR:",
        "worker allocation failure": r"std::bad_alloc",
        "signal termination": r"Command terminated by signal",
        "nonzero time exit status": r"(?m)^\s*Exit status: [1-9][0-9]*\s*$",
    }
    for label, pattern in error_patterns.items():
        if re.search(pattern, log):
            failures.append(f"KLayout log contains {label}")
    report_marker = f"Writing report database: {args.report.resolve()} .."
    if log.count(report_marker) != 1:
        failures.append(
            "expected exactly one KLayout report-write marker for the requested RDB"
        )
    if len(re.findall(r"(?m)^Total elapsed:", log)) != 1:
        failures.append("expected exactly one KLayout total-elapsed marker")

    report = rdb.ReportDatabase()
    try:
        report.load(str(args.report))
    except Exception as error:  # KLayout exposes multiple C++ exception types.
        failures.append(f"cannot load KLayout RDB: {error}")
        report_items = 0
        by_category: collections.Counter[str] = collections.Counter()
        by_cell: collections.Counter[str] = collections.Counter()
    else:
        report_items = int(report.num_items())
        by_category = collections.Counter()
        by_cell = collections.Counter()
        for item in report.each_item():
            by_category[category_label(report, item)] += 1
            cell = report.cell_by_id(called(item, "cell_id"))
            by_cell[str(called(cell, "qname"))] += 1
        if report_items != 0:
            failures.append(f"KLayout RDB contains {report_items} DRC item(s)")

    result = {
        "status": "pass" if not failures else "fail",
        "policy": (
            "zero-waiver: expected GDS/deck hashes, process success, complete "
            "error-free log, readable RDB, and zero DRC items"
        ),
        "expected_sha256": expected_hashes,
        "failures": failures,
        "report_summary": {
            "total_items": report_items,
            "items_by_category": dict(sorted(by_category.items())),
            "items_by_cell": dict(sorted(by_cell.items())),
        },
        "artifacts": artifact_records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
