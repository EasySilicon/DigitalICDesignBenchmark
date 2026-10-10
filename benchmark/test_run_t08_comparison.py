import tempfile
import json
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmark.prepare_t08_comparison import prepare_comparison
from benchmark.run_t08_comparison import audit_claude, check_prepared, command, toml_value, parse_event_line, print_event, task_budget, prepare_auth


class T08RunnerTest(unittest.TestCase):
    def test_deepseek_command_and_auth_use_exact_model_without_host_skills(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            host = root / 'host'
            settings = host / '.claude/settings.json'
            settings.parent.mkdir(parents=True)
            settings.write_text(json.dumps({'env': {
                'ANTHROPIC_AUTH_TOKEN': 'test-token',
                'ANTHROPIC_BASE_URL': 'https://example.invalid',
                'ANTHROPIC_MODEL': 'wrong-model',
                'UNRELATED_SECRET': 'do-not-copy'}, 'enabledPlugins': {'x': True}}))
            explicit = root / 'deepseek-settings.json'
            explicit.write_text(settings.read_text())
            trial = root / 'trial'
            (trial / 'agent_home').mkdir(parents=True)
            with patch('benchmark.run_t08_comparison.Path.home', return_value=host):
                settings.write_text('{"env": {"ANTHROPIC_BASE_URL": "https://wrong.invalid"}}')
                prepare_auth(trial, 'claude', model='deepseek-flash', claude_settings=explicit)
            config = json.loads((trial / 'agent_home/.claude/settings.json').read_text())
            for key, value in config['env'].items():
                if 'MODEL' in key:
                    self.assertEqual(value, 'deepseek-flash')
            self.assertNotIn('UNRELATED_SECRET', config['env'])
            self.assertEqual(config['env']['ANTHROPIC_BASE_URL'], 'https://example.invalid')
            self.assertEqual(json.loads(settings.read_text())['env']['ANTHROPIC_BASE_URL'],
                             'https://wrong.invalid')
            self.assertNotIn('enabledPlugins', config)
            self.assertTrue(config['disableBundledSkills'])
            self.assertEqual(config['permissions']['deny'], ['Skill', 'WebSearch', 'WebFetch'])
            cmd = command(trial, 'claude', 'test-container', 'session', model='deepseek-flash')
            self.assertIn('--model deepseek-flash', cmd[-1])
            self.assertIn('--session-id session', cmd[-1])
            self.assertNotIn('glm-5.3-flash', cmd[-1])
            with self.assertRaises(ValueError):
                command(trial, 'claude', 'test-container', 'session', model='unknown-model')
            audit_claude({'model': 'deepseek-flash', 'skills': [], 'tools': ['Bash', 'Read'],
                          'slash_commands': ['help']}, 'deepseek-flash')

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

    def test_codex_models_are_explicit_persistent_and_skill_free(self):
        for model in ('gpt-6-astra', 'gpt-6.1-sol', 'gpt-6-sol'):
            cmd = command(Path('/trial'), 'codex', 'test-container', '', model=model)
            shell = cmd[-1]
            self.assertIn(f'-m {model}', shell)
            self.assertIn('7200s', shell)
            self.assertIn('CODEX_HOME=/home/benchmark/.codex', cmd)
            self.assertIn('/trial/empty_skills:/home/benchmark/.codex/skills:ro', cmd)
            self.assertIn('--ignore-user-config', shell)
            self.assertIn('--enable skip_host_skill_discovery', shell)
            self.assertIn('--disable skill_search', shell)
            self.assertIn('--disable plugins', shell)
            self.assertIn('web_search="disabled"', shell)
            self.assertNotIn('--ephemeral', shell)
            self.assertNotIn('--no-session-persistence', shell)
            self.assertFalse(any('frozen_judge:' in arg for arg in cmd))
        with self.assertRaises(ValueError):
            command(Path('/trial'), 'codex', 'test-container', '', model='unknown-model')

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

    def test_claude_resume_preserves_session_model_and_remaining_budget(self):
        cmd = command(Path('/trial'), 'claude', 'resume-container', '',
                      model='deepseek-flash', resume_session='original-session',
                      seconds=7112, gate='start_resume_1')
        self.assertIn('--resume original-session', cmd[-1])
        self.assertNotIn('--session-id', cmd[-1])
        self.assertIn('--model deepseek-flash', cmd[-1])
        self.assertIn('/workspace/RESUME_PROMPT.md', cmd[-1])
        self.assertIn('7112s', cmd[-1])
        self.assertIn('Skill,WebSearch,WebFetch', cmd[-1])

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
