#!/usr/bin/env python3
"""Current candidate aggregation, including source-bound compile receipts."""
import argparse
import json
from pathlib import Path

from ppa_aggregate import aggregate as frozen_aggregate, source_hash, SEEDS
from power_compile_budget import POLICY_ID, TIMEOUT_STATUS, validate_records
import physical_budget


def aggregate(task, submission, pairs, expected_seeds=SEEDS, *, physical_records=None):
    source = source_hash(submission)
    timeouts = physical_budget.validate_records(physical_records,source,task) if physical_records else set()
    if timeouts:
        expected_seeds=tuple(seed for seed in SEEDS if seed not in timeouts)
    records = [json.loads((power.parent/'power_compile.json').read_text()) for _, power in pairs]
    timeout = validate_records(records, source, task, require_complete=expected_seeds == SEEDS)
    if not timeout and tuple(sorted(record['layout_seed'] for record in records)) != expected_seeds:
        raise ValueError('compile receipts do not match the selected seeds')
    if timeout:
        return dict(task_id=task, source_sha256=source,
                    measurement_status=TIMEOUT_STATUS, power_compile_policy=POLICY_ID,
                    power_compile_records=records)
    if not expected_seeds:
        return dict(task_id=task,source_sha256=source,physical_policy=physical_budget.POLICY_ID,
                    physical_records=physical_records,measurement_status='physical_timeout_no_results')
    result = frozen_aggregate(task, submission, pairs, expected_seeds)
    if physical_records:
        result=physical_budget.attach(result,physical_records)
        result['parameter_set']['seeds']=list(SEEDS)
    for row, record in zip(sorted(result['per_seed'],key=lambda row:row['layout_seed']),
                           sorted(records,key=lambda row:row['layout_seed'])):
        power = Path(row['power_record'])
        if json.loads((power.parent/'power_compile.json').read_text()) != record:
            raise ValueError('power compile receipt belongs to another routed seed')
    return dict(result, power_compile_policy=POLICY_ID, power_compile_records=records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', choices=[f'T{i:02d}' for i in range(1,10)])
    parser.add_argument('submission', type=Path)
    parser.add_argument('--pair', nargs=2, action='append', default=[])
    parser.add_argument('--physical-record', type=Path, action='append', default=[])
    parser.add_argument('--pilot-one-seed', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = aggregate(args.task, args.submission,
                       [(Path(route),Path(power)) for route,power in args.pair],
                       (11,) if args.pilot_one_seed else SEEDS,
                       physical_records=[json.loads(p.read_text()) for p in args.physical_record] or None)
    encoded = json.dumps(result,indent=2)+'\n'
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded,end='')


if __name__ == '__main__':
    main()
