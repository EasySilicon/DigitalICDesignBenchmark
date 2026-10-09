# Task packages

[中文](README.md)

The active v0.3 suite contains T01 through T10. T08 is the frozen 1GbE MAC repair and VLAN admission task. Task-specific public artifacts belong in its package; shared tools, technology files, and suite-wide rules stay in shared locations.

`task.md` is the frozen task specification and `acceptance.md` is the task-specific acceptance plan. The [suite-wide task rules](../README.md#共享任务规则) and [acceptance rules](../README.md#通用验收规则) are in the benchmark README. Public testbenches and other public artifacts are read from each package's `public/` directory; `public_check.py` and `prepare_trial.py` expose the same material.

T10's public numerical oracle is `T10/public/matmul_oracle.py`. It defines the numerical contract and is not an RTL implementation.

T08/T09 task-level freeze (2026-10-09): [T08 receipt](../../benchmark/tasks/T08/FREEZE.json), [T09 receipt](../../benchmark/tasks/T09/FREEZE.json). Run `python3 benchmark/freeze_tasks.py` from the repository root to verify specification, RTL, judge, scoring, baseline and portable evidence hashes. All six T09 archives have been regraded; untested T08 models remain null. Host-only receipts are excluded from candidate packages. T10 PPA and the suite-wide tool-image/release gates remain pending.
