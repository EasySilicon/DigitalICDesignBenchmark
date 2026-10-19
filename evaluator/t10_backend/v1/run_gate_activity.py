#!/usr/bin/env python3
"""Compile/check the complete v15 gate model and collect 1 GHz native SAIF.

No power value is emitted here: every scope must subsequently be mapped to
its same-seed routed ODB/SPEF, checked for annotation, and averaged over PEs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "evaluator"))
from ppa_power_probe import check_t10_workload, instrument_testbench, useful_operations
from make_t10_power_vectors import create
from run_layout import BLOCKS, variant

HISTORICAL = {
    "pe": "ic_t10_frozen_pe_exact_v15_margin_escape_m7_wc_p1000_seed11",
    "fp0": "ic_t10_frozen_fp_class0_m7_wc_p1000_seed11",
    "fp1": "ic_t10_frozen_fp_class1_cornerio_h50_m7_wc_p1000_seed11",
    "fp2": "ic_t10_frozen_fp_class2_cornerio_h50_m7_wc_p1000_seed11",
    "int": "ic_t10_frozen_int_group_exact_v2_m7_wc_p1000_seed11",
    "cpa": "ic_t10_frozen_cpa_postprocess_exact_v2_m7_wc_p1000_seed11",
}


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4*1024**2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def limits():
    resource.setrlimit(resource.RLIMIT_AS, (30 * 1024**3, 30 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CORE, (0,0))
    os.nice(10)


def run(command, log, cwd):
    started = time.time()
    print(f"RUN {log}", flush=True)
    with log.open("w") as stream:
        subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                       cwd=cwd, check=True, preexec_fn=limits)
    return time.time()-started


def hierblock(source):
    # Add only a compilation boundary; mapped connectivity is unchanged.
    return re.sub(r"(\bmodule\s+[^;]+;)", r"\1\n/* verilator hier_block */", source)


def primitive_trace_off(source):
    # Physical nets remain visible in their containing mapped PE/macro.
    # Primitive pin aliases are redundant and explode full-DUT SAIF memory.
    return re.sub(r"(?m)^module\b.*?^\s*endmodule\b",
                  lambda m:"/* verilator tracing_off */\n"+m.group(0)+"\n/* verilator tracing_on */",
                  source,flags=re.S)


def shell_trace_off(source):
    def convert(match):
        body=match.group(0)
        if not re.search(r"\binput\s+(?:wire\s+)?clk\s*;",body):
            raise ValueError("mapped shell module lacks its expected clock port")
        # Retain a trace-only clock alias to keep child-library trace callbacks
        # reachable. It does not enter any physical power measurement.
        body=re.sub(r"\bendmodule\b$", "/* verilator tracing_on */\nwire t10_power_trace_clock;\nassign t10_power_trace_clock = clk;\nendmodule",body)
        return "/* verilator tracing_off */\n"+body+"\n/* verilator tracing_on */"
    return re.sub(r"\bmodule\s+.*?\bendmodule\b",convert,source,flags=re.S)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, choices=(11, 29, 47), required=True)
    parser.add_argument("--orfs", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--gate-shell", type=Path, required=True)
    parser.add_argument("--compile-only", action="store_true")
    parser.add_argument("--label", default="activity")
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--reuse-build", action="store_true")
    parser.add_argument("--reuse-simulation", action="store_true")
    parser.add_argument("--refresh-testbench", action="store_true")
    parser.add_argument("--pe-only-trace", action="store_true")
    parser.add_argument("--functional-only", action="store_true")
    parser.add_argument("--windowed-saif", action="store_true",
                        help="use the audited local delayed-open SAIF writer correction")
    args = parser.parse_args()
    if args.reuse_simulation and not args.reuse_build:
        parser.error("--reuse-simulation requires --reuse-build")
    if args.refresh_testbench and (not args.reuse_build or args.reuse_simulation):
        parser.error("--refresh-testbench requires --reuse-build and a new simulation")
    if args.functional_only and args.reuse_simulation:
        parser.error("functional-only diagnostics cannot reuse an activity simulation")
    flow = args.orfs.resolve() / "flow"
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.label):
        parser.error("label must be a simple directory name")
    out = args.work.resolve() / f"seed{args.seed}_{args.label}"
    out.mkdir(parents=True, exist_ok=True)
    sources = []
    provenance = []
    originals = [("shell", args.gate_shell.resolve())]
    for block in ("pe", "fp0", "fp1", "fp2", "int", "cpa"):
        label = HISTORICAL[block] if args.seed == 11 else variant(args.seed, block)
        original = flow / "results/asap7" / BLOCKS[block][0] / label / "6_final.v"
        originals.append((block, original))
    for block, original in originals:
        source = original.read_text()
        if block != "shell" and len(re.findall(r"\bmodule\s", source)) != 1:
            raise RuntimeError(f"unexpected module set in {original}")
        if args.pe_only_trace and block=="shell":
            source=shell_trace_off(source)
        modified = out / f"{block}.v"
        modified.write_text(hierblock(source))
        sources.append(modified)
        provenance.append(dict(block=block, path=str(original), sha256=sha(original),
                               annotated_source_sha256=sha(modified)))
    vectors = args.work.resolve() / "workload"
    if not (vectors / "manifest.json").exists():
        create(vectors)
    top = instrument_testbench("T10", REPO / "evaluator/hidden/tb_hidden_T10_stream.sv", out / "tb_power.sv")
    # The existing instrumentation uses $dumpfile/$dumpvars. --trace-saif
    # changes the writer, not the checked workload or its clock.
    cells = sorted((REPO / "vendor/asap7/verilog/stdcell").glob("asap7sc7p5t_*RVT_TT_*.v"))
    cells = [p for p in cells if "_SEQ_" not in p.name]
    sequential=REPO / "env/asap7_seq_sim.v"
    cell_provenance=[]
    if args.pe_only_trace:
        filtered=[]
        for original in [sequential,*cells]:
            copy=out / ("direct_nets_"+original.name)
            copy.write_text(primitive_trace_off(original.read_text()))
            filtered.append(copy)
            cell_provenance.append(dict(original=str(original),sha256=sha(original),instrumented_sha256=sha(copy)))
        sequential,*cells=filtered
    command = ["verilator", "--binary", "--hierarchical", "--timing", "--assert",
               "--trace-saif", "--trace-underscore", "--trace-max-width", "262144",
               "--output-split", "10000", "--output-split-cfuncs", "10000",
               "-Wno-fatal", "-Wno-SPECIFYIGN", "-j", "4", "--top-module", top,
               "--Mdir", str(out / "build"), str(out / "tb_power.sv"),
               *map(str, sources), str(sequential), *map(str, cells)]
    manifest = dict(layout_seed=args.seed, measurement_status="activity_not_yet_power_qualified",
                    reference_rtl_sha256=sha(REPO / "evaluator/reference/T10_v15/rtl/npu_systolic_matmul_16x16.sv"),
                    netlists=provenance, waveform_format="SAIF", clock_period_ps=1000,
                    trace_policy="all_direct_pe_and_internal_macro_nets" if args.pe_only_trace else "all_scopes",
                    simulation_cell_models=cell_provenance,
                    waveform_scope=f"TOP/{top}/dut", workload_manifest_sha256=sha(vectors / "manifest.json"),
                    compile_command=command, verilator=subprocess.check_output(["verilator", "--version"], text=True).strip())
    if args.reuse_build:
        staged = json.loads((out/"staged_build_manifest.json").read_text())
        expected_modules = {}
        for source in sources:
            for match in re.finditer(r"\bmodule\s+([^\s(;]+)(.*?\bendmodule\b)",source.read_text(),re.S):
                expected_modules[match.group(1)] = hashlib.sha256((match.group(0)+"\n").encode()).hexdigest()
        for item in staged["modules"]:
            refreshing = item["module"] == "testbench" and args.refresh_testbench
            if (not refreshing and sha(Path(item["source"])) != item["source_sha256"]) or sha(Path(item["args_file"])) != item["args_sha256"]:
                raise RuntimeError("compiled-model provenance has changed")
            if item["module"] != "testbench" and expected_modules.pop(item["module"],None) != item["source_sha256"]:
                raise RuntimeError("compiled module does not match the selected mapped netlist")
            if item["module"] == "testbench" and not refreshing and sha(out/"tb_power.sv") != item["source_sha256"]:
                raise RuntimeError("testbench differs from compiled workload")
        if expected_modules or staged["planning_sources_used_for_simulation"] is not False or not (out/"build"/f"V{top}").is_file():
            raise RuntimeError("incomplete compiled gate model")
        manifest["compile_seconds"] = None
        manifest["reused_build"] = True
        if args.refresh_testbench:
            original_manifest = out / ("staged_build_manifest."+sha(out/"staged_build_manifest.json")[:16]+".json")
            if not original_manifest.exists():
                shutil.copyfile(out/"staged_build_manifest.json",original_manifest)
            testbench = next(item for item in staged["modules"] if item["module"]=="testbench")
            run(["verilator","-f",testbench["args_file"]],out/"testbench_refresh.log",REPO)
            run(["make","-C",str(out/"build"),"-f","Vtb_hidden_T10_stream_hier.mk","-j4","hier_build"],out/"compile_refresh.log",REPO)
            staged.setdefault("testbench_refreshes",[]).append(dict(previous_sha256=testbench["source_sha256"],current_sha256=sha(out/"tb_power.sv")))
            testbench["source_sha256"] = sha(out/"tb_power.sv")
            (out/"staged_build_manifest.json").write_text(json.dumps(staged,indent=2)+"\n")
        manifest["staged_build_manifest_sha256"] = sha(out/"staged_build_manifest.json")
    elif args.staged:
        from staged_gate_build import build
        started = time.time()
        build(command, sources, out / "tb_power.sv", out, run, REPO)
        manifest["compile_seconds"] = time.time()-started
        manifest["staged_build_manifest_sha256"] = sha(out/"staged_build_manifest.json")
    else:
        manifest["compile_seconds"] = run(command, out / "compile.log", REPO)
    executable = out / "build" / f"V{top}"
    if args.windowed_saif:
        from saif_window import build
        executable, manifest["saif_writer"] = build(out, top, run, REPO)
    (out / "compile_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if args.compile_only:
        (out / "compile_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        return
    if args.functional_only:
        manifest["simulation_seconds"] = run([
            str(out/"build"/f"V{top}"),f"+VECTORS={vectors}","+CASE_COUNT=200"],out/"functional_only.log",REPO)
        check_t10_workload((out/"functional_only.log").read_text(),vectors,200)
        manifest.update(measurement_status="functional_only_not_activity_or_power_qualified",
                        numerical_oracle_passed=True,protocol_and_latency_passed=True,
                        completed_matrix_blocks=200,output_points_checked=51200)
        (out/"functional_only.json").write_text(json.dumps(manifest,indent=2)+"\n")
        print("PASS complete gate DUT functional diagnostic; no power claim",flush=True)
        return
    if args.reuse_simulation:
        if not (out/"activity.saif").is_file():
            raise RuntimeError("no saved activity to validate")
        saved = json.loads((out/"activity_manifest.json").read_text())
        if saved.get("activity_sha256") != sha(out/"activity.saif") or \
                saved.get("saif_writer") != manifest.get("saif_writer") or \
                saved.get("netlists") != manifest.get("netlists") or \
                saved.get("workload_manifest_sha256") != manifest.get("workload_manifest_sha256"):
            raise RuntimeError("saved simulation does not match this activity model/writer")
        manifest["simulation_seconds"] = None
        manifest["reused_simulation"] = True
    else:
        # Preserve every previous measurement before rerunning this owned
        # build directory, including measurements rejected by later gates.
        if (out/"activity_manifest.json").exists():
            previous = out/("previous_activity_"+sha(out/"activity_manifest.json")[:16])
            previous.mkdir(exist_ok=False)
            for name in ("activity_manifest.json", "activity.saif", "simulation.log",
                         "average.saif", "merge_audit.json"):
                if (out/name).exists():
                    shutil.move(str(out/name), str(previous/name))
        manifest["simulation_seconds"] = run([
            str(executable), f"+POWER_VCD={out / 'activity.saif'}",
            f"+VECTORS={vectors}", "+CASE_COUNT=200"], out / "simulation.log", REPO)
    log = (out / "simulation.log").read_text()
    check_t10_workload(log, vectors, 200)
    if useful_operations("T10", log) != 200:
        raise RuntimeError("gate workload operation count is not 200")
    manifest.update(numerical_oracle_passed=True, protocol_and_latency_passed=True,
                    completed_matrix_blocks=200, output_points_checked=51200,
                    activity_sha256=sha(out / "activity.saif"))
    (out / "activity_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"PASS: seed {args.seed}, complete gate DUT, 200 blocks and 51200 oracle outputs", flush=True)


if __name__ == "__main__":
    main()
