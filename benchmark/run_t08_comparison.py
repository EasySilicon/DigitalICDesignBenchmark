#!/usr/bin/env python3
"""Run one prepared Kimi/GLM T08 trial; host judge never enters the container."""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
import uuid
from pathlib import Path

from benchmark.prepare_t08_comparison import digest, inventory, write_json

NODE = Path('/home/reefshark/.nvm/versions/node/v24.15.0')
KIMI = Path('/home/reefshark/.kimi-code/bin')
OSS = Path('/data/zhongzhuanzhan/ic_bcmk_tools/oss-cad-suite')
TOOL_PATH = f'/opt/kimi/bin:{NODE}/bin:/home/reefshark/.local/bin:{OSS}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
LIMIT = 7200


def task_budget(manifest: dict) -> int:
    budget = manifest.get('time_limit_seconds', LIMIT)
    if type(budget) is not int or budget <= 0:
        raise RuntimeError('invalid trial time budget')
    return budget


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def toml_value(value):
    if isinstance(value, dict):
        return '{' + ', '.join(json.dumps(k) + ' = ' + toml_value(v)
                              for k, v in value.items()) + '}'
    if isinstance(value, list):
        return '[' + ', '.join(map(toml_value, value)) + ']'
    return json.dumps(value, ensure_ascii=False)


