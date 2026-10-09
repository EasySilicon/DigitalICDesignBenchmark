#!/usr/bin/env python3
"""Checked T11-power-v1 workload; deliberately separate from T01–T10 hashes."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

from ppa_power_probe import LIBERTY, SEQUENTIAL, STDCELL, tcl_brace, vcd_stats

ROOT = Path(__file__).resolve().parent
WORKLOAD = ROOT / "fixtures/t11_mac/tb_power.sv"
CLOCKS = ("logic_clk", "tx_clk", "rx_clk")
EXPECTED_OPS = 4296


def checked_macro_power(report: str, expected_count: int) -> list[dict]:
    rows = re.findall(r"^T08_SRAM_POWER name=(\S+) internal=(\S+) switching=(\S+) leakage=(\S+) total=(\S+)$", report, re.M)
    if len(rows) != expected_count or len({row[0] for row in rows}) != expected_count:
        raise ValueError("missing or duplicate per-macro power evidence")
    result = []
    for name, *values in rows:
        internal, switching, leakage, total = map(float, values)
        if not all(math.isfinite(v) and v >= 0 for v in (internal, switching, leakage, total)) or internal <= 0 or total <= 0:
            raise ValueError("SRAM model has zero/invalid active internal power")
        result.append(dict(instance=name, internal=internal, switching=switching, leakage=leakage, total=total))
    return result


def checked_operations(log: str) -> int:
    markers = re.findall(r"^T08_POWER_PASS TX=3 RX=5 DROP=1 OPS=4296$", log, re.M)
    operations = re.findall(r"^POWER_OPS=(\d+)$", log, re.M)
    if len(markers) != 1 or operations != [str(EXPECTED_OPS)]:
        raise ValueError("T08 workload missing unique checked completion/useful-byte count")
    return EXPECTED_OPS


def activity_window(path: Path) -> tuple[float, dict]:
    end_seconds, periods = vcd_stats(path, "tb_t08_power", CLOCKS)
    # VCD timestamps are absolute simulation times. Do not charge the reset
    # interval before capture starts as part of the measured activity window.
    scale = None
    first = None
    with path.open() as stream:
        for raw in stream:
            match = re.search(r"\$timescale\s+(\d+)\s*(fs|ps|ns|us)", raw)
            if match:
                scale = int(match[1]) * {"fs": 1e-15, "ps": 1e-12,
                                        "ns": 1e-9, "us": 1e-6}[match[2]]
            if raw.startswith("#"):
                first = int(raw[1:])
                break
    if scale is None or first is None or end_seconds <= first * scale:
        raise ValueError("T08 VCD has no positive measured activity window")
    if periods != {clock: 1000.0 for clock in CLOCKS}:
        raise ValueError("T08 power clocks must all be 1000 ps")
    return end_seconds - first * scale, periods


def run(result_dir: Path, output: Path, seed: int, *, sram_route: Path | None = None) -> dict:
    result_dir, output = result_dir.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    required = ("6_final.v", "6_final.odb", "6_final.spef", "6_final.sdc")
    for name in required:
        if not (result_dir / name).is_file():
            raise FileNotFoundError(result_dir / name)
    digest = hashlib.sha256()
    route = None
    macro_files = []
    if sram_route is not None:
        from t11_sram import contract, MACRO_SIM, MACRO_LIB
        route = json.loads(sram_route.read_text())
        if route.get("sram_contract") != contract() or route.get("exit_code") != 0:
            raise ValueError("SRAM route/model provenance mismatch")
        from ppa_aggregate import expected_result_dir
        if expected_result_dir(route["report"]) != result_dir:
            raise ValueError("power result directory differs from SRAM route")
        macro_files = [MACRO_SIM]
        digest.update(contract()["contract_sha256"].encode())
    for path in (WORKLOAD, Path(__file__), ROOT / "ppa_power_probe.py", SEQUENTIAL):
        payload = path.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    digest.update(str(seed).encode())
    cell_files = sorted(path for path in STDCELL.glob("asap7sc7p5t_*RVT_TT_*.v")
                        if "_SEQ_" not in path.name)
    command = ["verilator", "--binary", "--timing", "--assert", "--trace",
               "--trace-underscore", "-Wno-fatal", "-Wno-SPECIFYIGN", "-j", "4",
               "--top-module", "tb_t08_power", "--Mdir", str(output / "build"),
               str(WORKLOAD), str(result_dir / "6_final.v"), str(SEQUENTIAL),
               *map(str, cell_files), *map(str, macro_files)]
    compiled = subprocess.run(command, text=True, capture_output=True, timeout=1200)
    (output / "compile.log").write_text(compiled.stdout + compiled.stderr)
    if compiled.returncode:
        raise RuntimeError("T08 gate workload failed compilation; see compile.log")
    vcd = output / "activity.vcd"
    executed = subprocess.run([str(output / "build/Vtb_t08_power"),
                              f"+SEED={seed}", f"+POWER_VCD={vcd}"],
                             text=True, capture_output=True, timeout=1200)
    log = executed.stdout + executed.stderr
    (output / "simulation.log").write_text(log)
    if executed.returncode:
        raise RuntimeError("T08 gate workload failed self-check; see simulation.log")
    operations = checked_operations(log)
    duration, periods = activity_window(vcd)
    libraries = sorted(path for path in LIBERTY.glob("asap7sc7p5t_*RVT_TT_nldm_*.lib*")
                       if "FAKE" not in path.name)
    script = "".join(f"read_liberty {tcl_brace(path)}\n" for path in libraries)
    if route:
        script += f"read_liberty {tcl_brace(MACRO_LIB)}\n"
    script += (f"read_db {tcl_brace(result_dir / '6_final.odb')}\n"
               f"read_sdc {tcl_brace(result_dir / '6_final.sdc')}\n"
               f"read_spef {tcl_brace(result_dir / '6_final.spef')}\n"
               f"read_vcd -scope tb_t08_power/dut {tcl_brace(vcd)}\n"
               "report_activity_annotation\nreport_power\n")
    if route:
        script += ('puts "T08_SRAM_POWER_BEGIN"\n'
                   'set macro_cells [get_cells -hierarchical -filter {ref_name == fakeram7_tdp_4096x32} *]\n'
                   'report_power -instances $macro_cells\n'
                   'foreach inst $macro_cells {\n'
                   '  lassign [sta::instance_power $inst [sta::cmd_scene]] internal switching leakage total\n'
                   '  puts "T08_SRAM_POWER name=[sta::get_full_name $inst] internal=$internal switching=$switching leakage=$leakage total=$total"\n'
                   '}\n'
                   'puts "T08_SRAM_POWER_END"\n')
    tcl = output / "power.tcl"
    tcl.write_text(script)
    measured = subprocess.run([shutil.which("openroad") or "openroad", "-exit",
                               "-no_init", "-no_splash", str(tcl)],
                              text=True, capture_output=True, timeout=600)
    report = measured.stdout + measured.stderr
    (output / "power.log").write_text(report)
    if measured.returncode:
        raise RuntimeError("T08 TT power analysis failed; see power.log")
    annotated = re.search(r"vcd\s+(\d+)\s+unannotated\s+(\d+)", report)
    total = re.search(r"^Total\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", report, re.M)
    if not annotated or not total:
        raise ValueError("power report lacks activity annotation or total power")
    good, missing = map(int, annotated.groups())
    annotation = good / (good + missing)
    if annotation < 0.95:
        raise ValueError(f"T08 activity annotation {annotation:.1%} below 95%")
    internal, switching, leakage, power = map(float, total.groups())
    evidence = {"task": "T08", "flow_result_dir": str(result_dir),
            "workload_id": "T11-power-v1", "workload_sha256": digest.hexdigest(),
            "workload_parameters": {"seed": seed, "useful_unit": "accepted_body_octet",
                                    "tx_frames": 3, "rx_frames": 5, "policy_drops": 1},
            "seed": seed, "ops": operations, "vcd_window_seconds": duration,
            "vcd_clock_period_ps": periods, "activity_annotation": annotation,
            "power_w": {"internal": internal, "switching": switching,
                        "leakage": leakage, "total": power},
            "energy_j_per_op": power * duration / operations,
            "measurement": "checked single-seed gate-level power workload"}
    if route:
        macro_report = report.split("T08_SRAM_POWER_BEGIN", 1)[1].split("T08_SRAM_POWER_END", 1)[0]
        macro_power = checked_macro_power(macro_report, route["macro_count"])
        evidence.update(sram_contract=route["sram_contract"],
                        macro_count=route["macro_count"],
                        macro_power_report=macro_report.strip(),
                        macro_power_w=macro_power,
                        routed_netlist_sha256=hashlib.sha256((result_dir / "6_final.v").read_bytes()).hexdigest())
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flow-result-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=20260928)
    parser.add_argument("--sram-route", type=Path, help="matching routed result.json for SRAM policy")
    args = parser.parse_args()
    try:
        result = run(args.flow_result_dir, args.output_dir, args.seed, sram_route=args.sram_route)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        result = {"task": "T08", "phase": "failed", "error": str(exc)}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 1 if result.get("phase") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
