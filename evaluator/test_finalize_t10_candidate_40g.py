"""Exercise the deferred finalizer without launching native EDA jobs."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import finalize_t10_candidate_40g as M


MODELS = ('gpt-6.1-sol', 'gpt-6-astra', 'gpt-6-sol')


class FinalizerTest(unittest.TestCase):
    def run_finalizer(self, work, grade):
        argv = ['finalize', '--work', str(work), '--trials-root', str(work),
                '--orfs', str(work), '--controller-unit', 'finalizer-test.service']
        with patch.object(sys, 'argv', argv), patch.object(M, 'grade', side_effect=grade) as scorer, \
                patch.object(M, 'assert_serial') as serial, contextlib.redirect_stdout(io.StringIO()):
            M.main()
        serial.assert_called_once_with()
        return json.loads((work / 't10_ppa_scores40.json').read_text()), scorer

    def prepare(self, work, missing=None):
        state = dict(status='pending_infrastructure_review', policy=M.POLICY,
                     models={model: dict(ppa_score=None, diagnostic='old metadata failure') for model in MODELS})
        state['models']['existing-gate-zero'] = dict(ppa_score=0, status='existing_gate_zero')
        (work / 't10_ppa_scores40.json').write_text(json.dumps(state))
        for model in MODELS:
            for seed in (11, 29, 47):
                path = work / model / f'activity_seed{seed}' / 'power.json'
                path.parent.mkdir(parents=True)
                if (model, seed) != missing:
                    path.write_text('{}')
        return state

    @staticmethod
    def score(model, *_):
        return dict(model=model, score=dict(ppa_score=.25, time_score=3, display_score=53.25))

    def test_completes_only_after_all_three_reports_are_scored_and_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            original = self.prepare(work)
            # A report verified earlier must be reused without being overwritten.
            path = work / MODELS[0] / 'scored40.json'
            M.write_new_or_same(path, json.dumps(self.score(MODELS[0]), indent=2) + '\n')
            before = path.stat().st_mtime_ns
            state, scorer = self.run_finalizer(work, self.score)
            self.assertEqual(state['status'], 'complete')
            self.assertEqual(scorer.call_count, 3)
            self.assertEqual(path.stat().st_mtime_ns, before)
            for model in MODELS:
                row = state['models'][model]
                self.assertEqual(row['status'], 'measured_and_scored_40g')
                self.assertEqual(row['report'], M.artifact(work / model / 'scored40.json'))
                self.assertEqual(row['previous_aggregation_diagnostic'], 'old metadata failure')
            self.assertEqual(state['models']['existing-gate-zero'], original['models']['existing-gate-zero'])
            backup = json.loads((work / 'scores40_before_workload_metadata_repair.json').read_text())
            self.assertEqual(backup, original)

    def test_missing_power_remains_null_and_does_not_discard_other_scores(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            self.prepare(work, missing=(MODELS[1], 29))
            state, scorer = self.run_finalizer(work, self.score)
            self.assertEqual(state['status'], 'pending_infrastructure_review')
            self.assertEqual(scorer.call_count, 2)
            self.assertIsNone(state['models'][MODELS[1]]['ppa_score'])
            self.assertIn('power measurement not complete', state['models'][MODELS[1]]['diagnostic'])
            for model in (MODELS[0], MODELS[2]):
                self.assertEqual(state['models'][model]['ppa_score'], .25)


if __name__ == '__main__':
    unittest.main()