def prepare_auth(root: Path, agent: str, kimi_auth_dir: Path | None = None) -> None:
    home = root / 'agent_home'
    if any(home.iterdir()):
        raise RuntimeError('refusing to reuse a nonempty candidate home')
    home.chmod(0o700)
    if agent == 'kimi':
        source = Path.home() / '.kimi-code'
        auth_source = kimi_auth_dir or source
        credential = json.loads((auth_source / 'credentials/kimi-code.json').read_text())
        if not (credential.get('access_token') or credential.get('refresh_token')):
            raise RuntimeError('Kimi credential is empty; provide a valid --kimi-auth-dir before launch')
        target = home / '.kimi-code'
        target.mkdir(mode=0o700)
        host = tomllib.loads((source / 'config.toml').read_text())
        alias = 'kimi-code/k3-256k'
        model = host['models'][alias]
        provider = model['provider']
        lines = [f'default_model = {json.dumps(alias)}',
                 f'thinking = {toml_value(host.get("thinking", True))}',
                 f'\n[models.{json.dumps(alias)}]']
        lines += [f'{json.dumps(k)} = {toml_value(v)}' for k, v in model.items()]
        lines += [f'\n[providers.{json.dumps(provider)}]']
        lines += [f'{json.dumps(k)} = {toml_value(v)}'
                  for k, v in host['providers'][provider].items()]
        lines += ['\n[tools]', 'disabled = ["Skill", "WebSearch", "FetchURL", "mcp__*"]']
        (target / 'config.toml').write_text('\n'.join(lines) + '\n')
        (target / 'config.toml').chmod(0o600)
        for name in ('device_id', 'region'):
            if (source / name).is_file():
                shutil.copy2(source / name, target / name)
        for folder in ('credentials', 'oauth'):
            if (auth_source / folder).is_dir():
                shutil.copytree(auth_source / folder, target / folder)
                for path in (target / folder).rglob('*'):
                    if path.is_file():
                        path.chmod(0o600)
    else:
        target = home / '.claude'
        target.mkdir(mode=0o700)
        host = json.loads((Path.home() / '.claude/settings.json').read_text())
        env = {k: v for k, v in host.get('env', {}).items()
               if k in {'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_API_KEY',
                        'ANTHROPIC_BASE_URL', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'}}
        for key in ('ANTHROPIC_MODEL', 'ANTHROPIC_REASONING_MODEL',
                    'ANTHROPIC_DEFAULT_OPUS_MODEL', 'ANTHROPIC_DEFAULT_SONNET_MODEL',
                    'ANTHROPIC_DEFAULT_HAIKU_MODEL', 'ANTHROPIC_DEFAULT_FABLE_MODEL'):
            env[key] = 'glm-5.3-flash'
        write_json(target / 'settings.json', {
            'env': env, 'disableBundledSkills': True,
            'permissions': {'deny': ['Skill', 'WebSearch', 'WebFetch']},
            'hasCompletedOnboarding': True, 'skipDangerousModePermissionPrompt': True,
        })
        (target / 'settings.json').chmod(0o600)
    if any(home.rglob('SKILL.md')):
        raise RuntimeError('Skill found in candidate home')


def command(root: Path, agent: str, container: str, session: str,
            shell: str | None = None, *, seconds: int = LIMIT,
            gate: str = 'start_trial', resume_session: str | None = None) -> list[str]:
    cmd = ['docker', 'run', '--name', container, '--network', 'host',
           '--user', '1000:1000', '--cpus', '16', '--memory', '32g',
           '--memory-swap', '32g', '--pids-limit', '4096',
           '--security-opt', 'no-new-privileges', '--read-only']
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy',
                'https_proxy', 'all_proxy', 'NO_PROXY', 'no_proxy'):
        cmd += ['-e', key]
    cmd += ['-e', 'HOME=/home/benchmark', '-e', f'PATH={TOOL_PATH}',
            '-e', 'LANG=C.UTF-8', '-e', 'LC_ALL=C.UTF-8', '-e', 'CI=1',
            '-e', 'CCACHE_DIR=/tmp/ccache']
    if agent == 'claude':
        cmd += ['-e', 'CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000']
    for source in ('/usr', '/bin', '/lib', '/lib64', '/etc/passwd',
                   '/etc/group', '/etc/ssl', '/home/reefshark/.local', str(NODE), str(OSS)):
        cmd += ['-v', f'{source}:{source}:ro']
    if agent == 'kimi':
        cmd += ['-v', f'{KIMI}:/opt/kimi/bin:ro']
    # Optional, sanitized technology/tool kit: never mount the ORFS worktree,
    # which may contain reference netlists and other trials' artifacts.
    if (root / 'public_eda').is_dir():
        cmd += ['-v', f'{root / "public_eda"}:/opt/t08_eda:ro']
    config = '.kimi-code' if agent == 'kimi' else '.claude'
    cmd += ['-v', f'{root / "workspace"}:/workspace',
            '-v', f'{root / "agent_home"}:/home/benchmark',
            '-v', f'{root / "empty_skills"}:/empty_skills:ro',
            '-v', f'{root / "empty_skills"}:/home/benchmark/{config}/skills:ro',
            '-v', f'{root / "tmp"}:/tmp', '-w', '/workspace', 'ubuntu:24.04', 'bash', '-c']
    if shell is None:
        prompt_file = 'RESUME_PROMPT.md' if resume_session else 'PROMPT.md'
        kimi_start = (f'kimi --session {shlex.quote(resume_session)}'
                      if resume_session else 'kimi -m kimi-code/k3-256k')
        launch = (
            f'{kimi_start} --skills-dir /empty_skills '
            f'--output-format stream-json -p "$(< /workspace/{prompt_file})"'
            if agent == 'kimi' else
            f'claude -p "$(< /workspace/PROMPT.md)" --model glm-5.3-flash '
            f'--session-id {shlex.quote(session)} --disallowedTools Skill,WebSearch,WebFetch '
            '--dangerously-skip-permissions --output-format stream-json --verbose'
        )
        shell = (f'while [ ! -f /tmp/{gate} ]; do sleep 0.1; done; '
                 f'exec timeout --signal=INT --kill-after=30s {seconds}s {launch}')
    return [*cmd, shell]


def check_prepared(root: Path) -> dict:
    manifest = json.loads((root / 'run_manifest.json').read_text())
    if json.loads((root / 'status.json').read_text())['status'] != 'prepared':
        raise RuntimeError('refusing to restart an already launched trial')
    if digest(inventory(root / 'workspace')) != manifest['input_sha256']:
        raise RuntimeError('public inputs changed after preparation')
    if digest(inventory(root / 'frozen_judge')) != manifest['judge_sha256']:
        raise RuntimeError('frozen judge changed after preparation')
    if any((root / 'empty_skills').iterdir()):
        raise RuntimeError('skill override is not empty')
    tasks = sorted(p.name for p in (root / 'workspace/benchmark/tasks').iterdir())
    if tasks != ['T08']:
        raise RuntimeError(f'other tasks visible: {tasks}')
    return manifest


def preflight(root: Path, kimi_auth_dir: Path | None = None) -> None:
    manifest = check_prepared(root)
    agent = manifest['agent']
    if not any((root / 'agent_home').iterdir()):
        prepare_auth(root, agent, kimi_auth_dir)
    name = 'ic-bcmk-t08-' + root.name.replace('.', '-') + '-preflight-' + uuid.uuid4().hex[:8]
    script = '''set -e
test "$(ls /workspace/benchmark/tasks)" = T08
test ! -e /home/reefshark/research/agent_os/ic_bcmk
test ! -e /mnt/ubu_3T/ic_bcmk_trials
test ! -e /workspace/evaluator/t08_check.py
test -z "$(find /workspace /home/benchmark /empty_skills -name SKILL.md -print -quit)"
test -z "$(ls -A /empty_skills)"
verilator --version
yosys -V
openroad -version
g++ --version | head -1
python3 --version
'''
    script += 'kimi -V\nkimi doctor\n' if agent == 'kimi' else 'claude --version\n'
    cmd = command(root, agent, name, '', shell=script)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    (root / 'preflight.log').write_text(result.stdout + result.stderr)
    subprocess.run(['docker', 'rm', name], capture_output=True, check=True)
    if result.returncode:
        raise RuntimeError('container preflight failed; see host-side preflight.log')
    write_json(root / 'preflight.json', {'passed': True, 'utc': utc(),
        'task_directories': ['T08'], 'host_repo_visible': False,
        'host_trials_visible': False, 'skill_files_present': False,
        'credentials_copied': True, 'model_api_called': False})
    print(f'PREFLIGHT_PASS {manifest["model"]}', flush=True)


def audit_claude(event: dict, expected: str) -> None:
    if event.get('model') != expected or event.get('skills') != []:
        raise RuntimeError('Claude init failed model/Skill audit')
    if {'Skill', 'WebSearch', 'WebFetch'}.intersection(event.get('tools') or []):
        raise RuntimeError('forbidden Claude tools exposed')
    if not event.get('slash_commands'):
        raise RuntimeError('normal Claude commands unexpectedly disabled')


def parse_event_line(line: str) -> dict | None:
    """CLI stdout may mix structured events with arbitrary tool-output lines."""
    try:
        value = json.loads(line)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def print_event(event: dict) -> None:
    if event.get('type') == 'system' and event.get('subtype') == 'init':
        print(f'INIT model={event.get("model")} cwd={event.get("cwd")} '
              f'skills={event.get("skills")} session={event.get("session_id")}', flush=True)
    message = event.get('message', event)
    if not isinstance(message, dict):
        return
    if event.get('role') == 'tool':
        print(f'TOOL_RESULT {event.get("tool_call_id", "")} (full output saved)', flush=True)
        return
    for block in message.get('content', []) if isinstance(message.get('content'), list) else []:
        if not isinstance(block, dict):
            continue
        if block.get('type') == 'text':
            print(block.get('text', ''), flush=True)
        elif block.get('type') == 'tool_use':
            print(f'TOOL {block.get("name")} {json.dumps(block.get("input", {}), ensure_ascii=False)[:1200]}', flush=True)
    calls = event.get('tool_calls', [])
    for call in calls if isinstance(calls, list) else []:
        if not isinstance(call, dict):
            continue
        function = call.get('function', {})
        if not isinstance(function, dict):
            continue
        print(f'TOOL {function.get("name")} {str(function.get("arguments", ""))[:1200]}', flush=True)
    if event.get('type') == 'result':
        print(f'RESULT {event.get("result", event.get("subtype"))}', flush=True)


def grade(root: Path, elapsed: float, exit_code: int) -> dict:
    grading = root / 'grading'
    frozen = root / 'frozen_judge'
    env = {**os.environ, 'PYTHONPATH': str(frozen), 'PATH': TOOL_PATH,
           'PYTHONDONTWRITEBYTECODE': '1'}
    cmd = ['systemd-run', '--user', '--scope', '--quiet', '-p', 'MemoryMax=16G',
           '-p', 'MemorySwapMax=0', sys.executable, '-m', 'evaluator.t08_check',
           str(root / 'workspace'), '--output', str(grading / 'functional.json')]
    with (grading / 'functional_driver.log').open('w') as log:
        result = subprocess.run(cmd, cwd=frozen, env=env, stdout=log,
                                stderr=subprocess.STDOUT, timeout=2400)
    if not (grading / 'functional.json').is_file():
        raise RuntimeError(f'independent grading incomplete, exit={result.returncode}')
    report = json.loads((grading / 'functional.json').read_text())
    # Frozen parser only; never run candidate-authored code on the host.
    parse_cmd = [sys.executable, '-c',
                 'import json,sys; from pathlib import Path; '
                 'from evaluator.public_check import sources_from_filelist; '
                 'print(json.dumps([str(p) for p in sources_from_filelist(Path(sys.argv[1]))]))',
                 str(root / 'workspace')]
    sources = json.loads(subprocess.check_output(parse_cmd, cwd=frozen, env=env, text=True))
    script = ('read_verilog -defer -sv ' + ' '.join(map(json.dumps, sources)) +
              '; hierarchy -check -top mac_1g_repair; proc; opt; check -assert; memory_collect; stat')
    try:
        with (grading / 'yosys.log').open('w') as log:
            result = subprocess.run(['systemd-run', '--user', '--scope', '--quiet',
                '-p', 'MemoryMax=16G', '-p', 'MemorySwapMax=0',
                'yosys', '-Q', '-p', script], env=env, stdout=log,
                stderr=subprocess.STDOUT, timeout=300)
        report['synthesis'] = {'passed': result.returncode == 0, 'exit_code': result.returncode,
                               'method': 'Yosys hierarchy/proc/opt/check; not routed PPA'}
    except subprocess.TimeoutExpired:
        report['synthesis'] = {'passed': None, 'status': 'timeout_pending_attribution'}
    report.update(elapsed_seconds=elapsed, agent_exit_code=exit_code)
    # Freeze and replay the newly qualified concurrency suite separately. Its
    # result must not silently alter /50 group weights or historical trials.
    if (frozen / 'evaluator/t08_stress_check.py').is_file():
        stress_path = grading / 'concurrency.json'
        stress_cmd = ['systemd-run', '--user', '--scope', '--quiet',
            '-p', 'MemoryMax=16G', '-p', 'MemorySwapMax=0',
            sys.executable, '-m', 'evaluator.t08_stress_check',
            str(root / 'workspace'), '--output', str(stress_path)]
        try:
            with (grading / 'concurrency_driver.log').open('w') as log:
                stress_result = subprocess.run(stress_cmd, cwd=frozen, env=env,
                    stdout=log, stderr=subprocess.STDOUT, timeout=1500)
            if stress_path.is_file():
                stress = json.loads(stress_path.read_text())
                report['concurrency_qualification'] = {
                    'stress_revision': stress['stress_revision'], 'scored': False,
                    'compiled': stress['compiled'], 'full_pass': stress['full_pass'],
                    'passed_count': stress['passed_count'], 'run_count': stress['run_count'],
                    'report': 'grading/concurrency.json'}
            else:
                report['concurrency_qualification'] = {
                    'scored': False, 'status': 'incomplete_pending_attribution',
                    'exit_code': stress_result.returncode}
        except subprocess.TimeoutExpired:
            report['concurrency_qualification'] = {
                'scored': False, 'status': 'timeout_pending_attribution'}
    return report


def run(root: Path, resume: bool = False) -> None:
    prior_elapsed = 0.0
    prior_eda = []
    runtime = root
    gate = 'start_trial'
    resume_session = None
    if resume:
        state = json.loads((root / 'status.json').read_text())
        manifest = json.loads((root / 'run_manifest.json').read_text())
        limit = task_budget(manifest)
        if state['status'] != 'runner_error' or manifest['agent'] != 'kimi':
            raise RuntimeError('only a stopped Kimi runner-error session can use this resume path')
        prior_elapsed = float(state['elapsed_seconds'])
        seconds = int(limit - prior_elapsed)
        if seconds <= 0:
            raise RuntimeError('original task time budget is exhausted')
        sessions = []
        for path in (root / 'agent_home/.kimi-code/sessions').rglob('state.json'):
            item = json.loads(path.read_text())
            if isinstance(item, dict) and str(item.get('id', '')).startswith('session_'):
                sessions.append(item['id'])
        if len(sessions) != 1:
            raise RuntimeError('cannot identify exactly one persistent Kimi session')
        resume_session = sessions[0]
        index = len(manifest.get('resumes', [])) + 1
        runtime = root / 'resumes' / f'{index:02d}'
        runtime.mkdir(parents=True, exist_ok=False)
        archive = runtime / 'before_resume'
        archive.mkdir()
        for filename in ('status.json', 'run_manifest.json', 'command.json'):
            shutil.copy2(root / filename, archive / filename)
        shutil.copy2(root / 'workspace/TRIAL_CLOCK.json', archive / 'TRIAL_CLOCK.json')
        shutil.copytree(root / 'workspace/rtl', archive / 'rtl')
        shutil.copytree(root / 'workspace/verif', archive / 'verif')
        prior_eda = [json.loads(path.read_text()) for path in
                     (root / 'telemetry_eda').glob('*/eda_time.json')]
        for previous in manifest.get('resumes', []):
            prior_eda += [json.loads(path.read_text()) for path in
                         (Path(previous['runtime']) / 'telemetry_eda').glob('*/eda_time.json')]
        gate = f'start_resume_{index}'
        (root / 'workspace/RESUME_PROMPT.md').write_text(
            'Continue this exact existing T08 session and current workspace; do not '
            'restart the task. The host runner interrupted you because it incorrectly '
            'parsed a numeric tool-output line as a JSON event. This is an infrastructure '
            'fault, not a candidate failure. The parser is now fixed. '
            f'Already used candidate time: {prior_elapsed:.3f} seconds; '
            f'remaining original time budget: {seconds} seconds. '
            'Host interruption time is excluded. Read the updated TRIAL_CLOCK.json. '
            'No hidden-test feedback or reference RTL is supplied. Continue your own '
            'implementation and verification. No Skills or direct Web tools; no '
            'cumulative token hard cap. Keep the original persistent session.\n')
        manifest.setdefault('resumes', []).append({'index': index, 'session_id': resume_session,
            'runtime': str(runtime), 'reason': 'host_log_parser_error',
            'prior_elapsed_seconds': prior_elapsed, 'remaining_seconds': seconds})
        if (root / 'tmp' / gate).exists():
            raise RuntimeError('resume gate already exists')
    else:
        manifest = check_prepared(root)
        limit = task_budget(manifest)
        seconds = limit
    if not json.loads((root / 'preflight.json').read_text()).get('passed'):
        raise RuntimeError('container preflight is required')
    session = resume_session or str(uuid.uuid4())
    container = 'ic-bcmk-t08-' + root.name.replace('.', '-') + '-' + uuid.uuid4().hex[:8]
    manifest.update(container=container, session_id=session if resume_session or manifest['agent'] == 'claude' else None,
                    resource_limits={'memory_gib': 32, 'cpus': 16}, launched_utc=utc())
    cmd = command(root, manifest['agent'], container, session,
                  seconds=seconds, gate=gate, resume_session=resume_session)
    write_json(runtime / 'command.json', cmd)
    write_json(root / 'run_manifest.json', manifest)
    write_json(root / 'status.json', {'status': 'starting', 'container': container})
    telemetry = runtime / 'telemetry_eda'
    telemetry.mkdir(exist_ok=True)
    edalog = (runtime / 'eda_monitor.log').open('w')
    monitor = subprocess.Popen([sys.executable, str(root / 'frozen_judge/benchmark/eda_time.py'),
        '--container-prefix', container, '--output-dir', str(telemetry),
        '--interval', '0.1', '--idle-stop-seconds', '60'], stdout=edalog, stderr=subprocess.STDOUT)
    process = None
    started = None
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, bufsize=1)
        attach_deadline = time.monotonic() + 45
        while not list(telemetry.glob('*/eda_time.json')):
            if process.poll() is not None or monitor.poll() is not None:
                raise RuntimeError('container or EDA monitor exited before start gate')
            if time.monotonic() > attach_deadline:
                raise RuntimeError('EDA monitor failed to attach')
            time.sleep(0.1)
        ready_gate = root.parent / manifest.get('start_gate', 'start_both')
        write_json(runtime / 'ready.json', {'ready': True, 'container': container, 'utc': utc()})
        print(f'READY {manifest["model"]}: waiting for common start gate', flush=True)
        while not ready_gate.exists():
            if process.poll() is not None or monitor.poll() is not None:
                raise RuntimeError('container/monitor lost while waiting for start')
            if time.monotonic() > attach_deadline + 120:
                raise RuntimeError('common start gate was not released')
            time.sleep(0.1)
        started = time.time()
        clock = {'started_utc': utc(), 'started_epoch': started,
                 'deadline_epoch': started + seconds, 'time_limit_seconds': limit,
                 'remaining_seconds': seconds, 'prior_elapsed_seconds': prior_elapsed,
                 'deadline_utc': dt.datetime.fromtimestamp(started + seconds, dt.timezone.utc).isoformat(),
                 'token_stop_enabled': False}
        write_json(root / 'workspace/TRIAL_CLOCK.json', clock)
        write_json(root / 'status.json', {'status': 'running', 'model': manifest['model'],
                                         'task': 'T08', 'container': container, **clock})
        manifest.update(clock)
        write_json(root / 'run_manifest.json', manifest)
        (root / 'tmp' / gate).touch()
        print(f'AGENT_START {manifest["model"]} deadline={clock["deadline_utc"]}', flush=True)
        audited = manifest['agent'] != 'claude'
        with (runtime / 'agent_events.jsonl').open('w') as log:
            for line in process.stdout:
                log.write(line)
                log.flush()
                event = parse_event_line(line)
                if event is None:
                    continue
                if event.get('type') == 'system' and event.get('subtype') == 'init':
                    if manifest['agent'] == 'claude':
                        audit_claude(event, manifest['model'])
                        audited = True
                        write_json(root / 'init_audit.json', {'passed': True, 'model': event['model'],
                            'skills': event['skills'], 'tools': event.get('tools'),
                            'slash_commands': event.get('slash_commands'), 'session_id': event.get('session_id')})
                try:
                    print_event(event)
                except (AttributeError, TypeError, ValueError):
                    print('UNRECOGNIZED_EVENT_SHAPE (raw event retained)', flush=True)
        exit_code = process.wait()
        elapsed = prior_elapsed + time.time() - started
        print(f'AGENT_FINISH exit={exit_code} elapsed={elapsed:.1f}s', flush=True)
        time.sleep(2.5)
        monitor.terminate()
        monitor.wait(timeout=10)
        eda_files = list(telemetry.glob('*/eda_time.json'))
        eda = json.loads(eda_files[0].read_text()) if eda_files else None
        eda_segments = [*prior_eda, *([eda] if eda else [])]
        if prior_eda:
            eda = {'method': 'host_proc_sampling', 'finished': True,
                   'eda_wall_seconds_estimate': sum(s['eda_wall_seconds_estimate'] for s in eda_segments),
                   'observed_call_count': sum(s['observed_call_count'] for s in eda_segments),
                   'sampling_interval_seconds': 0.1, 'note': 'interruption excluded'}
        write_json(root / 'status.json', {'status': 'grading_wait', 'agent_exit_code': exit_code,
                                         'elapsed_seconds': elapsed, 'finished_utc': utc()})
        lock_path = Path('/mnt/ubu_3T/ic_bcmk_trials/grade.lock')
        with lock_path.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            write_json(root / 'status.json', {'status': 'grading', 'elapsed_seconds': elapsed})
            try:
                report = grade(root, elapsed, exit_code)
            except Exception as error:
                report = {'task': 'T08', 'functional_total': None,
                          'status': 'grading_incomplete', 'grading_error': str(error)}
        report.update(model=manifest['model'], experimental=True, elapsed_seconds=elapsed,
                      agent_exit_code=exit_code, init_audit_passed=audited, eda=eda,
                      ppa_status='pending_frozen_reference', ppa_score=None,
                      time_score=None, token_stop_enabled=False, finished_utc=utc())
        report['eda_segments'] = eda_segments
        report['prior_elapsed_seconds'] = prior_elapsed
        report['missing_delivery_files'] = [name for name in ('run.sh', 'results.json', 'README.md')
                                            if not (root / 'workspace' / name).is_file()]
        report['run_sh_executable'] = os.access(root / 'workspace/run.sh', os.X_OK)
        write_json(root / 'summary.json', report)
        write_json(root / 'status.json', {'status': 'complete' if report.get('functional_total') is not None
            else 'grading_incomplete', 'functional_total': report.get('functional_total'),
            'elapsed_seconds': elapsed, 'finished_utc': utc()})
        print(f'TRIAL_FINISH model={manifest["model"]} functional={report.get("functional_total")}/50 '
              f'eda={eda.get("eda_wall_seconds_estimate") if eda else None}s', flush=True)
    except BaseException as error:
        subprocess.run(['docker', 'stop', '--time', '10', container], capture_output=True)
        write_json(root / 'status.json', {'status': 'runner_error', 'error': str(error),
            'elapsed_seconds': prior_elapsed + time.time() - started if started else prior_elapsed,
            'utc': utc()})
        raise
    finally:
        if monitor.poll() is None:
            monitor.terminate()
            monitor.wait(timeout=10)
        if process is not None and process.poll() is None:
            process.wait(timeout=15)
        edalog.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--kimi-auth-dir', type=Path,
                        help='credentials only; never copies old sessions or Skills')
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    preflight(root, args.kimi_auth_dir) if args.preflight else run(root, resume=args.resume)


if __name__ == '__main__':
    main()
