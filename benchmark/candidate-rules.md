# Candidate rules and delivery contract

This workspace contains one assigned task only. Read its task.md and
acceptance.md completely. They define the fixed top-level ports, legal inputs,
reset/clock behavior, resource constraints, time budget and scoring status.
Task-specific requirements override this generic delivery contract.

Use only the supplied public task material and installed local tools. Do not
inspect other tasks, previous submissions, host repositories, reference RTL,
hidden tests or host grading directories. Do not download an alternative answer.
No Skills are supplied: do not discover, load, create as guidance, or install
Skills. Direct web-search/fetch tools are disabled. Normal local commands remain
available. Use one model session; do not delegate work to other model Agents.

## Deliverables

- rtl/: synthesizable .sv/.v design sources, preserving the specified top ports.
- rtl/files.f: UTF-8 filelist, one path relative to rtl/ per line; no absolute
  paths, '..', command options or macros. Include every required design source.
- verif/: independently written, executable self-checking verification.
- run.sh: executable, non-interactive entry point invoked from the workspace
  root. Return zero only for a real pass, nonzero for failure. Do not download
  dependencies or require pre-existing builds, mandatory cache paths or
  undocumented environment variables.
- results.json: generated from actual self-tests, not invented results. Include
  tests (each with name, passed and integer seed), tool_versions and
  elapsed_seconds. Test instances are unique by (name, seed).
- README.md: reproduction commands, tested behavior, known limitations, design
  choices, actual synthesis/PPA attempts and any optimization comparison.
- Preserve all supplied license and copyright notices.

Support optional BENCH_SEED with a documented deterministic default. It may
derive multiple test seeds deterministically. Repeated runs with the same seed
must reproduce the same outcomes. Failed simulations/compilers must not be
masked as passing tests. Use your own scoreboard, directed boundary cases and
randomized regression; the copied public evaluator is only a smoke test.
Do not edit the supplied public evaluator. Its source does not define extra
requirements beyond the task specification.

## Timing and evaluation

The runner writes TRIAL_CLOCK.json when it starts the candidate clock. Check
the deadline periodically. Coding, reasoning, compilation, simulation, EDA
exploration and candidate retries all count toward elapsed time. Preparation,
host queueing and independent grading do not. Preserve the session; an
interruption does not silently grant a fresh task budget.

Functional points come from independent host-side checks, not self-reported
results.json. Functional correctness and synthesizability are distinct checks.
Do not claim an official benchmark score. If the task says its physical PPA
baseline is pending, report honest synthesis/EDA attempts, not fabricated PPA
points. EDA timing includes compilation and simulation; overlapping parent,
child and parallel processes are combined as busy wall-time intervals.

Infrastructure faults are investigated separately from candidate failures.
Syntax, functional or synthesis failures attributable to the delivered RTL
are candidate failures; a missing tool or evaluator defect is not. Independent
functional groups retain their earned points. Candidate-caused fatal self-test
handoff failures are recorded by distinct root cause, not by repeated retries;
where a display score is enabled, each adjudicated root cause deducts 5 points.
