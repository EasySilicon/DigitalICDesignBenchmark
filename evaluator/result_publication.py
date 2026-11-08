"""Serialize final model results; operational records stay in external archives."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

if __package__:
    from .score_run import load_rules, weighted_suite_score
else:
    from score_run import load_rules, weighted_suite_score

SUMMARY_VERSION = 4
TASK_IDS = tuple(f'T{i:02d}' for i in range(1, 11))
SCORE_KEYS = ('functional_total', 'ppa_score', 'time_score', 'display_score')
METADATA_KEYS = ('suite_id', 'model', 'framework', 'framework_version',
                 'reasoning_effort', 'task_language', 'trial_kind', 'ranking_eligible')
METRIC_KEYS = ('measurement_scope', 'area_um2', 'delay_ns', 'energy_per_op_pj',
               'setup_worst_slack_ns', 'hold_worst_slack_ns', 'drc_violations')
TASK_KEYS = ('task_id', 'functional_total', 'full_functional_pass', 'ppa_eligible',
             'ppa_score', 'ppa_rank_bucket', 'time_score', 'candidate_delivery_penalty',
             'display_score', 'delivery_qualified', 'elapsed_seconds', 'time_limit_seconds',
             'score_status', 'functional_groups', 'score_items', 'ppa_metrics')


def task_record(summary: dict, task: str) -> dict:
    rows = [row for row in summary['tasks'] if row['task_id'] == task]
    if len(rows) != 1:
        raise ValueError(f'summary must contain exactly one {task}')
    return copy.deepcopy(rows[0])


def load_task(repo: Path, model: str, task: str) -> dict:
    return task_record(json.loads((repo / 'results' / model / 'summary.json').read_text()), task)


def final_task(row: dict) -> dict:
    """Select final facts only; never copy arbitrary diagnostic dictionaries."""
    result = {key: copy.deepcopy(row.get(key)) for key in TASK_KEYS}
    if 'full_functional_pass' not in row and result['functional_total'] is not None:
        result['full_functional_pass'] = result['functional_total'] == 50
    if result['task_id'] not in TASK_IDS:
        raise ValueError('unknown task ID')
    for key in SCORE_KEYS:
        value = result[key]
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
            raise ValueError(f'invalid {key}')
    if result['candidate_delivery_penalty'] is None:
        scores = [result[k] for k in SCORE_KEYS]
        difference = math.fsum(scores[:3]) - scores[3] if all(v is not None for v in scores) else None
        result['candidate_delivery_penalty'] = (0 if abs(difference) < 1e-9 else max(0, difference)) if difference is not None else None
    complete = all(result[k] is not None for k in SCORE_KEYS)
    result['score_status'] = 'scored' if complete else 'pending'
    if result['ppa_eligible'] is None and complete:
        # A positive measured score establishes eligibility. A zero does not
        # reveal whether a historical candidate was eligible, so retain null.
        result['ppa_eligible'] = True if result['ppa_score'] > 0 else None
    if result['ppa_rank_bucket'] is None and result['ppa_score'] is not None:
        width = load_rules()['ppa_bucket_width']
        result['ppa_rank_bucket'] = min(40, math.floor(result['ppa_score'] / width + 0.5))
    measurement = row.get('ppa_measurement') or row.get('ppa_metrics')
    if measurement:
        result['ppa_metrics'] = {key: copy.deepcopy(measurement.get(key)) for key in METRIC_KEYS}
    if result['functional_groups'] is not None:
        result['functional_groups'] = {
            name: {key: group[key] for key in ('cases_passed', 'cases_total', 'safety_violation') if key in group}
            for name, group in result['functional_groups'].items()}
    if result['score_items'] is not None:
        result['score_items'] = [
            {key: item[key] for key in ('id', 'layer', 'points', 'possible_points',
                                      'cases_passed', 'cases_total', 'safety_violation') if key in item}
            for item in result['score_items']]
    if complete:
        expected = max(0, result['functional_total'] + result['ppa_score'] + result['time_score'] - result['candidate_delivery_penalty'])
        if not math.isclose(result['display_score'], expected, abs_tol=1e-10, rel_tol=0):
            raise ValueError('display score does not match its components')
    return result


def final_summary(summary: dict, overrides: dict[str, dict] | None = None) -> dict:
    """Publish each task exactly once with a uniform, explicit field allowlist."""
    overrides = overrides or {}
    rows = {task: task_record(summary, task) for task in TASK_IDS}
    if len(summary['tasks']) != len(TASK_IDS) or set(overrides) - set(TASK_IDS):
        raise ValueError('summary must contain the ten unique suite tasks')
    for task, replacement in overrides.items():
        if replacement.get('task_id', task) != task:
            raise ValueError('task override identity mismatch')
        rows[task].update(replacement)
    result = {'schema_version': SUMMARY_VERSION}
    result.update({key: copy.deepcopy(summary.get(key)) for key in METADATA_KEYS})
    if not result['suite_id'] or not result['model']:
        raise ValueError('summary requires suite and model identity')
    # Historical per-task files sometimes carry metadata absent from the old
    # summary. Only promote a field when the retained values agree.
    for key in ('framework', 'framework_version', 'reasoning_effort', 'task_language', 'trial_kind'):
        if result[key] is None:
            values = {r[key] for r in rows.values() if r.get(key) is not None}
            if len(values) == 1:
                result[key] = values.pop()
    result['tasks'] = [final_task(rows[task]) for task in TASK_IDS]
    for key in SCORE_KEYS:
        result[key + '_sum'] = math.fsum(r[key] for r in result['tasks'] if r[key] is not None)
    result['completed_tasks'] = sum(r['score_status'] == 'scored' for r in result['tasks'])
    result['full_functional_task_count'] = sum(r['full_functional_pass'] is True for r in result['tasks'])
    weighted = weighted_suite_score({r['task_id']:r['display_score'] for r in result['tasks']})
    result['task_weights'] = copy.deepcopy(summary.get('task_weights') or load_rules()['task_weights'])
    if result['task_weights'] != load_rules()['task_weights']:
        raise ValueError('publication weights differ from the suite rules')
    result['weighted_display_score'] = weighted['weighted_display_score']
    result['weighted_display_possible'] = weighted['weighted_display_possible']
    return result
