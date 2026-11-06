# T04 · Ready/valid round-robin arbiter

Development time: 90 minutes. Resources: 16 vCPU, 40 GiB RAM and 100 GiB writable disk.

Implement a per-transaction arbiter supporting `N=4/8`, `WIDTH=8/32`. Ports: `clk,rst_n`, `in_valid[N-1:0]`, `in_ready[N-1:0]`, packed `in_data[N-1:0][WIDTH-1:0]` with element `i` belonging to source `i`, and `out_valid,out_ready,out_data[WIDTH-1:0],out_id[$clog2(N)-1:0]`. Do not hold a source until it stops asserting valid. After reset search from zero; after each output handshake search circularly from the served ID plus one. The search pointer does not advance without a handshake. If `out_valid && !out_ready`, hold the selected `out_id`, data and valid until handshake; later requests must not preempt it. Only the selected input may assert `in_ready`, and only when `out_ready=1`.

State updates on rising `clk`; `rst_n` is asynchronous active-low. Assertion immediately clears the search origin and cancels a stalled selection without waiting for an edge. Release does not itself handshake or advance the pointer; normal arbitration begins on the next rising edge. Sources hold data under `valid && !ready`; the receiver may apply arbitrary backpressure. No progress is required if `out_ready` never asserts. Data and ID are unchecked while output is invalid.

Use one arbitration pointer and necessary stalled-selection state only; no private per-input FIFOs. No throughput buffer is required; in the absence of stalls, accept one request per cycle.

## Acceptance

Raw 75 points normalize to functional 50: F=60, request selection 20, round-robin order 20, data/ID integrity 20; P=15, stall stability 10, persistent requests served within at most `N` successful outputs 5. Hidden tests mix independent sources, random backpressure and sustained contention for both N values.

| ID | Independent check |
| --- | --- |
| AC-21 | Single and all request combinations: select the first valid source circularly from the pointer. |
| AC-22 | All-valid and random arrivals/departures; advance the pointer only on output handshake. |
| AC-23 | Independently incrementing source sequences; preserve ID/data, with no loss or duplication. |
| AC-24 | Stall output 1–30 cycles while requests change; hold ID/data/valid. |
| AC-25 | All sources continuously request for N=4/8; each waits at most N successful outputs. |

The oracle tracks search origin and a selected stalled request, updating only on handshake. Mutants cover fixed priority, reselection during stalls, early pointer updates and multiple asserted `in_ready` bits.

## Delivery and evaluation

Deliver synthesizable RTL in `rtl/` and `rtl/files.f` (one source path relative to `rtl/` per line; no absolute paths, `..`, options or macros); an independently written, executable self-checking `verif/`; an executable, non-interactive `run.sh`; a generated `results.json`; and a `README.md` with reproduction commands, tests, limitations, design decisions and actual synthesis/PPA attempts. Preserve supplied license and copyright notices. `run.sh` must return nonzero on failure, require no downloads, pre-existing build or undocumented environment, and support optional `BENCH_SEED` with a documented deterministic default. The generated JSON must contain `tests` entries with unique (name, integer seed), pass status, tool versions and elapsed seconds. Do not fabricate results or mask failed tools.

Independent host-side checks determine functional points. A single missing deliverable or candidate-caused execution error deducts 5 display points; two or more missing items or two distinct errors deduct 10, capped at 10. Repeated symptoms of one root cause count once; infrastructure faults do not incur a deduction. Functional, PPA and time components remain visible and display score is floored at zero. PPA and time points require full functional credit. The public smoke test does not replace independent acceptance.

The model development clock includes reasoning, coding, compilation, simulation and EDA attempts; host preparation, queueing and independent grading are excluded. Token usage is recorded without a token budget. Physical evaluation has a separate cumulative per-seed synthesis-through-report deadline: 60 minutes for T01–T09, 120 minutes for T10; power-simulation compilation has a separate cumulative 20-minute limit per seed. Timeouts retain artifacts; valid completed measurements determine the score, and no valid measurement yields zero PPA and time points. These evaluation limits do not extend the development deadline.
