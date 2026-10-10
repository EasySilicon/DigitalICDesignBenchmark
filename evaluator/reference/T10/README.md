# T10 reference RTL development snapshots

These sources are evaluator-side reference development material. They are not
candidate inputs, and must stay outside candidate containers and workspaces.
The repository policy permits reference source publication; public availability
does not establish that a model has never seen this implementation.

- `rtl/`: existing reference snapshot, SHA-256
  `0c7646d7019e45477582faba0605f1c3ba557810a61cb617844aeeb24b632622`.
- `../T10_candidates/v123/rtl/`: previous distributed-egress candidate, SHA-256
  `6601f244693bf0a4b3c890164c34f3c64cf12f5705c2b7bc82a7a0256c4915c7`.
- [`../T10_candidates/v138_bank_alignment_clean/`](../T10_candidates/v138_bank_alignment_clean/README.md):
  latest function-qualified control candidate, SHA-256
  `2268a60e508243ac9b448457969b7f409218fa9fe8cb845339ca6f5c2b2cd70c`.
  Original 2,752-case, both mixed-backpressure seeds and supplemental corners
  passed. Its physical run was stopped during native placement checking;
  there is no v138 timing/CTS/routed PPA qualification.

The v123 source is byte-identical to the existing local 2,752-case functional
qualification run, including reset and 256-PE structure checks. That statement
is historical qualification evidence; no new simulation was run for this copy.
Its complete-DUT 1 GHz physical baseline remains unqualified. Do not use these
sources as evidence that the official T10 PPA reference has been released.

Source repository snapshot: `ic_bcmk_eval_private`, commit
`e9da70a19e662940e329205e594fa44142ab96e0` (RTL saved by `77013b2`).
Only the listed source files are copied; private repository history and hidden
acceptance programs are not imported. The relative `rtl/files.f` lists are
preserved. Existing benchmark interfaces, scoring rules and PPA baselines are
unchanged by this snapshot import.
