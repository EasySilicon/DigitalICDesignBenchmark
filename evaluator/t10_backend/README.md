# T10 backend development archive

This directory preserves the committed PE, 4x4-tile and complete 16x16-DUT
backend development sources from `ic_bcmk_eval_private` commit
`e9da70a19e662940e329205e594fa44142ab96e0`. It includes 218 physical-flow files;
`SNAPSHOT.json` records their source paths, destinations, SHA-256 and executable
modes, together with the four associated reference/candidate RTL files.

Reference RTL snapshots are in [../reference/T10/](../reference/T10/README.md),
with the latest distributed-egress candidate in
`../reference/T10_candidates/v123/rtl/`. Source bytes are preserved. Only files
were imported: this public branch has the public repository's ancestry, not
the private repository's history or its hidden acceptance programs.

## Publication and candidate isolation

The public benchmark permits evaluator and reference sources to be published,
while candidate workspaces contain selected task materials and public smoke
checks only. These backend sources and reference implementations are evaluator
material. They must stay outside candidate containers and accessible mounts.
`benchmark/prepare_trial.py` does not copy this directory or the reference RTL.
A separate directory or instructions alone do not enforce isolation when the
candidate has full filesystem access. Public reference implementations may
also be present in future model training data; describe results accordingly.

## Reproduction limits

This is a source archive, not a portable, standalone flow release. The original
scripts contain absolute paths to the author's private evaluator checkout,
OpenROAD/Yosys installations, ORFS checkout and scratch storage. They also refer
to generated macro LEF/Liberty/ODB, workload and qualification artifacts that
are not included here. Some functional qualification helpers import the
external `runner_t10_stream` module. Those dependencies must be supplied and
paths configured before executing a flow. Copying these sources does not
make the old commands work from this directory.

The archive contains experimental alternatives and diagnostic-only tools,
including a hash-guarded OpenROAD GCell probe generator. No generated tool
executables, PDK databases, hidden tests or raw physical build products are
redistributed by this import. The source manifests identify the preserved
versions; experiment notes do not define the official grading configuration.

## PPA status

The complete-DUT 1 GHz PPA reference is not qualified. The latest v127
placement-parasitic, ideal-clock estimate reports setup WNS -14106.48 ps
and hold WNS -363.59 ps; it is not post-route or CTS signoff evidence.
See [the top-level path analysis](physical/T10_TOP_TIMING_CLOSURE_20261006.md).
Earlier PE/tile successes and alternative libraries, timing budgets or
placement probes are historical experiments, not interchangeable baselines.

This import changes no task specification, score formula, frozen toolchain,
PPA parameter or `benchmark/ppa-baselines.json` entry. Formal scoring uses
only the benchmark's published evaluator configuration and qualified reference.
