import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from benchmark import candidate_ppa, public_eda
from benchmark.run_t08_comparison import command


class PublicEdaTests(unittest.TestCase):
    def test_t09_constraints_match_the_independent_physical_flow(self):
        sys.path.insert(0, str(public_eda.ROOT / 'evaluator'))
        from ppa_probe import constraint_text
        self.assertEqual(candidate_ppa.constraints('T09', 'rv32i_five_stage_cpu'),
            constraint_text('rv32i_five_stage_cpu', ('clk',), 1000, .2))

    def test_t10_settings_match_actual_candidate_single_pe_flow(self):
        sys.path.insert(0, str(public_eda.ROOT / 'evaluator'))
        import t10_candidate_physical as physical
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            submission = root / 'submission'
            (submission / 'rtl').mkdir(parents=True)
            source = submission / 'rtl/pe.sv'
            source.write_text('module pe(input clk, rst_n); endmodule\n')
            (submission / 'rtl/files.f').write_text('pe.sv\n')
            proof = root / 'structure.json'
            proof.write_text('{}\n')
            item = dict(model='public-test', pe='pe', submission=submission,
                        source_sha256='a' * 64, structure=physical.artifact(proof))
            with patch.object(physical.subprocess, 'check_output', return_value='test-version\n'):
                physical.run_seed(item, 11, root / 'work', root / 'orfs',
                                  'baseline', prepare_only=True, allow_swap=True)
            seed = root / 'work/public-test/seed11'
            sdc, hook = seed / 'constraint.sdc', seed / 'clock_layers.tcl'
            self.assertEqual(candidate_ppa.constraints('T10', 'pe'), sdc.read_text())
            expected = dict(line.removeprefix('export ').split(' = ', 1)
                            for line in (seed / 'config.mk').read_text().splitlines())
            actual = dict(line.removeprefix('export ').split(' = ', 1)
                          for line in candidate_ppa.configuration('T10', 'pe', [source], sdc, hook).splitlines())
            for key, value in expected.items():
                if key not in ('GRT_SEED', 'OR_SEED'):
                    self.assertEqual(actual[key], value, key)
            self.assertEqual(actual['SYNTH_HDL_FRONTEND'], 'slang')

    def test_kit_has_public_assets_only_and_is_relocatable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, orfs = root / 'repo', root / 'orfs'
            for name in ['benchmark/candidate_ppa.py', 'evaluator/slang_frontend.py',
                         'evaluator/yosys_slang.py', 'vendor/asap7/allowed.lib',
                         'evaluator/reference/T09/answer.sv', 'evaluator/t09_hidden_tb.sv']:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('public' if 'reference' not in name else 'answer')
            for name in ['Makefile', 'scripts/synth.tcl', 'util/gen.py',
                         'platforms/common/lcu_kogge_stone.v', 'designs/private/answer.v',
                         'results/private/answer.v', 'reports/private/answer.rpt']:
                path = orfs / 'flow' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture')
            for task in ('T09', 'T10'):
                trial = root / task
                (trial / 'workspace').mkdir(parents=True)
                (trial / 'workspace/PROMPT.md').write_text('task\n')
                with patch.object(public_eda, 'ROOT', source):
                    kit = public_eda.prepare_public_eda(trial, orfs, task)
                self.assertTrue((kit / 'asap7/allowed.lib').exists())
                self.assertFalse(any(kit.rglob('answer*')))
                self.assertFalse(any(kit.rglob('SKILL.md')))
                self.assertEqual(json.loads((kit / 'task.json').read_text())['task'], task)
                cmd = command(trial, 'kimi', 'test', 'test', shell='true')
                self.assertIn(f'{kit}:/opt/benchmark_eda:ro', cmd)
                if task == 'T10':
                    self.assertIn('--top YOUR_PE_MODULE', (trial / 'workspace/PROMPT.md').read_text())
                self.assertIn('existing task deadline', (trial / 'workspace/EDA_TOOLS.md').read_text())

    def test_filelist_cannot_escape_candidate_rtl(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'rtl').mkdir()
            (root / 'outside.sv').write_text('module outside; endmodule')
            for entry in ('../outside.sv', str(root / 'outside.sv'), '-f secret.f'):
                (root / 'rtl/files.f').write_text(entry + '\n')
                with self.assertRaises(ValueError):
                    candidate_ppa.sources(root)


if __name__ == '__main__':
    unittest.main()
