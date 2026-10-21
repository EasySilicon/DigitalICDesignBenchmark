#!/usr/bin/env python3
"""Score new candidates with the uniform power compile deadline policy."""
import argparse
import copy
import json
from pathlib import Path

if __package__:
    from .power_compile_budget import POLICY_ID, TIMEOUT_STATUS, validate_records
    from .score_run import score_run as frozen_score_run
else:
    from power_compile_budget import POLICY_ID, TIMEOUT_STATUS, validate_records
    from score_run import score_run as frozen_score_run


def score_run(payload, rules=None):
    task=payload['task_id']
    measurement=payload.get('ppa_measurement')
    records=payload.get('power_compile_records',(measurement or {}).get('power_compile_records',[]))
    source=payload.get('candidate_source_sha256',(payload.get('ppa_measurement') or {}).get('source_sha256'))
    if isinstance(measurement,dict) and measurement.get('source_sha256')!=source:
        raise ValueError('power compilation and PPA candidate source differ')
    marked=payload.get('power_compile_policy')==POLICY_ID or POLICY_ID in payload.get('scoring_policy','')
    timed_out=validate_records(records,source,task,require_complete=isinstance(measurement,dict) or marked)
    if payload.get('ppa_status')==TIMEOUT_STATUS and not timed_out:
        raise ValueError('timeout zero requires a matching timeout receipt')
    if timed_out:
        payload=copy.deepcopy(payload);payload.pop('ppa_measurement',None);payload.pop('ppa_reference',None)
    result=frozen_score_run(payload,rules)
    if records:
        result.update(power_compile_policy=POLICY_ID,
                      candidate_source_sha256=source,power_compile_records=copy.deepcopy(records))
    if timed_out:
        result.update(ppa_status=TIMEOUT_STATUS,
            ppa_zero_reason='Power-simulation compilation exceeded the cumulative 1200-second per-seed wall-clock budget.',
            power_compile_policy=POLICY_ID)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(score_run(json.loads(args.results.read_text())),indent=2))


if __name__=='__main__':main()
