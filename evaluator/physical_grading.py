"""Retain completed physical seeds and grade them with the existing PPA formula."""
import json
import statistics
from pathlib import Path

import physical_budget
from ppa_aggregate import source_hash
from score_run import expected_ppa_parameters


def read_receipt(path, task, source, seed):
    record = json.loads(Path(path).read_text())
    physical_budget.validate_records([record], source, task, complete=False)
    if record['layout_seed'] != seed:
        raise ValueError('physical receipt belongs to another seed')
    return record


def single_pe_measurement(model, orfs, reference, physical_records):
    from grade_t10_candidate_ppa import seed_record, workload_parameters
    source = source_hash(model/'submission')
    timeouts = physical_budget.validate_records(physical_records, source, 'T10')
    seeds = [s for s in physical_budget.SEEDS if s not in timeouts]
    if not seeds:
        return None
    rows = [seed_record(model, s, orfs, reference) for s in seeds]
    measurement = dict(task_id='T10', measurement_scope='single_pe',
        measurement_status='three_seed_single_pe', source_sha256=source,
        workload_id=reference['workload_id'], workload_sha256=reference['workload_sha256'],
        workload_parameters=workload_parameters(model, reference),
        parameter_set=expected_ppa_parameters('T10'), routed=True, per_seed=rows,
        **{k: statistics.median(r[k] for r in rows) for k in
           ('area_um2', 'delay_ns', 'energy_per_op_pj', 'average_power_mw')},
        setup_worst_slack_ns=min(r['setup_worst_slack_ns'] for r in rows),
        hold_worst_slack_ns=min(r['hold_worst_slack_ns'] for r in rows),
        drc_violations=max(r['drc_violations'] for r in rows),
        annotation_fraction=min(r['annotation_fraction'] for r in rows))
    return physical_budget.attach(measurement, physical_records)
