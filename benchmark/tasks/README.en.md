# Task packages

[中文](README.md)

Each task from `T01` through `T10` is an independent package. Task-specific public artifacts belong in its package; shared tools, technology files, and suite-wide rules stay in shared locations.

`task.md` is the frozen task specification and `acceptance.md` is the task-specific acceptance plan. The root [tasks.md](../tasks.md) and [acceptance.md](../acceptance.md) define only suite-wide rules. Public testbenches and other public artifacts are read from each package's `public/` directory; `public_check.py` and `prepare_trial.py` expose the same material.

T10's public numerical oracle is `T10/public/matmul_oracle.py`. It defines the numerical contract and is not an RTL implementation.
