#!/usr/bin/env python3
"""Measure complete single-PE TT power from checked, 256-PE averaged SAIF."""
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

from run_layout import BLOCKS, variant
from run_gate_activity import HISTORICAL
from saif_window import POLICY as SAIF_WINDOW_POLICY
from saif_activity import export_scope, TCL as IMPORT_ACTIVITY_TCL

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4*1024**2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def brace(value):
    return "{" + str(value).replace("\\", "\\\\").replace("}", "\\}") + "}"


def limit():
    resource.setrlimit(resource.RLIMIT_AS, (30*1024**3, 30*1024**3))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, choices=(11,29,47), required=True)
    parser.add_argument("--orfs", type=Path, required=True)
    parser.add_argument("--activity-manifest", type=Path, required=True)
    parser.add_argument("--merge-audit", type=Path, required=True)
    parser.add_argument("--saif", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed11-repaired-final", type=Path)
    args = parser.parse_args()
    activity = json.loads(args.activity_manifest.read_text())
    audit = json.loads(args.merge_audit.read_text())
    if activity.get("saif_writer", {}).get("policy") != SAIF_WINDOW_POLICY:
        raise ValueError("activity lacks the verified delayed-open SAIF window correction")
    if activity.get("numerical_oracle_passed") is not True or activity.get("protocol_and_latency_passed") is not True or \
            activity.get("completed_matrix_blocks") != 200 or activity.get("layout_seed") != args.seed:
        raise ValueError("gate-level workload is not qualified for this seed")
    if audit["pe_instances"] != 256 or audit["source_sha256"] != activity["activity_sha256"] or \
            audit["output_sha256"] != sha(args.saif) or audit["per_instance_weight"] != 1/256:
        raise ValueError("SAIF provenance or PE averaging is invalid")
    timescale = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(s|ms|us|ns|ps|fs)", audit["timescale"])
    if not timescale:
        raise ValueError("invalid SAIF time scale")
    scale = float(timescale[1])*dict(s=1,ms=1e-3,us=1e-6,ns=1e-9,ps=1e-12,fs=1e-15)[timescale[2]]
    duration = audit["duration_per_instance_ticks"]*scale
    clock = audit["clock_activity"]
    if not clock or abs(clock[2]/(duration*256)-2e9) > 2/duration:
        raise ValueError("averaged PE clock is not 1 GHz")
    flow = args.orfs.resolve() / "flow"
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    platform = REPO / "vendor/asap7"
    libs = sorted(p for p in (platform / "lib/NLDM").glob("asap7sc7p5t_*RVT_TT_nldm_*.lib*") if "FAKE" not in p.name)
    if len(libs) != 5:
        raise ValueError("expected the five TT standard-cell libraries")
    physical = {}
    for block, (design, _) in BLOCKS.items():
        label = HISTORICAL[block] if args.seed == 11 else variant(args.seed,block)
        physical[design] = flow / "results/asap7" / design / label
    if args.seed == 11:
        if args.seed11_repaired_final is None:
            raise ValueError("seed 11 must use the manually repaired final checkpoint")
        physical["t10_reference_pe"] = args.seed11_repaired_final.resolve()
    # Power is measured at TT, including each macro's boundary capacitance.
    # WC timing abstracts are not used as TT power loads. Characterize fresh
    # TT boundary models from the exact same routed child ODB/SPEF instead.
    tt_models={}
    for child in sorted(set(audit["physical_child_masters"].values())):
        directory=physical[child]
        model_dir=out/"macro_tt_models"/child
        model_dir.mkdir(parents=True,exist_ok=True)
        model=model_dir/(child+"_tt.lib")
        script="set_thread_count 4\n"+"".join(f"read_liberty {brace(p)}\n" for p in libs)
        script+=f"read_db {brace(directory/'6_final.odb')}\nread_sdc {brace(directory/'6_final.sdc')}\nread_spef {brace(directory/'6_final.spef')}\n"
        script+="set_propagated_clock [all_clocks]\nset_clock_latency -source 0 [all_clocks]\n"
        script+=f"write_timing_model {brace(model)}\nexit\n"
        (model_dir/"export.tcl").write_text(script)
        with (model_dir/"export.log").open("w") as stream:
            subprocess.run([shutil.which("openroad"),"-exit","-no_init","-no_splash",str(model_dir/"export.tcl")],stdout=stream,stderr=subprocess.STDOUT,check=True,preexec_fn=limit)
        if not model.is_file() or model.stat().st_size==0:
            raise ValueError("TT boundary characterization failed")
        tt_models[child]=model
    pieces = [("pe_shell", "t10_reference_pe", "pe")]
    pieces += [(scope, master, "pe/"+scope) for scope,master in sorted(audit["physical_child_masters"].items())]
    rows = []
    for name, master, scope in pieces:
        directory = physical[master]
        prefix = "v15_manual_final" if args.seed == 11 and name == "pe_shell" else "6_final"
        files = {kind:directory/f"{prefix}.{kind}" for kind in ("odb","sdc","spef")}
        for path in files.values():
            if not path.is_file():
                raise ValueError(f"missing routed power input: {path}")
        sub = out / re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        sub.mkdir(exist_ok=True)
        used_libs = list(libs)
        if name == "pe_shell":
            for child in set(audit["physical_child_masters"].values()):
                used_libs.append(tt_models[child])
        script = "set_thread_count 4\n" + "".join(f"read_liberty {brace(p)}\n" for p in used_libs)
        script += f"read_db {brace(files['odb'])}\nread_sdc {brace(files['sdc'])}\nread_spef {brace(files['spef'])}\n"
        mapping = export_scope(args.saif, scope.split("/"), sub/"activity_nets.tsv")
        script += f"source {brace(IMPORT_ACTIVITY_TCL)}\n"
        script += "report_activity_annotation -report_unannotated\nreport_power -digits 9\nexit\n"
        (sub / "power.tcl").write_text(script)
        with (sub / "power.log").open("w") as stream:
            subprocess.run([shutil.which("openroad"), "-exit", "-no_init", "-no_splash", str(sub/"power.tcl")],
                           stdout=stream, stderr=subprocess.STDOUT, check=True, preexec_fn=limit,
                           env=os.environ|{"T10_ACTIVITY_NETS":str(sub/"activity_nets.tsv")})
        report = (sub / "power.log").read_text()
        annotations = re.findall(r"^input\s+(\d+)\s+unannotated\s+(\d+)", report, re.M)
        if not annotations:
            raise ValueError(f"missing activity annotation counts: {sub}")
        ratios = [int(a)/(int(a)+int(b)) if int(a)+int(b) else 0 for a,b in annotations]
        if min(ratios) < .95:
            raise ValueError(f"activity annotation below 95%: {name}, {ratios}")
        sequential = re.search(r"T10_SEQUENTIAL_ACTIVITY annotated=(\d+) total=(\d+)", report)
        imported = re.search(r"T10_ACTIVITY_IMPORT nets=(\d+) pins=(\d+)", report)
        if not sequential or not imported or int(imported[1]) != mapping["activity_nets"]:
            raise ValueError("missing exact-net or sequential activity coverage audit")
        sequential_fraction = int(sequential[1])/int(sequential[2])
        if sequential_fraction < .95:
            raise ValueError("sequential activity coverage below 95%")
        def powers(label):
            match = re.search(r"^"+label+r"\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", report, re.M)
            if not match:
                raise ValueError(f"power report has no {label} row")
            return list(map(float,match.groups()))
        total = powers("Total")
        macro = powers("Macro")
        # Root macro power, if present in abstracts, is accounted independently.
        watts = total[3] - macro[3] if name == "pe_shell" else total[3]
        if watts <= 0:
            raise ValueError("nonpositive physical component power")
        row = dict(instance=name, master=master, scope=scope, power_w=watts,
                   total_reported_w=total[3], macro_reported_w=macro[3],
                   activity_annotation_fraction=min(ratios),
                   sequential_activity_annotation_fraction=sequential_fraction,
                   activity_import=mapping,
                   activity_net_data_sha256=sha(sub/"activity_nets.tsv"),
                   artifacts={kind:dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)) for kind,p in files.items()},
                   report_path=str(sub/"power.log"), report_sha256=sha(sub/"power.log"))
        rows.append(row)
        print(f"POWER {name} {watts:.9g} W annotation={min(ratios):.3%}",flush=True)
    shell = rows[0]["power_w"]
    internal = sum(row["power_w"] for row in rows[1:])
    result = dict(task_id="T10", measurement_scope="single_pe",layout_seed=args.seed,
                  status="single_seed_activity_power_qualified_not_three_seed_baseline",
                  power_corner="TT",workload_id="T10-power-v1",matrix_blocks=200,
                  activity_annotation_fraction=min(row["activity_annotation_fraction"] for row in rows),
                  vcd_window_seconds=duration, activity_format="SAIF",instance_weights={"pe":1},
                  components_w={"pe_shell":shell,"internal_macros":internal}, total_power_w=shell+internal,
                  energy_j_per_block=(shell+internal)*duration/200, components=rows,
                  merged_saif_sha256=sha(args.saif),merge_audit_sha256=sha(args.merge_audit),
                  activity_manifest_sha256=sha(args.activity_manifest),
                  tt_macro_abstracts={name:dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)) for name,p in tt_models.items()},
                  tt_standard_libraries={str(p):sha(p) for p in libs})
    (out/"power.json").write_text(json.dumps(result,indent=2)+"\n")


if __name__ == "__main__":
    main()
