#!/usr/bin/env python3
"""Build one v15 PE or internal macro without modifying historical results."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RTL = REPO / "evaluator/reference/T10_v15/rtl/npu_systolic_matmul_16x16.sv"
EXPECTED_RTL = "576afc80af06e936089fd8f841fbcc4f555cee254bfa1922f701296e1d092b8e"
BLOCKS = {
    "fp0": ("t10_reference_fp_quad_class0_exact", "physical/t10_frozen_fp_quad/config.mk"),
    "fp1": ("t10_reference_fp_quad_class1_exact", "physical/t10_frozen_fp_quad/config.mk"),
    "fp2": ("t10_reference_fp_quad_class2_exact", "physical/t10_frozen_fp_quad/config.mk"),
    "int": ("t10_reference_int_group", "physical/t10_frozen_int_group/config.mk"),
    "cpa": ("t10_reference_cpa_postprocess", "physical/t10_frozen_cpa_postprocess/config.mk"),
    "pe": ("t10_reference_pe", "physical/t10_frozen_pe/config_exact.mk"),
}


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(4*1024**2),b""):
            digest.update(chunk)
    return digest.hexdigest()


def variant(seed, block):
    return f"ic_t10_v1_v15_seed{seed}_{block}"


def baseline_files(block, design):
    files=[f"6_final.{suffix}" for suffix in ("odb","sdc","spef","v")]
    if block!="pe":
        files += [f"{design}_wc.lib",f"{design}_m7.lef"]
    return files


def completed_baseline(output, result, inputs):
    marker=output/"baseline.completed.json"
    if not marker.exists():
        return False
    saved=json.loads(marker.read_text())
    old_inputs=output/"inputs.json"
    if saved.get("status")!="flow_completed_not_yet_qualified" or \
            not old_inputs.is_file() or saved.get("inputs_sha256")!=sha(old_inputs) or \
            json.loads(old_inputs.read_text())!=inputs or saved.get("result_dir")!=str(result):
        raise RuntimeError("completed baseline has different input provenance")
    files=baseline_files(inputs["block"],BLOCKS[inputs["block"]][0])
    artifacts=saved.get("artifacts",{})
    if set(artifacts)!=set(files):
        raise RuntimeError("completed baseline lacks output hashes; do not rerun over historical results")
    for name,record in artifacts.items():
        path=result/name
        if not path.is_file() or path.stat().st_size!=record["bytes"] or sha(path)!=record["sha256"]:
            raise RuntimeError(f"completed output changed: {path}")
    return True


def limit_memory(cap=30 * 1024**3):
    resource.setrlimit(resource.RLIMIT_AS, (cap,cap))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    os.nice(10)


def run(command, log, env, cwd):
    print(f"RUN {log}", flush=True)
    with log.open("w") as stream:
        cap=int(env.get("T10_MAX_AS_BYTES",30*1024**3))
        subprocess.run(command, env=env, cwd=cwd, stdout=stream,
                       stderr=subprocess.STDOUT, check=True, preexec_fn=lambda:limit_memory(cap))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, choices=(11, 29, 47), required=True)
    parser.add_argument("--block", choices=BLOCKS, required=True)
    parser.add_argument("--orfs", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--route-iterations", type=int, default=20)
    parser.add_argument("--target", choices=("baseline", "synth", "floorplan", "place", "cts", "grt", "route", "do-finish"), default="baseline")
    args = parser.parse_args()
    if not 1 <= args.threads <= 16 or args.route_iterations < 1:
        parser.error("invalid resource limits")
    if sha(RTL) != EXPECTED_RTL:
        raise RuntimeError("v15 RTL does not match the frozen source")
    orfs, work = args.orfs.resolve(), args.work.resolve()
    flow, platform = orfs / "flow", REPO / "vendor/asap7"
    work.mkdir(parents=True, exist_ok=True)
    design, relative_config = BLOCKS[args.block]
    config = HERE / relative_config
    label = variant(args.seed, args.block)
    output = work / label
    output.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(T10_V1_ROOT=str(HERE), T10_V1_RTL=str(RTL),
               T10_LAYOUT_SEED=str(args.seed), PLATFORM_DIR=str(platform),
               DETAILED_ROUTE_END_ITERATION=str(args.route_iterations),
               T10_FP_DESIGN_NAME=design,
               T10_FP_CONSTRAINT=str(HERE / f"physical/t10_frozen_fp_quad/constraint_class{args.block[-1]}.sdc"),
               T10_FP_IO_CONSTRAINTS=str(HERE / "physical/t10_class2_corner_io.tcl") if args.block in ("fp1", "fp2") else "",
               T10_FP_HOLD_SLACK_MARGIN="50" if args.block in ("fp1", "fp2") else "")
    if args.block == "pe":
        # Both 30 and 31.75 GiB AS caps aborted guides-tiles allocation.
        # Virtual address space is not RAM: enforce actual whole-flow usage
        # with cgroup v2 below, rather than substituting a guessed AS limit.
        env.update(T10_MAX_AS_BYTES="-1",MALLOC_ARENA_MAX="2")
        for block, prefix in (("fp0", "FP0"), ("fp1", "FP1"), ("fp2", "FP2"), ("int", "INT"), ("cpa", "CPA")):
            child = BLOCKS[block][0]
            directory = flow / "results/asap7" / child / variant(args.seed, block)
            for suffix, filename in (("LEF", f"{child}_m7.lef"), ("LIB", f"{child}_wc.lib")):
                path = directory / filename
                if not path.is_file():
                    raise RuntimeError(f"same-seed macro missing: {path}")
                env[f"T10_{prefix}_{suffix}"] = str(path)
    openroad, yosys = shutil.which("openroad"), shutil.which("yosys")
    if not openroad or not yosys:
        raise RuntimeError("OpenROAD and Yosys must be installed")
    tool_version = subprocess.check_output([openroad, "-version"], text=True).strip()
    if "08f67ee5ec" not in tool_version:
        raise RuntimeError("wrong OpenROAD version")
    inventory = {str(p.relative_to(HERE)): sha(p) for p in (HERE / "physical").rglob("*") if p.is_file()}
    inputs = dict(rtl_sha256=sha(RTL), config_sha256=sha(config), seed=args.seed,
                  block=args.block, variant=label, threads=args.threads,
                  route_iterations=args.route_iterations, openroad=tool_version,
                  source_config_sha256=inventory)
    old_inputs = output / "inputs.json"
    # Independent seeds have disjoint ORFS variants. Serialize within each
    # seed; a second orchestrator must verify/skip an already finished block.
    # The original seed29 process retains its original global lock in memory.
    with (work / f"eda_seed{args.seed}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if old_inputs.exists() and json.loads(old_inputs.read_text()) != inputs:
            raise RuntimeError("existing run has different inputs; select a new output/variant")
        result = flow / "results/asap7" / design / label
        if args.target=="baseline" and completed_baseline(output,result,inputs):
            print(f"REUSE COMPLETE {label}: verified output hashes; no tools rerun",flush=True)
            return
        old_inputs.write_text(json.dumps(inputs, indent=2) + "\n")
        resources=dict(max_address_space_bytes=int(env.get("T10_MAX_AS_BYTES",30*1024**3)),
                       malloc_arena_max=env.get("MALLOC_ARENA_MAX"),threads=args.threads)
        if args.block=="pe":
            resources.update(max_address_space_bytes=None,memory_max_bytes=32*1024**3,
                             memory_swap_max_bytes=0,cgroup_scope=f"{label}-ram32.scope")
        (output/"runtime_resources.json").write_text(json.dumps(resources,indent=2)+"\n")
        targets = ["route", "do-finish"] if args.target == "baseline" else [args.target]
        started = time.time()
        command = ["make", f"DESIGN_CONFIG={config}", f"FLOW_VARIANT={label}",
                   f"OPENROAD_EXE={openroad}", f"YOSYS_EXE={yosys}",
                   f"NUM_CORES={args.threads}", *targets]
        if args.block=="pe":
            command=["systemd-run","--user","--scope","--quiet",f"--unit={label}-ram32",
                     "--property=MemoryMax=32G","--property=MemorySwapMax=0",*command]
        run(command, output / f"{args.target}.log", env, flow)
        result = flow / "results/asap7" / design / label
        if args.target == "baseline" and args.block != "pe":
            export_env = env | dict(ASAP7_PLATFORM=str(platform), ODB_INPUT=str(result / "6_final.odb"),
                                    SDC_INPUT=str(result / "6_final.sdc"), SPEF_INPUT=str(result / "6_final.spef"),
                                    LIB_OUTPUT=str(result / f"{design}_wc.lib"),
                                    LEF_OUTPUT=str(result / f"{design}_detailed.lef"),
                                    PG_OUTPUT=str(output / "m8_pg.txt"))
            for name in ("bank_timing", "detailed_lef"):
                run([openroad, "-exit", "-no_init", str(HERE / f"t10_export_{name}.tcl")], output / f"export_{name}.log", export_env, flow)
            run([openroad, "-exit", "-no_init", str(HERE / "t10_extract_macro_pg.tcl")], output / "export_pg.log", export_env, flow)
            run([sys.executable, str(HERE / "t10_build_macro_lef.py"), export_env["LEF_OUTPUT"],
                 export_env["PG_OUTPUT"], str(result / f"{design}_m7.lef")], output / "build_lef.log", export_env, flow)
        artifacts={}
        if args.target=="baseline":
            for name in baseline_files(args.block,design):
                path=result/name
                artifacts[name]=dict(bytes=path.stat().st_size,sha256=sha(path))
        (output / f"{args.target}.completed.json").write_text(json.dumps(dict(
            status="flow_completed_not_yet_qualified", elapsed_seconds=time.time()-started,
            result_dir=str(result), inputs_sha256=sha(old_inputs),artifacts=artifacts,
            runtime_resources=resources), indent=2) + "\n")
    print(f"COMPLETE {label} {args.target}: {result}", flush=True)


if __name__ == "__main__":
    main()
