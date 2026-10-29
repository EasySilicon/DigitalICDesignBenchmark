#!/usr/bin/env python3
"""Score current candidates with power deadlines and capped delivery deductions."""
import argparse
import copy
import json
from pathlib import Path

if __package__:
    from .delivery_policy import apply_to_score
    from .power_compile_budget import POLICY_ID, TIMEOUT_STATUS, validate_records
    from .score_run import score_run as frozen_score_run
    from .score_run import load_rules
    from . import physical_budget
else:
    from delivery_policy import apply_to_score
    from power_compile_budget import POLICY_ID, TIMEOUT_STATUS, validate_records
    from score_run import score_run as frozen_score_run
    from score_run import load_rules
    import physical_budget


def score_run(payload, rules=None):
    task=payload['task_id']
    measurement=payload.get('ppa_measurement')
    records=payload.get('power_compile_records',(measurement or {}).get('power_compile_records',[]))
    source=payload.get('candidate_source_sha256',(payload.get('ppa_measurement') or {}).get('source_sha256'))
    if isinstance(measurement,dict) and measurement.get('source_sha256')!=source:
        raise ValueError('power compilation and PPA candidate source differ')
    marked=payload.get('power_compile_policy')==POLICY_ID or POLICY_ID in payload.get('scoring_policy','')
    physical_records=payload.get('physical_records',(measurement or {}).get('physical_records',[]))
    expected_physical_policy=physical_budget.policy_id(task)
    if (payload.get('physical_policy')==expected_physical_policy or
            (measurement or {}).get('physical_policy')==expected_physical_policy) and not physical_records:
        raise ValueError('physical deadline policy requires terminal receipts')
    power_timeout=validate_records(records,source,task)
    physical_timeouts=physical_budget.validate_records(physical_records,source,task,complete=not power_timeout) if physical_records else set()
    if (measurement or {}).get('measurement_status')=='physical_timeout_no_results':
        if physical_timeouts!={11,29,47} or measurement.get('physical_records')!=physical_records:
            raise ValueError('no-results zero requires three confirmed physical timeouts')
        payload=copy.deepcopy(payload);payload.pop('ppa_measurement',None);payload.pop('ppa_reference',None)
        measurement=None
    timed_out=validate_records(records,source,task,require_complete=(isinstance(measurement,dict) or marked) and not physical_timeouts)
    if physical_timeouts and not timed_out:
        completed={r['layout_seed'] for r in records if r['status']=='completed'}
        expected={11,29,47}-physical_timeouts
        if completed != expected:
            raise ValueError('retained seeds require matching completed power compile receipts')
    if payload.get('ppa_status')==TIMEOUT_STATUS and not timed_out:
        raise ValueError('timeout zero requires a matching timeout receipt')
    if timed_out:
        payload=copy.deepcopy(payload);payload.pop('ppa_measurement',None);payload.pop('ppa_reference',None)
    base_payload=payload
    if physical_timeouts:
        base_payload=copy.deepcopy(payload);base_payload.pop('ppa_measurement',None);base_payload.pop('ppa_reference',None)
    result=frozen_score_run(base_payload,rules)
    if physical_records:
        if not timed_out:
            result=physical_budget.score_retained(dict(payload,physical_records=physical_records,candidate_source_sha256=source),result,rules or load_rules())
        else:
            result.update(physical_policy=expected_physical_policy,physical_records=copy.deepcopy(physical_records))
    if records:
        result.update(power_compile_policy=POLICY_ID,
                      candidate_source_sha256=source,power_compile_records=copy.deepcopy(records))
    if timed_out:
        result.update(ppa_status=TIMEOUT_STATUS,
            ppa_zero_reason='Power-simulation compilation exceeded the cumulative 1200-second per-seed wall-clock budget.',
            power_compile_policy=POLICY_ID)
    return apply_to_score(result, payload)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(score_run(json.loads(args.results.read_text())),indent=2))


if __name__=='__main__':main()
