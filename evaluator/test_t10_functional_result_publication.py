"""Publish one final summary per model and exclude trial bookkeeping."""
import copy
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import jsonschema
from evaluator.score_run import weighted_suite_score
from evaluator.result_publication import final_summary

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results'


class T10FunctionalPublicationTest(unittest.TestCase):
    def test_final_summaries_recompute_totals_and_have_one_canonical_shape(self):
        schema = json.loads((RESULTS / 'result.schema.json').read_text())
        for path in RESULTS.glob('*/summary.json'):
            summary = json.loads(path.read_text())
            jsonschema.validate(summary, schema)
            self.assertEqual(summary, final_summary(summary), path)
            self.assertEqual([r['task_id'] for r in summary['tasks']], [f'T{i:02}' for i in range(1,11)])
            weighted = weighted_suite_score({r['task_id']:r['display_score'] for r in summary['tasks']})
            self.assertAlmostEqual(summary['weighted_display_score'], weighted['weighted_display_score'], places=12)
            for component in ['functional_total','ppa_score','time_score','display_score']:
                self.assertAlmostEqual(summary[component+'_sum'], math.fsum(r[component] for r in summary['tasks']), places=12)

    def test_schema_rejects_bookkeeping_in_summary_and_task_rows(self):
        schema = json.loads((RESULTS / 'result.schema.json').read_text())
        original = json.loads((RESULTS / 'claude-opus-5.5/summary.json').read_text())
        for key in ['functional_retest','archive_evidence','task_freeze_receipts','source_trial','previous_summary','structure_evaluator_repair']:
            for nested in [False, True]:
                sample = copy.deepcopy(original)
                target = sample['tasks'][-1] if nested else sample
                target[key] = {'path':'/private/report.json'}
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(sample, schema)

    @unittest.skipUnless(shutil.which('git'), 'Git is needed to verify publication ignore rules')
    def test_allowlist_publishes_only_one_summary_in_each_model_directory(self):
        rules = (ROOT / '.gitignore').read_text()
        allowed = [line[2:] for line in rules.splitlines()
                   if line.startswith('!/results/') and not line.endswith('/')]
        model_files = [p for p in allowed if len(Path(p).parts)==3]
        self.assertEqual({Path(p).name for p in model_files}, {'summary.json'})
        self.assertEqual(len(allowed), len(model_files)+7)
        for name in allowed:
            self.assertFalse(any(c in name for c in '*?['), name)
            self.assertTrue((ROOT/name).is_file(), name)
        blocked = ['results/claude-opus-5.5/evidence/T01/report.json',
                   'results/claude-sonnet-5.5/functional-retest-20261106/functional.json',
                   'results/archive/old/summary.json', 'results/gpt-6-astra/T10-ppa40.json',
                   'results/kimi-k3.1-pro/token-evidence/T01.agent_result.json',
                   'results/claude-opus-5.5/archive_manifest.json',
                   'results/claude-opus-5.5/T01.json', 'results/gpt-6-astra/T10.json',
                   'results/t10-functional-results-update-20261105.json', 'results/new-report.json']
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            subprocess.run(['git','init','-q',str(directory)],check=True)
            (directory/'.gitignore').write_text(rules)
            for name in [*allowed,*blocked]:
                result = subprocess.run(['git','-C',str(directory),'check-ignore','--no-index','-q',name])
                self.assertEqual(result.returncode, 0 if name in blocked else 1, name)
