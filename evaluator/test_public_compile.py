import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from public_check import compile_smoke, main


class PublicCompileTest(unittest.TestCase):
    def test_fifo_public_cli_defaults_and_explicit_depth(self):
        cases = [("T02", [], 3), ("T05", [], 8),
                 ("T05", ["--depth", "16"], 16)]
        for task, options, depth in cases:
            with self.subTest(task=task, options=options), \
                    patch('sys.argv', ['public_check.py', task, 'submission', *options]), \
                    patch('public_check.run', return_value={'passed': True}) as run, \
                    patch('builtins.print'):
                self.assertEqual(main(), 0)
                run.assert_called_once_with(task, Path('submission'), 20260925, 8, depth, 4)

    def test_t05_public_cli_rejects_depth_three(self):
        with patch('sys.argv', ['public_check.py', 'T05', 'submission', '--depth', '3']), \
                patch('public_check.run') as run, \
                patch('sys.stderr'):
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 2)
        run.assert_not_called()

    def test_known_vm_trace_failure_uses_remaining_shared_deadline(self):
        command=['verilator','--binary','--hierarchical','--timing','--assert',
                 '--Mdir','/tmp/build','candidate.sv','oracle.sv']
        first=subprocess.CompletedProcess(command,1,'-DVM_TRACE= ',
                                          'error: #if with no expression')
        second=subprocess.CompletedProcess(command,0,'built','')
        with patch('public_check.time.monotonic',side_effect=[10,15]), \
                patch('public_check.subprocess.run',side_effect=[first,second]) as run:
            result,build,log=compile_smoke(command,Path('/tmp/build'),30)
        self.assertEqual(result.returncode,0)
        self.assertEqual(build,Path('/tmp/build/trace_fallback'))
        retry=run.call_args.args[0]
        self.assertIn('--trace',retry)
        self.assertIn('--assert',retry)
        self.assertEqual(retry[-2:],command[-2:])
        self.assertEqual(run.call_args.kwargs['timeout'],25)
        self.assertIn('error: #if with no expression',log)

    def test_other_compiler_errors_are_not_retried(self):
        command=['verilator','--hierarchical']
        failed=subprocess.CompletedProcess(command,1,'','syntax error')
        with patch('public_check.subprocess.run',return_value=failed) as run:
            result,build,log=compile_smoke(command,Path('/tmp/build'),30)
        run.assert_called_once()
        self.assertEqual(result.returncode,1)


if __name__=='__main__':unittest.main()
