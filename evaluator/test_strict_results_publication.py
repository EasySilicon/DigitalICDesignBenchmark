"""Final summaries are the sole source of current per-model results."""
from collections import Counter
from pathlib import Path
import json
import unittest
import re
import xml.etree.ElementTree as ET

import jsonschema
from score_run import load_rules, score_functional
from runner_t10_stream import stream_cases

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results'
read = lambda p: json.loads(p.read_text())


class StrictPublicationTest(unittest.TestCase):
    def test_published_views_match_finalized_summaries(self):
        summaries = {p.parent.name: read(p) for p in RESULTS.glob('*/summary.json')}
        for model, summary in summaries.items():
            with self.subTest(model=model):
                self.assertEqual(summary['completed_tasks'], 10)
                self.assertEqual(len(summary['tasks']), 10)
                self.assertEqual({task['score_status'] for task in summary['tasks']}, {'scored'})
        groups = [node for node in ET.parse(RESULTS / 'model-score-leaderboard.svg').iter()
                  if 'data-model' in node.attrib]
        expected = sorted(summaries, key=lambda model: -summaries[model]['weighted_display_score'])
        self.assertEqual([node.attrib['data-model'] for node in groups], expected)
        for node in groups:
            summary = summaries[node.attrib['data-model']]
            labels = [part.strip() for part in node.itertext() if part.strip()]
            self.assertEqual(labels[-1], f"{summary['weighted_display_score']:.2f}")
            self.assertNotIn('None', ''.join(labels))
            self.assertAlmostEqual(float(node.attrib['data-score']), summary['weighted_display_score'], places=10)
            self.assertEqual(node.attrib['data-status'], 'complete')
        documents = [(ROOT / rel).read_text() for rel in
                     ['README.md', 'README.en.md', 'results/model-score-comparison.md']]
        main_rows = []
        for text in documents:
            row = next(line for line in text.splitlines()
                       if line.startswith('| T10 |') and len(line.split('|')) > 10)
            self.assertRegex(row, r'^\| T10 \| \d+% \|(?: \d+\.\d{2} \|)+$')
            main_rows.append(row)
        self.assertEqual(len(set(main_rows)), 1)
        overview = (RESULTS / 'README.md').read_text()
        published = re.findall(r'^\| (\S+) \| \[summary\.json\]\(([^)]+)\) \| (\d+\.\d{6}) \|$',
                               overview, re.MULTILINE)
        self.assertEqual(published, [(model, f'{model}/summary.json',
                                     f"{summaries[model]['weighted_display_score']:.6f}")
                                    for model in expected])

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
        published = {p.parent.name for p in RESULTS.glob('*/summary.json')}
        self.assertEqual(set(checked), published - {'deepseek-flash'})
        for name in ['gpt-6-astra', 'gpt-6.1-sol', 'gpt-6-sol', 'kimi-k3.1-pro',
                     'claude-fable-5.2', 'gpt-6.2-astra']:
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

    def test_token_totals_preserve_complete_and_partial_final_counters(self):
        records = {r['model']:r for r in read(RESULTS / 'token-usage.json')['models']}
        self.assertEqual(records['kimi-k3.1-pro']['reasoning_effort'], 'max')
        self.assertEqual(records['kimi-k3.1-pro']['total_tokens'], 405087147)
        self.assertEqual(records['claude-opus-5.5']['total_tokens'], 126636800)
        self.assertEqual(records['claude-fable-5.2']['total_tokens'], 102366910)
        self.assertIsNone(records['gpt-6.2-astra']['total_tokens'])
        self.assertEqual(records['gpt-6.2-astra']['known_tokens_total'], 127316134)
        self.assertEqual(records['gpt-6.2-astra']['missing_tasks'], ['T08'])
        for model in records.values():
            missing = [row['task_id'] for row in model['tasks'] if row['tokens'] is None]
            known = sum(row['tokens'] for row in model['tasks'] if row['tokens'] is not None)
            if missing:
                self.assertIsNone(model['total_tokens'])
                self.assertEqual(model['missing_tasks'], missing)
                self.assertEqual(model['known_tokens_total'], known)
            else:
                self.assertEqual(model['total_tokens'], known)
            self.assertEqual([r['task_id'] for r in model['tasks']], [f'T{i:02}' for i in range(1,11)])
            for row in model['tasks']:
                self.assertEqual(set(row), {'task_id', 'tokens'})
                if row['tokens'] is not None:
                    self.assertIs(type(row['tokens']), int)
                    self.assertGreater(row['tokens'], 0)
