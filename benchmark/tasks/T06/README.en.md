# T06 · AXI4-Lite to APB4 bridge

Development time: 120 minutes. Resources: 16 vCPU, 40 GiB RAM and 100 GiB writable disk.

Implement a single-clock bridge with `clk,rst_n`, a 32-bit AXI4-Lite slave and a 32-bit APB4 master. AXI ports: `AWADDR[31:0]/AWPROT[2:0]/AWVALID/AWREADY`, `WDATA[31:0]/WSTRB[3:0]/WVALID/WREADY`, `BRESP[1:0]/BVALID/BREADY`, `ARADDR[31:0]/ARPROT[2:0]/ARVALID/ARREADY`, `RDATA[31:0]/RRESP[1:0]/RVALID/RREADY`. APB ports: `PADDR[15:0],PSEL,PENABLE,PWRITE,PWDATA[31:0],PSTRB[3:0],PPROT[2:0],PRDATA[31:0],PREADY,PSLVERR`. Forward write `AWPROT` and read `ARPROT` to `PPROT`. AW and W may arrive in either order; buffer one of each to form a write. Buffer one AR independently. At most one transaction per direction may await response, and only one APB transaction runs at once. Alternate between pending reads and writes, initially preferring writes. APB requires at least one SETUP cycle, followed by ACCESS held until `PREADY=1`; hold control, address and write data during waits.

Normal state updates on rising `clk`. `rst_n` is asynchronous active-low: assertion immediately cancels buffered AXI requests, response-valid state and in-flight APB state without a clock edge. Pre-reset transactions cannot resume or generate a response. Release itself accepts or issues nothing; normal operation resumes at the next rising edge.

The valid address aperture is `0x0000_0000..0x0000_FFFF`, 4-byte aligned. Invalid requests do not access APB and return AXI `DECERR`. A valid APB `PSLVERR=1` maps to `SLVERR`, otherwise `OKAY`; erroneous reads return zero. A write with `WSTRB=0` returns OKAY without APB; otherwise `PSTRB=WSTRB`. Reads use `PSTRB=0`. Hold B/R valid, response and data until ready. Reset drops unfinished requests/responses without ghost transfers.

The AXI master obeys each channel's valid-hold rule. The APB slave eventually asserts `PREADY`, with 0–15 ACCESS cycles of delay; sample `PRDATA/PSLVERR` on the ACCESS cycle with PREADY. Use only one-deep AW, W and AR buffers and necessary response registers; no large FIFO, external protocol-conversion black box or altered bus semantics.

## Acceptance

Raw 75 points normalize to 50: F=60, writes/strobes 20, reads/data 20, OKAY/SLVERR/DECERR mapping 20; P=15, independent AW/W order and read/write fairness 5, APB wait and AXI response backpressure stability 5, reset 5. Hidden checks use independent AXI master and APB slave scoreboards with randomized delay.

| ID | Independent check |
| --- | --- |
| AC-32 | Full, partial and zero-strobe writes; record APB address, data, PSTRB and PPROT. |
| AC-33 | Valid reads with varied APB data; check AXI RDATA, protection and exactly one response. |
| AC-34 | Valid success, PSLVERR, unaligned and out-of-range map to OKAY/SLVERR/DECERR; no invalid APB side effects. |
| AC-35 | AW first, W first and simultaneous, mixed with AR; round-robin service without starvation. |
| AC-36 | APB ready delayed 0–15 cycles, arbitrary BREADY/RREADY stalls; hold all waiting payloads. |
| AC-37 | Assert reset asynchronously with isolated buffered AW, APB SETUP/ACCESS or stalled response; cancel valid state before a clock edge and never produce a ghost transaction. |

The APB model accepts only `PSEL && PENABLE && PREADY` and records the full transaction; the AXI model independently drives five channels. Mutants include assuming simultaneous AW/W, committing during SETUP, wrong PSTRB mapping, overwriting a stalled response and dropping PSLVERR.

## Delivery and evaluation

Deliver synthesizable RTL in `rtl/` and `rtl/files.f` (one source path relative to `rtl/` per line; no absolute paths, `..`, options or macros); an independently written, executable self-checking `verif/`; an executable, non-interactive `run.sh`; a generated `results.json`; and a `README.md` with reproduction commands, tests, limitations, design decisions and actual synthesis/PPA attempts. Preserve supplied license and copyright notices. `run.sh` must return nonzero on failure, require no downloads, pre-existing build or undocumented environment, and support optional `BENCH_SEED` with a documented deterministic default. The generated JSON must contain `tests` entries with unique (name, integer seed), pass status, tool versions and elapsed seconds. Do not fabricate results or mask failed tools.

Independent host-side checks determine functional points. A single missing deliverable or candidate-caused execution error deducts 5 display points; two or more missing items or two distinct errors deduct 10, capped at 10. Repeated symptoms of one root cause count once; infrastructure faults do not incur a deduction. Functional, PPA and time components remain visible and display score is floored at zero. PPA and time points require full functional credit. The public smoke test does not replace independent acceptance.

The model development clock includes reasoning, coding, compilation, simulation and EDA attempts; host preparation, queueing and independent grading are excluded. Token usage is recorded without a token budget. Physical evaluation has a separate cumulative per-seed synthesis-through-report deadline: 60 minutes for T01–T09, 120 minutes for T10; power-simulation compilation has a separate cumulative limit per seed: 20 minutes for T01–T09 and 40 minutes for T10. Timeouts retain artifacts; valid completed measurements determine the score, and no valid measurement yields zero PPA and time points. These evaluation limits do not extend the development deadline.
