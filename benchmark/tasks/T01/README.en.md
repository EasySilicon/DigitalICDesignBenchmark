# T01 · SerDes RX comma aligner

Development time: 30 minutes. Resources: 16 vCPU, 40 GiB RAM and 100 GiB writable disk.

Deliver a synthesizable `serdes_rx_comma_aligner`, self-checking tests and a run script. Model a serial-link receive PCS: find comma symbols in continuous 10-bit input slices that may be misaligned, lock to symbol boundaries, reconstruct symbols, and lose and regain lock when markers are lost. DPI, file I/O, delays, black boxes and external helper modules are prohibited.

Inputs: `clk`, `rst_n`, `rx_valid`, `rx_bits[9:0]`. Outputs: `locked`, `symbol_valid`, `symbol_out[9:0]`. On a valid input, bit 0 arrives first, followed by bits 1–9; consecutive valid slices are contiguous. An invalid slice inserts no bits: preserve alignment and lock and deassert `symbol_valid`.

Sequential state updates on rising `clk` edges. `rst_n` is asynchronous active-low: assertion immediately clears lock, training, marker and reconstruction state and deasserts `locked` and `symbol_valid`, without waiting for a clock edge. Deassertion does not advance state; retraining begins on the next rising edge.

Positive comma is `10'b0011111010`, negative comma `10'b1100000101`, interpreted with `symbol[0]` earliest. Training is three consecutive commas of either polarity. After reset or loss of lock, scan every contiguous 10-bit window, including across slice boundaries; lock when three commas are exactly 10 bits apart. Assert `locked` immediately after the edge accepting the last bit of the third comma, including phase zero. Do not output training commas.

The next valid input cycle must output the first complete post-training symbol; `symbol_out[0]` is earliest. Thereafter output exactly one symbol per valid input, without loss, duplication or reordering. The stream uses 16-symbol frames: 15 non-comma payload symbols followed by a comma marker. Two consecutive expected markers that are not commas must deassert `locked` immediately after the second mismatch edge and suppress `symbol_valid` on that cycle and thereafter. Retrain on three new commas at any bit phase.

Finite shift/reassembly buffers, phase state, and training/marker counters are allowed; do not specialize to slice boundaries or fixed test contents. `symbol_out` is checked only when valid.

## Acceptance

Raw 75 points normalize to 50 functional points: F=60, comprising training/search 20, continuous symbol reconstruction and bit order 20, polarity/phases 0–9 and input gaps 20; P=15, comprising marker loss/relock 10 and asynchronous reset 5.

| ID | Independent check |
| --- | --- |
| AC-05 | All offsets 0–9 and positive/negative three-comma training across arbitrary slice boundaries; lock immediately after the final bit. |
| AC-06 | Fixed-seed multi-frame payload, comparing every symbol's bit order, boundary and integrity. |
| AC-07 | Mixed polarities, random `rx_valid` gaps, all phases and non-comma payload. |
| AC-08A | Lose lock after two missing expected markers or bit slip; retrain at any new phase. |
| AC-08B | Asynchronous reset during lock, output and retraining; clear outputs immediately and never emit pre-reset remnants. |

The independent oracle uses a bit queue, scanning window, training phase and frame markers, without DUT internals. Mutants include reversed bit order, slice-only search, off-by-one lock phase, bad cross-boundary assembly, treating invalid cycles as zeros, missing negative comma and failing to lose lock.

## Delivery and evaluation

Deliver synthesizable RTL in `rtl/` and `rtl/files.f` (one source path relative to `rtl/` per line; no absolute paths, `..`, options or macros); an independently written, executable self-checking `verif/`; an executable, non-interactive `run.sh`; a generated `results.json`; and a `README.md` with reproduction commands, tests, limitations, design decisions and actual synthesis/PPA attempts. Preserve supplied license and copyright notices. `run.sh` must return nonzero on failure, require no downloads, pre-existing build or undocumented environment, and support optional `BENCH_SEED` with a documented deterministic default. The generated JSON must contain `tests` entries with unique (name, integer seed), pass status, tool versions and elapsed seconds. Do not fabricate results or mask failed tools.

Independent host-side checks determine functional points. A single missing deliverable or candidate-caused execution error deducts 5 display points; two or more missing items or two distinct errors deduct 10, capped at 10. Repeated symptoms of one root cause count once; infrastructure faults do not incur a deduction. Functional, PPA and time components remain visible and display score is floored at zero. PPA and time points require full functional credit. The public smoke test does not replace independent acceptance.

The model development clock includes reasoning, coding, compilation, simulation and EDA attempts; host preparation, queueing and independent grading are excluded. Token usage is recorded without a token budget. Physical evaluation has a separate cumulative per-seed synthesis-through-report deadline: 60 minutes for T01–T09, 120 minutes for T10; power-simulation compilation has a separate cumulative limit per seed: 20 minutes for T01–T09 and 40 minutes for T10. Timeouts retain artifacts; valid completed measurements determine the score, and no valid measurement yields zero PPA and time points. These evaluation limits do not extend the development deadline.
