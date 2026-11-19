import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from benchmark.runner.grade_resources import execute, snapshot


class GradingResourceTest(unittest.TestCase):
    def test_snapshot_reads_actual_scope_accounting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            group = root/'cpu/worker.scope'
            group.mkdir(parents=True)
            (root/'membership').write_text('0::/worker.scope\n')
            (group/'cpu.stat').write_text('usage_usec 4000000\nnr_throttled 2\nthrottled_usec 3000\n')
            (group/'cpu.weight').write_text('10000\n')
            (group/'cpu.max').write_text('max 100000\n')
            (group/'cpu.pressure').write_text('some avg10=0.00 total=123\n')
            result = snapshot(root/'cpu', root/'membership')
            self.assertEqual(result['cpu_weight'], 10000)
            self.assertEqual(result['usage_usec'], 4000000)
            self.assertEqual(result['nr_throttled'], 2)
            self.assertEqual(result['cgroup'], '/worker.scope')
            (root/'membership').write_text('0::/../outside\n')
            with self.assertRaises(ValueError):
                snapshot(root/'cpu', root/'membership')

    def test_weight_mismatch_refuses_to_start_grader(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch('benchmark.runner.grade_resources.snapshot', return_value={'cpu_weight':100}), \
                 patch('benchmark.runner.grade_resources.subprocess.run') as run:
                with self.assertRaisesRegex(RuntimeError, 'not applied'):
                    execute({'cpu_weight':10000}, Path(temporary)/'resource.json')
                run.assert_not_called()

    def test_success_and_tool_failure_preserve_actual_accounting(self):
        for code in (0, 9):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                request = {'command':['fake-grader'], 'cwd':str(root),
                           'pythonpath':str(root), 'cpu_weight':10000}
                with patch('benchmark.runner.grade_resources.snapshot', side_effect=[
                        {'cgroup':'/scope','cpu_weight':10000,'usage_usec':100},
                        {'cgroup':'/scope','cpu_weight':10000,'usage_usec':2000100}]), \
                     patch('benchmark.runner.grade_resources.subprocess.run',
                           return_value=subprocess.CompletedProcess([],code)) as run:
                    self.assertEqual(execute(request, root/'resource.json'), code)
                data = json.loads((root/'resource.json').read_text())
                self.assertEqual(data['status'], 'completed' if code==0 else 'grader_error')
                self.assertEqual(data['cpu_seconds'], 2.0)
                self.assertEqual(run.call_args.kwargs['env']['PYTHONPATH'], str(root))

    def test_launch_error_is_saved_and_propagated(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'resource.json'
            with patch('benchmark.runner.grade_resources.snapshot', side_effect=[
                    {'cgroup':'/scope','cpu_weight':10000,'usage_usec':0},
                    {'cgroup':'/scope','cpu_weight':10000,'usage_usec':1}]), \
                 patch('benchmark.runner.grade_resources.subprocess.run', side_effect=OSError('failed')):
                with self.assertRaises(OSError):
                    execute({'command':['missing'],'cwd':temporary,'pythonpath':temporary,
                             'cpu_weight':10000}, path)
            self.assertEqual(json.loads(path.read_text())['status'], 'infrastructure_error')

    def test_policy_change_invalidates_completed_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'resource.json'
            with patch('benchmark.runner.grade_resources.snapshot', side_effect=[
                    {'cgroup':'/scope','cpu_weight':10000,'usage_usec':0},
                    {'cgroup':'/scope','cpu_weight':100,'usage_usec':1}]), \
                 patch('benchmark.runner.grade_resources.subprocess.run',
                       return_value=subprocess.CompletedProcess([],0)):
                with self.assertRaisesRegex(RuntimeError, 'policy changed'):
                    execute({'command':['grader'],'cwd':temporary,'pythonpath':temporary,
                             'cpu_weight':10000}, path)
            self.assertEqual(json.loads(path.read_text())['status'], 'infrastructure_error')
