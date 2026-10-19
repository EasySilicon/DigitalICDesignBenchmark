"""Bound planning memory without compiling placeholder logic into the model.

Plan using port/dependency-only modules, then regenerate every hierarchical
block from its complete mapped module before building any executable.
The generated native Verilator child flags keep other blocks behind their
DPI interfaces, so each compile reads only one large mapped module.
"""
import hashlib
import json
from pathlib import Path
import re


def build(command, sources, bench, out, run, cwd):
    from merge_pe_saif import instances
    modules = {}
    for source in sources:
        for match in re.finditer(r"\bmodule\s+([^\s(;]+)(.*?\bendmodule\b)", source.read_text(), re.S):
            name = match.group(1)
            if name in modules:
                raise ValueError(f"duplicate mapped module {name}")
            modules[name] = match.group(0)
    actual, planning = out / "actual_modules", out / "planning_only"
    actual.mkdir(exist_ok=True)
    planning.mkdir(exist_ok=True)
    dependencies, actual_files, plan_files = {}, {}, {}
    for name, source in modules.items():
        if not re.fullmatch(r"\w+", name):
            raise ValueError("parameterized/escaped module names need an explicit staging adapter")
        dependencies[name] = sorted({master for master,_ in instances(source, modules)})
        header = source[:source.index(";")+1]
        ports = re.findall(r"(?m)^\s*(?:input|output|inout)\b[^;]*;", source)
        if not ports:
            raise ValueError(f"non-ANSI mapped ports expected: {name}")
        skeleton = header + "\n/* verilator hier_block */\n" + "\n".join(ports)
        for index, master in enumerate(dependencies[name]):
            skeleton += f"\n{master} planning_dependency_{index} ();"
        skeleton += "\nendmodule\n"
        actual_files[name] = actual / f"{name}.v"
        plan_files[name] = planning / f"{name}.v"
        actual_files[name].write_text(source+"\n")
        plan_files[name].write_text("// PLANNING ONLY; NEVER USED TO BUILD A SIMULATION EXECUTABLE\n"+skeleton)
    order, visited = [], set()
    def visit(name):
        if name in visited:
            return
        visited.add(name)
        for child in dependencies[name]:
            visit(child)
        order.append(name)
    visit("npu_systolic_matmul_16x16")
    if set(order) != set(modules):
        raise ValueError("unreachable mapped module")
    plan_command = [arg for arg in command if arg not in {str(p) for p in sources}]
    index = plan_command.index("--binary")
    plan_command[index:index+1] = ["--cc", "--main", "--exe"]
    plan_command += [*map(str,plan_files.values()), "--protect-key", "576afc80af06e936089fd8f841fbcc4f555cee254bfa1922f701296e1d092b8e"]
    run(plan_command, out / "planning.log", cwd)
    build_dir = out / "build"
    if any(build_dir.rglob("*.o")) or any(build_dir.rglob("*.a")) or (build_dir/"Vtb_hidden_T10_stream").exists():
        raise RuntimeError("planning stage unexpectedly compiled a placeholder model")
    generated = list(build_dir.glob("*__hierMkArgs.f"))
    if not generated:
        raise RuntimeError("native Verilator did not emit the hierarchical command files")
    remove = {str(p) for p in plan_files.values()} | {str(bench)}
    records = []
    def regenerate(name, filename, source):
        args_file = build_dir / filename
        lines = [line for line in args_file.read_text().splitlines() if line.strip() not in remove]
        lines.append(str(source))
        args_file.write_text("\n".join(lines)+"\n")
        if str(planning) in args_file.read_text():
            raise RuntimeError("a planning-only source leaked into an actual compile")
        run([command[0], "-f", str(args_file)], out / f"actual_{name}.log", cwd)
        records.append(dict(module=name, source=str(source),
                            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                            args_file=str(args_file),args_sha256=hashlib.sha256(args_file.read_bytes()).hexdigest()))
    for name in order:
        regenerate(name, f"V{name}__hierMkArgs.f", actual_files[name])
    regenerate("testbench", "Vtb_hidden_T10_stream__hierMkArgs.f", bench)
    # All hierarchical C++/SV wrappers now derive from actual gate logic.
    # This native target builds the libraries in dependency order and links
    # the executable; no placeholder model was ever compiled or simulated.
    run(["make", "-C", str(build_dir), "-f", "Vtb_hidden_T10_stream_hier.mk", "-j4", "hier_build"],
        out / "compile.log", cwd)
    (out/"staged_build_manifest.json").write_text(json.dumps(dict(
        status="actual_gate_blocks_built", dependency_order=order, modules=records,
        planning_sources_used_for_simulation=False),indent=2)+"\n")
