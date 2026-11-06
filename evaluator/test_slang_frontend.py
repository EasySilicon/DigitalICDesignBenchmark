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

    def test_structure_native_read_timeout_retries_slang_and_restores_runner(self):
        original = structure.frozen.subprocess.run
        def inspect(submission):
            structure.frozen.subprocess.run(
                ['yosys', '-p', 'read_verilog -sv dut.sv; hierarchy -top top'], timeout=180)
            return {'passed': True}
        with patch.object(structure, 'yosys_command', return_value=('/tool/yosys', '-m', 'slang')), \
                patch.object(structure.frozen, 'inspect', side_effect=inspect), \
                patch.object(structure.frozen.subprocess, 'run', side_effect=[
                    subprocess.TimeoutExpired(['yosys'], 180),
                    subprocess.CompletedProcess([], 0, '', '')]) as native:
            result = structure.inspect(Path('/submission'))
            self.assertTrue(result['passed'])
            self.assertEqual(result['hdl_frontend'], 'slang')
            self.assertIn('read_slang', native.call_args.args[0][-1])
        self.assertIs(structure.frozen.subprocess.run, original)

    def test_structure_does_not_retry_non_frontend_timeouts(self):
        original = structure.frozen.subprocess.run
        def inspect(submission):
            structure.frozen.subprocess.run(['yosys', '-p', 'read_json design.json; opt_clean'])
        with patch.object(structure, 'yosys_command', return_value=('/tool/yosys',)), \
                patch.object(structure.frozen, 'inspect', side_effect=inspect), \
                patch.object(structure.frozen.subprocess, 'run',
                             side_effect=subprocess.TimeoutExpired(['yosys'], 180)) as native:
            with self.assertRaises(subprocess.TimeoutExpired):
                structure.inspect(Path('/submission'))
            self.assertEqual(native.call_count, 1)
        self.assertIs(structure.frozen.subprocess.run, original)

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

    @unittest.skipUnless(shutil.which('yosys'),'Yosys not installed')
    def test_parameterized_array_helper_keeps_overrides_and_common_pe_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            helper=root/'reducer.sv';pe=root/'pe.sv';tile=root/'tile.sv';top=root/'mesh.sv'
            helper.write_text('''module reducer #(parameter int N=2, W=4)(
              input logic [W-1:0] din[N], output logic [W-1:0] dout);
              always_comb begin
                dout='0;
                for (int i=0;i<N;i++) dout^=din[i];
              end
            endmodule
''')
            pe.write_text('''module pe(input logic clk, input logic [47:0] x,
                         output logic [15:0] q);
              logic [15:0] words[3], d;
              for (genvar i=0;i<3;i++) assign words[i]=x[16*i+:16];
              reducer #(.N(3),.W(16)) reduce(words,d);
              always_ff @(posedge clk) q<=d;
            endmodule
''')
            tile.write_text('''module tile(input logic clk,input logic [47:0] x[2],
                           output logic [15:0] q[2]);
              pe left(clk,x[0],q[0]);
              pe right(clk,x[1],q[1]);
            endmodule
''')
            top.write_text('''module mesh #(parameter int COPIES=2)
                           (input logic clk,input logic [47:0] a,b,
                            output logic [15:0] y,z);
              logic [47:0] x[2];
              logic [15:0] q[2];
              assign x[0]=a; assign x[1]=b;
              assign y=q[0]; assign z=q[1];
              tile wrapper(clk,x,q);
            endmodule
''')
            output=root/'design.json'
            script=(f'read_verilog -sv {helper} {pe} {tile} {top}; hierarchy -top mesh; '
                    f'proc; opt_clean; write_json {output}')
            staged=structure._staged_slang_reads(script)
            self.assertIsNotNone(staged)
            result=subprocess.run([*frontend.yosys_command(),'-Q','-T','-p',staged],
                                  capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,(result.stdout+result.stderr)[-3000:])
            design=json.loads(output.read_text())['modules']
            self.assertEqual(len(design['pe']['ports']['q']['bits']),16)
            def count_pe(name):
                return sum(1 if cell['type']=='pe' else count_pe(cell['type'])
                           if cell['type'] in design else 0
                           for cell in design[name]['cells'].values())
            self.assertEqual(count_pe('mesh'),2)
            # All three specialized 16-bit inputs must reach the PE logic.
            inputs=set(design['pe']['ports']['x']['bits'])
            used={bit for cell in design['pe']['cells'].values()
                  for name,bits in cell['connections'].items()
                  if cell['port_directions'][name]=='input' for bit in bits}
            self.assertTrue(inputs.issubset(used))

    @unittest.skipUnless(shutil.which('yosys'),'Yosys not installed')
    def test_stateful_parameterized_tiles_keep_overrides_registers_and_shared_pe(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            pe=root/'pe.sv';tile=root/'tile.sv';top=root/'mesh.sv'
            pe.write_text('''module pe(input logic clk,input logic [63:0] x,
                                     output logic [63:0] q);
              always_ff @(posedge clk) q<=x;
            endmodule
''')
            tile.write_text('''module tile #(parameter int N=1,W=8)
                           (input logic clk,input logic [N*W-1:0] x,
                            output logic [N*64-1:0] q);
              for (genvar i=0;i<N;i++) begin : g
                logic [W-1:0] hop;
                always_ff @(posedge clk) hop<=x[i*W+:W];
                pe u(clk,{{(64-W){1'b0}},hop},q[i*64+:64]);
              end
            endmodule
''')
            top.write_text('''module mesh(input logic clk,input logic [7:0] a,
                           input logic [47:0] b,output logic [63:0] y,
                           output logic [191:0] z);
              tile #(.N(1),.W(8)) t_narrow(clk,a,y);
              tile #(.N(3),.W(16)) t_wide(clk,b,z);
            endmodule
''')
            output=root/'design.json'
            script=(f'read_verilog -sv {pe} {tile} {top}; hierarchy -top mesh; '
                    f'proc; opt_clean; write_json {output}')
            staged=structure._staged_slang_reads(script)
            self.assertIsNotNone(staged)
            result=subprocess.run([*frontend.yosys_command(),'-Q','-T','-p',staged],
                                  capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,(result.stdout+result.stderr)[-3000:])
            design=json.loads(output.read_text())['modules']
            self.assertEqual(structure.frozen._reachable_instances(design,'mesh','pe'),4)
            tiles=[design[cell['type']] for cell in design['mesh']['cells'].values()]
            self.assertEqual(sorted(len(t['ports']['x']['bits']) for t in tiles),[8,48])
            self.assertEqual(sorted(len(t['ports']['q']['bits']) for t in tiles),[64,192])
            self.assertEqual(sorted(sum(len(c['connections']['Q'])
                for c in t['cells'].values() if c['type'] in structure.frozen.FLOP_TYPES)
                for t in tiles),[8,48])
            # The four leaves must share one real registered PE body.
            self.assertTrue(any(c['type'] in structure.frozen.FLOP_TYPES
                                for c in design['pe']['cells'].values()))

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

    @unittest.skipUnless(shutil.which('yosys'),'Yosys not installed')
    def test_only_static_register_arrays_are_lowered_for_mesh_analysis(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'arrays.sv';output=root/'before.json'
            source.write_text('''module arrays(input logic clk, input logic [1:0] en,addr,
              input logic [7:0] x, output logic [15:0] y, output logic [7:0] z);
              logic [1:0][7:0] stages[2];
              logic [7:0] store[4];
              always_ff @(posedge clk) begin
                if (en[0]) begin stages[0][0]<=x; stages[1][0]<=stages[0][0]; end
                if (en[1]) begin stages[0][1]<=x; stages[1][1]<=stages[0][1]; end
                store[addr]<=x;
              end
              assign y=stages[1]; assign z=store[addr];
            endmodule
''')
            result=subprocess.run([*frontend.yosys_command(),'-Q','-T','-p',
                f'read_slang --top arrays {source}; proc; opt_clean; write_json {output}'],
                capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            design=json.loads(output.read_text())
            # Candidate attributes must not make a dynamic store eligible.
            design['modules']['arrays']['memories']['store']['attributes']['ic_bcmk_static_array']=1
            self.assertEqual(structure.frozen._mark_static_register_arrays(design),1)
            memories=design['modules']['arrays']['memories']
            self.assertEqual(memories['stages']['attributes']['ic_bcmk_static_array'],1)
            self.assertEqual(memories['store']['attributes']['ic_bcmk_static_array'],0)
            output.write_text(json.dumps(design));after=root/'after.json'
            result=subprocess.run(['yosys','-Q','-T','-p',
                structure.frozen._static_register_array_script(output,after)],
                capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            module=json.loads(after.read_text())['modules']['arrays']
            self.assertNotIn('stages',module.get('memories',{}))
            self.assertIn('store',module.get('memories',{}))
            self.assertTrue(any(c['type']=='$dffe' for c in module['cells'].values()))
            self.assertEqual(sum(len(c['connections']['Q']) for c in module['cells'].values()
                                 if c['type'] in structure.frozen.FLOP_TYPES),32)
            registers={bit:(cell,index) for cell in module['cells'].values()
                       if cell['type'] in structure.frozen.FLOP_TYPES
                       for index,bit in enumerate(cell['connections']['Q'])}
            for index,bit in enumerate(module['ports']['y']['bits']):
                cell,_=registers[bit]
                self.assertEqual(cell['connections']['EN'],
                                 [module['ports']['en']['bits'][index//8]])
            # Check observable behavior with independently enabled partial
            # writes. A legal priority mux may remain on D, so requiring a
            # literal wire here would repeat the checker's representation bug.
            drivers={bit:(cell,pin) for cell in module['cells'].values()
                     for port,bits in cell['connections'].items()
                     if cell['port_directions'][port]=='output'
                     for pin,bit in enumerate(bits) if isinstance(bit,int)}
            state=dict.fromkeys(registers,0)
            expected=[[0,0],[0,0]]
            for enable,value in [(1,0x12),(2,0x34),(3,0x56),(0,0x78),(1,0x90),(2,0xbc)]:
                values=state.copy()
                for port,number in [('en',enable),('x',value)]:
                    values.update({bit:(number>>i)&1
                                   for i,bit in enumerate(module['ports'][port]['bits'])})
                def evaluate(bit):
                    if bit in ('0','1'):return int(bit)
                    if bit in values:return values[bit]
                    cell,pin=drivers[bit];connections=cell['connections']
                    if cell['type']=='$mux':
                        branch='B' if evaluate(connections['S'][0]) else 'A'
                        result=evaluate(connections[branch][pin])
                    elif cell['type']=='$or':
                        result=evaluate(connections['A'][pin])|evaluate(connections['B'][pin])
                    else:self.fail(f"unexpected cell in register-array cone: {cell['type']}")
                    values[bit]=result
                    return result
                state={bit:evaluate(cell['connections']['D'][pin])
                       if evaluate(cell['connections']['EN'][0]) else state[bit]
                       for bit,(cell,pin) in registers.items()}
                for lane in range(2):
                    if enable>>lane&1:expected[lane]=[value,expected[lane][0]]
                observed=sum(state[bit]<<i for i,bit in enumerate(module['ports']['y']['bits']))
                self.assertEqual(observed,expected[0][1]|expected[1][1]<<8)
            # Preparatory optimization must leave the dynamic store's ports
            # unchanged too, rather than only protecting it from memory_map.
            def dynamic_ports(body):
                return {name:cell for name,cell in body['cells'].items()
                        if cell['type'].startswith('$mem') and
                        cell['parameters'].get('MEMID','').lstrip('\\')=='store'}
            self.assertEqual(dynamic_ports(module),dynamic_ports(design['modules']['arrays']))

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
