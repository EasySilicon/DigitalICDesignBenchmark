#!/usr/bin/env python3
"""Exploratory ASAP7 gate-activity and OpenROAD TT power measurement.

Uses a checked workload to validate the VCD-to-OpenROAD path. This is not the
frozen hidden power workload or an official PPA score.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import subprocess
from pathlib import Path

from elf_image import load_elf, write_hex_image
from public_check import ROOT

STDCELL = ROOT.parent / "vendor/asap7/verilog/stdcell"
LIBERTY = ROOT.parent / "vendor/asap7/lib/NLDM"
SEQUENTIAL = ROOT.parent / "env/asap7_seq_sim.v"
POWER_CLOCKS = {
    "T01": (), "T02": ("clock",), "T03": ("clk",),
    "T04": ("clk",), "T05": ("clk",),
    "T06": ("wr_clk", "rd_clk"), "T07": ("clk",),
    "T08": ("clk",), "T09": ("clk",),
}
PARAMETERS = {"T03": ("WIDTH=32", "DEPTH=16"),
              "T05": ("N=8", "WIDTH=32"),
              "T06": ("WIDTH=32", "DEPTH=16")}


def tcl_brace(value: Path | str) -> str:
    return "{" + str(value).replace("\\", "\\\\").replace("}", "\\}") + "}"


def instrument_testbench(task: str, original: Path, output: Path) -> str:
    source = original.read_text()
    if source.count("endmodule") != 1:
        raise ValueError("power probe expects a single-module testbench")
    for top, instance in (("synchronous_fifo", "#(.WIDTH(WIDTH), .DEPTH(DEPTH))"),
                          ("round_robin_stream_arbiter", "#(.N(N), .WIDTH(WIDTH))"),
                          ("asynchronous_fifo", "#(.WIDTH(WIDTH), .DEPTH(DEPTH))")):
        source = source.replace(f"{top} {instance} dut", f"{top} dut")
    if task in {"T07", "T08"}:
        # The zero-delay cell simulator starts registers at zero. Force a
        # reset falling edge before the APB monitor samples the first setup.
        source = source.replace("clk = 0; rst_n = 0;",
                                "clk = 0; rst_n = 1; #1; rst_n = 0;")
    ready = ("wait(rst_n); #1;" if task in {"T03", "T04", "T07", "T08", "T09"}
             else "wait(wr_rst_n && rd_rst_n); #1;" if task == "T06" else "")
    monitor = ("initial begin\n  string vcd_path;\n"
               "  if ($value$plusargs(\"POWER_VCD=%s\", vcd_path)) begin\n"
               f"    {ready}\n"
               "    $dumpfile(vcd_path);\n    $dumpvars(0,dut);\n"
               "  end\nend\n")
    output.write_text(source.replace("endmodule", monitor + "endmodule"))
    return "tb_cpu_elf" if task == "T09" else f"tb_{task}"


def vcd_stats(path: Path, top: str, clock_names: tuple[str, ...]) -> tuple[float, dict]:
    scale = None
    symbols = {}
    scopes = []
    in_header = True
    current_time = 0
    last_time = 0
    edges: dict[str, list[int]] = {name: [] for name in clock_names}
    with path.open() as stream:
        for raw in stream:
            line = raw.strip()
            if in_header:
                if line.startswith("$timescale"):
                    match = re.search(r"(\d+)\s*(fs|ps|ns|us)", line)
                    if not match:
                        raise ValueError("unsupported VCD timescale")
                    scale = int(match.group(1)) * {
                        "fs": 1e-15, "ps": 1e-12, "ns": 1e-9, "us": 1e-6}[match.group(2)]
                elif line.startswith("$scope"):
                    scopes.append(line.split()[2])
                elif line.startswith("$upscope"):
                    scopes.pop()
                elif line.startswith("$var") and scopes[-2:] == [top, "dut"]:
                    parts = line.split()
                    if parts[4] in clock_names:
                        symbols[parts[3]] = parts[4]
                elif line.startswith("$enddefinitions"):
                    in_header = False
                continue
            if line.startswith("#"):
                current_time = int(line[1:])
                last_time = current_time
            elif line.startswith("1") and line[1:] in symbols:
                edges[symbols[line[1:]]].append(current_time)
    if scale is None or last_time <= 0:
        raise ValueError("VCD lacks time scale or activity window")
    periods = {}
    for name, timestamps in edges.items():
        differences = [b - a for a, b in zip(timestamps, timestamps[1:]) if b > a]
        if not differences:
            raise ValueError(f"VCD clock {name} never completes a period")
        periods[name] = round(statistics.median(differences) * scale * 1e12, 3)
    return last_time * scale, periods


def run(args: argparse.Namespace) -> dict:
    result_dir = args.flow_result_dir.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for file in ("6_final.v", "6_final.odb", "6_final.spef", "6_final.sdc"):
        if not (result_dir / file).is_file():
            raise FileNotFoundError(result_dir / file)
    tb_path = (ROOT / "public" / "tb_cpu_elf.sv" if args.task == "T09" else
               ROOT / "public" / f"tb_{args.task}.sv")
    top = instrument_testbench(args.task, tb_path, output / "tb_power.sv")
    cell_files = sorted(STDCELL.glob("asap7sc7p5t_*RVT_TT_*.v"))
    cell_files = [path for path in cell_files if "_SEQ_" not in path.name]
    command = ["verilator", "--binary", "--timing", "--trace", "--trace-underscore", "-Wno-fatal",
               "-Wno-SPECIFYIGN", "-j", "4", "--top-module", top,
               "--Mdir", str(output / "build")]
    for definition in PARAMETERS.get(args.task, ()):
        command.append(f"-G{definition}")
    command += [str(output / "tb_power.sv"), str(result_dir / "6_final.v"),
                str(SEQUENTIAL), *map(str, cell_files)]
    compilation = subprocess.run(command, text=True, capture_output=True, timeout=300)
    (output / "compile.log").write_text(compilation.stdout + compilation.stderr)
    if compilation.returncode:
        raise RuntimeError("gate-level workload compile failed; see compile.log")
    vcd = output / "activity.vcd"
    run_command = [str(output / "build" / f"V{top}"),
                   f"+POWER_VCD={vcd}", f"+SEED={args.seed}"]
    if args.task == "T09":
        if args.elf is None:
            raise ValueError("T09 requires --elf")
        image = output / "image.hex"
        write_hex_image(load_elf(args.elf), image)
        run_command += [f"+IMAGE={image}", "+MAX_CYCLES=200000"]
    simulation = subprocess.run(run_command, text=True, capture_output=True,
                                timeout=600)
    (output / "simulation.log").write_text(simulation.stdout + simulation.stderr)
    if simulation.returncode or ("CPU_ELF_PASS" if args.task == "T09" else
                                 f"PUBLIC_PASS {args.task}") not in simulation.stdout:
        raise RuntimeError("gate-level workload failed self-check; see simulation.log")
    duration, periods = vcd_stats(vcd, top, POWER_CLOCKS[args.task])
    power_sdc = (result_dir / "6_final.sdc").read_text()
    for name, period in periods.items():
        pattern = rf"(create_clock -name {re.escape(name)}_clock -period )\S+"
        power_sdc, count = re.subn(pattern, rf"\g<1>{period:g}", power_sdc)
        if count != 1:
            raise ValueError(f"cannot set VCD clock period for {name}")
    (output / "power.sdc").write_text(power_sdc)
    libraries = sorted(path for path in LIBERTY.glob("asap7sc7p5t_*RVT_TT_nldm_*.lib*")
                       if "FAKE" not in path.name)
    script = "".join(f"read_liberty {tcl_brace(lib)}\n" for lib in libraries)
    script += (f"read_db {tcl_brace(result_dir / '6_final.odb')}\n"
               f"read_sdc {tcl_brace(output / 'power.sdc')}\n"
               f"read_spef {tcl_brace(result_dir / '6_final.spef')}\n"
               f"read_vcd -scope {top}/dut {tcl_brace(vcd)}\n"
               "report_activity_annotation\nreport_power\n")
    (output / "power.tcl").write_text(script)
    evaluated = subprocess.run([shutil.which("openroad") or "openroad", "-exit",
                                "-no_init", "-no_splash", str(output / "power.tcl")],
                               text=True, capture_output=True, timeout=300)
    report = evaluated.stdout + evaluated.stderr
    (output / "power.log").write_text(report)
    if evaluated.returncode:
        raise RuntimeError("OpenROAD TT power analysis failed; see power.log")
    annotated = re.search(r"vcd\s+(\d+)\s+unannotated\s+(\d+)", report)
    total = re.search(r"^Total\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", report,
                      re.MULTILINE)
    if not annotated or not total:
        raise RuntimeError("power report lacks annotation or total power")
    annotated_count, missing_count = map(int, annotated.groups())
    annotation_ratio = annotated_count / (annotated_count + missing_count)
    if annotation_ratio < 0.95:
        raise RuntimeError(f"activity annotation {annotation_ratio:.1%} below 95%")
    internal, switching, leakage, total_power = map(float, total.groups())
    return {"task": args.task, "flow_result_dir": str(result_dir),
            "seed": args.seed, "ops": args.ops, "vcd_window_seconds": duration,
            "vcd_clock_period_ps": periods, "activity_annotation": annotation_ratio,
            "power_w": {"internal": internal, "switching": switching,
                        "leakage": leakage, "total": total_power},
            "energy_j_per_op": total_power * duration / args.ops,
            "measurement": "exploratory workload; no official PPA score"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=POWER_CLOCKS)
    parser.add_argument("--flow-result-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ops", type=int, required=True)
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--elf", type=Path)
    args = parser.parse_args()
    if args.ops <= 0:
        parser.error("--ops must be positive")
    try:
        result = run(args)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        result = {"task": args.task, "phase": "failed", "error": str(exc)}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result.get("phase") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
