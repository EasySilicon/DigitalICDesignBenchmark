# EDA tool timing

The host-side monitor estimates EDA wall time inside contestant Docker containers.
It includes synthesis, implementation, formal/simulation tools, build commands
(make/CMake/Ninja), C/C++ compilation/linking, and common simulator executables
(including Verilator `V*` binaries and `vvp`). It does not change scoring.

Run on the host, before starting the candidate container:

```sh
python3 benchmark/eda_time.py \
  --container-prefix ic-bcmk-claude-glm-5-3-flash- \
  --container-prefix ic-bcmk-kimi-k3-256k- \
  --output-dir /path/to/host-only/telemetry
```

The monitor discovers matching containers every two seconds and samples their
cgroup v2 process lists every 0.1 seconds. Each container instance receives an
`eda_time.json` summary (updated every five seconds) and `calls.jsonl` containing
completed observed process intervals. A separate host directory must be used;
do not mount it into contestants. Stop with SIGINT/SIGTERM, or it exits after an
hour with no matching containers; adjust `--idle-stop-seconds` for long grading
gaps. The tool requires Docker read access and permission to read the contestant
processes' `/proc` files. It requires no extra contestant privileges or dependencies.

`eda_wall_seconds_estimate` combines overlapping/nested EDA activity, so a
Verilator build's parent, make and compiler children do not multiply total time.
`process_seconds_sum_estimate` is the separate sum of process intervals, which
can exceed wall time. `observed_call_count` counts processes, not Agent tool-use
requests. Background processes are included as long as they remain in the
candidate container. Host-side acceptance/grading processes are excluded.

These are sampled estimates, not exact exec/exit timestamps. Very short processes
can be missed, and busy boundaries are interpolated between samples. The summary
records both the configured interval and maximum actual sampling gap. Attaching
mid-task measures only subsequent activity. No earlier work is reconstructed.

Tool names are matched against actual process argv/executable, not shell-command
substrings. Build commands inside the candidate container count regardless of
purpose. Arbitrarily named custom simulator binaries can be missed; register a
known executable basename with `--extra-tool my_cpu_sim`. These classification
rules and the tool version should be frozen for model comparisons. Candidates
can evade a sampled name-based monitor; this is descriptive telemetry and must
not be treated as a tamper-proof accounting source or score input.

Persistent Claude/Kimi session settings are independent of the monitor. No
additional Agent prompt, Skill, reference RTL or acceptance code is exposed.

The 2026-10-07 parser fix preserves empty arguments in `/proc/*/cmdline`.
OSS CAD's explicit ELF loader uses `--inhibit-rpath ""`; dropping that empty
value shifted option parsing and could miss the main Yosys process. The fix is
frozen into the GLM T08 v3 90-minute trial. Historical sampled reports are not
retrospectively repaired by this change and should not be treated as complete
EDA accounting without a separate audit.
