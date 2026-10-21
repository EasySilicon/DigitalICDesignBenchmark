from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parent))
from t10_candidate_power import annotation, validate_paths, run, run_unoptimized_periphery, check_connectivity, shell_target, qualified_shell, artifact, BACKEND, REPO


class CandidatePowerTest(unittest.TestCase):
    def test_frontend_o0_only_changes_the_named_unmeasured_parent_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);build=out/'build';build.mkdir()
            parent=build/'Vnpu_systolic_matmul_16x16__hierMkArgs.f'
            original='--cc\n--top-module-encoded npu_systolic_matmul_16x16\n--assert\n--trace-saif\nactual.v\n'
            parent.write_text(original)
            command=['verilator','-f',str(parent)]
            with patch('t10_candidate_power.run',return_value=1) as execute:
                run_unoptimized_periphery(command,out/'actual_npu_systolic_matmul_16x16.log',REPO)
                execute.assert_called_once_with(command,out/'actual_npu_systolic_matmul_16x16.log',REPO)
            self.assertEqual(parent.read_text(),original+'\n-O0\n')
            child=build/'Vcandidate_pe__hierMkArgs.f';child.write_text('--cc\nactual_pe.v\n')
            with patch('t10_candidate_power.run'):
                run_unoptimized_periphery(['verilator','-f',str(child)],out/'actual_candidate_pe.log',REPO)
            self.assertEqual(child.read_text(),'--cc\nactual_pe.v\n')
            with self.assertRaisesRegex(ValueError,'measured PE'):
                run_unoptimized_periphery(['verilator','-f',str(child)],out/'actual_npu_systolic_matmul_16x16.log',REPO)

    def test_shell_reuse_requires_matching_source_full_gate_pass_and_unchanged_netlist(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory=root/'activity_seed11';directory.mkdir()
            shell=root/'shell.v';shell.write_text('candidate shell')
            inputs={'source_sha256':'candidate'}
            self.assertIsNone(qualified_shell(root,29,inputs))
            proof=dict(status='candidate_single_seed_activity_power_measured',source_sha256='candidate',
                numerical_oracle_passed=True,protocol_and_latency_passed=True,matrix_blocks=200,
                output_points_checked=51200,netlists=[artifact(shell)])
            (directory/'power.json').write_text(json.dumps(proof))
            self.assertIsNone(qualified_shell(root,11,inputs))
            self.assertEqual(qualified_shell(root,29,inputs),shell)
            with self.assertRaisesRegex(ValueError,'matching full-DUT'):
                qualified_shell(root,47,{'source_sha256':'other'})
            shell.write_text('changed')
            with self.assertRaisesRegex(ValueError,'netlist changed'):
                qualified_shell(root,29,inputs)

    def test_opendb_checker_runs_inside_openroad_not_system_python(self):
        with patch('t10_candidate_power.run') as execute:
            check_connectivity(Path('final.odb'),Path('connectivity.json'),Path('connectivity.log'))
        execute.assert_called_once_with(['openroad','-exit','-no_init','-python',
            str(BACKEND/'check_connectivity_full.py'),'final.odb','connectivity.json'],
            Path('connectivity.log'),REPO)

    def test_full_candidate_instance_count_not_reference_module_names(self):
        body='\n'.join(f'candidate_pe instance{i} (.clk(clk));' for i in range(256))
        shell='module npu_systolic_matmul_16x16;\n'+body+'\nendmodule'
        self.assertEqual(len(validate_paths(shell,'candidate_pe')),256)
        with self.assertRaisesRegex(ValueError,'256 distinct'):
            validate_paths(shell.replace('endmodule','candidate_pe instance0 (.clk(clk));\nendmodule'),'candidate_pe')
        with self.assertRaisesRegex(ValueError,'256 distinct'):
            validate_paths(shell,'reference_pe')

    def test_tile_wrappers_expand_to_256_distinct_candidate_paths(self):
        shell='module npu_systolic_matmul_16x16;\n'+ '\n'.join(
            f'tile tile{i} (.clk(clk));' for i in range(16))+'\nendmodule\nmodule tile;\n'+ '\n'.join(
            f'candidate_pe pe{j} (.clk(clk));' for j in range(16))+'\nendmodule'
        paths=validate_paths(shell,'candidate_pe')
        self.assertEqual(len(paths),256)
        self.assertIn('tile15.pe15',paths)

    def test_shell_synthesis_stops_at_the_verilog_target(self):
        self.assertEqual(shell_target('candidate'),'results/asap7/npu_systolic_matmul_16x16/candidate/1_2_yosys.v')

    def test_requires_both_overall_and_sequential_activity(self):
        text='input 99 unannotated 1\nT10_SEQUENTIAL_ACTIVITY annotated=100 total=100\n'
        self.assertEqual(annotation(text),(.99,1))
        with self.assertRaisesRegex(ValueError,'below 95'):
            annotation(text.replace('annotated=100','annotated=94'))
        with self.assertRaisesRegex(ValueError,'missing activity'):
            annotation('Total 1 1 1 3')

    def test_native_children_do_not_inherit_a_va_cap(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('t10_candidate_power.resource.setrlimit') as limit, \
                 patch('t10_candidate_power.subprocess.run') as execute:
                run(['tool'],Path(temp)/'native.log',Path(temp))
            import resource
            limit.assert_called_once_with(resource.RLIMIT_AS,(resource.RLIM_INFINITY,resource.RLIM_INFINITY))
            self.assertNotIn('preexec_fn',execute.call_args.kwargs)


if __name__=='__main__':unittest.main()
