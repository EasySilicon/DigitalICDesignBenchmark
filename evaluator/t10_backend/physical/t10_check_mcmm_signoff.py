#!/usr/bin/env python3
"""Turn T10 MCMM reports into a strict, machine-checkable qualification gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shlex
from pathlib import Path
from typing import Any


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


def validate_manifest(
    path: Path, failures: list[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.is_file():
        failures.append(f"missing MCMM input manifest: {path}")
        return {}, {}
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        failures.append(f"cannot load MCMM input manifest: {error}")
        return {}, {}
    if manifest.get("schema_version") != 1:
        failures.append("MCMM input manifest schema_version is not 1")
    roles = manifest.get("roles")
    if not isinstance(roles, dict):
        failures.append("MCMM input manifest has no roles object")
        return manifest, {}
    expected_roles = {
        "odb", "sdc", "rcx_rules", "setrc_tcl", "wc_libs", "bc_libs",
        "wc_macro_libs", "bc_macro_libs",
    }
    if set(roles) != expected_roles:
        failures.append(
            "MCMM input manifest roles differ: "
            f"observed={sorted(roles)} expected={sorted(expected_roles)}"
        )
    seen_paths: list[str] = []
    list_roles = {"wc_libs", "bc_libs", "wc_macro_libs", "bc_macro_libs"}
    expected_list_lengths = {role: 5 for role in list_roles}
    for role in sorted(expected_roles & set(roles)):
        if role in list_roles and not isinstance(roles[role], list):
            failures.append(f"MCMM input role {role} is not a list")
            records = []
        elif role not in list_roles and not isinstance(roles[role], dict):
            failures.append(f"MCMM input role {role} is not a scalar record")
            records = []
        else:
            records = roles[role] if isinstance(roles[role], list) else [roles[role]]
        if role in list_roles and not records:
            failures.append(f"MCMM input role {role} is empty")
        if role in list_roles and len(records) != expected_list_lengths[role]:
            failures.append(
                f"MCMM input role {role} has {len(records)} entries, "
                f"expected {expected_list_lengths[role]}"
            )
        for index, expected in enumerate(records):
            label = f"{role}[{index}]" if isinstance(roles[role], list) else role
            if not isinstance(expected, dict) or "path" not in expected:
                failures.append(f"invalid MCMM input record {label}")
                continue
            input_path = Path(expected["path"])
            seen_paths.append(str(input_path.resolve()))
            actual = file_record(input_path)
            if not actual.get("present"):
                failures.append(f"MCMM input is missing: {input_path}")
                continue
            for field in ("bytes", "sha256"):
                if actual.get(field) != expected.get(field):
                    failures.append(
                        f"MCMM input {label} {field} is {actual.get(field)!r}, "
                        f"expected {expected.get(field)!r}"
                    )
    duplicates = sorted(path for path in set(seen_paths) if seen_paths.count(path) > 1)
    if duplicates:
        failures.append("MCMM inputs occur in multiple roles: " + ", ".join(duplicates))
    return manifest, roles


def one_float(pattern: str, text: str, label: str, failures: list[str]) -> float | None:
    matches = re.findall(pattern, text, re.MULTILINE)
    if len(matches) != 1:
        failures.append(f"expected exactly one {label}, found {len(matches)}")
        return None
    value = float(matches[0])
    if not math.isfinite(value):
        failures.append(f"{label} is not finite")
        return None
    return value


def summary_assignments(text: str, failures: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in re.findall(r"(?m)^(T10_[A-Z0-9_]+)=(.*)$", text):
        if key in values:
            failures.append(f"duplicate summary key {key}")
        values[key] = value.strip()
    return values


def scene_report_wns(
    path: Path,
    expected_corner: str,
    expected_path_type: str,
    failures: list[str],
) -> float | None:
    if not path.is_file():
        return None
    text = path.read_text(errors="replace")
    corners = set(re.findall(r"(?m)^Corner: (\S+)$", text))
    path_types = set(re.findall(r"(?m)^Path Type: (\S+)$", text))
    if corners != {expected_corner}:
        failures.append(
            f"{path.name} corners are {sorted(corners)}, expected [{expected_corner!r}]"
        )
    if path_types != {expected_path_type}:
        failures.append(
            f"{path.name} path types are {sorted(path_types)}, "
            f"expected [{expected_path_type!r}]"
        )
    slacks = [
        float(value)
        for value in re.findall(
            r"(?m)^\s+([+-]?[0-9.eE]+)\s+slack \((?:MET|VIOLATED)\)\s*$",
            text,
        )
    ]
    if not slacks:
        failures.append(f"{path.name} contains no reported path slack")
        return None
    if not all(math.isfinite(value) for value in slacks):
        failures.append(f"{path.name} contains non-finite path slack")
        return None
    return min(slacks)


def clock_route_audit(path: Path, failures: list[str]) -> dict[str, Any]:
    """Parse and enforce the routed clock-layer audit emitted by OpenROAD."""
    result: dict[str, Any] = {
        "clock_nets": None,
        "clock_segments": None,
        "clock_via_shapes": None,
        "segments_by_layer": {},
        "span_um_by_layer": {},
    }
    if not path.is_file():
        failures.append(f"missing clock route audit: {path}")
        return result

    lines = [line.split("\t") for line in path.read_text().splitlines()]
    expected_headers = {
        ("metric", "value"),
        ("layer", "segment_count", "bbox_span_um"),
    }
    observed_headers = {tuple(fields) for fields in lines if fields and fields[0] in {"metric", "layer"}}
    if observed_headers != expected_headers:
        failures.append(
            "clock route audit headers differ: "
            f"observed={sorted(observed_headers)} expected={sorted(expected_headers)}"
        )

    scalar_names = {"clock_nets", "clock_segments", "clock_via_shapes"}
    seen_scalars: set[str] = set()
    seen_layers: set[str] = set()
    for fields in lines:
        if not fields or fields[0] in {"metric", "layer"}:
            continue
        if fields[0] in scalar_names:
            if len(fields) != 2 or fields[0] in seen_scalars:
                failures.append(f"invalid clock audit scalar row: {fields!r}")
                continue
            seen_scalars.add(fields[0])
            try:
                value = int(fields[1])
            except ValueError:
                failures.append(f"non-integer clock audit scalar row: {fields!r}")
                continue
            result[fields[0]] = value
            continue
        if re.fullmatch(r"M[0-9]+", fields[0]):
            if len(fields) != 3 or fields[0] in seen_layers:
                failures.append(f"invalid clock audit layer row: {fields!r}")
                continue
            seen_layers.add(fields[0])
            try:
                count = int(fields[1])
                span = float(fields[2])
            except ValueError:
                failures.append(f"invalid clock audit layer values: {fields!r}")
                continue
            if count <= 0 or not math.isfinite(span) or span <= 0:
                failures.append(f"non-positive clock audit layer values: {fields!r}")
            result["segments_by_layer"][fields[0]] = count
            result["span_um_by_layer"][fields[0]] = span
            continue
        failures.append(f"unknown clock route audit row: {fields!r}")

    if seen_scalars != scalar_names:
        failures.append(
            "clock route audit scalar set differs: "
            f"observed={sorted(seen_scalars)} expected={sorted(scalar_names)}"
        )
    if result["clock_nets"] is not None and result["clock_nets"] <= 0:
        failures.append("clock route audit contains no clock nets")
    if result["clock_segments"] is not None and result["clock_segments"] <= 0:
        failures.append("clock route audit contains no routed clock segments")
    segment_total = sum(result["segments_by_layer"].values())
    if result["clock_segments"] is not None and segment_total != result["clock_segments"]:
        failures.append(
            f"clock segment total {segment_total} differs from audit scalar "
            f"{result['clock_segments']}"
        )
    forbidden = sorted(
        layer
        for layer in result["segments_by_layer"]
        if int(layer[1:]) >= 8
    )
    if forbidden:
        failures.append(
            "clock route uses forbidden M8-or-higher layers: "
            + ", ".join(forbidden)
        )
    if not result["segments_by_layer"]:
        failures.append("clock route audit has no per-layer segment rows")
    elif not ({"M6", "M7"} & set(result["segments_by_layer"])):
        failures.append("clock route has no M6/M7 trunk segments")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--setup-uncertainty-ps", required=True, type=float)
    parser.add_argument("--hold-uncertainty-ps", required=True, type=float)
    parser.add_argument("--input-manifest", required=True, type=Path)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-odb-sha256", required=True)
    parser.add_argument("--expected-sdc-sha256", required=True)
    args = parser.parse_args()

    if args.setup_uncertainty_ps <= 0 or args.hold_uncertainty_ps <= 0:
        parser.error("uncertainty values must be positive")
    prefix = args.prefix
    paths = {
        "log": args.log,
        "exit": Path(f"{args.log}.exit"),
        "summary": Path(f"{prefix}_summary.rpt"),
        "spef": Path(f"{prefix}.spef"),
        "setup_wc": Path(f"{prefix}_setup_wc.rpt"),
        "hold_bc": Path(f"{prefix}_hold_bc.rpt"),
        "constraint_coverage": Path(f"{prefix}_constraint_coverage.rpt"),
        "unconstrained": Path(f"{prefix}_unconstrained.rpt"),
        "electrical_wc": Path(f"{prefix}_electrical_wc.rpt"),
        "electrical_bc": Path(f"{prefix}_electrical_bc.rpt"),
        "antenna": Path(f"{prefix}_antenna.rpt"),
        "vdd_connectivity_errors": Path(f"{prefix}_vdd_connectivity.rpt"),
        "vss_connectivity_errors": Path(f"{prefix}_vss_connectivity.rpt"),
        "clock_route_audit": prefix.parent / "t10_clock_route_audit.tsv",
    }
    failures: list[str] = []
    for label, digest in (
        ("--expected-manifest-sha256", args.expected_manifest_sha256),
        ("--expected-odb-sha256", args.expected_odb_sha256),
        ("--expected-sdc-sha256", args.expected_sdc_sha256),
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            parser.error(f"{label} must be lowercase SHA-256")
    manifest, input_roles = validate_manifest(args.input_manifest, failures)
    manifest_record = file_record(args.input_manifest)
    if manifest_record.get("sha256") != args.expected_manifest_sha256:
        failures.append(
            "MCMM input manifest SHA-256 is "
            f"{manifest_record.get('sha256')}, expected {args.expected_manifest_sha256}"
        )
    for role, expected in (
        ("odb", args.expected_odb_sha256),
        ("sdc", args.expected_sdc_sha256),
    ):
        role_record = input_roles.get(role) if input_roles else None
        observed = role_record.get("sha256") if isinstance(role_record, dict) else None
        if observed != expected:
            failures.append(f"MCMM {role} SHA-256 is {observed}, expected {expected}")
    required = (
        "log", "exit", "summary", "spef", "setup_wc", "hold_bc",
        "constraint_coverage", "unconstrained", "electrical_wc",
        "electrical_bc", "antenna", "clock_route_audit",
    )
    for name in required:
        if not paths[name].is_file():
            failures.append(f"missing required artifact {name}: {paths[name]}")

    log = paths["log"].read_text(errors="replace") if paths["log"].is_file() else ""
    summary = (
        paths["summary"].read_text(errors="replace")
        if paths["summary"].is_file()
        else ""
    )
    assignments = summary_assignments(summary, failures)
    assignment_roles = {
        "T10_INPUT_ODB": "odb",
        "T10_INPUT_SDC": "sdc",
        "T10_RCX_RULES": "rcx_rules",
        "T10_SETRC_TCL": "setrc_tcl",
        "T10_WC_LIB_FILES": "wc_libs",
        "T10_BC_LIB_FILES": "bc_libs",
        "T10_WC_MACRO_LIB_FILES": "wc_macro_libs",
        "T10_BC_MACRO_LIB_FILES": "bc_macro_libs",
    }
    for key, role in assignment_roles.items():
        role_value = input_roles.get(role) if input_roles else None
        records = role_value if isinstance(role_value, list) else [role_value]
        expected_paths = [
            str(Path(record["path"]).resolve())
            for record in records if isinstance(record, dict)
        ]
        observed_text = assignments.get(key)
        try:
            observed_paths = (
                [str(Path(token).resolve()) for token in shlex.split(observed_text)]
                if observed_text is not None else []
            )
        except ValueError as error:
            failures.append(f"summary {key} is not a valid path list: {error}")
            continue
        if observed_paths != expected_paths:
            failures.append(
                f"summary {key} resolves to {observed_paths!r}, "
                f"expected {expected_paths!r}"
            )
    setup_wns = one_float(r"^worst slack max ([+-]?[0-9.eE]+)$", summary,
                          "setup WNS", failures)
    setup_tns = one_float(r"^tns max ([+-]?[0-9.eE]+)$", summary,
                          "setup TNS", failures)
    hold_wns = one_float(r"^worst slack min ([+-]?[0-9.eE]+)$", summary,
                         "hold WNS", failures)
    hold_tns = one_float(r"^tns min ([+-]?[0-9.eE]+)$", summary,
                         "hold TNS", failures)
    setup_scene_wns = scene_report_wns(
        paths["setup_wc"], "wc", "max", failures
    )
    hold_scene_wns = scene_report_wns(
        paths["hold_bc"], "bc", "min", failures
    )
    for label, global_wns, scene_wns in (
        ("setup", setup_wns, setup_scene_wns),
        ("hold", hold_wns, hold_scene_wns),
    ):
        if global_wns is not None and scene_wns is not None and not math.isclose(
            global_wns, scene_wns, rel_tol=0.0, abs_tol=1e-4
        ):
            failures.append(
                f"global {label} WNS {global_wns} ps does not match the "
                f"required scene WNS {scene_wns} ps"
            )

    if assignments.get("T10_SETUP_SCENE") != "wc":
        failures.append("setup scene is not wc")
    if assignments.get("T10_HOLD_SCENE") != "bc":
        failures.append("hold scene is not bc")
    expected_uncertainty = {
        "T10_SETUP_UNCERTAINTY_PS": args.setup_uncertainty_ps,
        "T10_HOLD_UNCERTAINTY_PS": args.hold_uncertainty_ps,
    }
    for key, expected in expected_uncertainty.items():
        try:
            actual = float(assignments[key])
        except (KeyError, ValueError):
            failures.append(f"missing or invalid {key}")
        else:
            if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-9):
                failures.append(f"{key} is {actual}, expected {expected}")

    if setup_wns is not None and setup_wns < 0:
        failures.append(f"setup WNS is negative: {setup_wns} ps")
    if hold_wns is not None and hold_wns < 0:
        failures.append(f"hold WNS is negative: {hold_wns} ps")
    if setup_tns is not None and not math.isclose(setup_tns, 0.0, abs_tol=1e-9):
        failures.append(f"setup TNS is nonzero: {setup_tns} ps")
    if hold_tns is not None and not math.isclose(hold_tns, 0.0, abs_tol=1e-9):
        failures.append(f"hold TNS is nonzero: {hold_tns} ps")

    if paths["exit"].is_file() and paths["exit"].read_text().strip() != "0":
        failures.append("OpenROAD runner exit status is nonzero")
    if re.search(r"(?m)^\[?ERROR|^Error:", log):
        failures.append("OpenROAD log contains an error")
    if re.search(r"STA-1140|library .* already exists", log):
        failures.append("OpenROAD log contains a duplicate Liberty library warning")
    for expected in (
        "Found 0 net violations.",
        "Found 0 pin violations.",
        "All shapes on net VDD are connected.",
        "All shapes on net VSS are connected.",
    ):
        if log.count(expected) != 1:
            failures.append(f"expected exactly one log marker: {expected}")

    zero_length_reports = (
        "constraint_coverage", "unconstrained", "electrical_wc",
        "electrical_bc", "antenna",
    )
    for name in zero_length_reports:
        if paths[name].is_file() and paths[name].stat().st_size != 0:
            failures.append(f"{name} report is nonempty")
    for name in ("vdd_connectivity_errors", "vss_connectivity_errors"):
        if paths[name].is_file() and paths[name].stat().st_size != 0:
            failures.append(f"{name} report is nonempty")

    clock_route = clock_route_audit(paths["clock_route_audit"], failures)

    result = {
        "status": "pass" if not failures else "fail",
        "setup_scene": assignments.get("T10_SETUP_SCENE"),
        "hold_scene": assignments.get("T10_HOLD_SCENE"),
        "setup_uncertainty_ps": args.setup_uncertainty_ps,
        "hold_uncertainty_ps": args.hold_uncertainty_ps,
        "setup_wns_ps": setup_wns,
        "setup_scene_wns_ps": setup_scene_wns,
        "setup_tns_ps": setup_tns,
        "hold_wns_ps": hold_wns,
        "hold_scene_wns_ps": hold_scene_wns,
        "hold_tns_ps": hold_tns,
        "clock_route": clock_route,
        "failures": failures,
        "expected_sha256": {
            "input_manifest": args.expected_manifest_sha256,
            "odb": args.expected_odb_sha256,
            "sdc": args.expected_sdc_sha256,
        },
        "input_manifest": manifest_record,
        "artifacts": {name: file_record(path) for name, path in paths.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
