#!/usr/bin/env python3
"""Public, answer-free T08 SRAM mapping and single-seed physical exploration.

This helper contains no reference RTL, acceptance tests, or scoring oracle.
Run inside the isolated candidate container. All outputs stay in the workspace.
"""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

KIT = Path('/opt/t08_eda')
DOMAINS = {
    'logic_clk': ('tx_axis_tdata tx_axis_tvalid tx_axis_tlast tx_axis_tuser rx_axis_tready',
                  'tx_axis_tready rx_axis_tdata rx_axis_tvalid rx_axis_tlast rx_axis_tuser rx_axis_tagged rx_axis_tci tx_error_underflow rx_error_bad_frame rx_error_bad_fcs tx_fifo_overflow tx_fifo_bad_frame tx_fifo_good_frame rx_fifo_overflow rx_fifo_bad_frame rx_fifo_good_frame'),
    'tx_clk': ('', 'gmii_txd gmii_tx_en gmii_tx_er'),
    'rx_clk': ('gmii_rxd gmii_rx_dv gmii_rx_er cfg_vlan_enable cfg_accept_untagged cfg_accept_priority cfg_vlan_valid cfg_vlan_vids', 'rx_vlan_drop'),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--submission', type=Path, default=Path('/workspace'))
    parser.add_argument('--output', type=Path, required=True, help='new output directory inside /workspace')
    parser.add_argument('--map-only', action='store_true')
    args = parser.parse_args()
    submission, output = args.submission.resolve(), args.output.resolve()
    if not output.is_relative_to(Path('/workspace')) or output.exists():
        parser.error('use a new output directory inside /workspace')
    rtl = submission / 'rtl'
    sources = []
    for line in (rtl / 'files.f').read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(('#', '//')):
            continue
        path = (rtl / line).resolve(strict=True)
        if Path(line).is_absolute() or not path.is_relative_to(rtl) or path.suffix not in ('.v', '.sv'):
            parser.error('files.f must list relative RTL source files only')
        sources.append(path)
    output.mkdir(parents=True)
    mapped = output / 'mapped.v'
    q = lambda p: json.dumps(str(p))
    commands = ['read_verilog -defer -sv ' + ' '.join(map(q, sources)),
                'hierarchy -check -top mac_1g_repair', 'proc',
                'setattr -mod -unset keep_hierarchy', 'flatten', 'opt', 'memory -nomap',
                'memory_libmap -lib ' + q(KIT / 'sram_libmap.txt'),
                'techmap -map ' + q(KIT / 'sram_map.v'), 'opt', 'memory_map', 'opt',
                'read_verilog -lib ' + q(KIT / 'sram_stub.v'),
                'hierarchy -check -top mac_1g_repair', 'check -assert',
                'write_json ' + q(output / 'mapped.json'), 'write_verilog -noattr ' + q(mapped)]
    script = output / 'mapping.ys'
    script.write_text('\n'.join(commands) + '\n')
    with (output / 'mapping.log').open('w') as log:
        subprocess.run(['yosys', '-Q', '-T', '-s', str(script)], stdout=log, stderr=subprocess.STDOUT, check=True)
    cells = json.loads((output / 'mapped.json').read_text())['modules']['mac_1g_repair']['cells']
    count = sum(c['type'] == 'fakeram7_tdp_4096x32' for c in cells.values())
    print(f'SRAM_MAPPING_COMPLETE macros={count}', flush=True)
    if not count:
        raise RuntimeError('No SRAM inferred: fix memory structure; do not reduce FIFO capacity.')
    if args.map_only:
        return
    lines = ['current_design mac_1g_repair']
    lines += [f'create_clock -name {clock}_clock -period 1000 [get_ports {clock}]' for clock in DOMAINS]
    lines += ['set_clock_groups -asynchronous ' + ' '.join(f'-group [get_clocks {clock}_clock]' for clock in DOMAINS)]
    for clock, (inputs, outputs) in DOMAINS.items():
        for direction, ports in (('input', inputs), ('output', outputs)):
            if ports:
                lines += [f'set_{direction}_delay 200 -clock {clock}_clock [get_ports {{{ports}}}]']
    lines += [f'set_false_path -from [get_ports {reset}]' for reset in ('logic_rst', 'tx_rst', 'rx_rst')]
    sdc = output / 'constraint.sdc'
    sdc.write_text('\n'.join(lines) + '\n')
    macro = KIT / 'lambdapdk_fakeram7/upstream'
    fields = {'PLATFORM': 'asap7', 'DESIGN_NAME': 'mac_1g_repair', 'VERILOG_FILES': mapped,
              'SDC_FILE': sdc, 'CORE_UTILIZATION': 10, 'CORE_ASPECT_RATIO': 1,
              'CORE_MARGIN': 0.5, 'PLACE_DENSITY': 0.6, 'SYNTH_USE_SYN': 0,
              'SYNTH_HIERARCHICAL': 0, 'CORNER': 'WC', 'SYNTH_MEMORY_MAX_BITS': 262144,
              'SYNTH_MOCK_LARGE_MEMORIES': 0, 'SYNTH_HDL_FRONTEND': '',
              'ADDITIONAL_LEFS': macro / 'lef/fakeram7_tdp_4096x32.lef',
              'ADDITIONAL_LIBS': macro / 'nldm/fakeram7_tdp_4096x32.lib'}
    config = output / 'config.mk'
    config.write_text(''.join(f'export {k} = {v}\n' for k, v in fields.items()))
    work = output / 'flow'
    work.mkdir()
    target = work / 'logs/asap7/mac_1g_repair/seed11/6_report.log'
    cmd = ['make', '-C', str(KIT / 'flow'), f'DESIGN_CONFIG={config}', f'WORK_HOME={work}',
           f'PLATFORM_DIR={KIT / "asap7"}', 'FLOW_VARIANT=seed11', 'LIB_MODEL=NLDM',
           'ASAP7_USE_VT=RVT', 'GRT_SEED=11', 'OR_SEED=11', 'NUM_CORES=4',
           f'YOSYS_EXE={shutil.which("yosys")}', f'OPENROAD_EXE={shutil.which("openroad")}', str(target)]
    print('ROUTE_START seed=11 clocks=1GHz; log=' + str(output / 'make.log'), flush=True)
    with (output / 'make.log').open('w') as log:
        result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
    print('ROUTE_FINISH exit=' + str(result.returncode), flush=True)
    print('Timing/area reports: ' + str(work / 'reports/asap7/mac_1g_repair/seed11'), flush=True)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
