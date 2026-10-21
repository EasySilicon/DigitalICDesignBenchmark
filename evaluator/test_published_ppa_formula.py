"""Published historical scores must agree with their audited formula inputs.

The compact audit is self-contained for arithmetic checks. Large physical
artifacts remain in the original archives, identified by paths and hashes.
"""
import hashlib
import json
import math
from pathlib import Path
import unittest

from evaluator.score_run import load_rules, ppa_provenance_valid, ppa_score, weighted_suite_score

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT/'results/ppa-formula-audit-20261021.json'


class PublishedPPAFormulaTest(unittest.TestCase):
    def setUp(self):
        self.audit = json.loads(AUDIT.read_text())
        self.rules = load_rules()
        self.references = json.loads((ROOT/'benchmark/ppa-baselines.json').read_text())['tasks']

    def test_audit_is_bound_to_the_actual_formula_rules_and_reference(self):
        for name, evidence in self.audit['input_fingerprints'].items():
            raw = (ROOT/name).read_bytes()
            self.assertEqual(len(raw), evidence['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), evidence['sha256'])

    def test_all_sixty_published_scores_match_the_audit_and_current_formula(self):
        counts = dict(measured_formula_recomputed=0, preserved_functional_gate_zero=0,
                      preserved_explicit_user_adjudication=0)
        changes = []
        for model, evidence in self.audit['models'].items():
            summary = json.loads((ROOT/'results'/model/'summary.json').read_text())
            rows = {row['task_id']:row for row in summary['tasks']}
            self.assertEqual(set(rows), {f'T{i:02d}' for i in range(1,11)})
            for item in evidence['tasks']:
                task = item['task_id']
                row = rows[task]
                counts[item['status']] += 1
                with self.subTest(model=model, task=task):
                    for key, value in item['expected'].items():
                        self.assertAlmostEqual(row[key], value, places=9)
                    self.assertEqual(item['before']['functional_total'], row['functional_total'])
                    self.assertEqual(item['before']['time_score'], row['time_score'])
                    if item['status'] == 'measured_formula_recomputed':
                        self.assertEqual(row['functional_total'], 50)
                        self.assertTrue(item['normalized_provenance_valid'])
                        self.assertEqual(sorted(item['layout_seeds']), [11,29,47])
                        ppa = ppa_score(item['measurement_inputs'], self.references[task],
                                        self.rules['ppa_points'], self.rules['ppa_reference_points'],
                                        self.rules['setup_violation_exponent'])
                        time = max(0, min(5, 5*(1-item['elapsed_seconds']/item['time_limit_seconds']))) if ppa > 0 else 0
                        self.assertAlmostEqual(row['ppa_score'], ppa, places=9)
                        self.assertAlmostEqual(row['time_score'], time, places=9)
                        self.assertAlmostEqual(row['display_score'],
                            max(0, 50+ppa+time-item['candidate_delivery_penalty']), places=9)
                    else:
                        self.assertEqual(row['ppa_score'], 0)
                        self.assertEqual(row['time_score'], 0)
                        if item['status'] == 'preserved_functional_gate_zero':
                            self.assertLess(row['functional_total'], 50)
                        else:
                            self.assertEqual((model,task), ('gpt-6-sol','T10'))
                    if item['changed_components']:
                        changes.append((model,task))
            weighted = weighted_suite_score({task:row['display_score'] for task,row in rows.items()})
            for key in ('weighted_display_score', 'weighted_display_score_with_unscored_components_omitted'):
                self.assertAlmostEqual(summary[key], weighted['weighted_display_score'], places=9)
            for component, aliases in {
                'functional_total':('functional_score_sum','functional_total_sum'),
                'ppa_score':('ppa_score_sum_for_available_tasks','ppa_score_sum'),
                'time_score':('time_score_sum_for_available_tasks','time_score_sum'),
                'display_score':('display_score_subtotal_with_unscored_components_omitted','display_score_sum')}.items():
                total = math.fsum(row[component] for row in rows.values())
                for alias in aliases:
                    self.assertAlmostEqual(summary[alias], total, places=9)
        self.assertEqual(list(counts.values()), [49,10,1])
        self.assertEqual(changes, [('kimi-k3','T07')])

    def test_kimi_correction_exactly_identifies_the_missing_setup_factor(self):
        item = next(row for row in self.audit['models']['kimi-k3']['tasks'] if row['task_id']=='T07')
        inputs = item['measurement_inputs']
        legacy = ppa_score(inputs, self.references['T07'], setup_violation_exponent=0)
        factor = (1/(1+max(0,-inputs['setup_worst_slack_ns'])))**4
        self.assertAlmostEqual(legacy, item['before']['ppa_score'], places=12)
        self.assertAlmostEqual(legacy*factor, item['expected']['ppa_score'], places=12)
        record = json.loads((ROOT/'results/kimi-k3/T07.json').read_text())
        self.assertTrue(ppa_provenance_valid('T07', record['ppa_measurement'], self.references['T07']))
        self.assertEqual(record['candidate_sha256'], record['ppa_measurement']['source_sha256'])
        self.assertEqual(record['ppa_rank_bucket'], 23)
        self.assertEqual(record['ppa_formula_regrade']['audit'], 'results/ppa-formula-audit-20261021.json')
        for key, value in item['expected'].items():
            self.assertAlmostEqual(record[key], value, places=12)


if __name__ == '__main__':
    unittest.main()
