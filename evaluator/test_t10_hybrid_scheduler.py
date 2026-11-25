"""Failure isolation, durable continuation and truthful terminal queue state."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from t10_hybrid_scheduler import admit, isolated, run, terminal_result
from t10_hybrid_ppa import artifact, write


class SchedulerTest(unittest.TestCase):
    def test_host_pressure_waits_without_charging_a_worker_or_candidate(self):
        events = []
        samples = iter([20, 39, 50])
        sleep = unittest.mock.Mock()
        admit(dict(host_admission_available_bytes=40), events.append,
              sample=lambda: next(samples), sleep=sleep)
        self.assertEqual([r['stage'] for r in events], ['waiting_host_memory'] * 2)
        self.assertEqual(sleep.call_count, 2)
        self.assertTrue(all('ppa_score' not in event for event in events))

    def config(self, root):
        return dict(output=str(root / 'out'), jobs=[dict(label=s) for s in ['oom', 'bad', 'timeout', 'ok']],
                    grade_lock=str(root / 'grade.lock'), orfs=str(root / 'orfs'), reference_label='reference')

    def test_failed_dispatch_and_workers_do_not_stop_later_jobs_or_repeat_on_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = self.config(root)
            called = []

            def dispatch(job, directory, config, notify):
                label = job['label']
                called.append(label)
                if label == 'oom':
                    return terminal_result(label, directory, dict(Result='oom-kill', controller_returncode=137))
                if label == 'bad':
                    raise RuntimeError('missing executable')
                if label == 'timeout':
                    write(directory / 'failure.json', dict(label=label, status='power_compile_timeout_zero', ppa_score=0.))
                    return terminal_result(label, directory, dict(Result='exit-code', controller_returncode=124))
                write(directory / 'measurement.json', dict(label=label))
                return terminal_result(label, directory, dict(Result='success', controller_returncode=0))

            rows = run(config, dispatch=dispatch)
            self.assertEqual(called, ['oom', 'bad', 'timeout', 'ok'])
            self.assertEqual([r['status'] for r in rows], ['worker_oom_requires_attribution',
                             'dispatch_failed_requires_attribution', 'power_compile_timeout_zero', 'measured'])
            state = json.loads((root / 'out/status.json').read_text())
            self.assertTrue(state['queue_finished'])
            self.assertFalse(state['all_scored'])
            self.assertEqual(state['unresolved'], ['oom', 'bad', 'ok'])
            self.assertEqual(run(config, dispatch=lambda *a: self.fail('terminal attempt was repeated')), rows)

    def test_bad_score_report_does_not_stop_following_workers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = self.config(root)
            (root / 'out/reference').mkdir(parents=True)
            (root / 'out/reference/measurement.json').write_text('{truncated')
            called = []

            def dispatch(job, directory, config, notify):
                called.append(job['label'])
                return dict(label=job['label'], status='power_compile_timeout_zero', ppa_score=0.)

            run(config, dispatch=dispatch)
            self.assertEqual(len(called), 4)
            self.assertTrue((root / 'out/scoring_error.json').exists())

    def test_measurement_without_a_valid_score_is_not_marked_all_scored(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = self.config(root)
            config['jobs'] = [dict(label='ok')]

            def dispatch(job, directory, config, notify):
                write(directory / 'measurement.json', dict(label='ok'))
                return terminal_result('ok', directory, dict(Result='success', controller_returncode=0))

            run(config, dispatch=dispatch)
            state = json.loads((root / 'out/status.json').read_text())
            self.assertTrue(state['queue_finished'])
            self.assertFalse(state['all_scored'])
            self.assertEqual(state['unresolved'], ['ok'])

    def test_oom_overrides_any_incomplete_success_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'measurement.json').write_text('{}')
            result = terminal_result('x', root, dict(Result='oom-kill', controller_returncode=137))
            self.assertEqual(result['status'], 'worker_oom_requires_attribution')
            self.assertNotIn('ppa_score', result)
            result = terminal_result('x', root, dict(Result='timeout', controller_returncode=1))
            self.assertEqual(result['status'], 'worker_watchdog_incomplete')

    def test_controller_reattaches_without_launching_a_second_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            job = dict(label='x')
            config = dict(orfs='/unused/orfs', grade_lock=str(root / 'lock'))
            request = dict(job=job, output=str(root), compiler_root=None,
                           orfs=config['orfs'], grade_lock=config['grade_lock'])
            write(root / 'worker_request.json', request)
            import hashlib
            unit = 't10-v16-worker-' + hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16] + '.service'
            write(root / 'worker_launch.json', dict(unit=unit, request=artifact(root / 'worker_request.json')))
            states = [dict(ActiveState='active'), dict(ActiveState='active'),
                      dict(ActiveState='inactive'), dict(Result='oom-kill', ActiveState='failed')]
            with patch('t10_hybrid_scheduler.properties', side_effect=states), \
                 patch('t10_hybrid_scheduler.time.sleep'), \
                 patch('t10_hybrid_scheduler.subprocess.Popen') as launch:
                result = isolated(job, root, config, lambda row: None)
            launch.assert_not_called()
            self.assertEqual(result['status'], 'worker_oom_requires_attribution')

    def test_mismatched_input_and_duplicate_labels_fail_before_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self.config(Path(temp))
            config['jobs'].append(dict(label='ok'))
            with self.assertRaises(ValueError): run(config)


if __name__ == '__main__':
    unittest.main()
