"""No Agent calls or credentials; packaging/release isolation regression."""
import json
import tempfile
import unittest
from pathlib import Path

from benchmark.prepare_t08_comparison import MODELS, inventory, prepare_comparison, copy_common_synthesis_maps


class T08ComparisonTest(unittest.TestCase):
    def test_deepseek_uses_claude_code_and_two_hour_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'single'
            release = prepare_comparison(root, models=('deepseek-flash',))
            self.assertEqual(set(release['models']), {'deepseek-flash'})
            self.assertEqual(release['time_limit_seconds'], 7200)
            self.assertEqual(release['start_gate'], 'start_single')
            manifest = json.loads((root / 'deepseek-flash/run_manifest.json').read_text())
            self.assertEqual(manifest['model'], 'deepseek-flash')
            self.assertEqual(manifest['agent'], 'claude')

    def test_gpt61_sol_uses_exact_model_and_two_hour_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'single'
            release = prepare_comparison(root, models=('gpt-6.1-sol',))
            self.assertEqual(set(release['models']), {'gpt-6.1-sol'})
            self.assertEqual(release['time_limit_seconds'], 7200)
            self.assertEqual(release['start_gate'], 'start_single')
            manifest = json.loads((root / 'gpt-6.1-sol/run_manifest.json').read_text())
            self.assertEqual(manifest['model'], 'gpt-6.1-sol')
            self.assertEqual(manifest['agent'], 'codex')
            self.assertEqual(manifest['reasoning_effort'], 'high')

    def test_identical_inputs_and_host_only_judges(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "comparison"
            release = prepare_comparison(root, models=tuple(MODELS))
            trials = [root / name for name in MODELS]
            self.assertEqual(inventory(trials[0] / "workspace"),
                             inventory(trials[1] / "workspace"))
            self.assertEqual(inventory(trials[0] / "frozen_judge"),
                             inventory(trials[1] / "frozen_judge"))
            self.assertEqual(release["status"], "prepared_not_started")
            self.assertFalse(release["credentials_copied"])
            self.assertEqual(release["time_limit_seconds"], 7200)
            for trial in trials:
                self.assertFalse(any((trial / "agent_home").iterdir()))
                self.assertFalse(any((trial / "empty_skills").iterdir()))
                self.assertFalse((trial / "workspace/evaluator/t08_check.py").exists())
                self.assertTrue((trial / "frozen_judge/evaluator/t08_check.py").is_file())
                self.assertTrue((trial / "frozen_judge/evaluator/t08_stress_check.py").is_file())
                self.assertTrue((trial / "frozen_judge/evaluator/fixtures/t11_mac/tb_stress.sv").is_file())
                self.assertFalse((trial / "workspace/evaluator/t08_stress_check.py").exists())
                self.assertFalse((trial / "workspace/evaluator/fixtures").exists())
                manifest = json.loads((trial / "run_manifest.json").read_text())
                self.assertEqual(manifest["input_sha256"], release["input_sha256"])
                self.assertTrue(manifest["session_persistence"])
                self.assertFalse(manifest["token_stop_enabled"])
                self.assertFalse(manifest["supplemental_checks"]["t08_concurrency"]["scored"])

    def test_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileExistsError):
                prepare_comparison(Path(temporary))

    def test_single_glm_90_minutes_is_consistent_in_every_candidate_document(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'single'
            release = prepare_comparison(root, models=('glm-5.3-flash',), time_limit_minutes=90)
            self.assertEqual(set(release['models']), {'glm-5.3-flash'})
            self.assertEqual(release['time_limit_seconds'], 5400)
            self.assertEqual(release['start_gate'], 'start_single')
            self.assertFalse((root / 'kimi-k3-256k').exists())
            trial = root / 'glm-5.3-flash'
            workspace = trial / 'workspace'
            task = workspace / 'benchmark/tasks/T08'
            self.assertIn('90 minutes', (workspace / 'PROMPT.md').read_text())
            self.assertIn('Budget: 90 minutes', (task / 'task.md').read_text())
            self.assertIn('90-minute budget', (task / 'task.md').read_text())
            self.assertIn('time_limit_minutes: 90', (task / 'task.yaml').read_text())
            self.assertIn('5,400 seconds', (task / 'acceptance.md').read_text())
            self.assertNotIn('120 分钟', (task / 'README.md').read_text())
            manifest = json.loads((trial / 'run_manifest.json').read_text())
            self.assertEqual(manifest['time_limit_seconds'], 5400)
            self.assertTrue(manifest['trial_time_limit_override'])

    def test_invalid_model_or_budget_is_rejected_before_creating_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'bad'
            for models, minutes in [((), 90), (('unknown',), 90),
                                    (('glm-5.3-flash',), 0), (('glm-5.3-flash',), True)]:
                with self.assertRaises(ValueError):
                    prepare_comparison(root, models=models, time_limit_minutes=minutes)
                self.assertFalse(root.exists())

    def test_inventory_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "leak").symlink_to("/etc/passwd")
            with self.assertRaises(ValueError):
                inventory(root)

    def test_common_synthesis_map_is_included_without_designs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            orfs, kit = root / 'orfs', root / 'kit'
            source = orfs / 'flow/platforms/common/lcu_kogge_stone.v'
            source.parent.mkdir(parents=True)
            source.write_text('module public_map; endmodule\n')
            copy_common_synthesis_maps(kit, orfs)
            target = kit / 'flow/platforms/common/lcu_kogge_stone.v'
            self.assertEqual(source.read_bytes(), target.read_bytes())
            self.assertFalse((kit / 'flow/designs').exists())
            copy_common_synthesis_maps(kit, orfs)
            target.write_text('different\n')
            with self.assertRaises(ValueError):
                copy_common_synthesis_maps(kit, orfs)

    def test_common_synthesis_map_missing_or_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            orfs, kit = root / 'orfs', root / 'kit'
            with self.assertRaises(ValueError):
                copy_common_synthesis_maps(kit, orfs)
            source = orfs / 'flow/platforms/common/lcu_kogge_stone.v'
            source.parent.mkdir(parents=True)
            source.symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):
                copy_common_synthesis_maps(kit, orfs)


if __name__ == "__main__":
    unittest.main()
