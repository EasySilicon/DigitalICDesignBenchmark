import importlib.util
import json
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
    def test_explicit_trial_selection_accepts_new_labels_and_rejects_ambiguous_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            self.assertEqual(M.trial_paths([f'new-model={root}']),{'new-model':root})
            for values in ([],[f'../escape={root}'],[f'={root}'],
                           [f'new-model={root}',f'new-model={root}']):
                with self.subTest(values=values),self.assertRaises(ValueError):M.trial_paths(values)
            with self.assertRaises(FileNotFoundError):M.trial_paths([f'new-model={root/"missing"}'])

    def test_snapshot_uses_explicit_trial_and_rejects_source_or_structural_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);trial=root/'trial';workspace=trial/'workspaces/T10'
            rtl=workspace/'rtl';rtl.mkdir(parents=True)
            (rtl/'files.f').write_text('pe.sv\n')
            source=rtl/'pe.sv';source.write_text('module pe; endmodule\n')
            trials={'new-model':trial};work=root/'work'
            with patch.object(M,'inspect',return_value={'passed':True,'pe_module':'pe'}) as inspect:
                item=M.prepare('new-model',trials,work)
                inspect.assert_called_once()
            with patch.object(M,'inspect') as inspect:
                M.prepare('new-model',trials,work,cached_only=True)
                inspect.assert_not_called()
            proof=work/'new-model/structure.json';original=proof.read_bytes()
            changed=json.loads(original);changed['checker_sha256']='0'*64
            proof.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError,'structural provenance changed'):
                M.prepare('new-model',trials,work,cached_only=True)
            proof.write_bytes(original)
            source.write_text('module changed; endmodule\n')
            with self.assertRaisesRegex(ValueError,'snapshot/source mismatch'):
                M.prepare('new-model',trials,work,cached_only=True)
            self.assertEqual((item['submission']/'rtl/pe.sv').read_text(),'module pe; endmodule\n')

    def test_cached_preparation_never_starts_missing_structural_check(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);trial=root/'trial';workspace=trial/'workspaces/T10'
            rtl=workspace/'rtl';rtl.mkdir(parents=True)
            (rtl/'files.f').write_text('pe.sv\n');(rtl/'pe.sv').write_text('module pe; endmodule\n')
            with patch.object(M,'inspect') as inspect,self.assertRaisesRegex(ValueError,'snapshot is missing'):
                M.prepare('new-model',{'new-model':trial},root/'work',cached_only=True)
            inspect.assert_not_called()

    def fixture(self,root):
        submission=root/'submission';(submission/'rtl').mkdir(parents=True)
        (submission/'rtl/files.f').write_text('dut.sv\n')
        (submission/'rtl/dut.sv').write_text('module pe(input clk, rst_n); endmodule\n')
        proof=root/'structure.json';proof.write_text('{}\n')
        return dict(model='candidate-a',pe='pe',submission=submission,source_sha256='a'*64,structure=M.artifact(proof))

    def test_failed_flow_remains_pending_and_uses_fixed_pe_parameters(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);item=self.fixture(root)
            with patch.object(M.subprocess,'check_output',return_value='locked-version\n'), \
                 patch.object(M,'physical_run',return_value=subprocess.CompletedProcess([],1)) as run:
                result=M.run_seed(item,11,root/'work',root/'orfs','baseline',memory_gib=32)
            self.assertEqual(result['status'],'failed_pending_attribution')
            self.assertNotIn('ppa_score',result)
            command=run.call_args.args[0]
            self.assertIn('MemoryMax=32G',command);self.assertIn('MemorySwapMax=0',command)
            self.assertIn('CPUQuota=400%',command)
            config=(root/'work/candidate-a/seed11/config.mk').read_text()
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
                 patch.object(M,'physical_run',return_value=subprocess.CompletedProcess([],1)):
                M.run_seed(item,11,work,orfs,'baseline',memory_gib=32)
            directory=work/'candidate-a/seed11';old=(directory/'inputs.json').read_bytes()
            with patch.object(M.subprocess,'check_output',return_value='locked-version\n'), \
                 patch.object(M,'physical_run') as execute:
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
            trial=root/'trial';trial.mkdir()
            argv=['physical','--trial',f'candidate-a={trial}','--work',str(work),
                  '--orfs',str(root/'orfs'),'--seeds','11','29']
            with patch.object(sys,'argv',argv), \
                 patch.object(M,'prepare',return_value={'model':'candidate-a'}), \
                 patch.object(M,'run_seed') as legacy, \
                 patch('run_t10_candidate_40g.completed_physical',return_value=False), \
                 patch('t10_physical_with_slang.physical',return_value=({'exit_code':0},{})) as monitored:
                M.main()
            legacy.assert_not_called()
            self.assertEqual([call.args[1] for call in monitored.call_args_list],[11,29])
            self.assertTrue((work/'baseline_summary.json').is_file())


if __name__=='__main__':unittest.main()
