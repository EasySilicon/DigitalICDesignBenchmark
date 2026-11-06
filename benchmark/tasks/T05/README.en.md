# T05 · Dual-clock asynchronous FIFO

Development time: 120 minutes. Resources: 16 vCPU, 40 GiB RAM and 100 GiB writable disk.

Implement a FIFO with `WIDTH=8/32`, `DEPTH=8/16`, where depth is a power of two. Write-domain ports: `wr_clk,wr_rst_n,wr_valid,wr_ready,wr_data[WIDTH-1:0]`; read-domain ports: `rd_clk,rd_rst_n,rd_valid,rd_ready,rd_data[WIDTH-1:0]`. Reset leaves the FIFO empty. Return accepted writes in order exactly once. There is no combinational fall-through; assert read valid only after the read domain synchronizes knowledge of a write. Full/empty deassertion may be conservative, but never accept a full write or an empty read. If a stable item is present and the read clock runs, assert `rd_valid` within 200 read clocks even if `rd_ready=0`. Hold `rd_valid/rd_data` during a read stall.

Cross write and read pointers as Gray code with at least two destination-domain register stages per bit. Multi-bit data crosses only through dual-port storage, never individual two-flop synchronizers. Assert both resets asynchronously together for at least two local clocks each; they may be released separately. Apply the same convention to resets during operation.

Write and read state update normally only on the respective rising clock edge. `wr_rst_n` and `rd_rst_n` are asynchronous active-low local resets. Assertion immediately clears local pointers, flags and synchronizer chains without waiting for the local clock; release itself does not advance state. Normal operation resumes on the next local rising edge.

Both clocks run continuously with independent, slowly varying periods and phases; the source obeys write-domain ready/valid. Storage has one write and one read port; the judge must not rely on undefined same-address read/write values. RTL simulation does not model analog metastability.

For PPA and power, use independent `wr_clk=1000 ps` and `rd_clk=1000 ps` clocks, each 1 GHz, with separate `create_clock` and asynchronous clock groups. Equal nominal periods do not make the domains synchronous. Exclude cross-domain paths from STA but meet 1000 ps for within-domain and post-synchronizer paths. Do not tie clocks together or replace CDC with synchronous behavior. Functional acceptance covers multiple unrelated ratios and phases.

Capacity is exactly `DEPTH × WIDTH` plus finite pointer and synchronizer state. No asynchronous combinational multi-bit pointer crossing is permitted. No specific FPGA RAM primitive is required.

## Acceptance

Raw 75 points normalize to 50: F=60, ordered exactly-once delivery 25, full/empty safety 15, fast/slow clock combinations 10, parameter combinations 10; P=15, two-domain reset and recovery 7, automated netlist checks for two destination synchronizer stages and local reset 8. Random tests use coprime and dynamically changing clock periods and at least 100,000 transactions per test. Gray encoding and remaining CDC requirements are verified through observable behavior; netlist checks complement simulation and are not full CDC signoff.

| ID | Independent check |
| --- | --- |
| AC-26 | Unique sequence IDs read in order exactly once; drain the queue. |
| AC-27 | Fast-write/slow-read and converse; no overwrite or empty read. After filling, hold `rd_ready=0` for 200 read clocks and require valid data eventually and stable thereafter. |
| AC-28 | Ratios 2:3, 3:5 and near 1:1, including phase offsets and slowly varying periods. |
| AC-29 | All WIDTH and DEPTH combinations. |
| AC-30 | Assert both asynchronous resets together and release independently; each domain resets before its next edge, with no stale items after reset during operation. |
| AC-31 | Check destination two-stage synchronization and local reset for all four configurations. Exercise Gray coding and other requirements through long streams, changing ratios and mutants; this is not complete CDC signoff. |

The oracle appends on write handshakes and pops on read handshakes. It does not require a fixed synchronization delay, but requires safety and eventual visibility. Static checks use elaborated connectivity; candidate `ASYNC_REG` or `cdc_sync` annotations are hints, not exemptions for missing stages, bypass or combinational crossings. Mutants include a missing stage, binary pointer crossing, incorrect full comparison and one-domain reset residue.

## Delivery and evaluation

Deliver synthesizable RTL in `rtl/` and `rtl/files.f` (one source path relative to `rtl/` per line; no absolute paths, `..`, options or macros); an independently written, executable self-checking `verif/`; an executable, non-interactive `run.sh`; a generated `results.json`; and a `README.md` with reproduction commands, tests, limitations, design decisions and actual synthesis/PPA attempts. Preserve supplied license and copyright notices. `run.sh` must return nonzero on failure, require no downloads, pre-existing build or undocumented environment, and support optional `BENCH_SEED` with a documented deterministic default. The generated JSON must contain `tests` entries with unique (name, integer seed), pass status, tool versions and elapsed seconds. Do not fabricate results or mask failed tools.

Independent host-side checks determine functional points. A single missing deliverable or candidate-caused execution error deducts 5 display points; two or more missing items or two distinct errors deduct 10, capped at 10. Repeated symptoms of one root cause count once; infrastructure faults do not incur a deduction. Functional, PPA and time components remain visible and display score is floored at zero. PPA and time points require full functional credit. The public smoke test does not replace independent acceptance.

The model development clock includes reasoning, coding, compilation, simulation and EDA attempts; host preparation, queueing and independent grading are excluded. Token usage is recorded without a token budget. Physical evaluation has a separate cumulative per-seed synthesis-through-report deadline: 60 minutes for T01–T09, 120 minutes for T10; power-simulation compilation has a separate cumulative 20-minute limit per seed. Timeouts retain artifacts; valid completed measurements determine the score, and no valid measurement yields zero PPA and time points. These evaluation limits do not extend the development deadline.
