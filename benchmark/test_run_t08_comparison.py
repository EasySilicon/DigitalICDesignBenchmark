import tempfile
import tomllib
import unittest
from pathlib import Path

from benchmark.prepare_t08_comparison import prepare_comparison
from benchmark.run_t08_comparison import audit_claude, check_prepared, command, toml_value, parse_event_line, print_event, task_budget


class T08RunnerTest(unittest.TestCase):
    def test_commands_keep_sessions_and_avoid_budget_stops(self):
        for agent in ('kimi', 'claude'):
            cmd = command(Path('/host/trial'), agent, 'test-container', 'abc-session')
            shell = cmd[-1]
            self.assertIn('7200s', shell)
            self.assertIn('/tmp/start_trial', shell)
            self.assertNotIn('--no-session-persistence', shell)
            self.assertNotIn('--disable-slash-commands', shell)
            self.assertNotIn('--max-budget-usd', shell)
            self.assertIn('/host/trial/workspace:/workspace', cmd)
            self.assertIn('/host/trial/agent_home:/home/benchmark', cmd)
            self.assertIn('/host/trial/empty_skills:/empty_skills:ro', cmd)
            self.assertFalse(any('frozen_judge:' in value for value in cmd))
        claude = command(Path('/host/trial'), 'claude', 'test-container', 'abc-session')
        self.assertIn('--session-id abc-session', claude[-1])
        self.assertIn('Skill,WebSearch,WebFetch', claude[-1])
        self.assertIn('CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000', claude)
        kimi = command(Path('/host/trial'), 'kimi', 'test-container', '')
        self.assertNotIn('--auto', kimi[-1])

    def test_init_requires_correct_model_and_no_skills(self):
        event = {'model': 'glm-5.3-flash', 'skills': [], 'tools': ['Bash', 'Read'],
                 'slash_commands': ['help']}
        audit_claude(event, 'glm-5.3-flash')
        for key, value in [('skills', ['unexpected']), ('model', 'wrong'),
                           ('tools', ['WebFetch']), ('slash_commands', [])]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                audit_claude({**event, key: value}, 'glm-5.3-flash')

    def test_public_eda_kit_is_readonly_and_does_not_mount_host_orfs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'public_eda').mkdir()
            cmd = command(root, 'kimi', 'test-container', '')
            self.assertIn(f'{root}/public_eda:/opt/t08_eda:ro', cmd)
            self.assertFalse(any('frozen_scoring:' in arg or 'ic_bcmk_orfs_asap7:' in arg for arg in cmd))

    def test_toml_config_values_roundtrip(self):
        expected = {'oauth': {'storage': 'file', 'enabled': True},
                    'aliases': ['a', 'b'], 'limit': 262144}
        self.assertEqual(tomllib.loads('value = ' + toml_value(expected))['value'], expected)

    def test_changed_inputs_block_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'comparison'
            prepare_comparison(root)
            trial = root / 'kimi-k3-256k'
            check_prepared(trial)
            (trial / 'workspace/benchmark/README.md').write_text('changed')
            with self.assertRaises(RuntimeError):
                check_prepared(trial)

    def test_mixed_stdout_is_not_always_an_event_object(self):
        for line in ('0', '47', 'null', 'true', '"text"', '[1,2]', 'raw tool text'):
            self.assertIsNone(parse_event_line(line))
        self.assertEqual(parse_event_line('{"type":"system"}'), {'type': 'system'})
        print_event({'message': 42})
        print_event({'tool_calls': [42, {'function': 42}]})

    def test_resume_keeps_original_session_and_remaining_budget(self):
        cmd = command(Path('/trial'), 'kimi', 'resume-container', '',
                      resume_session='session_original', seconds=6107, gate='resume_1')
        self.assertIn('--session session_original', cmd[-1])
        self.assertIn('6107s', cmd[-1])
        self.assertIn('/tmp/resume_1', cmd[-1])
        self.assertIn('/workspace/RESUME_PROMPT.md', cmd[-1])

    def test_trial_override_reaches_timeout_and_retains_persistence(self):
        seconds = task_budget({'time_limit_seconds': 5400})
        cmd = command(Path('/trial'), 'claude', 'test-container', 'new-session', seconds=seconds)
        self.assertIn('5400s', cmd[-1])
        self.assertNotIn('7200s', cmd[-1])
        self.assertIn('--session-id new-session', cmd[-1])
        self.assertEqual(task_budget({}), 7200)
        for invalid in (0, -1, True, '5400'):
            with self.assertRaises(RuntimeError):
                task_budget({'time_limit_seconds': invalid})


if __name__ == '__main__':
    unittest.main()
