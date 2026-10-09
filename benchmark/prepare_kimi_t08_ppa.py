#!/usr/bin/env python3
"""Prepare a one-hour, isolated PPA continuation of Kimi's own T08 answer."""
import argparse
import json
import shutil
from pathlib import Path

from benchmark.prepare_t08_comparison import prepare_comparison, inventory, digest, write_json
from benchmark.prepare_trial import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--previous', type=Path, required=True)
    parser.add_argument('--orfs', type=Path, required=True)
    args = parser.parse_args()
    prepare_comparison(args.destination, models=('kimi-k3-256k',), time_limit_minutes=60)
    trial = args.destination.resolve() / 'kimi-k3-256k'
    workspace = trial / 'workspace'
    old = args.previous.resolve()
    for folder in ('rtl', 'verif'):
        if (workspace / folder).exists():
            shutil.rmtree(workspace / folder)  # only freshly generated, known trial folders
        shutil.copytree(old / 'workspace' / folder, workspace / folder,
                        ignore=shutil.ignore_patterns('build*', 'obj_dir', '*.log', '*.vcd', '__pycache__'))
    for name in ('run.sh', 'README.md'):
        if (old / 'workspace' / name).is_file():
            shutil.copy2(old / 'workspace' / name, workspace / name)
    kit = trial / 'public_eda'
    (kit / 'flow').mkdir(parents=True)
    shutil.copy2(args.orfs / 'flow/Makefile', kit / 'flow/Makefile')
    for name in ('scripts', 'util'):
        shutil.copytree(args.orfs / 'flow' / name, kit / 'flow' / name)
    for name in ('asap7', 'lambdapdk_fakeram7'):
        shutil.copytree(ROOT / 'vendor' / name, kit / name)
    for name in ('sram_libmap.txt', 'sram_map.v', 'sram_stub.v'):
        shutil.copy2(ROOT / 'evaluator/fixtures/t11_mac' / name, kit / name)
    shutil.copy2(ROOT / 'benchmark/t08_candidate_ppa.py', kit / 'ppa.py')
    if any(kit.rglob('SKILL.md')) or any((kit / 'flow' / name).exists() for name in ('designs', 'logs', 'results', 'reports')):
        raise RuntimeError('unsafe public EDA kit')
    old_summary = json.loads((old / 'summary.json').read_text())
    prior_elapsed = old_summary['elapsed_seconds']
    prompt = '''You are Kimi K3-256k, continuing YOUR previously completed MAC RTL submission, now task T08 (formerly T11).
The existing /workspace/rtl and your own verif/run.sh/README.md were copied from your last submission. Do NOT start again from buggy starter RTL.
You have an ADDITIONAL 60 minutes for PPA optimization and adapting to the updated SRAM policy. The clock starts now; read TRIAL_CLOCK.json and manage the remaining time. There is NO token cap. Your CLI session is persisted.
Read the self-contained current benchmark/tasks/T08/task.md, task.yaml and acceptance.md, especially 1 GHz physical constraints and the public SRAM contract. Preserve all functionality, FIFO capacities, frame atomicity, VLAN feature and valid run.sh/results.json/README.md delivery. You must maintain and run your own tests. Hidden tests and reference RTL are unavailable.
Tools available: Yosys, Verilator, OpenROAD, g++, Python and a READ-ONLY, answer-free technology/tool kit in /opt/t08_eda.
Public SRAM views: /opt/t08_eda/lambdapdk_fakeram7. Generic automatic memory mapping templates: /opt/t08_eda/sram_{libmap.txt,map.v,stub.v}.
To map your current RTL only: python3 /opt/t08_eda/ppa.py --output /workspace/ppa_map_1 --map-only
To map and run a single seed11 synthesis/place/route: python3 /opt/t08_eda/ppa.py --output /workspace/ppa_iter_1
Each output directory must be new. The helper uses WC standard cells, explicit TT 4096x32 dual-clock SRAM, independent logic_clk/tx_clk/rx_clk at 1 GHz, 200 ps IO delays and the same uniform flow parameters as final judging. All reports are saved under your chosen output folder. ASAP7 time units are ps. Keep NUM_CORES=4 for heavy EDA jobs and run only one physical job at a time.
Run seed11 during optimization, NOT seeds29/47: after you finish, the host will independently evaluate the final unchanged RTL across seeds11/29/47, including power. Negative setup/hold slack is continuously penalized, not automatically zero; nonzero DRC halves PPA. Do not tamper with constraints, cell models or technology views. You may modify RTL and your own tests. The final grader re-maps and verifies functionality before scoring.
No Skills and no direct web tools are available. Do not fetch benchmark/references online. Remain entirely inside this single-task workspace.
Use your time actively: inspect timing, optimize actual critical paths and area, replay your tests, then leave final RTL in rtl/files.f and update the handoff. Stop when done and report your measurements, changes and any remaining limitations.
'''
    (workspace / 'PROMPT.md').write_text(prompt)
    records = inventory(workspace)
    write_json(trial / 'starting_inventory.json', records)
    manifest = json.loads((trial / 'run_manifest.json').read_text())
    manifest.update(input_sha256=digest(records), trial_kind='ppa_continuation_60m',
                    previous_trial=str(old), previous_submission_elapsed_seconds=prior_elapsed,
                    cumulative_time_limit_seconds=9000, ranking_eligible=False,
                    public_eda_sha256=digest(inventory(kit)), ppa_policy_revision='2.0-lambdapdk-tdp-1ghz')
    write_json(trial / 'run_manifest.json', manifest)
    release = json.loads((args.destination / 'release.json').read_text())
    release.update(input_sha256=digest(records), trial_kind='ppa_continuation_60m', previous_trial=str(old))
    write_json(args.destination / 'release.json', release)
    print(trial)


if __name__ == '__main__':
    main()
