# Public executable examples for independent port-level checking

[中文](README.md)

`public_check.py` reads only a submission's `rtl/files.f` and RTL sources, then compiles the fixed task-specific testbench. It does not run the submission's `run.sh`, `verif/`, or `results.json`.

```bash
python3 evaluator/public_check.py T01 /path/to/submission
python3 evaluator/public_check.py T02 /path/to/submission --seed 1234
python3 evaluator/public_check.py T03 /path/to/submission --width 32 --depth 16
python3 evaluator/public_check.py T04 /path/to/submission
python3 evaluator/public_check.py T05 /path/to/submission --n-inputs 8 --width 32
python3 evaluator/public_check.py T06 /path/to/submission --depth 16 --width 32
python3 evaluator/public_check.py T07 /path/to/submission
python3 evaluator/public_check.py T08 /path/to/submission
python3 evaluator/public_check.py T09 /path/to/submission
```

Compilation and simulation run in an isolated temporary directory. Failures return a nonzero status and a JSON summary. These public tests are smoke examples, not the formal scoring suite. T10's public material includes the task-local numerical oracle at `benchmark/tasks/T10/public/matmul_oracle.py`; it specifies numeric decoding, MX scales, and output tolerance without supplying RTL or hidden vectors.

`cpu_elf_check.py` loads an RV32 ELF under the task-card memory map and checks the fixed CPU interface. The 45 public ACT4 ELF artifacts under `act4_elfs/` can be checked with `verify_act4_artifacts.py` and run with `check_act4_sail.py` using a locked Sail setup.

`delivery_check.py` validates the submission layout and self-checking entry point. A passing submission test is evidence of delivery quality only: independent evaluator tests decide DUT correctness.
