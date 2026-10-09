# T08 specification/input revisions

## Public freeze reconciliation (2026-10-09)

`FREEZE.json` freezes specification/starter/judge and SRAM policy together.
Portable original qualification and three-seed reports are under
`evaluator/fixtures/t08_reference_20261008/`; historical T11 labels are retained
for provenance. `benchmark/ppa-baselines.json` is the sole scoring baseline.
Older pending statements below describe historical states, superseded by this
completed freeze. No RTL, historical budget or measured physical value changed.

## PPA policy 2.0-lambdapdk-tdp-1ghz (2026-10-08)

- Clarify the candidate-visible SRAM contract in task.md section 1.5, acceptance,
  README and generated PROMPT. Generic synthesizable arrays remain sufficient;
  SRAM integration is evaluator-side technology mapping, not a third feature ticket.
- Pin lambdapdk's dual-clock 4096x32 research macro and upstream revision.
  Retain both 4096-entry FIFO capacities and all payload/metadata; document
  synchronous-read register absorption, stall retention, CDC and collision limits.
- Keep three independent 1 GHz physical clocks and unchanged functional clocks.
  Include full macro area/power, routed parasitics and per-instance audits.
  State WC standard-cell/TT SRAM mixed-corner limitations and routing-only DRC,
  without claiming SRAM internal DRC/LVS or manufacturable silicon signoff.
- Reference qualification uses macro self-test, 111 mapped functional and 270
  concurrency runs, seeds 11/29/47 and fresh final replay. Qualification completed
  on 2026-10-08; the reference is qualified_1ghz, not pending.
- No change to functional specification/starter/judge revision, ports, repair
  ticket, VLAN feature or time budget. No old trial package or score is changed.
  New public package hashes identify these physical-policy clarifications.

## PPA policy 1.0-uniform-1ghz (2026-10-08)

- Freeze the physical target at 1 GHz / 1,000 ps for logic_clk, tx_clk and
  rx_clk. The clocks remain asynchronous; IO is timed to its owning domain.
- Preserve functional GMII 125 MHz and logic_clk 80–160 MHz acceptance,
  starter RTL, functional judge revision, time budget and functional /50.
- Reference RTL and checked power workload remain pending qualification.
  Timing violations are measured and continuously penalized under suite rules;
  choosing 1 GHz does not assert that any reference already meets this target.
- Completed trials retain original copied inputs and scores. Subsequent physical
  evaluation is recorded separately with this PPA policy identity.

## Judge 3.1-boundary-crosses (specification/starter unchanged)

- Close a confirmed first-byte-and-last-byte false pass: stale snapshot or
  predecessor header can admit an enabled one-byte body or leak VLAN metadata.
- Add nine host-only cases (28–36): bodies 1..18, policy transitions and tagged
  predecessors, MAC-error precedence/recovery, independently modeled policy
  crosses, mixed queued metadata with terminal stalls and ring reuse, and reset.
- Run 37 cases × three seeds. New cases use 80/100/160 MHz system clocks with
  independent RX phases; legacy cases retain their previous clock settings.
- Preserve section 7.3 short-input/bypass rules; do not invent a broader runt
  filter. Count synchronized MAC events in the system domain and policy events
  in RX. Register expected output before injection and verify exact payload,
  frame count, drop count and metadata; never resynchronize a missing scoreboard.
- Expand feature-negative controls from 14 to 18, including stale first/last
  state, illicit bypass runt filtering, and MAC/policy double counting. Keep
  the five transaction-negative controls and positive coalescing control.
- Keep functional /50, existing group maxima, ports, feature, starter and timing
  budget unchanged. New qualification evidence uses v31 filenames; historical
  qualification, frozen trials, original submissions and scores are not rewritten.
- Simulation timeout is a recorded non-pass; later cases still run. Neither a
  zero exit without pass witness nor a pass witness with fatal exit earns points.
- Finite checks and negative controls are not proof that all possible bugs are
  detected. Subsequent discovered counterexamples must become regression cases.

## 3.0-frame-transactions / 3.0-coalesced-commit-regression / 3.0-frame-pressure

- Replace the old easy-to-localize TX-tail faults with one coupled frame-boundary
  management regression across deferred publication, bad/overflow rollback and
  notification retention. TX padding/FCS are restored and remain regression checks.
- Isolated packet tests can pass; failures require overlapping transactions under
  retained-batch pressure, subsequent discard or sink release during an incomplete
  body. Preserve deterministic simulation and externally stated invariants.
