#!/usr/bin/env python3
"""Current candidate power entry; retain byte-identical frozen workload probes."""
import argparse
import importlib
from pathlib import Path
import re
import subprocess
import sys

from power_compile_budget import CompileBudget, PowerCompileTimeout, TIMEOUT_EXIT_CODE


def compile_command(command):
    if isinstance(command,(str,bytes)) or not command:return False
    name=Path(command[0]).name
    if any(flag in command for flag in ('--help','--version','-V')):return False
    return name in ('verilator','verilator_bin','make','gmake','g++','c++','clang++')


def run_probe(module, argv, output, source, seed, task, *, budget_factory=CompileBudget):
    """Limit compilation only, not synthesis, simulation, or power analysis."""
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    original_run=subprocess.run;original_argv=sys.argv
    budget=None;compile_failure=None
    def finish(kind=None,error=None,traceback=None):
        nonlocal budget
        active=budget;budget=None
        if active is not None:active.__exit__(kind,error,traceback)
    def bounded(command,*positional,**options):
        nonlocal budget,compile_failure
        if not compile_command(command):
            if (budget is not None and command and
                    (Path(command[0]).name.startswith('V') and Path(command[0]).parent==output/'build'
                     or Path(command[0]).name=='openroad')):
                finish()
            return original_run(command,*positional,**options)
        if positional or options.get('shell') or options.get('input') is not None:
            raise ValueError('unsupported compiler invocation; not a candidate timeout')
        if budget is None:
            budget=budget_factory(output,source,seed,task=task);budget.__enter__()
        stream=options.get('stdout')
        log=Path(stream.name) if hasattr(stream,'name') else output/f'power_compile_command_{len(budget.record["commands"]):04d}.log'
        launch={key:options[key] for key in ('env','preexec_fn') if key in options}
        try:
            budget.run(command,log,options.get('cwd'),**launch);code=0
        except subprocess.CalledProcessError as error:
            compile_failure=error;code=error.returncode
        except BaseException as error:
            compile_failure=error
            raise
        capture=options.get('capture_output') or options.get('stdout')==subprocess.PIPE
        payload=log.read_bytes()
        textual=options.get('text') or options.get('universal_newlines') or options.get('encoding')
        data=payload.decode(options.get('encoding') or 'utf-8',options.get('errors') or 'replace') if textual else payload
        result=subprocess.CompletedProcess(command,code,data if capture else None,('' if textual else b'') if capture else None)
        if code and options.get('check'):raise subprocess.CalledProcessError(code,command,result.stdout,result.stderr)
        return result
    try:
        subprocess.run=bounded;sys.argv=[str(module.__file__),*argv]
        result=module.main()
        # Frozen probes may catch OSError/TimeoutError and return a failure.
        # Keep the real compiler cause in the receipt and propagate expiry.
        if compile_failure is not None:raise compile_failure
    except BaseException as error:
        finish(type(error),error,error.__traceback__)
        raise
    else:
        finish();return result
    finally:
        subprocess.run=original_run;sys.argv=original_argv


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',choices=[f'T{i:02d}' for i in range(1,11)],required=True)
    parser.add_argument('--candidate-source-sha256',required=True)
    parser.add_argument('--layout-seed',type=int,choices=(11,29,47),required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--model-dir',type=Path)
    parser.add_argument('--orfs',type=Path)
    args,forward=parser.parse_known_args()
    if not re.fullmatch('[0-9a-f]{64}',args.candidate_source_sha256):parser.error('invalid evaluator-owned candidate source hash')
    try:
        if args.task=='T10':
            if not args.model_dir or not args.orfs or forward:parser.error('T10 requires --model-dir and --orfs')
            from ppa_aggregate import source_hash
            from t10_candidate_power import measure
            model=args.model_dir.resolve()
            if source_hash(model/'submission')!=args.candidate_source_sha256:parser.error('T10 candidate source mismatch')
            if args.output_dir.resolve()!=model/f'activity_seed{args.layout_seed}':parser.error('T10 output must be its seed-specific activity directory')
            measure(model,args.layout_seed,args.orfs.resolve())
            return 0
        module=importlib.import_module('t08_power_probe' if args.task=='T08' else 'ppa_power_probe')
        if args.task!='T08':forward=[args.task,*forward]
        forward+=['--output-dir',str(args.output_dir)]
        return run_probe(module,forward,args.output_dir,args.candidate_source_sha256,args.layout_seed,args.task)
    except PowerCompileTimeout as error:
        print(str(error),file=sys.stderr)
        return TIMEOUT_EXIT_CODE


if __name__=='__main__':raise SystemExit(main())
