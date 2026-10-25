#!/usr/bin/env python3
"""Public T09 whole-CPU / T10 single-PE synthesis and routed timing feedback.

Only the candidate's RTL, public technology files and public physical settings
are used. This helper contains no reference RTL, hidden tests or score oracle.
"""
import argparse
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

KIT = Path(__file__).resolve().parent


def sources(submission):
    rtl = (submission / 'rtl').resolve(strict=True)
    result = []
    for raw in (rtl / 'files.f').read_text().splitlines():
        entry = raw.strip()
        if not entry or entry.startswith(('#', '//')):
            continue
        name = Path(entry)
        if name.is_absolute() or '..' in name.parts or entry.startswith('-'):
            raise ValueError('files.f must contain relative RTL paths only')
        path = (rtl / name).resolve(strict=True)
        if not path.is_relative_to(rtl) or path.suffix not in ('.sv', '.v'):
            raise ValueError('RTL source outside rtl/ or unsupported source type')
        result.append(path)
    if not result or len(result) != len(set(result)):
        raise ValueError('files.f must contain at least one unique RTL source')
    return result


def constraints(task, top):
    lines = [f'current_design {top}',
             'create_clock -name clk_clock -period 1000 [get_ports clk]']
    if task == 'T09':
        lines += ['create_clock -name vclk -period 1000',
                  'set_input_delay 200 -clock vclk [all_inputs -no_clocks]',
                  'set_output_delay 200 -clock vclk [all_outputs]']
    else:
        lines += ['create_clock -name vclk_in -period 1000',
                  'create_clock -name vclk_out -period 1000',
                  'set_clock_latency -source 600 [get_clocks vclk_out]',
                  'set_input_delay 200 -clock vclk_in [all_inputs -no_clocks]',
                  'set_output_delay 200 -clock vclk_out [all_outputs]']
    return '\n'.join(lines + ['set_false_path -from [get_ports rst_n]', ''])


def configuration(task, top, files, sdc, hook):
    fields = dict(PLATFORM='asap7', DESIGN_NAME=top,
                  VERILOG_FILES=' '.join(map(str, files)), SDC_FILE=sdc,
                  CORE_UTILIZATION=10, CORE_ASPECT_RATIO=1, CORE_MARGIN=.5,
                  PLACE_DENSITY=.6, SYNTH_USE_SYN=0, SYNTH_HIERARCHICAL=0,
                  CORNER='WC', SYNTH_HDL_FRONTEND='slang')
    if task == 'T10':
        fields.update(CORE_UTILIZATION=24, PLACE_DENSITY=.24,
            GPL_ROUTABILITY_DRIVEN=0, DETAIL_PLACEMENT_ARGS='-max_displacement 100',
            MAX_ROUTING_LAYER='M7', MIN_CLK_ROUTING_LAYER='M6',
            ROUTING_LAYER_ADJUSTMENT=0, HOLD_SLACK_MARGIN=75, SETUP_SLACK_MARGIN=175,
            SKIP_INCREMENTAL_REPAIR=0, CTS_CLUSTER_SIZE=64, CTS_CLUSTER_DIAMETER=100,
            CTS_ARGS='-sink_clustering_enable -repair_clock_nets -sink_clustering_size 64 -sink_clustering_max_diameter 100 -no_insertion_delay',
            SKIP_CTS_REPAIR_TIMING=0, PRE_CTS_TCL=hook, DETAILED_ROUTE_END_ITERATION=20)
    return ''.join(f'export {k} = {v}\n' for k, v in fields.items())


def measured_fields(report_dir, log_dir):
    metrics = json.loads((log_dir / '6_report.json').read_text())
    setup = metrics['finish__timing__setup__ws']
    hold = metrics['finish__timing__hold__ws']
    drc = report_dir / '5_route_drc.rpt'
    count = None
    if drc.is_file():
        text = drc.read_text()
        records = len(re.findall(r'^violation type:', text, re.MULTILINE))
        count = records if records or not text.strip() else None
    return dict(area_um2=metrics['finish__design__instance__area__stdcell'],
                setup_worst_slack_ns=setup / 1000, hold_worst_slack_ns=hold / 1000,
                delay_ns=(1000 - setup) / 1000, drc_violations=count,
                timing_report=str(report_dir / '6_finish.rpt'),
                metrics=str(log_dir / '6_report.json'), drc_report=str(drc))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', choices=('T09', 'T10'))
    parser.add_argument('--submission', type=Path, default=Path('/workspace'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--top', help='T10: your own PE module name, not the 256-PE top')
    parser.add_argument('--seed', type=int, default=11)
    parser.add_argument('--num-cores', type=int, default=4)
    parser.add_argument('--stage', choices=('synth', 'finish'), default='finish')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args(argv)
    top = 'rv32i_five_stage_cpu' if args.task == 'T09' else args.top
    if not top or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9$]*', top):
        parser.error('T10 requires --top with your PE module identifier')
    if args.task == 'T09' and args.top and args.top != top:
        parser.error('T09 measures the fixed full CPU top')
    if args.seed < 0 or args.num_cores < 1:
        parser.error('seed must be nonnegative and num-cores positive')
    output = args.output.resolve()
    if not output.is_relative_to(Path('/workspace')) or output.exists():
        parser.error('use a new output directory inside /workspace')
    files = sources(args.submission.resolve())
    output.mkdir(parents=True)
    sdc, config, hook = (output / n for n in ('constraint.sdc', 'config.mk', 'clock_layers.tcl'))
    sdc.write_text(constraints(args.task, top))
    hook.write_text('set_routing_layers -clock M6-M7\nset_wire_rc -clock -layer M7\n')
    config.write_text(configuration(args.task, top, files, sdc, hook))
    work = output / 'flow'
    variant = f'seed{args.seed}'
    reports = work / 'reports/asap7' / top / variant
    logs = work / 'logs/asap7' / top / variant
    result = dict(task_id=args.task, top=top, layout_seed=args.seed, period_ps=1000,
                  measurement_scope='full_dut' if args.task == 'T09' else 'single_pe',
                  stage=args.stage, scoring=False, power_status='not_measured',
                  report_directory=str(reports), log_directory=str(logs))
    target = str(logs / '6_report.log') if args.stage == 'finish' else 'synth'
    command = ['make', '-C', str(KIT / 'flow'), f'DESIGN_CONFIG={config}',
        f'WORK_HOME={work}', f'PLATFORM_DIR={KIT / "asap7"}', f'FLOW_VARIANT={variant}',
        'LIB_MODEL=NLDM', 'ASAP7_USE_VT=RVT', f'GRT_SEED={args.seed}', f'OR_SEED={args.seed}',
        f'NUM_CORES={args.num_cores}', f'YOSYS_EXE={KIT / "yosys_slang.py"}',
        f'OPENROAD_EXE={shutil.which("openroad")}', target]
    result['command'] = command
    if args.prepare_only:
        result['status'] = 'prepared_not_run'
    else:
        from slang_frontend import yosys_command
        yosys_command()
        if not shutil.which('openroad'):
            raise RuntimeError('OpenROAD is missing')
        start = time.monotonic()
        print(f'EDA_START {args.task} {result["measurement_scope"]}; log={output / "make.log"}', flush=True)
        with (output / 'make.log').open('w') as log:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        result.update(exit_code=process.returncode, elapsed_seconds=time.monotonic() - start,
                      status='completed' if process.returncode == 0 else 'failed')
        if process.returncode == 0 and args.stage == 'finish':
            result.update(measured_fields(reports, logs))
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2), flush=True)
    return result.get('exit_code', 0)


if __name__ == '__main__':
    raise SystemExit(main())