- Add Appendix G and the frame-transaction symptom dossier. No internal register
  names, fault locations, corrected patch or reference RTL are contestant input.
- Add five independent black-box cases for TX good/bad/good retention, RX capacity
  exhaustion, speculative-prefix leakage, VLAN discard and circular address reuse.
  Adjacent RX payloads are distinct; byte counts, frame counts, order and metadata
  stability are checked. Current inventory is 28 cases × three seeds.
- Keep the same public ports, VLAN feature, memory allowance, 120 minutes,
  functional /50, group maxima, public smoke scaffolding and pending physical PPA.
- Version and refresh the starter lock and specification/isolation tests. New
  host-only repair qualification verifies complete and incomplete repairs and an
  incorrect wrap-epoch truncation; compilation failure does not count as detection.
- Do not modify completed Kimi/GLM v2 trials, their frozen inputs/judges or scores.
  Positive-control replays are separate author checks, not new candidate scores.
- Difficulty remains a hypothesis until timed trials of the new frozen input.

Author validation: three distinct already-correct submissions each pass 84/84.
The coalescing-only positive control also passes. All five transaction-negative
variants and fourteen VLAN-negative variants compile and fail all designated
seed witnesses. The full starter FIFO fails only the five added pressure cases.
Yosys hierarchy/proc/opt/check reports zero problems; 39 host unit/isolation checks
pass. Versioned evidence is saved separately from historical v2 qualification.
These replays do not start new model trials or change completed model scores.

## Judge 2.1-early-snapshot

- Close the three observed false passes: live VID/mask lookup, live untagged
  flag and live priority flag after the first decoded byte.
- Add four independent early-header update cases: VID values, valid mask,
  untagged flag and priority flag. Exercise both directions, offsets 8/10/12,
  every list slot and next-frame application without simultaneously changing enable.
- Clarify that an added feature pipeline cannot move the supplied raw-decoder
  snapshot anchor; do not impose a new system-output latency requirement.
- Keep functional maximum 50 and the snapshot group's maximum 4 unchanged.
- Correct baseline passes 23 cases x 3 seeds (69 runs), functional 50/50.
- All 14 compilable feature-negative variants trigger their designated failures
  at every seed; 25 host unit/isolation/runner/timing checks pass.
- Add a repeatable host-only mutation qualification script and evidence record
  under evaluator/fixtures/t11_mac/feature_mutation_qualification.json.
- No corrected RTL, mutation script or independent judge is copied to candidates.
- No old trial input, frozen judge, original RTL or authoritative result is changed.
- Finite negative controls do not prove detection of every possible implementation bug.

## 2.0-long-form / 2.0-multisite-tail-regression

- Replace the 222-line brief with one information-rich, self-contained specification.
- Preserve top ports, supported GMII subset, VLAN policy, storage allowance,
  120-minute time budget, functional /50 and pending physical PPA status.
- Add port datasheets, independent arithmetic vectors, concrete scenario cards,
  sampling/event traces, verification obligations and scope clarifications.
- Strengthen the TX repair ticket from an isolated short-padding CRC defect to
  a multi-site frame-tail regression. New inputs are intentionally harder.
- Retain the prewired VLAN hook and wide RX FIFO; do not add another feature.
- Refresh starter.sha256 for the intentionally revised buggy input.
- Add independent queued-frame CRC-epoch acceptance; preserve the /50 total,
  with equal subcase weighting inside the revised frame-tail repair group.
- Keep specification regression checks host-side, outside contestant packages.

No already-running trial is upgraded in place. Its copied task, RTL and frozen
judge remain its authoritative experiment input. In particular the initial
gpt-6.1-sol T08 MAC pilot retains the short specification with SHA-256
`0409bf6d4e300421078718cc066d1f72ba233f9f542ab6d01ff9d3dace6afac4`.
Label old pilot results separately; this document does not retroactively regrade them.

Author validation: 20 host-side specification/isolation/runner/timing checks pass.
The already-repaired old-pilot RTL passes all 19 revised acceptance scenarios at
three independent seeds (57 passes, functional 50/50). Applying only the old
isolated padding-CRC correction to the revised buggy fixture still fails the
one-byte-padding wire-length and queued-frame CRC-epoch obligations. Validation
does not constitute a new timed candidate trial or a routed PPA result.

## 1.0 pilot

222-line brief; prewired feature/FIFO scaffolding; isolated padding CRC defect.
The original pilot had no token cap in the final corrected execution policy.
Its initial orchestrator token stop was removed and is not a benchmark rule.
