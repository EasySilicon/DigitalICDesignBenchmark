"""T10 v16: whole-design cost, extracted PE-internal timing, strict V1 math.

No top-level timing estimate is admitted into this score. Raw evidence belongs
in the caller's external output directory, never in published summaries.
"""
from __future__ import annotations

import hashlib
import copy
import argparse
import json
import math
from pathlib import Path
import statistics

from ppa_aggregate import source_hash
from score_run import expected_ppa_parameters, load_rules, ppa_score

REPO = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO / 'benchmark/tasks/T10/ppa-policy-v16.json'


def policy():
    return json.loads(POLICY_PATH.read_text())


def artifact(path):
    path = Path(path).resolve(strict=True)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            digest.update(block)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest.hexdigest())


def check(record):
    found = artifact(record['path'])
    if record.get('sha256') != found['sha256'] or (
            'bytes' in record and record['bytes'] != found['bytes']):
        raise ValueError('changed evidence: ' + record['path'])
    return found


def external_directory(path):
    path = Path(path).resolve()
    if path == REPO or REPO in path.parents:
        raise ValueError('measurement outputs must be outside the repository')
    return path


def write(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def finite(value, *, positive=False):
    return (type(value) in (int, float) and math.isfinite(value)
            and (not positive or value > 0))


def functional_qualified(report):
    """Counts alone do not prove stream, reset, structure or strict precision."""
    from runner_t10_stream import functional_passed
    return (report.get('task_id') == 'T10'
            and report.get('profile', 'exact-dot-v1') == 'exact-dot-v1'
            and functional_passed(report))


def aggregate(source, rows, physical_records=None):
    contract = policy()
    timed_out = set()
    if physical_records:
        from physical_budget import validate_records
        timed_out = validate_records(physical_records, source, 'T10')
    expected_seeds = {11, 29, 47} - timed_out
    if (not isinstance(source, str) or len(source) != 64 or not isinstance(rows, list)
            or not rows or len(rows) != len(expected_seeds)
            or {r.get('layout_seed') for r in rows} != expected_seeds):
        raise ValueError('all completed source-bound layout seeds are required')
    for row in rows:
        if (row.get('source_sha256') != source or row.get('policy_id') != contract['policy_id']
                or row.get('timing_scope') != contract['timing_scope']
                or row.get('pe_routed') is not True or row.get('matrix_blocks') != 200
                or row.get('annotation_fraction', 0) < .95
                or row.get('peripheral_annotation_fraction', 0) < .95
                or type(row.get('drc_violations')) is not int or row['drc_violations'] < 0):
            raise ValueError('incompatible or incomplete hybrid measurement')
        for key in ('area_um2', 'delay_ns', 'energy_per_op_pj', 'average_power_mw'):
            if not finite(row.get(key), positive=True):
                raise ValueError('invalid positive measurement: ' + key)
        for key in ('setup_worst_slack_ns', 'hold_worst_slack_ns'):
            if not finite(row.get(key)):
                raise ValueError('invalid PE timing: ' + key)
        if not math.isclose(row['delay_ns'], 1 - row['setup_worst_slack_ns'], abs_tol=1e-9):
            raise ValueError('delay must use the PE-internal setup path')
        expected_area = row['peripheral_cell_area_um2'] + 256 * row['pe_cell_area_um2']
        expected_power = row['peripheral_power_w'] + 256 * row['pe_power_w'] + row['primary_input_power_w']
        for key in ('peripheral_cell_area_um2', 'peripheral_power_w', 'primary_input_power_w'):
            if not finite(row[key]) or row[key] < 0:
                raise ValueError('invalid peripheral cost')
        if (not math.isclose(row['area_um2'], expected_area, rel_tol=1e-10)
                or not math.isclose(row['average_power_mw'], expected_power * 1000, rel_tol=1e-10)
                or not finite(row['duration_seconds'], positive=True)
                or not math.isclose(row['energy_per_op_pj'], expected_power * row['duration_seconds'] / 200 * 1e12,
                                    rel_tol=1e-10)):
            raise ValueError('whole-design cost accounting mismatch')
    return dict(task_id='T10', policy_id=contract['policy_id'], source_sha256=source,
                measurement_scope='whole_design_cost_pe_internal_timing',
                measurement_status='physical_timeout_retained_hybrid' if timed_out else 'three_seed_hybrid',
                **({'physical_records': copy.deepcopy(physical_records)} if physical_records else {}),
                timing_scope=contract['timing_scope'],
                full_design_routed=False, pe_routed=True,
                # ppa_score's routing prerequisite is satisfied by the PE;
                # never expose this flag without the explicit scopes above.
                routed=True, parameter_set=expected_ppa_parameters('T10'),
                workload_id='T10-power-v1', per_seed=copy.deepcopy(sorted(rows, key=lambda r: r['layout_seed'])),
                **{key: statistics.median(r[key] for r in rows)
                   for key in ('area_um2', 'delay_ns', 'energy_per_op_pj', 'average_power_mw')},
                setup_worst_slack_ns=min(r['setup_worst_slack_ns'] for r in rows),
                hold_worst_slack_ns=min(r['hold_worst_slack_ns'] for r in rows),
                drc_violations=max(r['drc_violations'] for r in rows),
                annotation_fraction=min(min(r['annotation_fraction'], r['peripheral_annotation_fraction']) for r in rows))


def reference_qualified(reference):
    frozen = json.loads((REPO / 'evaluator/reference/T10_v16/reference.json').read_text())
    return (reference.get('source_sha256') == frozen['source_sha256']
            and reference.get('policy_id') == policy()['policy_id']
            and reference.get('measurement_status') == 'three_seed_hybrid'
            and reference['setup_worst_slack_ns'] >= 0
            and reference['hold_worst_slack_ns'] >= 0 and reference['drc_violations'] == 0
            and reference['annotation_fraction'] >= .95)


def provenance_valid(measurement, reference):
    """Validate both scopes and accounting before the common scorer uses v16."""
    try:
        for record in (measurement, reference):
            rebuilt = aggregate(record['source_sha256'], record['per_seed'], record.get('physical_records'))
            if any(record.get(key) != value for key, value in rebuilt.items()):
                return False
            if 'workload_sha256' in record and record['workload_sha256'] != reference.get('workload_sha256'):
                return False
            if 'workload_parameters' in record and record['workload_parameters'] != reference.get('workload_parameters'):
                return False
        return reference_qualified(reference)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def official_reference():
    """Read the sole authoritative baseline; do not keep a second value table."""
    reference = json.loads((REPO / 'benchmark/ppa-baselines.json').read_text())['tasks']['T10']
    if reference.get('qualification_status') != 'qualified_1ghz' or not provenance_valid(reference, reference):
        raise ValueError('the authoritative T10 v16 reference is not qualified')
    return reference


def score(measurement, reference):
    """Keep the existing formula; reject legacy/single-PE or mixed scopes."""
    if not provenance_valid(measurement, reference):
        raise ValueError('incompatible v16 scopes, aggregate or reference qualification')
    rules = load_rules()
    return ppa_score(measurement, reference, rules['ppa_points'],
                     rules['ppa_reference_points'], rules['setup_violation_exponent'])


def compare_files(reference_path, paths, output):
    """Recompute a source-bound comparison without launching any EDA."""
    output = external_directory(output)
    reference = official_reference() if reference_path is None else json.loads(Path(reference_path).read_text())
    reference_artifact = artifact(REPO / 'benchmark/ppa-baselines.json' if reference_path is None else reference_path)
    records, labels = [], set()
    for path in paths:
        measurement = json.loads(Path(path).read_text())
        label = measurement['label']
        if label in labels:
            raise ValueError('duplicate measurement label')
        labels.add(label)
        check(measurement['functional_report'])
        if not functional_qualified(json.loads(Path(measurement['functional_report']['path']).read_text())):
            raise ValueError('strict functional acceptance no longer matches')
        for row in measurement['per_seed']:
            for record in row['evidence'].values():
                check(record)
        records.append(dict(label=label, ppa_score=score(measurement, reference),
                            area_mm2=measurement['area_um2'] / 1e6,
                            energy_nj_per_matrix=measurement['energy_per_op_pj'] / 1000,
                            pe_delay_ns=measurement['delay_ns'],
                            pe_setup_slack_ns=measurement['setup_worst_slack_ns'],
                            pe_hold_slack_ns=measurement['hold_worst_slack_ns'],
                            drc_violations=measurement['drc_violations'], evidence=artifact(path)))
    write(output, dict(policy=policy(), reference=reference_artifact,
                       reference_selector='tasks.T10' if reference_path is None else None,
                       measurements=records))
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, help='explicit qualified reference; defaults to the authoritative T10 baseline')
    parser.add_argument('--measurement', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    for record in compare_files(args.reference, args.measurement, args.output):
        print(record['label'], format(record['ppa_score'], '.6f'))
