# Official experiment runner

`benchmark.runner` runs a full suite with two independent pipelines. Candidate tasks remain sequential, while completed submissions enter a separate serial host-grading queue. Waiting for the machine-wide physical-flow lock therefore never delays the next candidate task.

The runner enforces these boundaries:

- Time, CPU, RAM, disk, and token policy come only from `benchmark/manifest.yaml`; local configuration cannot add token, turn, monetary, or model-response limits.
- Every task receives a fresh workspace, Agent home, container, and session. The candidate sees only that task, the public EDA kit, and explicitly configured tool mounts.
- The repository, judges, reference RTL, other submissions, and prior sessions never enter the candidate container.
- A completed workspace is frozen as `submission/`. A task with `agent_result.json` is never sent to the model again.
- Host grading is single-file behind a global lock but runs independently from candidate development.
- `grading/Txx/job_status.json` distinguishes lock wait, active grading, failure, and completion; long jobs emit a grading heartbeat every minute.
- Changed configuration, frozen inputs, model, or reasoning binding fail closed rather than silently altering an existing trial.
- Authentication values are never copied into the trial. Kimi mounts one shared mutable OAuth directory so concurrent processes do not create divergent refresh-token copies.

Adapters are included for Kimi CLI, Codex CLI, Claude Code, and ZCode CLI. CLI-specific profile preparation, launch arguments, event parsing, model/effort checks, and credential handling live in `adapters.py`; orchestration, containers, clocks, recovery, archival, and grading queues are model-independent.

Copy `benchmark/runner.example.yaml` outside the repository and replace local paths. The file contains policy and paths, never credentials. `grader.command` is a host-only integration command that must include `{task_id}` and write `{grading}/report.json`. Supported placeholders are `{task_id}`, `{trial_root}`, `{task_root}`, `{submission}`, `{grading}`, `{repo_root}`, `{frozen_repo}`, and `{elapsed_seconds}`.

Preflight and run:

```bash
python3 -m benchmark.runner /path/to/local-runner.yaml --preflight-only
tmux new-session -s ic-bcmk-run \
  "cd /path/to/ic_bcmk && python3 -m benchmark.runner /path/to/local-runner.yaml"
```

Creating `STOP` in the trial root prevents the next task from starting without deleting the active or completed evidence. See the Chinese README for the adapter matrix and regression-test command.
