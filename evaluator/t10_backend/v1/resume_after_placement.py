"""Resume seed47 after a checked, exact one-cell fence repair, without search."""
import argparse
import fcntl
import json
import os
import shutil
import subprocess
import time

from pathlib import Path
from resume_after_oom import artifact
from run_layout import BLOCKS, HERE, REPO, RTL, EXPECTED_RTL, baseline_files, run, sha, variant


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--orfs', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve(); flow = args.orfs.resolve() / 'flow'
    label = variant(47, 'pe'); output = work / label
    result = flow / 'results/asap7/t10_reference_pe' / label
    with (work / 'eda_seed47.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        record_path = output / 'placement_resume.inputs.json'
        if record_path.exists() or (result / '3_5_place_dp.odb').exists():
            raise RuntimeError('repair already attempted or successful placement exists; inspect, do not repeat')
        inputs_path = output / 'inputs.json'; inputs = json.loads(inputs_path.read_text())
        inventory = {str(p.relative_to(HERE)): sha(p) for p in (HERE / 'physical').rglob('*') if p.is_file()}
        if inputs['seed'] != 47 or inputs['block'] != 'pe' or inputs['threads'] != 4 or \
                inputs['route_iterations'] != 20 or inputs['rtl_sha256'] != EXPECTED_RTL or sha(RTL) != EXPECTED_RTL or \
                inputs['source_config_sha256'] != inventory or inputs['config_sha256'] != sha(HERE / BLOCKS['pe'][1]):
            raise ValueError('original seed47 silicon inputs changed')
        tool = shutil.which('openroad')
        if subprocess.check_output([tool, '-version'], text=True).strip() != inputs['openroad']:
            raise ValueError('tool changed')
        failure = output / 'baseline.log'
        failed_log = flow / 'logs/asap7/t10_reference_pe' / label / '3_5_place_dp.log'
        text = failed_log.read_text()
        if 'Region placement check failed (1)' not in text or 'DPL-0033' not in text or \
                'at_out_payload\\[4\\]$_DFF_PN0_' not in text:
            raise ValueError('not the measured single-cell fence failure')
        archive = output / 'failed_placement'; archive.mkdir(exist_ok=False)
        for path in (failure, failed_log):
            shutil.copyfile(path, archive / path.name)
        env = os.environ | dict(T10_V1_ROOT=str(HERE), T10_V1_RTL=str(RTL), T10_LAYOUT_SEED='47',
                                PLATFORM_DIR=str(REPO / 'vendor/asap7'), DETAILED_ROUTE_END_ITERATION='20',
                                T10_MAX_AS_BYTES=str(int(31.75 * 1024**3)), MALLOC_ARENA_MAX='2')
        views = {}
        for key, prefix in (('fp0', 'FP0'), ('fp1', 'FP1'), ('fp2', 'FP2'), ('int', 'INT'), ('cpa', 'CPA')):
            master = BLOCKS[key][0]; directory = flow / 'results/asap7' / master / variant(47, key)
            for suffix, filename in (('LEF', master + '_m7.lef'), ('LIB', master + '_wc.lib')):
                path = directory / filename
                env[f'T10_{prefix}_{suffix}'] = str(path)
                views[f'{prefix}_{suffix}'] = artifact(path)
        record = dict(reason='one_cell_outside_unchanged_forwarding_fence_by_40_DBU',
                      original_inputs=artifact(inputs_path), failed_odb=artifact(result / '3_5_place_dp-failed.odb'),
                      failed_logs=[artifact(p) for p in archive.iterdir()], macro_views=views,
                      repair_script=artifact(HERE / 'repair_seed47_placement.tcl'),
                      cell='at_out_payload\\[4\\]$_DFF_PN0_', before=[444960,245700], after=[445014,246240])
        record_path.write_text(json.dumps(record, indent=2) + '\n')
        command = ['make', f'DESIGN_CONFIG={HERE / BLOCKS["pe"][1]}', f'FLOW_VARIANT={label}',
                   f'OPENROAD_EXE={tool}', f'YOSYS_EXE={shutil.which("yosys")}', 'NUM_CORES=4']
        run(command + ['run', f'RUN_SCRIPT={HERE / "repair_seed47_placement.tcl"}',
                       'RUN_LOG_NAME_STEM=3_5_manual_region_repair'], output / 'manual_placement.log', env, flow)
        if 'T10_MANUAL_PLACEMENT_PASS' not in (output / 'manual_placement.log').read_text():
            raise RuntimeError('missing native legality and exact-change audit')
        started = time.time()
        run(command + ['route', 'do-finish'], output / 'baseline.log', env, flow)
        artifacts = {name: dict(bytes=(result / name).stat().st_size, sha256=sha(result / name))
                     for name in baseline_files('pe', 't10_reference_pe')}
        completed = dict(status='flow_completed_not_yet_qualified', result_dir=str(result),
                         inputs_sha256=sha(inputs_path), elapsed_seconds=time.time()-started, artifacts=artifacts,
                         placement_resume_inputs_sha256=sha(record_path),
                         runtime_resources=dict(max_address_space_bytes=int(env['T10_MAX_AS_BYTES']),
                                                malloc_arena_max='2', threads=4))
        (output / 'baseline.completed.json').write_text(json.dumps(completed, indent=2) + '\n')
        print('COMPLETE resumed layout; physical and power checks still required', flush=True)


if __name__ == '__main__':
    main()
