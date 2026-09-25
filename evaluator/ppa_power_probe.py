#!/usr/bin/env python3
"""Exploratory ASAP7 gate-activity and OpenROAD TT power measurement.

Uses a checked workload to validate the VCD-to-OpenROAD path. This is not the
frozen hidden power workload or an official PPA score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import statistics
import subprocess
from pathlib import Path

from elf_image import load_elf, write_hex_image
from matmul_oracle import check_output
from public_check import ROOT

STDCELL = ROOT.parent / "vendor/asap7/verilog/stdcell"
LIBERTY = ROOT.parent / "vendor/asap7/lib/NLDM"
SEQUENTIAL = ROOT.parent / "env/asap7_seq_sim.v"
POWER_CLOCKS = {
    "T01": (), "T02": ("clock",), "T03": ("clk",),
    "T04": ("clk",), "T05": ("clk",),
    "T06": ("wr_clk", "rd_clk"), "T07": ("clk",),
    "T08": ("clk",), "T09": ("clk",), "T10": ("clk",),
}
PARAMETERS = {"T03": ("WIDTH=32", "DEPTH=16"),
              "T05": ("N=8", "WIDTH=32"),
              "T06": ("WIDTH=32", "DEPTH=16")}
MONITORED_OPS = {
    "T01": ("in", "1", "1"),
    "T02": ("posedge clock", "1", "1"),
    "T03": ("posedge clk", "rst_n", "out_valid && out_ready"),
    "T04": ("posedge clk", "rst_n", "PSEL && PENABLE && PREADY"),
    "T05": ("posedge clk", "rst_n", "out_valid && out_ready"),
    "T06": ("posedge rd_clk", "rd_rst_n", "rd_valid && rd_ready"),
    "T07": ("posedge clk", "rst_n", "(BVALID && BREADY) + (RVALID && RREADY)"),
    "T08": ("posedge clk", "rst_n", "rsp_valid && rsp_ready"),
    "T10": ("posedge clk", "rst_n", "out_valid && out_ready && out_row == 4'd15"),
}
LOG_OPS = {
    "T09": r"CPU_ELF_PASS .*commits=(\d+)",
}


def tcl_brace(value: Path | str) -> str:
    return "{" + str(value).replace("\\", "\\\\").replace("}", "\\}") + "}"


def instrument_testbench(task: str, original: Path, output: Path) -> str:
    source = original.read_text()
    if source.count("endmodule") != 1:
        raise ValueError("power probe expects a single-module testbench")
    match = re.search(r"\bmodule\s+(\w+)", source)
    if match is None:
        raise ValueError("power probe cannot identify testbench top module")
    top = match.group(1)
    for module_name, instance in (("synchronous_fifo", "#(.WIDTH(WIDTH), .DEPTH(DEPTH))"),
                                  ("round_robin_stream_arbiter", "#(.N(N), .WIDTH(WIDTH))"),
                                  ("asynchronous_fifo", "#(.WIDTH(WIDTH), .DEPTH(DEPTH))")):
        source = source.replace(f"{module_name} {instance} dut", f"{module_name} dut")
    if task == "T03" and top == "tb_hidden_T03":
        # Gate primitives start at 0 in two-state Verilator. Let the testbench's
        # initial rst_n=1 settle before the first asynchronous falling edge.
        source = source.replace("reset_fifo(0);", "#1; reset_fifo(0);", 1)
    if task == "T04" and top == "tb_hidden_T04":
        source = source.replace("    reset_timer();", "    #1; reset_timer();", 1)
    if task in {"T07", "T08"}:
        # The zero-delay cell simulator starts registers at zero. Force a
        # reset falling edge before the APB monitor samples the first setup.
        source = source.replace("clk = 0; rst_n = 0;",
                                "clk = 0; rst_n = 1; #1; rst_n = 0;")
    ready = ("wait(!rst_n); wait(rst_n); #1;" if task == "T10" else
             "wait(rst_n); #1;" if task in {"T03", "T04", "T07", "T08", "T09"}
             else "wait(wr_rst_n && rd_rst_n); #1;" if task == "T06" else "")
    monitor = ("initial begin\n  string vcd_path;\n"
               "  if ($value$plusargs(\"POWER_VCD=%s\", vcd_path)) begin\n"
               f"    {ready}\n"
               "    power_active = 1;\n"
               "    $dumpfile(vcd_path);\n    $dumpvars(0,dut);\n"
               "  end\nend\n")
    instrumentation = "bit power_active = 0;\n"
    if task in MONITORED_OPS:
        event, enabled, accepted = MONITORED_OPS[task]
        instrumentation += ("longint unsigned power_ops = 0;\n"
                            f"always @({event}) if (power_active && ({enabled})) "
                            f"power_ops = power_ops + ({accepted});\n"
                            "final if (power_active) "
                            "$display(\"POWER_OPS=%0d\", power_ops);\n")
    output.write_text(source.replace("endmodule", instrumentation + monitor + "endmodule"))
    return top


def useful_operations(task: str, simulation_log: str) -> int:
    pattern = r"POWER_OPS=(\d+)" if task in MONITORED_OPS else LOG_OPS[task]
    matches = re.findall(pattern, simulation_log)
    if len(matches) != 1:
        raise ValueError(f"{task}: expected exactly one useful-operation count")
    count = int(matches[0])
    if count <= 0:
        raise ValueError(f"{task}: zero useful operations")
    return count


def check_t10_workload(log: str, vectors: Path, case_count: int) -> None:
    if not 1 <= case_count <= 1024:
        raise ValueError("T10 case count outside hidden testbench capacity")
    markers = re.findall(r"^MM_CASE (\d+) ([01]) ([01]) ([01]) (\d+)$",
                         log, re.MULTILINE)
    if len(markers) != case_count or [int(row[0]) for row in markers] != list(range(case_count)):
        raise RuntimeError("T10 workload missing or duplicated case marker")
    if any(row[1:] != ("1", "1", "1", "16") for row in markers):
        raise RuntimeError("T10 workload protocol or latency check failed")
    reset = {int(i): passed == "1" for i, passed in
             re.findall(r"^MM_RESET (\d+) ([01])$", log, re.MULTILINE)}
    rows: dict[int, dict[int, int]] = {}
    for index, row, value in re.findall(r"^MM_ROW (\d+) (\d+) ([0-9a-fA-F]+)$",
                                        log, re.MULTILINE):
        index, row = int(index), int(row)
        if row in rows.setdefault(index, {}):
            raise RuntimeError("T10 workload duplicated output row")
        rows[index][row] = int(value, 16)
    files = {name: [int(line, 16) for line in (vectors / f"{name}.mem").read_text().splitlines()]
             for name in ("a", "b", "as", "bs", "mode", "reset")}
    if any(len(files[name]) != case_count for name in ("as", "bs", "mode", "reset")) or \
            any(len(files[name]) != case_count * 16 for name in ("a", "b")):
        raise ValueError("T10 workload vector file length mismatch")
    for index in range(case_count):
        if files["reset"][index] and not reset.get(index, False):
            raise RuntimeError(f"T10 workload reset probe failed at case {index}")
        if set(rows.get(index, {})) != set(range(16)):
            raise RuntimeError(f"T10 workload missing row at case {index}")
        mode = files["mode"][index]
        beats = 16 if mode in (1, 2, 3) else 4 if mode in (6, 9) else 8
        errors = check_output(files["a"][16 * index:16 * index + beats],
                              files["b"][16 * index:16 * index + beats],
                              files["as"][index], files["bs"][index], mode,
                              [rows[index][row] for row in range(16)])
        if errors:
            raise RuntimeError(f"T10 workload numerical mismatch at case {index}: {errors[0]}")


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
    tb_path = (args.testbench if args.testbench is not None else
               ROOT / "public" / ("tb_cpu_elf.sv" if args.task == "T09" else
                                  f"tb_{args.task}.sv"))
    workload_digest = hashlib.sha256()
    for payload in (tb_path.read_bytes(), Path(__file__).read_bytes(),
                    str(args.seed).encode(), str(args.power_goal).encode()):
        workload_digest.update(len(payload).to_bytes(8, "big"))
        workload_digest.update(payload)
    if args.elf is not None:
        elf_bytes = args.elf.read_bytes()
        workload_digest.update(len(elf_bytes).to_bytes(8, "big"))
        workload_digest.update(elf_bytes)
    if args.task == "T10":
        if args.vectors is None or args.case_count is None or args.testbench is None:
            raise ValueError("T10 requires --vectors, --case-count and --testbench")
        for name in ("a", "b", "as", "bs", "mode", "pause", "stall", "reset"):
            payload = (args.vectors / f"{name}.mem").read_bytes()
            workload_digest.update(len(payload).to_bytes(8, "big"))
            workload_digest.update(payload)
        workload_digest.update(str(args.case_count).encode())
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
    if args.task == "T10":
        run_command += [f"+VECTORS={args.vectors.resolve()}",
                        f"+CASE_COUNT={args.case_count}"]
    if args.power_goal is not None:
        if args.task != "T06" or args.testbench is None:
            raise ValueError("--power-goal requires a T06 evaluator-owned testbench")
        run_command.append(f"+POWER_GOAL={args.power_goal}")
    simulation = subprocess.run(run_command, text=True, capture_output=True,
                                timeout=600)
    (output / "simulation.log").write_text(simulation.stdout + simulation.stderr)
    if simulation.returncode:
        raise RuntimeError("gate-level workload failed self-check; see simulation.log")
    if args.task == "T10":
        check_t10_workload(simulation.stdout, args.vectors, args.case_count)
    elif args.testbench is not None:
        groups = re.findall(r"^IC_GROUP (AC-\d+) (\d+) (\d+)$",
                            simulation.stdout, re.MULTILINE)
        behavioral_groups = [(name, good, total) for name, good, total in groups
                             if not (args.task == "T06" and name == "AC-31")]
        if not behavioral_groups or any(int(good) != int(total) or int(total) <= 0
                                        for _, good, total in behavioral_groups):
            raise RuntimeError("hidden gate workload failed group checks; see simulation.log")
    elif ("CPU_ELF_PASS" if args.task == "T09" else
          f"PUBLIC_PASS {args.task}") not in simulation.stdout:
        raise RuntimeError("gate-level workload missed completion marker; see simulation.log")
    ops = useful_operations(args.task, simulation.stdout)
    if args.ops is not None and args.ops != ops:
        raise ValueError(f"declared --ops={args.ops} differs from measured {ops}")
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
            "seed": args.seed, "workload_sha256": workload_digest.hexdigest(),
            "ops": ops, "vcd_window_seconds": duration,
            "vcd_clock_period_ps": periods, "activity_annotation": annotation_ratio,
            "power_w": {"internal": internal, "switching": switching,
                        "leakage": leakage, "total": total_power},
            "energy_j_per_op": total_power * duration / ops,
            "measurement": "exploratory workload; no official PPA score"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=POWER_CLOCKS)
    parser.add_argument("--flow-result-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ops", type=int,
                        help="optional cross-check against workload-measured operations")
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--elf", type=Path)
    parser.add_argument("--vectors", type=Path,
                        help="T10 frozen power workload vector directory")
    parser.add_argument("--case-count", type=int,
                        help="T10 number of matrix blocks in the power workload")
    parser.add_argument("--testbench", type=Path,
                        help="evaluator-owned single-module checked workload")
    parser.add_argument("--power-goal", type=int,
                        help="T06 hidden power workload transactions per clock-ratio phase")
    args = parser.parse_args()
    if args.ops is not None and args.ops <= 0:
        parser.error("--ops must be positive")
    if args.power_goal is not None and not 1024 <= args.power_goal <= 34000:
        parser.error("--power-goal must be in [1024,34000]")
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
