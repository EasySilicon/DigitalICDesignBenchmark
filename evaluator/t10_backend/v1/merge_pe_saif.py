#!/usr/bin/env python3
"""Average native Verilator SAIF over all 256 gate-level PE instances.

Sum integer residency times/toggles and multiply duration by 256, preserving
rates and probabilities exactly without rounding individual activity counts.
Only direct nets of the PE and each physical child are needed by OpenSTA;
primitive-cell pin aliases below those scopes are intentionally not repeated.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re


def normalized(name):
    return name.replace("\\", "").replace("/", ".")


def instances(source, masters):
    pattern = r"(?m)^\s*(" + "|".join(map(re.escape, masters)) + r")\s+(\\\S+|\w+)\s*\("
    return [(m.group(1), m.group(2).lstrip("\\")) for m in re.finditer(pattern, source)]


def pe_paths(shell):
    modules = {m.group(1): m.group(2) for m in re.finditer(
        r"\bmodule\s+([^\s(;]+).*?;(.*?)\bendmodule\b", shell, re.S)}
    paths = []
    def visit(master, prefix):
        for child, name in instances(modules[master], [*modules, "t10_reference_pe"]):
            path = prefix + [name]
            if child == "t10_reference_pe":
                paths.append(".".join(map(normalized, path)))
            else:
                visit(child, path)
    visit("npu_systolic_matmul_16x16", [])
    if len(paths) != 256 or len(set(paths)) != 256:
        raise ValueError(f"expected 256 distinct mapped PE paths, got {len(paths)}")
    return set(paths)


STAT = re.compile(r"^\((\S+)\s+\(T0 (\d+)\) \(T1 (\d+)\) \(TZ (\d+)\) \(TX (\d+)\) \(TB (\d+)\) \(TC (\d+)\)\)$")


def merge(source, expected, macros, output):
    scopes, stack, seen, current_keys = [], [], set(), set()
    totals = defaultdict(lambda: [0, 0, 0, 0])
    active, root_depth, duration, timescale = None, None, None, None
    input_hash = hashlib.sha256()
    rows = 0
    with source.open("rb") as stream:
        for raw in stream:
            input_hash.update(raw)
            line = raw.decode().strip()
            if line.startswith("(DURATION "):
                duration = int(line[10:-1])
            elif line.startswith("(TIMESCALE "):
                timescale = line[11:-1].strip()
            elif line.startswith("(INSTANCE "):
                name = line[10:].strip()
                scopes.append(name)
                stack.append("INSTANCE")
                if active is None:
                    joined = ".".join(map(normalized, scopes))
                    candidate = joined.split(".dut.", 1)[-1]
                if active is None and candidate in expected:
                    if candidate in seen:
                        raise ValueError("ambiguous or duplicated PE scope")
                    active, root_depth = candidate, len(scopes)
                    current_keys = set()
            elif line in ("(NET", "(SAIFILE"):
                stack.append(line[1:])
            elif line == ")":
                kind = stack.pop()
                if kind == "INSTANCE":
                    if active is not None and len(scopes) == root_depth:
                        if not current_keys:
                            raise ValueError("PE scope has no activity records")
                        seen.add(active)
                        active, root_depth = None, None
                    scopes.pop()
            elif active is not None and line.startswith("("):
                stat = STAT.fullmatch(line)
                if not stat:
                    raise ValueError(f"unexpected native SAIF activity: {line[:160]}")
                relative = ".".join(map(normalized, scopes[root_depth:]))
                if relative and relative not in macros:
                    continue
                name, t0, t1, tz, tx, tb, tc = stat.groups()
                t0, t1, tc = int(t0), int(t1), int(tc)
                if duration is None or t0+t1 != duration or any(int(x) for x in (tz,tx,tb)):
                    raise ValueError("missing duration or invalid/unknown SAIF residency")
                key = (relative, name)
                if key in current_keys:
                    raise ValueError(f"duplicate per-PE activity record: {key}")
                current_keys.add(key)
                total = totals[key]
                for i, value in enumerate((t0,t1,tc,1)):
                    total[i] += value
                rows += 1
    count = len(expected)
    if stack or active is not None or seen != expected or not duration or not timescale:
        raise ValueError(f"incomplete SAIF coverage: {len(seen)}/{count} PEs")
    if any(value[3] != count for value in totals.values()):
        raise ValueError("PE net coverage differs between instances")
    groups = defaultdict(list)
    for (scope, name), values in totals.items():
        groups[scope].append((name, values))
    if set(groups) != {"", *macros}:
        raise ValueError("one or more physical child scopes have no activity")
    def escape(name):
        return name.replace("[", "\\[").replace("]", "\\]")
    with output.open("w") as stream:
        stream.write(f'(SAIFILE\n(SAIFVERSION "2.0")\n(DIRECTION "backward")\n(DIVIDER /)\n(TIMESCALE {timescale})\n(DURATION {duration*count})\n(INSTANCE pe\n')
        for scope in sorted(groups):
            if scope:
                stream.write(f"(INSTANCE {escape(scope)}\n")
            stream.write("(NET\n")
            for name, (t0,t1,tc,_) in sorted(groups[scope]):
                stream.write(f"({name} (T0 {t0}) (T1 {t1}) (TZ 0) (TX 0) (TB 0) (TC {tc}))\n")
            stream.write(")\n")
            if scope:
                stream.write(")\n")
        stream.write(")\n)\n")
    return dict(status="merged_not_yet_power_qualified", pe_instances=count,
                pe_paths=sorted(seen), duration_per_instance_ticks=duration,
                duration_merged_ticks=duration*count, timescale=timescale,
                source_sha256=input_hash.hexdigest(), output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                per_instance_weight=1/count, original_records_merged=rows,
                scope_net_counts={scope or "pe_shell":len(values) for scope,values in groups.items()},
                clock_activity=totals.get(("","clk")), physical_child_masters=macros)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--shell", type=Path, required=True)
    parser.add_argument("--pe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    masters = [f"t10_reference_fp_quad_class{i}_exact" for i in range(3)] + ["t10_reference_int_group", "t10_reference_cpa_postprocess"]
    macros = {normalized(name):master for master,name in instances(args.pe.read_text(), masters)}
    if len(macros) != 9:
        raise ValueError("expected nine physical children")
    result = merge(args.input, pe_paths(args.shell.read_text()), macros, args.output)
    args.audit.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k:v for k,v in result.items() if k!='pe_paths'}, indent=2))


if __name__ == "__main__":
    main()
