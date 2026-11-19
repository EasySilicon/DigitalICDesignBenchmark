"""Execute a grader inside an explicitly selected CPU scheduling scope."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid


def snapshot(cgroup_root: Path = Path('/sys/fs/cgroup'),
             membership: Path = Path('/proc/self/cgroup')) -> dict:
    groups = [line[3:] for line in membership.read_text().splitlines() if line.startswith('0::')]
    if len(groups) != 1 or not groups[0].startswith('/') or '..' in Path(groups[0]).parts:
        raise ValueError('a valid cgroup v2 membership is required')
    group = cgroup_root / groups[0].lstrip('/')
    stats = dict(line.split() for line in (group / 'cpu.stat').read_text().splitlines())
    return {'cgroup': groups[0], 'cpu_weight': int((group / 'cpu.weight').read_text()),
            'cpu_max': (group / 'cpu.max').read_text().strip(),
            'usage_usec': int(stats['usage_usec']),
            'nr_throttled': int(stats.get('nr_throttled', 0)),
            'throttled_usec': int(stats.get('throttled_usec', 0)),
            'cpu_pressure': (group / 'cpu.pressure').read_text()}


def save(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def execute(request: dict, output: Path) -> int:
    weight = request.get('cpu_weight')
    if type(weight) is not int or not 1 <= weight <= 10000:
        raise ValueError('an explicit valid CPU weight is required')
    before = snapshot()
    if before['cpu_weight'] != weight:
        raise RuntimeError('requested CPU scheduling weight was not applied')
    started = time.monotonic()
    record = {'policy': 'explicit-cpu-weight-v1', 'status': 'running',
              'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'requested_cpu_weight': weight, 'before': before}
    save(output, record)
    try:
        result = subprocess.run(request['command'], cwd=request['cwd'],
            env=os.environ | {'PYTHONPATH': request['pythonpath']})
        record.update(status='completed' if result.returncode == 0 else 'grader_error',
                      returncode=result.returncode)
        return result.returncode
    except BaseException as error:
        record.update(status='infrastructure_error', error=str(error))
        raise
    finally:
        after = snapshot()
        wall = time.monotonic() - started
        cpu = (after['usage_usec'] - before['usage_usec']) / 1e6
        changed = (after['cgroup'] != before['cgroup'] or after['cpu_weight'] != weight or cpu < 0)
        if changed:
            record.update(status='infrastructure_error', error='CPU scope or scheduling policy changed')
        record.update(after=after, wall_seconds=wall, cpu_seconds=cpu,
                      average_cpu_cores=cpu / wall if wall else 0)
        save(output, record)
        if changed:
            raise RuntimeError('CPU scope or scheduling policy changed')


if __name__ == '__main__':
    request_path = Path(sys.argv[1])
    request = json.loads(request_path.read_text())
    raise SystemExit(execute(request, Path(request['report']).parent / 'resource_usage.json'))
