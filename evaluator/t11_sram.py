"""Pinned research SRAM contract and automatic T11 memory technology mapping.

Only new evaluator-owned artifacts are written. No submitted RTL is patched.
The macro is a mixed-corner research abstraction, not a silicon/signoff claim.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from public_check import sources_from_filelist

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT.parent / "vendor/lambdapdk_fakeram7"
FIXTURES = ROOT / "fixtures/t11_mac"
CELL = "fakeram7_tdp_4096x32"
REVISION = "2.0-lambdapdk-tdp-1ghz"
MACRO_LIB = VENDOR / f"upstream/nldm/{CELL}.lib"
MACRO_LEF = VENDOR / f"upstream/lef/{CELL}.lef"
MACRO_SIM = VENDOR / f"sim/{CELL}.v"
CORNER_POLICY = {"setup_standard_cells": "WC", "hold_standard_cells": "WC",
                 "sram_timing": "TT_0.7V_25C_research_model",
                 "power_standard_cells": "TT", "power_sram": "TT",
                 "full_chip_worst_corner_signoff": False}
DRC_SCOPE = "OpenROAD detailed-router interconnect/pin-access DRC; macro internals excluded"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract() -> dict:
    manifest = json.loads((VENDOR / "manifest.json").read_text())
    for relative, expected in manifest["sha256"].items():
        if sha256(VENDOR / relative) != expected:
            raise ValueError(f"SRAM model changed without policy update: {relative}")
    paths = [MACRO_LIB, MACRO_LEF, MACRO_SIM,
             FIXTURES / "sram_libmap.txt", FIXTURES / "sram_map.v",
             FIXTURES / "sram_stub.v", Path(__file__)]
    hashes = {str(p.relative_to(ROOT.parent)): sha256(p) for p in paths}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return {"revision": REVISION, "cell": CELL, "upstream_commit": manifest["upstream_commit"],
            "model_sha256": hashes, "contract_sha256": digest,
            "corner_policy": CORNER_POLICY, "drc_scope": DRC_SCOPE,
            "lvs": "not_performed_not_required_for_research_PPA",
            "capacity_bits_per_macro": 4096 * 32,
            "mapping": "Yosys memory_libmap; independent positive-edge 1W1R; full physical width charged",
            "limitations": ["SRAM delay/power are simplified upstream predictions, not SPICE characterization",
                            "Macro GDS and internal transistor-level DRC/LVS are not provided",
                            "No fabricated SS/FF SRAM corners; timing is explicitly mixed-corner"]}


def prepare(submission: Path, output: Path) -> dict:
    submission, output = submission.resolve(), output.resolve()
    if output.exists():
        raise ValueError("mapping destination exists; use a fresh evidence directory")
    if output == submission or submission in output.parents:
        raise ValueError("mapping output must not modify a submission")
    policy = contract()
    sources = sources_from_filelist(submission)
    originals = {str(p.relative_to(submission)): sha256(p) for p in sources}
    output.mkdir(parents=True)
    rtl = output / "rtl"
    rtl.mkdir()
    def quoted(path):
        if '"' in str(path) or '\n' in str(path):
            raise ValueError("unsafe Yosys path")
        return '"' + str(path) + '"'
    commands = ["read_verilog -sv " + " ".join(map(quoted, sources)),
                f"hierarchy -check -top mac_1g_repair", "proc",
                "setattr -mod -unset keep_hierarchy", "flatten", "opt",
                "memory -nomap", f"write_json {quoted(output / 'before_mapping.json')}",
                f"memory_libmap -lib {quoted(FIXTURES / 'sram_libmap.txt')}",
                f"techmap -map {quoted(FIXTURES / 'sram_map.v')}",
                "opt", "memory_map", "opt",
                f"read_verilog -lib {quoted(FIXTURES / 'sram_stub.v')}",
                "hierarchy -check -top mac_1g_repair", "check -assert",
                f"write_json {quoted(output / 'after_mapping.json')}",
                f"write_verilog -noattr {quoted(rtl / 'mapped.v')}"]
    script = output / "mapping.ys"
    script.write_text("\n".join(commands) + "\n")
    with (output / "mapping.log").open("w") as log:
        result = subprocess.run(["yosys", "-Q", "-T", "-s", str(script)],
                                stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError("T11 memory mapping failed; see mapping.log")
    after = json.loads((output / "after_mapping.json").read_text())
    cells = after["modules"]["mac_1g_repair"]["cells"]
    macros = {name: {"type": c["type"], "connections": c["connections"]}
              for name, c in cells.items() if c["type"] == CELL}
    if not macros:
        raise ValueError("no SRAM inferred; not eligible for this SRAM qualification (no silent FF fallback)")
    if any(sha256(p) != originals[str(p.relative_to(submission))] for p in sources):
        raise ValueError("source changed during SRAM mapping")
    # Simulation uses the qualified behavioral model, synthesis uses Liberty.
    (rtl / "macro.v").write_bytes(MACRO_SIM.read_bytes())
    (rtl / "files.f").write_text("mapped.v\nmacro.v\n")
    evidence = {"task": "T11", "policy": policy, "source_sha256": originals,
                "macro_count": len(macros), "macros": macros,
                "mapped_netlist_sha256": sha256(rtl / "mapped.v"),
                "mapping_status": "mapped_pending_functional_replay",
                "source_submission": str(submission), "mapped_submission": str(output)}
    (output / "mapping.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def validated_mapping(submission: Path, directory: Path) -> dict:
    receipt = json.loads((directory / "mapping.json").read_text())
    original = {str(p.relative_to(submission.resolve())): sha256(p)
                for p in sources_from_filelist(submission.resolve())}
    if receipt["policy"] != contract() or receipt["source_sha256"] != original or \
            receipt["mapped_netlist_sha256"] != sha256(directory / "rtl/mapped.v") or \
            sha256(directory / "rtl/macro.v") != sha256(MACRO_SIM) or \
            (directory / "rtl/files.f").read_text() != "mapped.v\nmacro.v\n":
        raise ValueError("SRAM receipt/model/mapped netlist/source identity changed")
    qualified = json.loads((directory / "qualification.json").read_text())
    if qualified.get("mapped_netlist_sha256") != receipt["mapped_netlist_sha256"] or \
            qualified.get("contract_sha256") != receipt["policy"]["contract_sha256"] or \
            qualified.get("functional_passes") != 111 or qualified.get("stress_passes") != 270:
        raise ValueError("SRAM mapping lacks complete functional/stress replay")
    evidence = qualified.get("evidence_sha256", {})
    if set(evidence) != {"evidence/mapped_functional.json", "evidence/mapped_stress.json"} or \
            any(sha256(directory / name) != digest for name, digest in evidence.items()):
        raise ValueError("SRAM replay evidence is missing or changed")
    functional = json.loads((directory / "evidence/mapped_functional.json").read_text())
    stress = json.loads((directory / "evidence/mapped_stress.json").read_text())
    cases = functional.get("cases", {})
    if functional.get("full_functional_pass") is not True or len(cases) != 37 or \
            any(len(c.get("runs", [])) != 3 or any(r.get("passed") is not True for r in c["runs"]) for c in cases.values()) or \
            stress.get("full_pass") is not True or stress.get("run_count") != 270 or stress.get("passed_count") != 270:
        raise ValueError("SRAM replay reports do not contain 111/270 passing runs")
    return receipt


def geometry_audit(result_dir: Path, output: Path, expected_count: int) -> dict:
    """Count real placed macros and connected input pins, not synthesis promises."""
    script = output / "macro_geometry.tcl"
    script.write_text(f"read_db {{{result_dir / '6_final.odb'}}}\n" + r'''
set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
set count 0
set area 0.0
set missing 0
foreach inst [$block getInsts] {
    set master [$inst getMaster]
    if { ![$master isBlock] } { continue }
    if { [$master getName] != "fakeram7_tdp_4096x32" } { error "unexpected macro" }
    incr count
    set area [expr {$area + [$master getWidth] * double([$master getHeight]) / ($dbu * double($dbu))}]
    foreach pin [$inst getITerms] {
        if { [$pin getIoType] == "INPUT" && [$pin getNet] == "NULL" } { incr missing }
    }
}
puts "T11_MACRO_GEOMETRY count=$count area_um2=$area disconnected_inputs=$missing"
''')
    result = subprocess.run(["openroad", "-exit", "-no_init", "-no_splash", str(script)],
                            text=True, capture_output=True, check=False)
    (output / "macro_geometry.log").write_text(result.stdout + result.stderr)
    match = re.search(r"T11_MACRO_GEOMETRY count=(\d+) area_um2=([\d.eE+-]+) disconnected_inputs=(\d+)",
                      result.stdout)
    if result.returncode or not match or int(match[1]) != expected_count or int(match[3]):
        raise ValueError("placed SRAM count/connectivity audit failed; see macro_geometry.log")
    return {"macro_count": int(match[1]), "macro_area_um2": float(match[2]),
            "disconnected_macro_inputs": int(match[3]), "drc_scope": DRC_SCOPE,
            "lvs_performed": False}
