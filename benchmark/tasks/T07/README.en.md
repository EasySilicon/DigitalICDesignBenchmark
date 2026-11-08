# T07 · 256-byte direct-mapped write-back data cache

Development time: 120 minutes. Resources: 16 vCPU, 40 GiB RAM and 100 GiB writable disk.

Implement a 32-bit address/data, 256-byte direct-mapped cache: 16 lines, each 16 bytes/four 32-bit words; write-back, write-allocate and little-endian. Include `clk,rst_n`. CPU ports: `req_valid,req_ready,req_addr[31:0],req_write,req_wdata[31:0],req_wstrb[3:0]`, `rsp_valid,rsp_ready,rsp_rdata[31:0]`. CPU addresses are always word-aligned. Ignore write strobes on reads; writes update selected bytes and return zero response data. Accept only one CPU request until its response is complete; responses remain ordered.

Reset clears all valid/dirty bits; it is applied only when idle. The data array need not be cleared. Dirty data not written back before reset is discarded; a persistence test first evicts dirty lines and then resets. Normal control state updates on rising `clk`. `rst_n` is asynchronous active-low: assertion immediately clears all line valid/dirty bits, control and request/response-valid state, without waiting for a clock. Release itself accepts no request and issues no backend transaction; normal operation starts on the next rising edge. Data behind cleared valid bits is unobservable and need not reset.

Backend line interface: `mem_req_valid,mem_req_ready,mem_req_write,mem_req_addr[31:0],mem_req_wdata[127:0]`; `mem_rsp_valid,mem_rsp_ready,mem_rsp_rdata[127:0]`. Addresses are 16-byte aligned; writes transfer a complete line and reads refill a complete line. Each accepted request receives exactly one response; ignore data on write responses. The backend has at most one outstanding request, responds in order without errors, and may wait 0–7 cycles. Hold response valid/data until handshake. On a dirty miss, write back the victim first, then refill; on a write miss, refill before merging byte writes. Hits must not access the backend and must assert `rsp_valid` within two clocks of accepting the CPU request, independently of the backend. Each accepted CPU request produces exactly one response.

Limit resources to the 16×128-bit data array, 16 tags, valid/dirty bits and small control state. No direct backend bypass on hits, additional measured capacity or prefetcher. All state must be synthesizable.

## Acceptance

Raw 75 points normalize to 50: F=60, read/write hits 15, clean misses/refills 15, dirty eviction address/data 15, partial writes/write allocation 15; P=15, CPU/backend backpressure stability 10, reset/hit latency/no backend traffic on hits 5. An independent byte-addressable memory model checks all reads and backend transactions. Compare final external memory only after conflict evictions of dirty lines at every index and completion of all responses.

| ID | Independent check |
| --- | --- |
| AC-38 | After cold start, read/write different words of the same line; later hits do not access backend. |
| AC-39 | Cold misses and clean replacement at same index/different tag; correct refill address/data. |
| AC-40 | Dirty conflict writes back the full victim at its original address before refilling. |
| AC-41 | All WSTRB combinations, write misses and consecutive partial writes; evict all dirty lines, wait for writebacks, then compare external memory byte by byte. |
| AC-42 | Independently stall CPU and backend request/response channels; hold requests and responses while stalled. |
| AC-43 | Asynchronous reset immediately clears valid control state; all lines miss after reset and dirty data not written back is discarded. Warm hits respond within two clocks without backend traffic. |

The oracle predicts CPU-visible results and mandatory backend line transaction order using byte-addressable memory and 16 abstract lines. Mutants include omitted dirty writeback, bad tag/index, missing write allocation, reversed strobes and duplicated stalled requests.

## Delivery and evaluation

Deliver synthesizable RTL in `rtl/` and `rtl/files.f` (one source path relative to `rtl/` per line; no absolute paths, `..`, options or macros); an independently written, executable self-checking `verif/`; an executable, non-interactive `run.sh`; a generated `results.json`; and a `README.md` with reproduction commands, tests, limitations, design decisions and actual synthesis/PPA attempts. Preserve supplied license and copyright notices. `run.sh` must return nonzero on failure, require no downloads, pre-existing build or undocumented environment, and support optional `BENCH_SEED` with a documented deterministic default. The generated JSON must contain `tests` entries with unique (name, integer seed), pass status, tool versions and elapsed seconds. Do not fabricate results or mask failed tools.

Independent host-side checks determine functional points. A single missing deliverable or candidate-caused execution error deducts 5 display points; two or more missing items or two distinct errors deduct 10, capped at 10. Repeated symptoms of one root cause count once; infrastructure faults do not incur a deduction. Functional, PPA and time components remain visible and display score is floored at zero. PPA and time points require full functional credit. The public smoke test does not replace independent acceptance.

The model development clock includes reasoning, coding, compilation, simulation and EDA attempts; host preparation, queueing and independent grading are excluded. Token usage is recorded without a token budget. Physical evaluation has a separate cumulative per-seed synthesis-through-report deadline: 60 minutes for T01–T09, 120 minutes for T10; power-simulation compilation has a separate cumulative limit per seed: 20 minutes for T01–T09 and 40 minutes for T10. Timeouts retain artifacts; valid completed measurements determine the score, and no valid measurement yields zero PPA and time points. These evaluation limits do not extend the development deadline.
