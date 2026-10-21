import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
sys.path.insert(0,str(HERE))
SPEC=importlib.util.spec_from_file_location('t10_candidate_physical',HERE/'t10_candidate_physical.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)


class CandidatePhysicalTest(unittest.TestCase):
    def fixture(self,root):
        submission=root/'submission';(submission/'rtl').mkdir(parents=True)
        (submission/'rtl/files.f').write_text('dut.sv\n')
        (submission/'rtl/dut.sv').write_text('module pe(input clk, rst_n); endmodule\n')
        proof=root/'structure.json';proof.write_text('{}\n')
        return dict(model='gpt-6-sol',pe='pe',submission=submission,source_sha256='a'*64,structure=M.artifact(proof))

    def test_failed_flow_remains_pending_and_uses_fixed_pe_parameters(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);item=self.fixture(root)
            with patch.object(M.subprocess,'check_output',return_value='locked-version\n'), \
                 patch.object(M.subprocess,'run',return_value=subprocess.CompletedProcess([],1)) as run:
                result=M.run_seed(item,11,root/'work',root/'orfs','baseline',memory_gib=32)
            self.assertEqual(result['status'],'failed_pending_attribution')
            self.assertNotIn('ppa_score',result)
            command=run.call_args.args[0]
            self.assertIn('MemoryMax=32G',command);self.assertIn('MemorySwapMax=0',command)
            self.assertIn('CPUQuota=400%',command)
            config=(root/'work/gpt-6-sol/seed11/config.mk').read_text()
            for entry in ('DESIGN_NAME = pe','CORE_UTILIZATION = 24','PLACE_DENSITY = 0.24','MAX_ROUTING_LAYER = M7'):
                self.assertIn(entry,config)
            self.assertEqual((item['submission']/'rtl/dut.sv').read_text(),'module pe(input clk, rst_n); endmodule\n')
            with patch.object(M.subprocess,'check_output',return_value='locked-version\n'):
                with self.assertRaisesRegex(ValueError,'previous failure needs attribution'):
                    M.run_seed(item,11,root/'work',root/'orfs','baseline',memory_gib=32)

    def test_no_silent_config_rewrite(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'input';M.write_new_or_same(path,'original')
            M.write_new_or_same(path,'original')
            with self.assertRaisesRegex(ValueError,'changed inputs'):
                M.write_new_or_same(path,'replacement')
            self.assertEqual(path.read_text(),'original')

    def test_40g_prepare_preserves_32g_attempt_and_allows_swap(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);item=self.fixture(root);work=root/'work';orfs=root/'orfs'
            with patch.object(M.subprocess,'check_output',return_value='locked-version\n'), \
                 patch.object(M.subprocess,'run',return_value=subprocess.CompletedProcess([],1)):
                M.run_seed(item,11,work,orfs,'baseline',memory_gib=32)
            directory=work/'gpt-6-sol/seed11';old=(directory/'inputs.json').read_bytes()
            with patch.object(M.subprocess,'check_output',return_value='locked-version\n'), \
                 patch.object(M.subprocess,'run') as execute:
                new=M.run_seed(item,11,work,orfs,'baseline',memory_gib=40,allow_swap=True,prepare_only=True)
            execute.assert_not_called()
            self.assertEqual((directory/'inputs.json').read_bytes(),old)
            self.assertIn('MemoryMax=40G',new['command'])
            self.assertIn('MemorySwapMax=infinity',new['command'])
            self.assertEqual(new['inputs']['memory_max_bytes'],40*1024**3)
            self.assertIsNone(new['inputs']['memory_swap_max_bytes'])
            self.assertTrue(new['marker'].endswith('baseline40.json'))

    def test_default_preparation_uses_40g_actual_memory(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);item=self.fixture(root)
            with patch.object(M.subprocess,'check_output',return_value='locked-version\n'):
                prepared=M.run_seed(item,11,root/'work',root/'orfs','baseline',prepare_only=True)
            self.assertIn('MemoryMax=40G',prepared['command'])
            self.assertEqual(prepared['inputs']['memory_max_bytes'],40*1024**3)

    def test_default_cli_uses_monitored_serial_40g_flow(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);work=root/'work'
            work.mkdir()
            argv=['physical','--trials-root',str(root/'trials'),'--work',str(work),
                  '--orfs',str(root/'orfs'),'--models','gpt-6-sol','--seeds','11','29']
            with patch.object(sys,'argv',argv), \
                 patch.object(M,'prepare',return_value={'model':'gpt-6-sol'}), \
                 patch.object(M,'run_seed') as legacy, \
                 patch('run_t10_candidate_40g.completed_physical',return_value=False), \
                 patch('run_t10_candidate_40g.physical',return_value=({'exit_code':0},{})) as monitored:
                M.main()
            legacy.assert_not_called()
            self.assertEqual([call.args[1] for call in monitored.call_args_list],[11,29])
            self.assertTrue((work/'baseline_summary.json').is_file())


if __name__=='__main__':unittest.main()
