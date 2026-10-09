# T08 acceptance

Revision 3.0-frame-transactions; functional maximum: 50. Independent checks observe frozen external
ports, using bit-serial wire CRC and frame/metadata scoreboards, not DUT hierarchy.

| Group | Points | Obligation |
| --- | ---: | --- |
| TX regression | 8 | Long CRC, framing, IFG, gaps, queued bad-frame rollback and circular reuse |
| RX regression | 8 | Corrupt/denied-frame rollback, retained frames under overflow, no speculative prefix, circular reuse |
| Frame-tail regression | 10 | All padding bytes, boundaries, repeated and queued CRC epochs |
| VLAN admission | 10 | Four slots/masks, untagged, priority, reserved/nested tags |
| Metadata/header edges | 6 | TCI, terminal alignment, truncation, no state leakage |
| Config snapshot | 4 | First decoded byte freezes every field; early single-field edits and next-frame effects |
| Reset/recovery | 4 | Coordinated reset, pending traffic, stale-state isolation |

Subcases within groups are equally weighted. Candidate self-reported passes cannot
award points. Infrastructure/checker defects are investigated; candidate syntax or
synthesis errors are reported as candidate failures. Feature failures do not erase
passing unchanged-regression points. Public smoke is not a complete regression.

Judge revision 3.1-boundary-crosses retains separate VID-value, valid-mask, untagged and
priority edits after the supplied raw decoder's first byte but before header
classification. Both allow-to-deny and deny-to-allow directions are tested; the
next frame must use the updated configuration. All four list slots are exercised.
These tests retain the inherited raw-decoder snapshot anchor, not the output
delivery edge or a candidate-added feature pipeline. Existing frozen trials keep
their copied judges and original reports; the current functional maximum is 50.
Five additional independent cases stress overlapping good/bad frames, exhaustion,
release while a corrupt body is incomplete, policy discard and circular reuse.
Current inventory: 37 cases × three seeds. Group maxima remain unchanged;
subcases within each group remain equally weighted. Public smoke supplies reusable
wire-model helpers but does not exercise the complete repair ticket.

Boundary regression also checks short decoded bodies, including first-and-last
on the same byte, predecessor-state isolation, bypass/enabled transitions, MAC
error precedence, mixed terminal metadata under stalls, and reset recovery.
Short bodies are diagnostic inputs defined by section 7.3, not minimum-size
standard Ethernet packets. Bypass must not acquire a new runt filter. Independent
policy expectations use actual body bytes and configuration, not DUT internals.
Additional checks vary system-clock frequency and RX phase within the stated
profile; nominal TX/RX frequency remains 125 MHz. Original frozen judges and
reports are retained. Replays with this revision are labeled separately rather
than silently replacing historical scores.

The three-seed 1 GHz reference and power workload were frozen on 2026-10-08. Scoring uses function /50 + PPA /50 + time /5; absent candidate measurements remain pending, not zero.
The PPA policy is `2.0-lambdapdk-tdp-1ghz`: logic_clk, tx_clk and rx_clk
each have a 1,000 ps period and remain in three asynchronous clock groups.
This does not change functional acceptance frequencies. A negative setup/hold
slack uses the suite's continuous timing penalty, not an automatic PPA zero.
Time bonus is not awarded from partial smoke.

Generic synthesizable FIFO arrays are accepted; manually instantiating an SRAM
macro is not a third task. Automatic evaluator-side mapping uses the pinned
`fakeram7_tdp_4096x32` dual-clock model specified in task.md section 1.5.
Both 4,096-entry capacities, all payload/metadata bits, synchronous-read cycle
alignment and backpressure retention must be preserved. Reference qualification
includes macro self-test, 111 mapped functional runs and 270 additional concurrency
runs; these author-side checks are not supplied as candidate test vectors and do
not create extra functional points. Physical qualification uses seeds 11/29/47,
routed parasitics and checked gate-level power including every placed macro.
Reference setup/hold must pass and routed DRC must be zero before freezing;
candidate timing misses retain the suite's continuous penalty after baseline freeze.
WC standard cells plus TT SRAM are explicitly mixed-corner research timing,
not full-chip WC signoff. Macro internal DRC/LVS is outside this evaluation.
Unsupported mapping and evaluator failures are diagnosed separately; no silent
memory shrink, free black box or mixed-policy reference comparison is allowed.
Passing RTL simulation does not itself establish mapped behavior or physical timing.

EDA wall time includes EDA programs, simulator binaries and C/C++ compilation.
Host sampling at 100 ms estimates the union of busy intervals: parallel/child
process times are not summed into aggregate time. Keep per-process times too.
Short processes may be missed. Judge/preparation EDA is outside contestant time.

Time cap is 7,200 seconds. Preserve session, input/package hashes, exact launch,
start/deadline/end timestamps, logs and exit status. An interrupted/no-delivery
run is evaluated as present; do not silently restart or reset its clock.
No skills, reference implementation or hidden acceptance is given to the candidate.
