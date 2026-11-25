"""Checkpoint identity, retained runtime and router-only low-memory retry."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import t10_route_resume as M
from t10_hybrid_ppa import artifact, write


class RouteResumeTest(unittest.TestCase):
    def fixture(self, root):
        previous = root / 'previous'
        seed = previous / 'seed11'
        seed.mkdir(parents=True)
        old = dict(source_sha256='a'*64, pe_module='pe', layout_seed=11, variant='old',
                   orfs_revision='revision', openroad='version')
        write(seed / 'inputs.json', old)
        write(seed / 'runtime.json', dict(confirmed=True, systemd_result='oom-kill', policy=M.POLICY))
        write(seed / 'baseline.json', dict(inputs_sha256=artifact(seed / 'inputs.json')['sha256'],
                                          runtime=artifact(seed / 'runtime.json')))
        write(seed / 'physical_budget.json', dict(task_id='T10', layout_seed=11,
              candidate_source_sha256='a'*64, limit_seconds=7200, elapsed_seconds=4300))
        orfs = root / 'orfs'
        source = orfs / 'flow/results/asap7/pe/old'
        source.mkdir(parents=True)
        for name in ('5_1_grt.odb', '5_1_grt.sdc', 'route.guide'):
            (source / name).write_text('immutable checkpoint ' + name)
        work = root / 'work'
        directory = work / 'retry/seed11'
        directory.mkdir(parents=True)
        inputs = dict(old, variant='new', threads=1)
        write(directory / 'inputs40.json', inputs)
        prepared = dict(inputs=inputs, input_path=str(directory / 'inputs40.json'),
                        marker=str(directory / 'baseline40.json'),
                        command=['systemd-run', '--unit=test', 'make', 'NUM_CORES=1', 'route', 'do-finish'])
        item = dict(model='retry', pe='pe', source_sha256='a'*64, submission=root / 'submission')
        return previous, orfs, work, source, prepared, item

    def test_resume_preserves_old_checkpoints_and_charges_old_elapsed(self):
        with tempfile.TemporaryDirectory() as temp:
            previous, orfs, work, source, prepared, item = self.fixture(Path(temp))
            before = {p.name: artifact(p) for p in source.iterdir()}
            with patch.object(M, 'source_hash', return_value='a'*64), \
                 patch.object(M, 'run_seed', return_value=prepared) as prepare:
                result = M.plan(item, 11, work, orfs, previous)
            self.assertEqual(result['remaining_seconds'], 2900)
            self.assertEqual(result['previous_elapsed_seconds'], 4300)
            self.assertEqual(prepare.call_args.kwargs['threads'], 1)
            self.assertNotIn('route', result['command'])
            self.assertIn('do-5_2_route', result['command'])
            self.assertNotIn('do-5_1_grt', result['command'])
            self.assertEqual(before, {p.name: artifact(p) for p in source.iterdir()})
            for name in before:
                self.assertEqual(artifact(Path(result['result_dir']) / name)['sha256'], before[name]['sha256'])

    def test_changed_source_is_rejected_before_preparing_or_copying(self):
        with tempfile.TemporaryDirectory() as temp:
            previous, orfs, work, source, prepared, item = self.fixture(Path(temp))
            with patch.object(M, 'source_hash', return_value='b'*64), \
                 patch.object(M, 'run_seed') as prepare:
                with self.assertRaises(ValueError): M.plan(item, 11, work, orfs, previous)
            prepare.assert_not_called()
            self.assertFalse((source.parent / 'new').exists())

    def test_user_pause_excludes_idle_time_and_keeps_interrupted_retry_time(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            previous, orfs, work, source, prepared, item = self.fixture(root)
            old_plan=root/'old_resume_plan.json'
            write(old_plan,dict(previous_elapsed_seconds=4300,inputs=dict(source_sha256='a'*64,
                layout_seed=11,checkpoint_resume=dict(original_inputs=artifact(previous/'seed11/inputs.json')))))
            pause=root/'pause.json'
            write(pause,dict(status='paused_by_user',current_seed=11,preserved_resume_plan=str(old_plan),
                prior_active_seconds=4300,retry_active_seconds=700,total_active_seconds=5000,
                paused_utc='2000-01-01T00:00:00+00:00'))
            with patch.object(M,'source_hash',return_value='a'*64), \
                 patch.object(M,'run_seed',return_value=prepared):
                result=M.plan(item,11,work,orfs,previous,pause_record=pause)
            self.assertEqual(result['previous_elapsed_seconds'],5000)
            self.assertEqual(result['remaining_seconds'],2200)
            self.assertEqual(result['inputs']['checkpoint_resume']['user_pause']['pause'],artifact(pause))

    def test_pause_from_another_seed_cannot_transfer_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            previous, orfs, work, source, prepared, item=self.fixture(root)
            old_plan=root/'plan.json'
            write(old_plan,dict(previous_elapsed_seconds=4300,inputs=dict(source_sha256='a'*64,
                layout_seed=29,checkpoint_resume=dict(original_inputs=artifact(previous/'seed11/inputs.json')))))
            pause=root/'pause.json'
            write(pause,dict(status='paused_by_user',current_seed=29,preserved_resume_plan=str(old_plan),
                prior_active_seconds=4300,retry_active_seconds=700,total_active_seconds=5000))
            with patch.object(M,'source_hash',return_value='a'*64), \
                 patch.object(M,'run_seed') as prepare:
                with self.assertRaises(ValueError):M.plan(item,11,work,orfs,previous,pause_record=pause)
            prepare.assert_not_called()


if __name__ == '__main__':
    unittest.main()
