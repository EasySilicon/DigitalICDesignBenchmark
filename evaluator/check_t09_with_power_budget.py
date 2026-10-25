#!/usr/bin/env python3
"""Current T09 acceptance: frozen functional checks plus bounded-power scoring."""
import argparse
import json
from pathlib import Path
import sys

from ppa_aggregate import source_hash
from power_compile_budget import validate_records
from score_with_power_budget import score_run
import physical_budget


def run(submission, seed, elapsed_seconds, delivery_qualified,
        ppa_measurement=None, ppa_reference=None, power_compile_records=None,
        delivery_assessment=None, candidate_delivery_error_count=None, physical_records=None):
    import t09_check as frozen
    source = source_hash(submission)
    records = power_compile_records or []
    if physical_records is None and ppa_measurement is not None and Path(ppa_measurement).is_file():
        physical_records=json.loads(Path(ppa_measurement).read_text()).get('physical_records')
    timeouts=physical_budget.validate_records(physical_records,source,'T09') if physical_records else set()
    validate_records(records, source, 'T09', require_complete=ppa_measurement is not None and not timeouts)
    original = frozen.score_run
    def current_score(payload, rules=None):
        payload = dict(payload, candidate_source_sha256=source, power_compile_records=records)
        if physical_records:
            payload['physical_records']=physical_records
        if candidate_delivery_error_count is not None:
            payload['candidate_delivery_error_count'] = candidate_delivery_error_count
        if delivery_assessment is not None:
            payload['delivery_assessment'] = delivery_assessment
        return score_run(payload, rules)
    try:
        frozen.score_run = current_score
        return frozen.run(submission, seed, elapsed_seconds, delivery_qualified,
                          ppa_measurement, ppa_reference)
    finally:
        frozen.score_run = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('submission', type=Path)
    parser.add_argument('--seed', type=int, default=20260925)
    parser.add_argument('--elapsed-seconds', type=float, required=True)
    parser.add_argument('--delivery-qualified', action='store_true')
    parser.add_argument('--delivery-report', type=Path,
                        help='evaluator delivery report including delivery_assessment')
    parser.add_argument('--ppa-measurement', type=Path)
    parser.add_argument('--ppa-reference', type=Path)
    parser.add_argument('--power-compile-record', action='append', type=Path, default=[])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if (args.ppa_measurement is None) != (args.ppa_reference is None):
        parser.error('both PPA measurement and reference are required')
    try:
        delivery = json.loads(args.delivery_report.read_text()) if args.delivery_report else None
        result = run(args.submission.resolve(), args.seed, args.elapsed_seconds,
                     delivery['delivery_qualified'] if delivery else args.delivery_qualified,
                     args.ppa_measurement, args.ppa_reference,
                     [json.loads(path.read_text()) for path in args.power_compile_record],
                     delivery['delivery_assessment'] if delivery else None)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        result = dict(task_id='T09', phase='infrastructure', error=str(error))
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(encoded)
    else:
        sys.stdout.write(encoded)
    return 0 if result['phase'] == 'scored' else 1


if __name__ == '__main__':
    raise SystemExit(main())
