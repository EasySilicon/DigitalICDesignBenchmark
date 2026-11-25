from pathlib import Path
import sys
import unittest
import tempfile
import shutil
import subprocess
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parent))
from t10_candidate_power import annotation, validate_paths, run, run_unoptimized_periphery, check_connectivity, shell_target, qualified_shell, artifact, BACKEND, REPO


class CandidatePowerTest(unittest.TestCase):
    def test_default_optimized_compiler_does_not_receive_legacy_parent_o0(self):
        from t10_candidate_power import gate_compile_runner
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);build=root/'build';build.mkdir()
            arguments=build/'Vnpu_systolic_matmul_16x16__hierMkArgs.f'
            original='--cc\n--top-module-encoded npu_systolic_matmul_16x16\n--assert\n--trace-saif\nactual.v\n'
            arguments.write_text(original)
            observed=[]
            def execute(command,log,cwd):
                observed.append(arguments.read_text())
            command=['verilator','-f',str(arguments)]
            runner=gate_compile_runner(execute,large_shell=True,parent_optimization='default')
            runner(command,root/'actual_npu_systolic_matmul_16x16.log',root)
            self.assertEqual(observed,[original])
            self.assertEqual(arguments.read_text(),original)
            runner=gate_compile_runner(execute,large_shell=True,parent_optimization='auto')
            runner(command,root/'actual_npu_systolic_matmul_16x16.log',root)
            self.assertIn('-O0',observed[-1].split())

    @unittest.skipUnless(shutil.which('verilator'), 'Verilator is required')
    def test_staging_preserves_escaped_wrapper_instances_and_state(self):
        import json
        from run_gate_activity import hierblock
        from staged_gate_build import build as staged_build
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);shell=root/'shell.v';pe=root/'pe.v';bench=root/'bench.sv'
            wrapper=r'\tile$parameter.0'
            shell.write_text(hierblock(f'''module npu_systolic_matmul_16x16(clk,d,q);
 input clk,d;
 output q;
 {wrapper} u (.clk(clk),.d(d),.q(q));
endmodule
module {wrapper} (clk,d,q);
 input clk,d;
 output q;
 wire {wrapper} ;
 assign {wrapper} = d;
 candidate_pe p (.clk(clk),.d({wrapper} ),.q(q));
endmodule
'''))
            pe.write_text(hierblock('''module candidate_pe(clk,d,q);
 input clk,d;
 output reg q;
 always @(posedge clk) q <= d;
endmodule
'''))
            bench.write_text('''module tb_hidden_T10_stream;
 bit clk=0,d=0; wire q;
 npu_systolic_matmul_16x16 dut(clk,d,q);
 always #1 clk=~clk;
 initial begin
   @(negedge clk); d=1;
   @(negedge clk); if(q!==1) $fatal(1,"missing registered one"); d=0;
   @(negedge clk); if(q!==0) $fatal(1,"missing registered zero");
   $display("ESCAPED_WRAPPER_PASS"); $finish;
 end
endmodule
''')
            command=['verilator','--binary','--hierarchical','--timing','--trace-saif',
                     '-Wno-fatal','-j','2','--top-module','tb_hidden_T10_stream',
                     '--Mdir',str(root/'build'),str(bench),str(shell),str(pe)]
            staged_build(command,[shell,pe],bench,root,run,root)
            manifest=json.loads((root/'staged_build_manifest.json').read_text())
            alias=manifest['module_type_aliases'][wrapper]
            actual=(root/'actual_modules'/f'{alias}.v').read_text()
            self.assertIn(f'wire {wrapper} ;',actual)
            self.assertIn('candidate_pe p ',actual)
            self.assertNotIn('module '+wrapper,actual)
            self.assertFalse(manifest['planning_sources_used_for_simulation'])
            completed=subprocess.run([str(root/'build/Vtb_hidden_T10_stream')],
                                     capture_output=True,text=True,check=True,timeout=30)
            self.assertIn('ESCAPED_WRAPPER_PASS',completed.stdout)

    @unittest.skipUnless(shutil.which('verilator'), 'Verilator is required')
    def test_staging_keeps_shell_trace_disabled_and_measured_pe_trace_enabled(self):
        from run_gate_activity import hierblock, shell_trace_off
        from staged_gate_build import build as staged_build
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            shell=root/'shell.v';pe=root/'pe.v';bench=root/'bench.sv'
            shell.write_text(hierblock(shell_trace_off('''module npu_systolic_matmul_16x16(clk,a,b,y);
 input clk;
 input a,b;
 output y;
 reg shell_secret_state;
 wire pe_out;
 always @(posedge clk) shell_secret_state <= a;
 candidate_pe pe(.clk(clk), .a(b), .y(pe_out));
 assign y = shell_secret_state ^ pe_out;
endmodule
''')))
            pe.write_text(hierblock('''module candidate_pe(clk,a,y);
 input clk;
 input a;
 output y;
 reg measured_pe_state;
 always @(posedge clk) measured_pe_state <= a;
 assign y = measured_pe_state;
endmodule
'''))
            bench.write_text('module tb_hidden_T10_stream; endmodule\n')
            def plan_only(command,log,cwd):
                if log.name=='planning.log':
                    directory=root/'build';directory.mkdir()
                    for name in ('candidate_pe','npu_systolic_matmul_16x16','tb_hidden_T10_stream'):
                        (directory/f'V{name}__hierMkArgs.f').write_text('--cc\n')
            staged_build(['verilator','--binary',str(shell),str(pe),str(bench)],
                         [shell,pe],bench,root,plan_only,root)
            # Inspect real Verilator trace declarations from the actual staged
            # sources. No gate workload, C++ build or power flow is launched.
            subprocess.run(['verilator','--cc','--hierarchical','--trace-saif','-Wno-fatal',
                '--top-module','npu_systolic_matmul_16x16','--Mdir',str(root/'trace'),
                str(root/'actual_modules/npu_systolic_matmul_16x16.v'),
                str(root/'actual_modules/candidate_pe.v')],
                capture_output=True,text=True,check=True,timeout=30)
            trace=''.join(f.read_text() for f in (root/'trace').rglob('*Trace*.cpp'))
            self.assertIn('"measured_pe_state"',trace)
            self.assertIn('"t10_power_trace_clock"',trace)
            self.assertFalse('"shell_secret_state"' in trace,
                             'staging re-enabled unmeasured shell state tracing')

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
