"""Use the required SV frontend for the unmeasured T10 peripheral shell."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

if __package__:
    from .slang_frontend import executable
    from .t10_structure_check import MAX_NON_PE_STATE_BITS
    from .power_compile_continuation import ContinuedCompileBudget
else:
    from slang_frontend import executable
    from t10_structure_check import MAX_NON_PE_STATE_BITS
    from power_compile_continuation import ContinuedCompileBudget


def normalize_blackbox_parameters(shell, pe, original_module):
    """Drop Slang blackbox metadata for a source PE with no public parameters.

    Slang can emit local constants and generate indices as blackbox parameter
    overrides. The real, fully mapped PE has no such override interface. Only
    uniform literal-valued metadata on all 256 instances is accepted here.
    """
    pattern = re.compile(r'(?m)^(\s*' + re.escape(pe) +
                         r')\s*#\((?P<params>(?:[^()]|\([^()]*\))*)\)\s*'
                         r'(?P<name>\\\S+|\w+)\s*\(')
    matches = list(pattern.finditer(shell))
    if not matches:
        return shell, None
    source = re.sub(r'/\*.*?\*/|//[^\n]*', '', original_module, flags=re.S)
    if re.search(r'\bparameter\b', source):
        raise ValueError('PE has public parameters; cannot discard blackbox overrides')
    if len(matches) != 256 or len({m['name'] for m in matches}) != 256:
        raise ValueError('blackbox normalization requires exactly 256 distinct PEs')
    constant = re.compile(r'\.([A-Za-z_][A-Za-z0-9_$]*)\s*\(\s*'
                          r'([-+]?[0-9_]+(?:\x27[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+)?)\s*\)')
    parameter_sets = []
    for match in matches:
        values = constant.findall(match['params'])
        remainder = constant.sub('', match['params'])
        if not values or remainder.strip(' \t\r\n,'):
            raise ValueError('blackbox metadata must use named constant literals')
        parameter_sets.append(tuple(values))
    if len(set(parameter_sets)) != 1:
        raise ValueError('PE blackbox metadata varies between instances')
    converted = pattern.sub(lambda m: m[1] + ' ' + m['name'] + ' (', shell)
    return converted, dict(pe_module=pe,instances=256,
        discarded_non_overridable_metadata=dict(parameter_sets[0]),
        original_module_sha256=hashlib.sha256(original_module.encode()).hexdigest(),
        mapped_shell_before_sha256=hashlib.sha256(shell.encode()).hexdigest(),
        mapped_shell_after_sha256=hashlib.sha256(converted.encode()).hexdigest())


def measure(*args, **kwargs):
    import t10_candidate_power as frozen
    yosys = str(executable())
    original_write, original_which, original_run = frozen.write_new_or_same, shutil.which, frozen.run
    original_build, original_budget = frozen.staged_build, frozen.CompileBudget

    def build(command, sources, bench, out, execute, cwd):
        # The unmeasured parent can be costly below the historical 128 MiB
        # heuristic too. Use the existing guarded parent-only path uniformly.
        def bounded(command, log, cwd):
            return frozen.run_unoptimized_periphery(command,log,cwd,execute=execute)
        return original_build(command,sources,bench,out,bounded,cwd)

    def run(command, log, cwd):
        elapsed = original_run(command, log, cwd)
        if log.name == 'shell_synth.log':
            model_dir, seed = Path(args[0]), args[1]
            inputs = json.loads((model_dir / f'seed{seed}/inputs40.json').read_text())
            pe = inputs['pe_module']
            source = '\n'.join(path.read_text() for path in
                               frozen.sources_from_filelist(model_dir / 'submission'))
            source = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
            module = re.search(r'\bmodule\s+' + re.escape(pe) + r'\b.*?\bendmodule\b', source, re.S)
            if module is None:
                raise ValueError('original PE module is missing')
            shell = Path(command[command.index('-C') + 1]) / command[-1]
            before = shell.read_text()
            converted, audit = normalize_blackbox_parameters(before, pe, module[0])
            if audit:
                backup = log.parent / 'shell_before_blackbox_parameter_adapter.v'
                if backup.exists():
                    raise ValueError('blackbox parameter adapter already attempted')
                backup.write_text(before)
                shell.write_text(converted)
                (log.parent / 'blackbox_parameter_adapter.json').write_text(json.dumps(audit,indent=2)+'\n')
        return elapsed

    def write(path, text):
        if path.name == 'shell_area.mk':
            text += 'export SYNTH_HDL_FRONTEND = slang\n'
            # ORFS defaults to 4096 bits per inferred memory. T10 explicitly
            # permits larger finite result staging; the independent structure
            # gate already enforces its full non-PE state allowance.
            text += f'export SYNTH_MEMORY_MAX_BITS = {MAX_NON_PE_STATE_BITS}\n'
        return original_write(path, text)

    def which(name, *values, **options):
        return yosys if name == 'yosys' else original_which(name, *values, **options)

    try:
        frozen.write_new_or_same, shutil.which, frozen.run = write, which, run
        frozen.staged_build, frozen.CompileBudget = build, ContinuedCompileBudget
        result = frozen.measure(*args, **kwargs)
        audit = Path(args[0]) / f'activity_seed{args[1]}/blackbox_parameter_adapter.json' if args else None
        if audit is not None and audit.exists():
            power = audit.with_name('power.json')
            record = json.loads(power.read_text())
            record['blackbox_parameter_adapter'] = frozen.artifact(audit)
            power.write_text(json.dumps(record,indent=2)+'\n')
        return result
    finally:
        frozen.write_new_or_same, shutil.which, frozen.run = original_write, original_which, original_run
        frozen.staged_build, frozen.CompileBudget = original_build, original_budget


if __name__ == '__main__':
    from power_compile_budget import PowerCompileTimeout, TIMEOUT_EXIT_CODE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--seed', type=int, choices=(11, 29, 47), required=True)
    parser.add_argument('--orfs', type=Path, required=True)
    args = parser.parse_args()
    try:
        measure(args.model_dir.resolve(), args.seed, args.orfs.resolve())
    except PowerCompileTimeout as error:
        print(str(error), file=sys.stderr, flush=True)
        raise SystemExit(TIMEOUT_EXIT_CODE)
