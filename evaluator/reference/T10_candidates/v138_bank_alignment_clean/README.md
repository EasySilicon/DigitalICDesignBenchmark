# T10 v138: credit-pipelined control candidate

This is the latest author-side, function-qualified T10 development candidate.
It derives from v123; it is not a released 1 GHz PPA baseline.
Keep evaluator reference sources outside candidate workspaces.

## Architecture

- Atomic four-row reservations in local eight-row capture FIFOs.
- Delayed last-column result-bank capture, with forwarding only for the exact
  pending FIFO address; data, row identity and block identity remain aligned.
- Seven-stage capture acknowledgment, six forward transport stages and seven
  return stages, with fifteen reserved receiver credits.
- Thirteen receiver array rows plus two registered head-cache rows, including
  empty-array bypass. External atomic acceptance terminates at the interface.
- Generate-time separation of active metadata/data write branches.

The twenty-two PE, tile, arithmetic and other unchanged module bodies remain
byte-identical to v123. See [rtl_delta.json](rtl_delta.json) for module hashes.

## Qualification

The exact source passed the original independent 2,752-case regression
(seed 20260925), mixed-backpressure seeds 20261010 and 20261011, supplemental
reservation/proxy/cache/credit/source-hold corners, and full-occupancy resets.
These are historical runs of this byte-identical source, not new tests run
during this branch update.

The unchanged gates include 256 PEs, one operand register per neighboring hop,
fourteen zero-bubble phases, and 64/80-cycle first/last-row limits. Non-PE state
is 306,058 bits, below the 306,304-bit limit. The compact evidence record is
[qualification.json](qualification.json).

RTL SHA-256: `2268a60e508243ac9b448457969b7f409218fa9fe8cb845339ca6f5c2b2cd70c`.

## Physical status

Seed-11 synthesis and diagnostic placement were generated. The full-top native
placement check stalled under memory pressure, and the run was stopped at the
user's request. No v138 placement STA, CTS or routed PPA result was produced.
Inherited v54 global-route macro views were diagnostic inputs only.
Timing results from older candidates do not qualify v138.

The legacy `reference/T10/rtl` snapshot, official baseline, scoring rules and
model results are unchanged.

## Select this source

From the repository root:

```bash
export T10_REFERENCE_RTL="$PWD/evaluator/reference/T10_candidates/v138_bank_alignment_clean/rtl/npu_systolic_matmul_16x16.sv"
source evaluator/t10_backend/env.sh
```

The source list `rtl/files.f` is relative to its own `rtl` directory.
Historical backend experiments retain their hash guards and require matching
inputs; selecting this source does not make old checkpoints reusable.
