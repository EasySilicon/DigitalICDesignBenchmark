"""Prepare relocatable, public-only EDA kits for CPU and single-PE exploration."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare_public_eda(trial, orfs, task):
    if task not in ('T09', 'T10'):
        raise ValueError('This public EDA entry supports T09 and T10')
    kit = Path(trial) / 'public_eda'
    (kit / 'flow').mkdir(parents=True)
    shutil.copy2(Path(orfs) / 'flow/Makefile', kit / 'flow/Makefile')
    for name in ('scripts', 'util'):
        shutil.copytree(Path(orfs) / 'flow' / name, kit / 'flow' / name)
    common = kit / 'flow/platforms/common'
    common.mkdir(parents=True)
    shutil.copy2(Path(orfs) / 'flow/platforms/common/lcu_kogge_stone.v', common)
    shutil.copytree(ROOT / 'vendor/asap7', kit / 'asap7')
    for source, target in [('benchmark/candidate_ppa.py', 'ppa.py'),
                           ('evaluator/slang_frontend.py', 'slang_frontend.py'),
                           ('evaluator/yosys_slang.py', 'yosys_slang.py')]:
        shutil.copy2(ROOT / source, kit / target)
    (kit / 'yosys_slang.py').chmod(0o755)
    if any(kit.rglob('SKILL.md')) or any((kit / 'flow' / n).exists()
            for n in ('designs', 'logs', 'results', 'reports')):
        raise ValueError('Unsafe public EDA kit')
    (kit / 'task.json').write_text(json.dumps({'task': task, 'mount': '/opt/benchmark_eda'}) + '\n')
    inventory = {str(p.relative_to(kit)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(kit.rglob('*')) if p.is_file()}
    (kit / 'inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
    notice = instructions(task, '/opt/benchmark_eda')
    with (Path(trial) / 'workspace/PROMPT.md').open('a') as out:
        out.write('\n' + notice + '\n')
    (Path(trial) / 'workspace/EDA_TOOLS.md').write_text(notice + '\n')
    return kit


def instructions(task, location):
    top = ' --top YOUR_PE_MODULE' if task == 'T10' else ''
    scope = 'your own single PE, not the full 256-PE array' if task == 'T10' else 'the full CPU'
    return (f'Public EDA tools and ASAP7 technology files are available at {location}. '
        'This kit contains only ORFS public scripts, technology views and physical constraints; '
        'no reference RTL, hidden tests or other submissions. '
        f'For synthesis feedback: `python3 {location}/ppa.py {task}{top} '
        '--stage synth --output /workspace/eda_synth_1`. '
        f'For routed timing/area/DRC: `python3 {location}/ppa.py {task}{top} '
        '--output /workspace/eda_route_1`. Use a fresh output directory for each attempt. '
        f'Measure {scope}; all RTL sources come from your rtl/files.f. '
        'The helper uses the published 1 GHz / WC / RVT settings and the required slang frontend. '
        'ASAP7 timing units are ps; result.json also reports delays and slack in ns. '
        'Inspect make.log and flow/reports for critical paths; optimize your own RTL and re-test correctness. '
        'This feedback is not an official score or an activity-based energy measurement. '
        'EDA time counts toward the existing task deadline; there is no extra development time.')
