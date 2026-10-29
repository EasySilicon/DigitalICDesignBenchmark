import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import slang_frontend as frontend
import route_with_slang as route
import t10_structure_with_slang as structure
import t10_candidate_physical as physical
import t10_physical_with_slang as current_physical
import run_t10_candidate_40g as backend


class FrontendTests(unittest.TestCase):
    def setUp(self):
        frontend.yosys_command.cache_clear()

    def tearDown(self):
        frontend.yosys_command.cache_clear()

    def test_builtin_and_plugin_installations_are_supported(self):
        for outputs, expected in ((['Read SystemVerilog sources'],('/tool/yosys',)),
                (['No such command','Read SystemVerilog sources'],('/tool/yosys','-m','slang'))):
            frontend.yosys_command.cache_clear()
            results=[subprocess.CompletedProcess([],0,output,'') for output in outputs]
            with patch.object(frontend.shutil,'which',return_value='/tool/yosys'), \
                    patch.object(frontend.subprocess,'run',side_effect=results):
                self.assertEqual(frontend.yosys_command(),expected)

    def test_missing_required_frontend_is_an_infrastructure_error(self):
        with patch.object(frontend.shutil,'which',return_value='/tool/yosys'), \
                patch.object(frontend.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','missing')):
            with self.assertRaisesRegex(RuntimeError,'Required Yosys read_slang'):
                frontend.yosys_command()

    @unittest.skipUnless(shutil.which('yosys'),'Yosys not installed')
    def test_function_return_logic_is_read_as_systemverilog(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'dut.sv';output=root/'design.json'
            source.write_text('module dut(input [9:0] x, output y);\n'
                'function automatic logic comma(input logic [9:0] v);\n'
                "return (v==10'b0011111010) || (v==10'b1100000101);\n"
                'endfunction\nassign y=comma(x);\nendmodule\n')
            command=[*frontend.yosys_command(),'-Q','-T','-p',
                f'read_slang --top dut {source}; write_json {output}']
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('dut',json.loads(output.read_text())['modules'])

    def test_route_enables_frontend_without_changing_physical_parameters(self):
        with tempfile.TemporaryDirectory() as temp:
            config=Path(temp)/'config.mk'
            def run():
                route.frozen.write_config(config,'serdes_rx_comma_aligner',[],Path('clock.sdc'),'',10,.6,'WC')
                self.assertEqual(route.shutil.which('yosys'),'/tool/yosys-slang')
                return 0
            original=route.frozen.write_config
            with patch.object(route,'executable',return_value=Path('/tool/yosys-slang')), \
                    patch.object(route.frozen,'main',side_effect=run):
                self.assertEqual(route.main(),0)
            self.assertIs(route.frozen.write_config,original)
            text=config.read_text()
            for field in ('SYNTH_HDL_FRONTEND = slang','CORE_UTILIZATION = 10',
                          'PLACE_DENSITY = 0.6','CORNER = WC'):
                self.assertIn(field,text)

    def test_structure_uses_slang_and_restores_native_runner(self):
        original=structure.frozen.subprocess.run
        def inspect(submission):
            structure.frozen.subprocess.run(['yosys','-p','read_verilog -sv dut.sv; hierarchy -top top'])
            return {'passed':True}
        with patch.object(structure,'yosys_command',return_value=('/tool/yosys','-m','slang')), \
                patch.object(structure.frozen,'inspect',side_effect=inspect), \
                patch.object(structure.frozen.subprocess,'run',side_effect=[
                    subprocess.CompletedProcess([],1,'','syntax error'),
                    subprocess.CompletedProcess([],0,'','')]) as native:
            result=structure.inspect(Path('/submission'))
            self.assertTrue(result['passed'])
            self.assertIn('read_slang --keep-hierarchy --top ',native.call_args.args[0][-1])
        self.assertIs(structure.frozen.subprocess.run,original)

    def test_structure_stages_one_module_per_file_for_stable_pe_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            leaf=root/'pe.sv';tile=root/'tile.sv';top=root/'top.sv'
            leaf.write_text('module pe; endmodule\n')
            tile.write_text('module tile; pe p(); endmodule\n')
            top.write_text('module top; tile t(); endmodule\n')
            script=(f'read_verilog -sv {leaf} {tile} {top}; hierarchy -top top')
            staged=structure._staged_slang_reads(script)
        self.assertIsNotNone(staged)
        self.assertIn(f'read_slang --top pe --compat=vcs -D SYNTHESIS --ignore-assertions {leaf}',staged)
        self.assertIn(f'read_slang --keep-hierarchy --top tile',staged)
        self.assertIn(f'read_slang --keep-hierarchy --top top',staged)

    def test_structure_stages_top_file_with_local_helper_module(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            leaf=root/'pe.sv';tile=root/'tile.sv';top=root/'top.sv'
            leaf.write_text('module pe; endmodule\n')
            tile.write_text('module tile; pe p(); endmodule\n')
            top.write_text('module delay; endmodule\n'
                           'module top; tile t(); delay d(); endmodule\n')
            script=(f'read_verilog -sv {leaf} {tile} {top}; hierarchy -top top')
            staged=structure._staged_slang_reads(script)
        self.assertIsNotNone(staged)
        self.assertIn(f'read_slang --top pe',staged)
        self.assertIn(f'read_slang --keep-hierarchy --top tile',staged)
        self.assertIn(f'read_slang --keep-hierarchy --top top',staged)

    def test_structure_keeps_monolithic_fallback_for_ambiguous_source_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'both.sv'
            source.write_text('module a; endmodule\nmodule b; endmodule\n')
            self.assertIsNone(structure._staged_slang_reads(
                f'read_verilog -sv {source}; hierarchy -top b'))

    def test_structure_keeps_successful_existing_elaboration(self):
        def inspect(submission):
            structure.frozen.subprocess.run(['yosys','-p','read_verilog -sv dut.sv; hierarchy -top top'])
            return {'passed':True}
        with patch.object(structure,'yosys_command',return_value=('/tool/yosys','-m','slang')), \
                patch.object(structure.frozen,'inspect',side_effect=inspect), \
                patch.object(structure.frozen.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','')) as native:
            self.assertTrue(structure.inspect(Path('/submission'))['passed'])
            native.assert_called_once()
            self.assertEqual(native.call_args.args[0][0],'yosys')

    def test_t10_physical_preserves_resource_and_geometry_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);submission=root/'submission';(submission/'rtl').mkdir(parents=True)
            (submission/'rtl/files.f').write_text('dut.sv\n')
            (submission/'rtl/dut.sv').write_text('module pe(input clk,rst_n); endmodule\n')
            proof=root/'structure.json';proof.write_text('{}\n')
            item=dict(model='glm-5.3',pe='pe',submission=submission,source_sha256='a'*64,structure=physical.artifact(proof))
            def prepare(item,seed,work,orfs):
                return physical.run_seed(item,seed,work,orfs,'baseline',memory_gib=40,allow_swap=True,prepare_only=True)
            with patch.object(current_physical,'executable',return_value=Path('/tool/yosys-slang')), \
                    patch.object(backend,'physical',side_effect=prepare), \
                    patch.object(physical.subprocess,'check_output',return_value='locked-version\n'):
                result=current_physical.physical(item,11,root/'work',root/'orfs')
            command=result['command'];self.assertIn('MemoryMax=40G',command)
            self.assertIn('MemorySwapMax=infinity',command)
            self.assertIn('YOSYS_EXE=/tool/yosys-slang',command)
            config=(root/'work/glm-5.3/seed11/config.mk').read_text()
            for field in ('SYNTH_HDL_FRONTEND = slang','CORE_UTILIZATION = 24','PLACE_DENSITY = 0.24'):
                self.assertIn(field,config)


if __name__=='__main__':unittest.main()
