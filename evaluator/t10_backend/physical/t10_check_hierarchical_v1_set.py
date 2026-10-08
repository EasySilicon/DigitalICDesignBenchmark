#!/usr/bin/env python3
"""Qualify complete, hash-bound hierarchical V1 DRC coverage for T10 PE."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_MACRO_GDS_KEYS = {
    "t10_reference_int_group": "int_group_gds",
    "t10_reference_fp_quad_class0_exact": "class0_gds",
    "t10_reference_fp_quad_class1_exact": "class1_gds",
    "t10_reference_fp_quad_class2_exact": "class2_gds",
    "t10_reference_cpa_postprocess_detailed_swap_pinobsfix": "cpa_renamed_gds",
}


def file_record(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {"path": str(path.resolve()), "present": path.is_file()}
    if not path.is_file():
        return record
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    record.update(bytes=path.stat().st_size, sha256=digest.hexdigest())
    return record


def load(path: Path, label: str, failures: list[str]) -> dict[str, Any]:
    if not path.is_file():
        failures.append(f"missing {label}: {path}")
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        failures.append(f"cannot load {label}: {error}")
        return {}
    if not isinstance(value, dict):
        failures.append(f"{label} is not a JSON object")
        return {}
    return value


def verify_artifact(
    expected: dict[str, Any], label: str, failures: list[str]
) -> dict[str, Any]:
    path_text = expected.get("path") if isinstance(expected, dict) else None
    if not path_text:
        failures.append(f"{label} has no artifact path")
        return {}
    actual = file_record(Path(path_text))
    if not actual.get("present"):
        failures.append(f"{label} artifact is missing: {path_text}")
        return actual
    for field in ("bytes", "sha256"):
        if actual.get(field) != expected.get(field):
            failures.append(
                f"{label} {field} is {actual.get(field)!r}, "
                f"expected {expected.get(field)!r}"
            )
    return actual


def parse_macro_gate(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("macro gate must be CELL=PATH")
    name, path = value.split("=", 1)
    if not name or not path:
        raise argparse.ArgumentTypeError("macro gate must be CELL=PATH")
    return name, Path(path)


def validate_strict_gate(
    gate: dict[str, Any],
    label: str,
    expected_gds_sha256: str,
    expected_deck_sha256: str,
    failures: list[str],
) -> None:
    if gate.get("status") != "pass" or gate.get("failures"):
        failures.append(f"{label} strict DRC gate did not pass cleanly")
    if gate.get("report_summary", {}).get("total_items") != 0:
        failures.append(f"{label} strict DRC gate has nonzero DRC items")
    expected = gate.get("expected_sha256", {})
    if expected.get("gds") != expected_gds_sha256:
        failures.append(f"{label} gate expected GDS hash does not match")
    if expected.get("deck") != expected_deck_sha256:
        failures.append(f"{label} gate expected deck hash does not match")
    artifacts = gate.get("artifacts", {})
    if artifacts.get("gds", {}).get("sha256") != expected_gds_sha256:
        failures.append(f"{label} gate observed GDS hash does not match")
    if artifacts.get("deck", {}).get("sha256") != expected_deck_sha256:
        failures.append(f"{label} gate observed deck hash does not match")
    for name, record in artifacts.items():
        verify_artifact(record, f"{label}.{name}", failures)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gds-manifest", required=True, type=Path)
    parser.add_argument("--view-manifest", required=True, type=Path)
    parser.add_argument("--boundary-gate", required=True, type=Path)
    parser.add_argument("--top-gate", required=True, type=Path)
    parser.add_argument("--macro-gate", action="append", required=True, type=parse_macro_gate)
    parser.add_argument("--expected-v1-deck-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    failures: list[str] = []
    gds_manifest = load(args.gds_manifest, "GDS manifest", failures)
    view_manifest = load(args.view_manifest, "view manifest", failures)
    boundary_gate = load(args.boundary_gate, "boundary gate", failures)
    top_gate = load(args.top_gate, "top gate", failures)
    macro_gate_paths = dict(args.macro_gate)
    if len(macro_gate_paths) != len(args.macro_gate):
        failures.append("macro gate cells are repeated")
    if set(macro_gate_paths) != set(EXPECTED_MACRO_GDS_KEYS):
        failures.append(
            "macro gate cell set differs: "
            f"observed={sorted(macro_gate_paths)} "
            f"expected={sorted(EXPECTED_MACRO_GDS_KEYS)}"
        )

    full_gds = gds_manifest.get("artifacts", {}).get("pe_gds", {})
    full_gds_sha = full_gds.get("sha256")
    verify_artifact(full_gds, "accepted PE GDS", failures)
    view_input = view_manifest.get("input", {})
    if view_input.get("sha256") != full_gds_sha:
        failures.append("view manifest input is not the accepted PE GDS")
    verify_artifact(view_input, "view input", failures)
    top_view = view_manifest.get("output_top_interconnect", {})
    top_view_sha = top_view.get("sha256")
    verify_artifact(top_view, "top-interconnect view", failures)

    if boundary_gate.get("status") != "pass" or boundary_gate.get("failures"):
        failures.append("V1 macro-boundary gate did not pass cleanly")
    if boundary_gate.get("expected_sha256", {}).get("gds") != full_gds_sha:
        failures.append("V1 macro-boundary gate is not bound to the accepted PE GDS")
    for name, record in boundary_gate.get("artifacts", {}).items():
        verify_artifact(record, f"boundary-gate.{name}", failures)
    boundary_macros = {
        record.get("name"): record.get("placement_count")
        for record in boundary_gate.get("macros", [])
        if isinstance(record, dict)
    }
    if set(boundary_macros) != set(EXPECTED_MACRO_GDS_KEYS):
        failures.append("V1 macro-boundary gate does not cover every macro master")
    if any(not isinstance(count, int) or count <= 0 for count in boundary_macros.values()):
        failures.append("V1 macro-boundary gate has an unplaced macro master")

    validate_strict_gate(
        top_gate,
        "top-interconnect",
        str(top_view_sha),
        args.expected_v1_deck_sha256,
        failures,
    )
    gate_records: dict[str, Any] = {
        "top": file_record(args.top_gate),
        "macros": {},
    }
    for cell, key in EXPECTED_MACRO_GDS_KEYS.items():
        path = macro_gate_paths.get(cell)
        if path is None:
            continue
        gate = load(path, f"{cell} gate", failures)
        macro_gds = gds_manifest.get("artifacts", {}).get(key, {})
        verify_artifact(macro_gds, f"{cell} GDS", failures)
        validate_strict_gate(
            gate,
            cell,
            str(macro_gds.get("sha256")),
            args.expected_v1_deck_sha256,
            failures,
        )
        gate_records["macros"][cell] = file_record(path)

    result = {
        "status": "pass" if not failures else "fail",
        "policy": (
            "Complete V1 coverage is the strict zero-item DRC of the reproducible "
            "macro-blackboxed top view plus every placed macro master, combined "
            "with the locked-deck 30 nm macro-boundary separation proof."
        ),
        "failures": failures,
        "expected_v1_deck_sha256": args.expected_v1_deck_sha256,
        "artifacts": {
            "gds_manifest": file_record(args.gds_manifest),
            "view_manifest": file_record(args.view_manifest),
            "boundary_gate": file_record(args.boundary_gate),
            "strict_gates": gate_records,
        },
        "coverage": {
            "top_interconnect_gds_sha256": top_view_sha,
            "macro_masters": sorted(EXPECTED_MACRO_GDS_KEYS),
            "macro_placement_counts": boundary_macros,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
