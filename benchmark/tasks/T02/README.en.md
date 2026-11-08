# T02 · Parameterized synchronous FIFO

Development time: 60 minutes. Resources: 16 vCPU, 40 GiB RAM and 100 GiB writable disk.

Implement a single-clock FIFO with `WIDTH` and `DEPTH`: `clk,rst_n`, input `in_valid,in_data[WIDTH-1:0]`, output `in_ready`, output `out_valid,out_data[WIDTH-1:0]`, and input `out_ready`. Support `DEPTH=3,8,16` and `WIDTH=8,32`. Capacity is exactly `DEPTH`; output accepted writes in order. Reset leaves it empty. An empty FIFO does not fall through: even with input and `out_ready`, `out_valid=0` that cycle and the new item is available no earlier than the next. A full FIFO may accept a write when a read succeeds on the same edge. `out_data` is unchecked when invalid.

Sequential state updates on rising `clk`. `rst_n` is asynchronous active-low: assertion immediately empties the FIFO and deasserts `out_valid` without a clock edge. Deassertion itself accepts no transaction and advances no pointer; normal operation begins on the next rising edge. Reset may be asserted during operation. The input obeys ready/valid hold; writes and reads are accepted on `in_valid && in_ready` and `out_valid && out_ready` respectively. Hold output data while stalled.

Use at most `DEPTH × WIDTH` storage plus finite pointer/count control. Register arrays and inferred RAM are allowed; simulation queues and latches are prohibited.

## Acceptance

Raw 75 points normalize to functional 50: F=60, order/integrity 25, empty/full and capacity 15, simultaneous operations 10, all six parameter combinations 10; P=15, reset 5, output stall 5, non-power-of-two wrap 5. Random tests include at least 100,000 accepted transactions against an independent software queue.

| ID | Independent check |
| --- | --- |
| AC-09 | Write-only, read-only, alternating and random accepted transactions agree with the queue head. |
| AC-10 | Fill exactly to capacity; no extra write without a pop and no output when empty. |
| AC-11 | At full, simultaneous read/write removes the old head and stores the new tail without changing occupancy. |
| AC-12 | All `WIDTH=8/32`, `DEPTH=3/8/16` combinations. |
| AC-13 | Assert reset asynchronously at nonempty, full and random occupancy; empty and `out_valid=0` before the next edge, with no stale data after release. |
| AC-14 | Hold valid and data through 1–30 stalled cycles. |
| AC-15 | Repeated `DEPTH=3` wrap preserves ordering and capacity. |

The `deque` oracle checks/pops the old head before appending a simultaneously accepted write. Mutants cover rejecting full replacement, undersized count, power-of-two wrap and overwriting stalled output.

## Delivery and evaluation

Deliver synthesizable RTL in `rtl/` and `rtl/files.f` (one source path relative to `rtl/` per line; no absolute paths, `..`, options or macros); an independently written, executable self-checking `verif/`; an executable, non-interactive `run.sh`; a generated `results.json`; and a `README.md` with reproduction commands, tests, limitations, design decisions and actual synthesis/PPA attempts. Preserve supplied license and copyright notices. `run.sh` must return nonzero on failure, require no downloads, pre-existing build or undocumented environment, and support optional `BENCH_SEED` with a documented deterministic default. The generated JSON must contain `tests` entries with unique (name, integer seed), pass status, tool versions and elapsed seconds. Do not fabricate results or mask failed tools.

Independent host-side checks determine functional points. A single missing deliverable or candidate-caused execution error deducts 5 display points; two or more missing items or two distinct errors deduct 10, capped at 10. Repeated symptoms of one root cause count once; infrastructure faults do not incur a deduction. Functional, PPA and time components remain visible and display score is floored at zero. PPA and time points require full functional credit. The public smoke test does not replace independent acceptance.

The model development clock includes reasoning, coding, compilation, simulation and EDA attempts; host preparation, queueing and independent grading are excluded. Token usage is recorded without a token budget. Physical evaluation has a separate cumulative per-seed synthesis-through-report deadline: 60 minutes for T01–T09, 120 minutes for T10; power-simulation compilation has a separate cumulative limit per seed: 20 minutes for T01–T09 and 40 minutes for T10. Timeouts retain artifacts; valid completed measurements determine the score, and no valid measurement yields zero PPA and time points. These evaluation limits do not extend the development deadline.
