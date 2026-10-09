#!/usr/bin/env python3
"""Checked routed area/timing run for one DUT and one layout seed.

The same numerical constraints are applied to every task. This entry point is
used to calibrate the shared ORFS/ASAP7 parameter set against reference designs.
Official reference values require three seeds plus checked gate-level power.
T08 is an experimental physical qualification, not a frozen scoring baseline.
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

if __package__:
    from .public_check import ROOT, sources_from_filelist
else:
    from public_check import ROOT, sources_from_filelist

DESIGNS = {
    "T01": ("serdes_rx_comma_aligner", "", ("clk",)),
    "T02": ("synchronous_fifo", "WIDTH 32 DEPTH 16", ("clk",)),
    "T03": ("apb4_timer", "", ("clk",)),
    "T04": ("round_robin_stream_arbiter", "N 8 WIDTH 32", ("clk",)),
    "T05": ("asynchronous_fifo", "WIDTH 32 DEPTH 16", ("wr_clk", "rd_clk")),
    "T06": ("axi4lite_to_apb4_bridge", "", ("clk",)),
    "T07": ("direct_mapped_writeback_cache", "", ("clk",)),
    "T09": ("rv32i_five_stage_cpu", "", ("clk",)),
    "T10": ("npu_systolic_matmul_16x16", "", ("clk",)),
    "T08": ("mac_1g_repair", "", ("logic_clk", "tx_clk", "rx_clk")),
}


T08_IO_DOMAINS = {
    "logic_clk": (
        "tx_axis_tdata tx_axis_tvalid tx_axis_tlast tx_axis_tuser rx_axis_tready",
        "tx_axis_tready rx_axis_tdata rx_axis_tvalid rx_axis_tlast rx_axis_tuser "
        "rx_axis_tagged rx_axis_tci tx_error_underflow rx_error_bad_frame "
        "rx_error_bad_fcs tx_fifo_overflow tx_fifo_bad_frame tx_fifo_good_frame "
        "rx_fifo_overflow rx_fifo_bad_frame rx_fifo_good_frame",
    ),
    "tx_clk": ("", "gmii_txd gmii_tx_en gmii_tx_er"),
    "rx_clk": (
        "gmii_rxd gmii_rx_dv gmii_rx_er cfg_vlan_enable cfg_accept_untagged "
        "cfg_accept_priority cfg_vlan_valid cfg_vlan_vids",
        "rx_vlan_drop",
    ),
}


def t08_constraints(period: int, io_delay_ratio: float) -> str:
    """Uniform-frequency physical qualification; three clocks remain asynchronous.

    Status errors are synchronized into logic_clk by eth_mac_1g_fifo. VLAN
    configuration and the drop event belong to rx_clk, not the AXIS domain.
    No global virtual clock is used: that would silently cut real IO paths
    when the three independent clocks are declared asynchronous.
    """
    lines = ["current_design mac_1g_repair"]
    for clock in T08_IO_DOMAINS:
        lines.append(f"create_clock -name {clock}_clock -period {period} [get_ports {clock}]")
    lines.append("set_clock_groups -asynchronous " + " ".join(
        f"-group [get_clocks {clock}_clock]" for clock in T08_IO_DOMAINS))
    for clock, (inputs, outputs) in T08_IO_DOMAINS.items():
        for direction, ports in (("input", inputs), ("output", outputs)):
            if ports:
                lines.append(f"set_{direction}_delay {period * io_delay_ratio:g} "
                             f"-clock {clock}_clock [get_ports {{{ports}}}]")
    for reset in ("logic_rst", "tx_rst", "rx_rst"):
        lines.append(f"set_false_path -from [get_ports {reset}]")
    return "\n".join(lines) + "\n"


def constraint_text(top: str, clocks: tuple[str, ...], period: int,
                    io_delay_ratio: float, clock_periods: dict[str, int] | None = None) -> str:
    clock_periods = clock_periods or {}
    if top == "mac_1g_repair":
        if any(value != period for value in clock_periods.values()):
            raise ValueError("T08 probe supports only uniform physical clock periods")
        return t08_constraints(period, io_delay_ratio)
    lines = [f"current_design {top}"]
    for clock in clocks:
        clock_period = clock_periods.get(clock, period)
        lines.append(f"create_clock -name {clock}_clock -period {clock_period} [get_ports {clock}]")
    lines.append(f"create_clock -name vclk -period {period}")
    delay = period * io_delay_ratio
    lines.append(f"set_input_delay {delay:g} -clock vclk [all_inputs -no_clocks]")
    lines.append(f"set_output_delay {delay:g} -clock vclk [all_outputs]")
    if clocks == ("wr_clk", "rd_clk"):
        lines.append("set_clock_groups -asynchronous "
                     "-group [get_clocks wr_clk_clock] -group [get_clocks rd_clk_clock]")
        lines.extend("set_false_path -from [get_ports {" + reset + "}]"
                     for reset in ("wr_rst_n", "rd_rst_n"))
    elif clocks:
        lines.append("set_false_path -from [get_ports rst_n]")
    return "\n".join(lines) + "\n"


def write_config(path: Path, top: str, source_files: list[Path], sdc: Path,
                 parameters: str, utilization: int, density: float,
                 corner: str, *, t11_sram: bool = False) -> None:
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
    if top == "mac_1g_repair":
        # The inherited 4096x27 RX and 4096x10 TX FIFOs exceed ORFS's default
        # 4096-bit per-memory guard. Preserve every row/bit in the standard-cell
        # qualification; never shrink memories to get misleading PPA numbers.
        fields.extend((("SYNTH_MEMORY_MAX_BITS", "262144"),
                       ("SYNTH_MOCK_LARGE_MEMORIES", "0")))
        if t11_sram:
            from t11_sram import MACRO_LEF, MACRO_LIB
            fields.extend((("ADDITIONAL_LEFS", str(MACRO_LEF)),
                           ("ADDITIONAL_LIBS", str(MACRO_LIB)),
                           ("SYNTH_HDL_FRONTEND", "")))
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
    fields["hold_worst_slack_ps"] = measurements["finish__timing__hold__ws"]
    fields["setup_violations"] = measurements["finish__timing__drv__setup_violation_count"]
    fields["hold_violations"] = measurements["finish__timing__drv__hold_violation_count"]
    drc_report = path.with_name("5_route_drc.rpt")
    fields["drc_violations"] = 0 if drc_report.is_file() and not drc_report.read_text().strip() else None
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
    parser.add_argument("--period-ps", type=int, default=1000)
    parser.add_argument("--rd-period-ps", type=int, default=1000,
                        help="T05 read-clock period; T05 write clock uses --period-ps")
    parser.add_argument("--io-delay-ratio", type=float, default=0.20)
    parser.add_argument("--utilization", type=int, default=10,
                        help="core utilization; default 10 reproduces the provisional T01-T09 baselines, not a frozen suite-wide requirement")
    parser.add_argument("--density", type=float, default=0.60,
                        help="placement density; default 0.60 reproduces the provisional T01-T09 baselines")
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--corner", choices=("BC", "TC", "WC"), default="WC")
    parser.add_argument("--num-cores", type=int, default=4)
    parser.add_argument("--t08-sram-mapping", type=Path,
                        help="qualified automatic SRAM mapping directory; only for new T08 runs")
    args = parser.parse_args()
    if (args.period_ps <= 0 or args.rd_period_ps <= 0 or not 0 <= args.io_delay_ratio < 0.5 or
            not 0 < args.utilization < 100 or not 0 < args.density < 1 or
            args.seed < 0 or args.num_cores < 1):
        parser.error("invalid numerical PPA parameter")
    if args.task == "T08" and args.period_ps != 1000:
        parser.error("T08 PPA policy 1.0-uniform-1ghz requires --period-ps 1000")
    if args.t08_sram_mapping and (args.task != "T08" or args.corner != "WC"):
        parser.error("T08 SRAM policy requires T08 and WC standard cells; SRAM remains explicit TT")
    orfs = args.orfs_root.resolve()
    flow = orfs / "flow"
    if not (flow / "Makefile").is_file():
        parser.error(f"ORFS flow Makefile missing: {flow}")
    yosys = shutil.which("yosys")
    openroad = shutil.which("openroad")
    if not yosys or not openroad:
        parser.error("yosys and openroad must be available on PATH")
    source_files = sources_from_filelist(args.submission.resolve())
    original_source_files = list(source_files)
    sram_receipt = None
    if args.t08_sram_mapping:
        from t11_sram import validated_mapping
        sram_receipt = validated_mapping(args.submission, args.t08_sram_mapping.resolve())
        source_files = [args.t08_sram_mapping.resolve() / "rtl/mapped.v"]
    top, parameters, clocks = DESIGNS[args.task]
    clock_periods = ({"wr_clk": args.period_ps, "rd_clk": args.rd_period_ps}
                     if args.task == "T05" else {})
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sdc = output / "constraint.sdc"
    config = output / "config.mk"
    write_if_changed(sdc, constraint_text(top, clocks, args.period_ps,
                                          args.io_delay_ratio, clock_periods))
    write_config(config, top, source_files, sdc, parameters,
                 args.utilization, args.density, args.corner, t11_sram=bool(sram_receipt))
    digest = hashlib.sha256()
    digest.update(config.read_bytes())
    digest.update(sdc.read_bytes())
    for source in source_files:
        digest.update(source.read_bytes())
    if sram_receipt:
        digest.update(json.dumps(sram_receipt["policy"], sort_keys=True).encode())
    t05_suffix = f"_rd{args.rd_period_ps}" if args.task == "T05" else ""
    variant = (f"ic_probe_{args.task.lower()}_{args.corner.lower()}_p{args.period_ps}{t05_suffix}_"
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
              "period_ps": args.period_ps,
              "clock_periods_ps": clock_periods or {clock: args.period_ps for clock in clocks},
              "utilization": args.utilization,
              "density": args.density, "seed": args.seed, "corner": args.corner,
              "report": str(report), "measurement": "checked single-seed routed area/timing"}
    if args.task == "T08":
        result.update({
            "qualification_status": "experimental_not_frozen_not_a_score",
            "ppa_policy_revision": "1.0-uniform-1ghz",
            "clock_relationship": "asynchronous",
            "synth_memory_max_bits": 262144,
            "power_status": "not_measured_by_this_probe",
            "memory_mapping": "standard_cells; no SRAM substitution or reduced FIFO depth",
            "source_sha256": {str(source.relative_to(args.submission.resolve())):
                              hashlib.sha256(source.read_bytes()).hexdigest()
                              for source in original_source_files},
            "constraint_sha256": hashlib.sha256(sdc.read_bytes()).hexdigest(),
        })
        if sram_receipt:
            from t11_sram import REVISION
            result.update(ppa_policy_revision=REVISION, memory_mapping="lambdapdk_tdp_4096x32",
                          sram_contract=sram_receipt["policy"],
                          mapped_netlist_sha256=sram_receipt["mapped_netlist_sha256"],
                          mapping_receipt=str(args.t08_sram_mapping.resolve() / "mapping.json"))
    if outcome.returncode == 0 and report.is_file():
        result.update(report_fields(report, metrics, args.period_ps))
        if sram_receipt:
            from t11_sram import geometry_audit
            result.update(geometry_audit(flow / "results/asap7" / top / variant,
                                        output, sram_receipt["macro_count"]))
            result["standard_cell_area_um2"] = result["cell_area_um2"]
            result["cell_area_um2"] += result["macro_area_um2"]
            result["area_accounting"] = "standard-cell area plus full placed macro footprint"
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if outcome.returncode == 0 and report.is_file() else 1


if __name__ == "__main__":
    raise SystemExit(main())
