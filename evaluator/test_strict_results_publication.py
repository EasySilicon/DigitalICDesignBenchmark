"""Final summaries are the sole source of current per-model results."""
from collections import Counter
from pathlib import Path
import json
import unittest

import jsonschema
from score_run import load_rules, score_functional
from runner_t10_stream import stream_cases

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results'
read = lambda p: json.loads(p.read_text())


class StrictPublicationTest(unittest.TestCase):
    def test_strict_scores_recompute_from_final_counts_inside_summary(self):
        rules = load_rules()
        checked = []
        for path in RESULTS.glob('*/summary.json'):
            summary = read(path)
            jsonschema.validate(summary, read(RESULTS / 'result.schema.json'))
            task = summary['tasks'][-1]
            if task['functional_groups'] is None:
                self.assertEqual(path.parent.name, 'deepseek-flash')
                self.assertEqual(task['functional_total'], 0)
                continue
            checked.append(path.parent.name)
            basic, edges, items = score_functional('T10', task['functional_groups'], rules)
            self.assertAlmostEqual(task['functional_total'], basic + edges)
            self.assertEqual(task['score_items'], items)
            if not task['full_functional_pass']:
                self.assertEqual((task['ppa_score'], task['time_score']), (0, 0))
        self.assertEqual(len(checked), 10)
        for name in ['gpt-6-astra', 'gpt-6.1-sol', 'gpt-6-sol', 'kimi-k3.1-pro']:
            self.assertEqual(read(RESULTS / name / 'summary.json')['tasks'][-1]['functional_total'], 50)
        self.assertAlmostEqual(read(RESULTS / 'claude-sonnet-5.5/summary.json')['tasks'][-1]['functional_total'], 48.43556579258209)
        self.assertAlmostEqual(read(RESULTS / 'claude-opus-5.5/summary.json')['tasks'][-1]['functional_total'], 49.240255138199856)

    def test_current_inventory_describes_acceptance_without_replay_history(self):
        inventory = read(RESULTS / 't10-strict-functional-retest-20261106.json')
        self.assertEqual(inventory['numerical_profile'], 'exact-dot-v1')
        self.assertFalse(inventory['numerical_precision_relaxed'])
        cases, _ = stream_cases(inventory['seed'])
        self.assertEqual(len(cases), inventory['scored_stream_cases'])
        counts = Counter(c.group for c in cases)
        counts['MM-PROTO'] += inventory['runtime_reset_probes']
        self.assertEqual(dict(counts), inventory['group_case_counts'])
        self.assertNotIn('models', inventory)
        self.assertNotIn('previous_results_backup', inventory)

    def test_token_totals_use_the_final_max_and_opus_trials_without_raw_logs(self):
        records = {r['model']:r for r in read(RESULTS / 'token-usage.json')['models']}
        self.assertEqual(records['kimi-k3.1-pro']['reasoning_effort'], 'max')
        self.assertEqual(records['kimi-k3.1-pro']['total_tokens'], 405087147)
        self.assertEqual(records['claude-opus-5.5']['total_tokens'], 126636800)
        for model in records.values():
            self.assertEqual(model['total_tokens'], sum(row['tokens'] for row in model['tasks']))
            self.assertEqual([r['task_id'] for r in model['tasks']], [f'T{i:02}' for i in range(1,11)])
            for row in model['tasks']:
                self.assertEqual(set(row), {'task_id', 'tokens'})
                self.assertGreater(row['tokens'], 0)
