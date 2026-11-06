import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from public_check import compile_smoke


class PublicCompileTest(unittest.TestCase):
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
