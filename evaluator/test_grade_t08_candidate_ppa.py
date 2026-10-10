"""Model identity, timing and final-summary publication regressions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from grade_t08_candidate_ppa import candidate_clock, publish, result_model, run
from score_run import load_rules


class T08CandidateGradingTest(unittest.TestCase):
    def test_fresh_trial_uses_exact_model_and_original_budget(self):
        for name in ('gpt-6-astra', 'gpt-6-sol', 'gpt-6.1-sol', 'deepseek-flash', 'glm-5.3-flash'):
            manifest = {'model': name, 'time_limit_seconds': 7200}
            self.assertEqual(result_model(manifest), name)
            self.assertEqual(candidate_clock(manifest, {'elapsed_seconds': 2992.5}), (2992.5, 7200))
        with self.assertRaises(ValueError):
            result_model({'model': 'unknown'})

    def test_existing_cumulative_clock_remains_supported(self):
        manifest = {'model': 'kimi-code/k3-256k', 'time_limit_seconds': 3600,
                    'previous_submission_elapsed_seconds': 4700,
                    'cumulative_time_limit_seconds': 9000}
        self.assertEqual(result_model(manifest), 'kimi-k3')
        self.assertEqual(candidate_clock(manifest, {'elapsed_seconds': 3300}), (8000, 9000))

    def test_partial_function_skips_physical_eda_and_records_zero_reason(self):
        groups = [group for item in load_rules()['tasks']['T08'] for group in item['groups']]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            trial = root / 'trial'
            (trial / 'workspace/rtl').mkdir(parents=True)
            (trial / 'workspace/rtl/dut.v').write_text('module dut; endmodule\n')
            (trial / 'workspace/rtl/files.f').write_text('dut.v\n')
            (trial / 'run_manifest.json').write_text(json.dumps({
                'model': 'deepseek-flash', 'time_limit_seconds': 7200}))
            (trial / 'summary.json').write_text(json.dumps({
                'functional_total': 0, 'full_functional_pass': False, 'elapsed_seconds': 10,
                'test_groups': [{'id': group, 'cases': [index]} for index, group in enumerate(groups)],
                'cases': {str(index): {'passed': False} for index in range(len(groups))}}))
            with patch('grade_t08_candidate_ppa.delivery', return_value={'delivery_qualified': True}), \
                 patch('grade_t08_candidate_ppa.prepare') as mapping, \
                 patch('grade_t08_candidate_ppa.subprocess.run') as execute, \
                 patch('grade_t08_candidate_ppa.publish') as publication:
                run(trial, root / 'orfs', root / 'repo')
            mapping.assert_not_called()
            execute.assert_not_called()
            publication.assert_called_once()
            score = json.loads((trial / 'final_score.json').read_text())
            self.assertEqual(score['ppa_score'], 0)
            self.assertEqual(score['time_score'], 0)
            self.assertEqual(score['ppa_status'], 'zero_functional_gate')
            self.assertIn('functional acceptance', score['ppa_zero_reason'])
            self.assertEqual(score['failed_functional_cases'], list(range(len(groups))))

    def test_publish_updates_only_selected_model_task_and_excludes_workflow_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results = root / 'repo/results/gpt-6-astra'
            results.mkdir(parents=True)
            original = {'tasks': [
                {'task_id': 'T01', 'functional_total': 50, 'full_functional_pass': True,
                 'ppa_score': 30, 'time_score': 2, 'display_score': 82},
                {'task_id': 'T08', 'functional_total': None, 'ppa_score': None,
                 'time_score': None, 'display_score': None, 'note': 'not run'}]}
            (results / 'summary.json').write_text(json.dumps(original))
            trial = root / 'trial'
            record = {'task_id': 'T08', 'functional_total': 50, 'ppa_score': 35,
                      'time_score': 2, 'display_score': 87, 'elapsed_seconds': 2992.5,
                      'trial_directory': '/private/trial', 'previous_trial': '/private/old',
                      'ppa_measurement_file': '/private/measurement',
                      'eda': {'method': 'host_proc_sampling', 'eda_wall_seconds_estimate': 100,
                              'container': 'private-container', 'container_init_pid': 123,
                              'attached_utc': 'private-attachment', 'active_calls': [],
                              'note': 'workflow bookkeeping'}}
            publish(root / 'repo', 'gpt-6-astra', record, trial)
            summary = json.loads((results / 'summary.json').read_text())
            self.assertEqual(summary['tasks'][0], original['tasks'][0])
            row = summary['tasks'][1]
            self.assertTrue(row['full_functional_pass'])
            self.assertEqual(row['display_score'], 87)
            self.assertNotIn('trial_directory', row)
            self.assertNotIn('previous_trial', row)
            self.assertNotIn('ppa_measurement_file', row)
            self.assertNotIn('note', row)
            self.assertEqual(row['eda'], {'method': 'host_proc_sampling',
                                          'eda_wall_seconds_estimate': 100})
            self.assertEqual(summary['functional_score_sum'], 100)
            self.assertEqual(summary['evaluated_task_count'], 2)
            self.assertEqual(summary['pending_functional_tasks'], [])
            self.assertEqual(json.loads((results / 'T08.json').read_text()), record)
            self.assertEqual(json.loads((trial / 'publication_backup/gpt-6-astra/summary.json').read_text()), original)


if __name__ == '__main__':
    unittest.main()
