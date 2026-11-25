"""Small controls for the v16 measurement boundary and retained score formula."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from t10_hybrid_ppa import aggregate, artifact, check, external_directory, official_reference, policy, score, REPO
from t10_hybrid_activity import aliases, extract
from t10_hybrid_measure import native


class NativeAnalysisTest(unittest.TestCase):
    def test_optional_analysis_deadline_and_tool_errors(self):
        # A small fake tool proves that removing an infrastructure deadline
        # preserves actual tool failures instead of turning them into success.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tool = root / 'openroad'
            tool.write_text('#!' + sys.executable + '\n'
                            'import pathlib, sys, time\n'
                            'time.sleep(.1)\n'
                            'text = pathlib.Path(sys.argv[-1]).read_text()\n'
                            'print(text)\n'
                            'sys.exit(7 if text == "fail" else 0)\n')
            tool.chmod(0o755)
            env = os.environ | {'PATH': str(root)}
            with self.assertRaises(subprocess.TimeoutExpired):
                native('ok', root / 'deadline.log', env=env, timeout=.01)
            self.assertEqual(native('ok', root / 'completed.log', env=env,
                                    timeout=None).strip(), 'ok')
            with self.assertRaises(subprocess.CalledProcessError):
                native('fail', root / 'failed.log', env=env, timeout=None)
            with self.assertRaises(ValueError):
                native('[ERROR test]', root / 'error.log', env=env, timeout=None)


class HybridScoreTest(unittest.TestCase):
    def official_payload(self):
        from score_run import load_rules
        reference = official_reference()
        groups = {group: dict(cases_passed=1, cases_total=1)
                  for item in load_rules()['tasks']['T10'] for group in item['groups']}
        return dict(task_id='T10', groups=groups, sustained_throughput_passed=True,
                    delivery_qualified=True, elapsed_seconds=3600, time_limit_seconds=14400,
                    ppa_reference=reference, ppa_measurement=copy.deepcopy(reference))

    def test_authoritative_v16_baseline_works_through_common_score_entry(self):
        from score_run import score_run
        result = score_run(self.official_payload())
        self.assertTrue(result['ppa_eligible'])
        self.assertEqual(result['functional_total'], 50.)
        self.assertEqual(result['ppa_score'], 35.)
        self.assertEqual(result['time_score'], 3.75)

    def test_trial_regrader_accepts_current_hybrid_measurement(self):
        from regrade_trial_ppa import main
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'summary.json').write_text(json.dumps(dict(tasks=[])))
            measurement = root / 'measurement.json'
            measurement.write_text(json.dumps(official_reference()))
            output = root / 'regraded.json'
            arguments = ['regrade', str(root), '--model', 'control',
                         '--measurement', 'T10=' + str(measurement), '--output', str(output)]
            with patch.object(sys, 'argv', arguments), patch('builtins.print'):
                self.assertEqual(main(), 0)
            row = next(row for row in json.loads(output.read_text())['tasks'] if row['task_id'] == 'T10')
            self.assertEqual(row['status'], 'scored')
            self.assertEqual(row['ppa_score'], 35.)

    def test_common_entry_rejects_scope_mixing_and_omitted_cost(self):
        from score_run import score_run
        for key, value in [('measurement_scope', 'single_pe'),
                           ('timing_scope', 'whole_design'),
                           ('full_design_routed', True), ('area_um2', 1.)]:
            payload = self.official_payload()
            payload['ppa_measurement'][key] = value
            with self.subTest(key=key):
                result = score_run(payload)
                self.assertFalse(result['ppa_eligible'])
                self.assertEqual(result['ppa_score'], 0.)
                self.assertEqual(result['time_score'], 0.)
                self.assertEqual(result['functional_total'], 50.)

    def test_retained_hybrid_seeds_work_through_budgeted_score_entry(self):
        from physical_budget import receipt
        from score_with_power_budget import score_run
        payload = self.official_payload()
        measurement = payload['ppa_measurement']
        source = measurement['source_sha256']
        budgets = [receipt('T10', source, seed, 7200 if seed != 11 else 100,
                           'timeout' if seed != 11 else 'completed',
                           process_group_terminated=seed != 11) for seed in (11, 29, 47)]
        partial = aggregate(source, measurement['per_seed'][:1], budgets)
        payload.update(ppa_measurement=partial, candidate_source_sha256=source,
                       physical_records=budgets,
                       power_compile_records=[dict(policy_id='power-compile-wall-2400s-v2',
                           limit_seconds=2400, task_id='T10', candidate_source_sha256=source,
                           layout_seed=11, status='completed', elapsed_seconds=100)])
        result = score_run(payload)
        self.assertTrue(result['ppa_eligible'])
        self.assertAlmostEqual(result['ppa_score'], score(partial, payload['ppa_reference']))
        self.assertEqual(result['physical_timed_out_seeds'], [29, 47])

    def rows(self):
        source = json.loads((REPO / 'evaluator/reference/T10_v16/reference.json').read_text())['source_sha256']
        rows = []
        for seed in (11, 29, 47):
            rows.append(dict(source_sha256=source, layout_seed=seed, policy_id=policy()['policy_id'],
                             timing_scope=policy()['timing_scope'], pe_routed=True, matrix_blocks=200,
                             annotation_fraction=1., peripheral_annotation_fraction=1., drc_violations=0,
                             area_um2=257., pe_cell_area_um2=1., peripheral_cell_area_um2=1.,
                             pe_power_w=.001, peripheral_power_w=.001, primary_input_power_w=.001,
                             average_power_mw=258., duration_seconds=2e-6, energy_per_op_pj=2580.,
                             delay_ns=.95, setup_worst_slack_ns=.05, hold_worst_slack_ns=.04))
        return source, rows

    def test_reference_self_score_35_and_peripheral_cost_penalized(self):
        source, rows = self.rows()
        reference = aggregate(source, rows)
        self.assertEqual(score(reference, reference), 35.)
        changed = copy.deepcopy(rows)
        for row in changed:
            row['peripheral_cell_area_um2'] += 257
            row['area_um2'] += 257
            row['peripheral_power_w'] += .258
            row['average_power_mw'] *= 2
            row['energy_per_op_pj'] *= 2
        candidate = aggregate(source, changed)
        self.assertLess(score(candidate, reference), 35.)
        self.assertEqual(candidate['delay_ns'], reference['delay_ns'])

    def test_arbitrary_top_level_slack_does_not_affect_score(self):
        source, rows = self.rows()
        reference = aggregate(source, rows)
        for row in rows:
            row['diagnostic_top_slack_ns'] = -1e9
        candidate = aggregate(source, rows)
        self.assertEqual(score(candidate, reference), 35.)

    def test_hold_and_setup_remain_in_formula(self):
        source, rows = self.rows()
        reference = aggregate(source, rows)
        for row in rows:
            row.update(setup_worst_slack_ns=-.2, delay_ns=1.2, hold_worst_slack_ns=-.1)
        candidate = aggregate(source, rows)
        expected = 35 * (.95 / 1.3)**.35 * (1 / 1.2)**4
        self.assertAlmostEqual(score(candidate, reference), expected)

    def test_rejects_missing_duplicate_seeds_and_mixed_scopes(self):
        source, rows = self.rows()
        for changed in (rows[:2], [rows[0], rows[0], rows[2]]):
            with self.assertRaises(ValueError): aggregate(source, changed)
        for key, value in [('source_sha256', 'b' * 64), ('timing_scope', 'whole_design'),
                           ('policy_id', 'legacy'), ('pe_routed', False),
                           ('peripheral_annotation_fraction', .94)]:
            changed = copy.deepcopy(rows)
            changed[0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): aggregate(source, changed)

    def test_rejects_cost_omission_nan_and_stale_aggregate(self):
        source, rows = self.rows()
        for key, value in [('area_um2', 256.), ('average_power_mw', 257.),
                           ('energy_per_op_pj', float('nan')), ('delay_ns', 1.)]:
            changed = copy.deepcopy(rows)
            changed[0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): aggregate(source, changed)
        reference = aggregate(source, rows)
        candidate = copy.deepcopy(reference)
        candidate['area_um2'] /= 2
        with self.assertRaises(ValueError): score(candidate, reference)

    def test_unqualified_reference_rejected(self):
        source, rows = self.rows()
        for row in rows:
            row['hold_worst_slack_ns'] = -.001
        reference = aggregate(source, rows)
        with self.assertRaises(ValueError): score(reference, reference)

    def test_partial_physical_results_require_actual_timeout_receipts(self):
        from physical_budget import receipt
        source, rows = self.rows()
        reference = aggregate(source, rows)
        budgets = [receipt('T10', source, seed, 7200 if seed != 11 else 100,
                           'timeout' if seed != 11 else 'completed',
                           process_group_terminated=seed != 11)
                   for seed in (11, 29, 47)]
        partial = aggregate(source, rows[:1], budgets)
        self.assertEqual(partial['measurement_status'], 'physical_timeout_retained_hybrid')
        self.assertEqual(score(partial, reference), 35.)
        with self.assertRaises(ValueError): aggregate(source, rows[:1])
        budgets[1]['process_group_terminated'] = False
        with self.assertRaises(ValueError): aggregate(source, rows[:1], budgets)

    def test_outputs_external_and_artifact_changes_detected(self):
        with self.assertRaises(ValueError): external_directory(REPO / 'archived/new')
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'proof.json'
            p.write_text('{}')
            record = artifact(p)
            self.assertEqual(check(record), record)
            p.write_text('{ }')
            with self.assertRaises(ValueError): check(record)


class PeripheralAliasTest(unittest.TestCase):
    def test_equivalent_bus_aliases_and_normalization_collision(self):
        module = {'netnames': {'x': {'bits': [3, 4], 'offset': 1},
                               'renamed': {'bits': [3]}}}
        found = aliases(module)
        self.assertEqual(found['x[1]'], found['renamed'])
        with self.assertRaises(ValueError):
            aliases({'netnames': {'a/b': {'bits': [3]}, 'a.b': {'bits': [4]}}})

    def test_conflicting_electrical_alias_activity_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'activity.saif'
            p.write_text('''(SAIFILE
(TIMESCALE 1 ps)
(DURATION 10)
(INSTANCE tb_hidden_T10_stream
(INSTANCE dut
(NET
(x (T0 5) (T1 5) (TZ 0) (TX 0) (TB 0) (TC 2))
(y (T0 5) (T1 5) (TZ 0) (TX 0) (TB 0) (TC 4))
)
)
)
)
''')
            with self.assertRaisesRegex(ValueError, 'different activity'):
                extract(p, {'x': 3, 'y': 3}, [], Path(temp) / 'out.json')


if __name__ == '__main__':
    unittest.main()
