#!/usr/bin/env python3
"""Exploratory routed PPA run for one DUT; does not produce official scores.

The same numerical constraints are applied to every task. This entry point is
for calibrating the shared ORFS/ASAP7 parameter set against reference designs.
It deliberately does not estimate power without a checked switching workload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from public_check import ROOT, sources_from_filelist

DESIGNS = {
    "T01": ("priority_encoder_8x3", "", ()),
    "T02": ("serial_in_parallel_out_8bit", "", ("clock",)),
    "T03": ("synchronous_fifo", "WIDTH 32 DEPTH 16", ("clk",)),
    "T04": ("apb4_timer", "", ("clk",)),
    "T05": ("round_robin_stream_arbiter", "N 8 WIDTH 32", ("clk",)),
    "T06": ("asynchronous_fifo", "WIDTH 32 DEPTH 16", ("wr_clk", "rd_clk")),
    "T07": ("axi4lite_to_apb4_bridge", "", ("clk",)),
    "T08": ("direct_mapped_writeback_cache", "", ("clk",)),
    "T09": ("rv32i_five_stage_cpu", "", ("clk",)),
    "T10": ("npu_systolic_matmul_16x16", "", ("clk",)),
}


def constraint_text(top: str, clocks: tuple[str, ...], period: int,
                    io_delay_ratio: float) -> str:
    lines = [f"current_design {top}"]
    for clock in clocks:
        lines.append(f"create_clock -name {clock}_clock -period {period} [get_ports {clock}]")
    lines.append(f"create_clock -name vclk -period {period}")
    delay = period * io_delay_ratio
    lines.append(f"set_input_delay {delay:g} -clock vclk [all_inputs -no_clocks]")
    lines.append(f"set_output_delay {delay:g} -clock vclk [all_outputs]")
    if clocks == ("wr_clk", "rd_clk"):
        lines.append("set_clock_groups -asynchronous "
                     "-group [get_clocks wr_clk_clock] -group [get_clocks rd_clk_clock]")
        lines.extend("set_false_path -from [get_ports {" + reset + "}]"
                     for reset in ("wr_rst_n", "rd_rst_n"))
    elif clocks and top != "serial_in_parallel_out_8bit":
        lines.append("set_false_path -from [get_ports rst_n]")
    return "\n".join(lines) + "\n"


def write_config(path: Path, top: str, source_files: list[Path], sdc: Path,
                 parameters: str, utilization: int, density: float,
                 corner: str) -> None:
    fields = [
        ("PLATFORM", "asap7"), ("DESIGN_NAME", top),
        ("VERILOG_FILES", " ".join(str(p) for p in source_files)),
        ("SDC_FILE", str(sdc)), ("CORE_UTILIZATION", str(utilization)),
        ("CORE_ASPECT_RATIO", "1"), ("CORE_MARGIN", "0.5"),
        ("PLACE_DENSITY", str(density)), ("SYNTH_USE_SYN", "0"),
        ("SYNTH_HIERARCHICAL", "0"), ("CORNER", corner),
    ]
    if parameters:
        fields.append(("VERILOG_TOP_PARAMS", parameters))
    write_if_changed(path, "".join(f"export {key} = {value}\n"
                                   for key, value in fields))


def write_if_changed(path: Path, content: str) -> None:
    if not path.is_file() or path.read_text() != content:
        path.write_text(content)


def report_fields(path: Path, metrics: Path, period: int) -> dict:
    report = path.read_text()
    fields = {}
    found = re.search(r"worst slack max (-?[0-9.]+)", report)
    if found:
        fields["worst_slack_ps"] = float(found.group(1))
        fields["critical_path_delay_ps"] = period - fields["worst_slack_ps"]
    measurements = json.loads(metrics.read_text())
    fields["cell_area_um2"] = measurements["finish__design__instance__area__stdcell"]
    fields["worst_slack_ps"] = measurements["finish__timing__setup__ws"]
    fields["critical_path_delay_ps"] = period - fields["worst_slack_ps"]
    fields["minimum_period_ps"] = {
        name: float(value) for name, value in
        re.findall(r"(\S+) period_min = ([0-9.]+)", report)
    }
    return fields


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=DESIGNS)
    parser.add_argument("submission", type=Path)
    parser.add_argument("--orfs-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--period-ps", type=int, default=750)
    parser.add_argument("--io-delay-ratio", type=float, default=0.20)
    parser.add_argument("--utilization", type=int, default=10)
    parser.add_argument("--density", type=float, default=0.60)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--corner", choices=("BC", "TC", "WC"), default="BC")
    parser.add_argument("--num-cores", type=int, default=4)
    args = parser.parse_args()
    if (args.period_ps <= 0 or not 0 <= args.io_delay_ratio < 0.5 or
            not 0 < args.utilization < 100 or not 0 < args.density < 1 or
            args.seed < 0 or args.num_cores < 1):
        parser.error("invalid numerical PPA parameter")
    orfs = args.orfs_root.resolve()
    flow = orfs / "flow"
    if not (flow / "Makefile").is_file():
        parser.error(f"ORFS flow Makefile missing: {flow}")
    yosys = shutil.which("yosys")
    openroad = shutil.which("openroad")
    if not yosys or not openroad:
        parser.error("yosys and openroad must be available on PATH")
    source_files = sources_from_filelist(args.submission.resolve())
    top, parameters, clocks = DESIGNS[args.task]
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sdc = output / "constraint.sdc"
    config = output / "config.mk"
    write_if_changed(sdc, constraint_text(top, clocks, args.period_ps,
                                          args.io_delay_ratio))
    write_config(config, top, source_files, sdc, parameters,
                 args.utilization, args.density, args.corner)
    digest = hashlib.sha256()
    digest.update(config.read_bytes())
    digest.update(sdc.read_bytes())
    for source in source_files:
        digest.update(source.read_bytes())
    variant = (f"ic_probe_{args.task.lower()}_{args.corner.lower()}_p{args.period_ps}_"
               f"u{args.utilization}_d{args.density:g}_s{args.seed}_"
               f"{digest.hexdigest()[:10]}")
    report = flow / "reports" / "asap7" / top / variant / "6_finish.rpt"
    final_log = flow / "logs" / "asap7" / top / variant / "6_report.log"
    metrics = final_log.with_suffix(".json")
    start = time.monotonic()
    command = ["make", "-C", str(flow), f"DESIGN_CONFIG={config}",
               f"PLATFORM_DIR={ROOT.parent / 'vendor' / 'asap7'}",
               f"FLOW_VARIANT={variant}", "LIB_MODEL=NLDM",
               "ASAP7_USE_VT=RVT", f"GRT_SEED={args.seed}",
               f"OR_SEED={args.seed}", f"NUM_CORES={args.num_cores}",
               f"YOSYS_EXE={yosys}", f"OPENROAD_EXE={openroad}",
               f"logs/asap7/{top}/{variant}/6_report.log"]
    with (output / "make.log").open("w") as log:
        outcome = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                 check=False)
    result = {"task": args.task, "variant": variant, "exit_code": outcome.returncode,
              "elapsed_seconds": round(time.monotonic() - start, 3),
              "period_ps": args.period_ps, "utilization": args.utilization,
              "density": args.density, "seed": args.seed, "corner": args.corner,
              "report": str(report), "measurement": "exploratory; no power or PPA score"}
    if outcome.returncode == 0 and report.is_file():
        result.update(report_fields(report, metrics, args.period_ps))
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if outcome.returncode == 0 and report.is_file() else 1


if __name__ == "__main__":
    raise SystemExit(main())
