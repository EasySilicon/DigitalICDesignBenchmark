"""Archive updates must use replayed evidence and preserve penalties/nulls."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from evaluator.regrade_t09_archive import ROOT, POLICY, read, refresh_summary, regrade_record
from evaluator.score_run import load_rules


class T09RegradeTest(unittest.TestCase):
    def setUp(self):
        self.rules = load_rules()
        self.reference = read(ROOT/'benchmark/ppa-baselines.json')['tasks']['T09']
        self.grade = read(ROOT/'evaluator/fixtures/t09_cpu_20261009_cycles10/functional.json')
        self.old = {'task_id': 'T09', 'functional_total': 50, 'full_functional_pass': True,
                    'ppa_score': 0, 'time_score': 0, 'display_score': 50,
                    'time_limit_seconds': 7200, 'candidate_delivery_error_count': 1}
        self.entry = {'submission': str(ROOT/'evaluator/reference/T09'),
                      'origin': 'frozen answer', 'elapsed': 1886, 'delivery': False}

    def score(self):
        return regrade_record(self.old, self.grade, self.entry, self.reference, self.rules)

    def fail_cycles(self, number):
        rows = self.grade['diagnostics']['timing_cycles']['outcomes']
        for row in rows[:number]:
            row['passed'] = False
        self.grade['groups']['CPU-PIPE-CYCLES']['cases_passed'] = 22-number

    def test_preserves_delivery_penalty_and_original_elapsed(self):
        result = self.score()
        self.assertEqual(result['functional_total'], 50)
        self.assertEqual(result['candidate_delivery_penalty'], 5)
        self.assertEqual(result['display_score'], 45)
        self.assertEqual(result['elapsed_seconds'], 1886)
        self.assertEqual(result['scoring_policy'], POLICY)
        self.assertFalse(result['delivery_qualified'])

    def test_cycle_failures_are_grouped_and_clear_full_pass(self):
        for failures, points in ((1, 45), (11, 45), (12, 40), (22, 40)):
            with self.subTest(failures=failures):
                self.setUp()
                self.fail_cycles(failures)
                result = self.score()
                self.assertEqual(result['functional_total'], points)
                self.assertEqual(result['display_score'], points-5)
                self.assertFalse(result['full_functional_pass'])
                self.assertFalse(result['ppa_eligible'])

    def test_missing_or_stale_replay_cannot_publish(self):
        self.grade['scoring_policy'] = 'old'
        with self.assertRaises(ValueError):
            self.score()
        self.setUp()
        self.grade['groups'].pop('CPU-PIPE-CYCLES')
        with self.assertRaises(ValueError):
            self.score()

    def test_count_totals_cannot_hide_an_individual_failure(self):
        self.grade['diagnostics']['timing_cycles']['outcomes'][0]['passed'] = False
        with self.assertRaises(ValueError):
            self.score()

    def test_wrong_candidate_hash_cannot_publish(self):
        self.old['candidate_sha256'] = 'a'*64
        with self.assertRaises(ValueError):
            self.score()

    def test_wrong_replay_source_hash_cannot_publish(self):
        self.grade['diagnostics']['timing_cycles']['rtl_sha256']['ref.sv'] = 'a'*64
        with self.assertRaises(ValueError):
            self.score()

    def test_ppa_source_binding_and_baseline_recompute(self):
        with tempfile.TemporaryDirectory() as directory:
            measurement = Path(directory)/'measurement.json'
            measurement.write_text(json.dumps(self.reference))
            self.entry['measurement'] = str(measurement)
            result = self.score()
            self.assertTrue(result['ppa_eligible'])
            self.assertEqual(result['ppa_score'], 35)
            self.assertEqual(result['candidate_delivery_penalty'], 5)
            self.assertFalse(result['delivery_qualified'])
            bad = copy.deepcopy(self.reference)
            bad['source_sha256'] = 'a'*64
            measurement.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                self.score()

    def test_previously_measured_passing_answer_needs_ppa_evidence(self):
        self.old['ppa_score'] = 5
        with self.assertRaises(ValueError):
            self.score()

    def test_summary_updates_aliases_without_changing_other_task_rows(self):
        updated = self.score()
        other = {'task_id': 'T08', 'functional_total': None, 'full_functional_pass': None,
                 'ppa_score': None, 'time_score': None, 'display_score': None}
        summary = {'tasks': [other, self.old], 'functional_total_sum': 50,
                   'ppa_score_sum': 0, 'time_score_sum': 0, 'display_score_sum': 50,
                   'weighted_display_score': 10, 'weighted_contributions': {'T09': 10}}
        result = refresh_summary(summary, [other, updated], updated, self.rules)
        self.assertEqual(result['tasks'][0], other)
        self.assertIsNone(result['tasks'][0]['display_score'])
        self.assertEqual(result['tasks'][1]['display_score'], 45)
        self.assertEqual(result['display_score_sum'], 45)
        self.assertEqual(result['display_score_subtotal_with_unscored_components_omitted'], 45)
        self.assertEqual(result['weighted_display_score'], 9)
        self.assertEqual(result['weighted_display_score_with_unscored_components_omitted'], 9)
        self.assertEqual(result['task_scoring_policies']['T09'], POLICY)


if __name__ == '__main__':
    unittest.main()
