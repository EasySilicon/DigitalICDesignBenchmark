"""Model identity, timing and final-summary publication regressions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import re
import yaml

from grade_t08_candidate_ppa import candidate_clock, publish, result_model, run, delivery
from score_run import load_rules
from result_publication import final_summary
from benchmark.runner.config import load_config
from benchmark.test_runner_config import valid_config


class T08CandidateGradingTest(unittest.TestCase):
    def test_delivery_uses_current_container_policy_without_a_model_runner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);trial=root/'trial';workspace=trial/'workspace';output=root/'output';output.mkdir()
            (workspace/'rtl').mkdir(parents=True);(workspace/'verif').mkdir()
            (workspace/'rtl/files.f').write_text('dut.v\n')
            (workspace/'rtl/dut.v').write_text('module dut; endmodule\n')
            (workspace/'verif/selfcheck.py').write_text('pass\n')
            (workspace/'README.md').write_text('Run ./run.sh')
            (workspace/'run.sh').write_text('#!/bin/sh\nexit 0\n');(workspace/'run.sh').chmod(0o755)
            config_path=root/'runner.yaml';config_path.write_text(yaml.safe_dump(valid_config(root)))
            commands=[]
            def execute(command,**kwargs):
                if command[:2]==['docker','run']:
                    commands.append(command)
                    seed=int(re.search(r'BENCH_SEED=(\d+)',command[-1])[1])
                    report=dict(tests=[dict(name='selfcheck',passed=True,seed=seed)],tool_versions={'tool':'test'},elapsed_seconds=1)
                    (output/'delivery_sandbox/workspace/results.json').write_text(json.dumps(report))
                return SimpleNamespace(returncode=0)
            with patch('grade_t08_candidate_ppa.subprocess.run',side_effect=execute):
                result=delivery(trial,output,load_config(config_path))
            self.assertEqual(result['delivery_seeds'],[11,29,47])
            self.assertEqual(result['replays_per_seed'],2)
            self.assertEqual(len(commands),6)
            for command in commands:
                self.assertEqual(command[command.index('--cpus')+1],'16')
                self.assertEqual(command[command.index('--memory')+1],'40g')
                self.assertNotIn('--pids-limit',command)
                self.assertFalse(any('frozen_judge' in part or '/opt/kimi' in part for part in command))
                self.assertEqual(command[-1].split()[-1],'./run.sh')

    def test_fresh_trial_uses_exact_model_and_original_budget(self):
        for name in ('gpt-6-astra', 'gpt-6-sol', 'gpt-6.1-sol', 'gpt-5.6-sol',
                     'deepseek-flash', 'glm-5.3-flash'):
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
            table = root / 'repo/results/model-score-comparison.md'
            table.write_text('| T08 | 11% | preserved |\n')
            original=final_summary(dict(suite_id='test',model='gpt-6-astra',ranking_eligible=False,
                tasks=[dict(task_id=f'T{i:02}',functional_total=50,full_functional_pass=True,
                            ppa_score=30,time_score=2,display_score=82) for i in range(1,11)]))
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
            self.assertEqual(table.read_text(), '| T08 | 11% | preserved |\n')
            summary = json.loads((results / 'summary.json').read_text())
            self.assertEqual(summary['tasks'][0], original['tasks'][0])
            row = summary['tasks'][7]
            self.assertTrue(row['full_functional_pass'])
            self.assertEqual(row['display_score'], 87)
            self.assertNotIn('trial_directory', row)
            self.assertNotIn('previous_trial', row)
            self.assertNotIn('ppa_measurement_file', row)
            self.assertNotIn('note', row)
            self.assertNotIn('eda',row)
            self.assertEqual(summary['functional_total_sum'],500)
            self.assertEqual(summary['completed_tasks'],10)
            self.assertEqual({p.name for p in results.iterdir()},{'summary.json'})
            self.assertEqual(summary['tasks'][:7],original['tasks'][:7])
            self.assertEqual(summary['tasks'][8:],original['tasks'][8:])
            self.assertEqual(json.loads((trial / 'publication_backup/gpt-6-astra/summary.json').read_text()), original)


if __name__ == '__main__':
    unittest.main()
