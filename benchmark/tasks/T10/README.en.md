# T10 · Multi-precision 16×16 systolic matrix multiplication

Development time: 240 minutes. Resources: 16 vCPU, 40 GiB RAM and 100 GiB writable disk.

Deliver synthesizable `npu_systolic_matmul_16x16`, a candidate-built numerical scoreboard and verification environment, and PPA exploration records. Each command computes `C[16][16] = A[16][64] × B[64][16]` using a **16×16 output-stationary PE grid**. A and B have the same mode within a command; consecutive commands may change format without reset. There is no bias, transpose, saturation or accumulation into an old C. Do not implement RTL using `real/shortreal`, DPI, black boxes or external coprocessors.

## Stream interface and reset

Inputs: `clk,rst_n,in_valid,in_start,in_block_id[15:0],mode[3:0],a_scale[255:0],b_scale[255:0],a_data[1023:0],b_data[1023:0],out_ready`. Outputs: `in_ready,out_valid[3:0],out_block_id[63:0],out_row[15:0],out_data[4095:0]`.

Each `in_valid && in_ready` handshake simultaneously transfers the full 1024 bits of A and 1024 bits of B. A block's first accepted beat has `in_start=1`, followed by `w−1` accepted beats with it low. Latch block ID, mode and both scale vectors on the first beat; ignore those metadata on subsequent beats. A first beat must occur at a block boundary, and its ID must be unique among unfinished blocks. Modes 10–15 are not driven. The sender may pause `in_valid`; pauses do not advance the block beat number. Once the first beat is accepted, keep `in_ready=1` for every remaining beat of that block, even when `out_ready=0`. Between blocks, finite buffer credits may deassert ready.

Normal state updates on rising `clk`. `rst_n` is asynchronous active-low: assertion immediately clears state governing validity of in-flight blocks, wavefronts and outputs, and sets `out_valid=0`, without waiting for a clock. Old blocks must never reappear after reset. Release accepts no input and advances no calculation; operation resumes on the next rising edge. Wide payload registers and arrays need not reset if valid state makes their old contents unobservable.

## Continuous throughput

With `out_ready=1`, continuous legal inputs and no reset, keep `in_ready=1` continuously, **with no inter-block bubbles**. The interval between starts of same-mode blocks is exactly `w`: 4 cycles for FP4/MXFP4, 8 for INT8/FP8/MXFP8, and 16 for INT16/FP16/BF16. In a mixed stream the interval between starts equals the previous block's `w`. Start a new block while the previous block is still computing or producing output; a single-block burst does not satisfy throughput. Hidden tests use at least 64 consecutive blocks per mode, at least 256 FP4/MXFP4 blocks and long random mixed-mode streams.

Finite storage cannot accept indefinitely at full speed under indefinite output backpressure. In backpressure tests, credit-based stops are allowed **between blocks**; accepted blocks must receive all remaining input beats without stalling and all accepted results must be preserved.

## Formats and input packing

Let element width be `w`, elements per row/column per cycle `L=64/w`, and input cycles per block `64/L=w`.

| mode | Format | w | L | Encoding |
| ---: | --- | ---: | ---: | --- |
| 0 | INT8 | 8 | 8 | signed two's complement |
| 1 | INT16 | 16 | 4 | signed two's complement |
| 2 | FP16 | 16 | 4 | IEEE binary16 |
| 3 | BF16 | 16 | 4 | bfloat16, the high 16 bits of binary32 encoding |
| 4 | FP8 E4M3 | 8 | 8 | OCP OFP8 E4M3 |
| 5 | FP8 E5M2 | 8 | 8 | OCP OFP8 E5M2 |
| 6 | FP4 E2M1 | 4 | 16 | OCP MX E2M1 element, unit scale |
| 7 | MXFP8 E4M3 | 8 | 8 | OCP MX, groups of 32, E8M0 scale |
| 8 | MXFP8 E5M2 | 8 | 8 | OCP MX, groups of 32, E8M0 scale |
| 9 | MXFP4 E2M1 | 4 | 16 | OCP MX, groups of 32, E8M0 scale |

Only the listed 4/8/16-bit input formats are required; FP32 and INT32 are not input modes. Binary32 and INT64 below describe output encoding and accuracy.

The [public exact-arithmetic numerical oracle](public/matmul_oracle.py) is part of the task materials and defines the precise element decoding, scaling and output comparison; it is not synthesizable RTL and contains no hidden vectors. For floating inputs, the fields after the sign bit are exponent then mantissa. FP16 uses 5 exponent bits, 10 mantissa bits and bias 15; BF16 uses 8, 7 and 127; E4M3 uses 4, 3 and 7; E5M2 uses 5, 2 and 15; E2M1 uses 2, 1 and 1. For finite values, an exponent field of zero decodes as `sign × mantissa × 2^(1 − bias − mantissa_bits)`; other finite exponent fields decode as `sign × (2^mantissa_bits + mantissa) × 2^(exponent − bias − mantissa_bits)`. The format-specific NaN/infinity exceptions are specified below and implemented in the oracle.

For accepted beat `t=0..w−1`, element `j=0..L−1`, `k=t·L+j`, A row `r=0..15` is at `a_data[(r·L+j)·w +: w]`; B column `c=0..15` is at `b_data[(c·L+j)·w +: w]`. Each operand thus carries exactly `16·L·w=1024` bits per beat. In MX mode the A scale is `a_scale[8·(2r+floor(k/32)) +: 8]`; B uses column c analogously. Scale byte `s=0..254` means `2^(s−127)`; 255 means NaN for its entire 32-element group, including encoded zero. Non-MX modes ignore scales. There is no NVFP4 semantics.

## Four-row output

Each cycle has up to four independent row slots. Slot `s=0..3` has valid `out_valid[s]`, block ID `out_block_id[16s +: 16]`, row `out_row[4s +: 4]`, and 16 results at `out_data[1024s + 64c +: 64]`. When `out_ready=1`, all valid slots handshake atomically; when low, hold valid mask and every valid slot's ID, row and data. Rows from different blocks may interleave in the same or different cycles. Each block must emit each of its 16 rows exactly once in ascending row order, with same-cycle slots ordered by slot index.

Integer results are exact signed INT64. Floating results are IEEE binary32 in the low 32 bits with high 32 bits zero. Without output backpressure, each block's first row must appear within 64 rising edges after its last input beat and its last row within 80. Reduction and gathering may be pipelined without relaxing continuous throughput. In continuous FP4/MXFP4 streams, from the 64th cycle after the first input through the last input, every cycle must have four valid output slots; 8-bit modes require two and 16-bit modes one. Runtime reset clears in-flight blocks, wavefronts, output queues and pending rows; no old block ID or response may emerge.

A/B and output column slices may be physically distributed; logical concatenation does not require physically centralized pins or registers. Distributed result banks, local row selection and output FIFOs are allowed; no separate gather module/register is mandated. All slices must still satisfy same-cycle data, IDs, rows, atomic handshakes, stall hold and continuous throughput.

## Numerical requirements

INT8/INT16 use signed multiplication and exact 64-term sum, without INT64 overflow. Floating elements are decoded exactly, MX elements are scaled, and a 64-term dot product is formed. For finite output D and infinite-precision dot product S:

`|D−S| ≤ γ(128)·Σ|a_k b_k| + 129·2^(−149)`, where `γ(n)=n·2^(−24)/(1−n·2^(−24))`.

Test all legal MX scales including extreme scales and mixed-sign inputs. Overflow of an individual product or partial binary32 sum does not change the exact-dot-product rule; a finite final result cannot be NaN or infinity. Any NaN element, `0×∞`, or cancellation of positive and negative infinity yields any quiet NaN. An exact finite value outside the binary32 finite range, or a sum of infinities of the same sign, yields infinity with the corresponding sign. Finite in-range results must not be NaN/infinity; exact zero permits either sign. E4M3 has NaN only when maximum exponent and mantissa are all ones and has no infinity; E5M2/FP16/BF16 have NaN and infinity; E2M1 has neither. NaN payload and exception flags are not checked.

## Systolic structure and resources

Each of 256 same-type PEs holds local C accumulation state. Register-forward each beat's L A elements to the right neighbor and L B elements down. Skew row/column input wavefronts so each PE (r,c) processes A/B vectors for the same k on every valid wavefront cycle. Each PE performs L parallel multiplies and local reduction: 4, 8 or 16 lanes for 16-, 8- or 4-bit input. Pipelined local accumulator reset at block boundaries and finite result staging/row alignment may overlap wavefronts from consecutive blocks. Finite input, result and backpressure buffers are allowed. Do not globally serialize all 256 outputs, build a complete product table, use off-chip storage or specialize to test names.

The top must instantiate 16 same-type 4×4 tiles, each with 16 same-type PEs; names are unrestricted. Each PE adjacency edge must cross exactly one operand-forwarding register, located at the PE boundary or in its tile shell. Each PE has one 64-bit registered local-result output. The evaluator's Yosys netlist retains only PE boundaries and automatically checks the orthogonal 16×16 grid, per-hop registered forwarding, local feedback, combinational dependence of every lane, and contribution of all 256 results to outputs. Candidate `keep_hierarchy` on tiles or intermediate wrappers does not alter this view. Structure and timing groups cannot be manually adjudicated.

Non-PE state is capped at 306,304 bits: 262,144 bits for multiple in-flight blocks/backpressure and 44,160 bits reserved for 480 shell-level operand/token adjacency register chains. The shell allowance applies only to the two orthogonal grids' 480 hop chains and cannot be repurposed for a full product table or extra result storage. PE local accumulator/result queues count in measured area, timing and energy. No extra full product table, external storage or undeclared ports.

## Functional acceptance and scoring

The independent oracle checks all 256 numeric results per block. Every legal block, including protocol and systolic tests, must be numerically correct. Output rows/IDs and input/output throughput are checked cycle by cycle; independently constructed candidate tests do not determine the score.

Raw 75 points normalize to 50 functional points: F=50, six numerical groups of 6 each, protocol/backpressure/IDs/reset 6, numerical boundaries 8; P=25 for continuous dual-1024-bit input, steady four-slot output, true systolic structure and latency. PPA contributes up to 50 and time up to 5, under the suite ranking rules. Score numerical, protocol and boundary groups by their own case pass fractions; a throughput failure does not erase other groups. The critical MM-SYSTOLIC item requires correct values, port timing and structure; a failure zeros that item and makes PPA and time zero. Any input bubble, incorrect block-start interval, missing steady output slot or wrong row in an unbackpressured continuous stream fails this gate. Other functional points remain diagnostic.

| Group | Independent checks | Raw points |
| --- | --- | ---: |
| MM-INT | Signed INT8/INT16, extremes, sparse/dense 64-term dots; all signed INT64 outputs exactly equal. | 6 |
| MM-F16 | FP16/BF16 signs, subnormals, exponent differences and cancellation; all values meet the error bound. | 6 |
| MM-F8 | E4M3/E5M2 independent modes, boundary encodings and random matrices. | 6 |
| MM-F4 | All E2M1 encodings, four continuous dual-1024-bit beats and highest nibble. | 6 |
| MM-MX8 | Both MXFP8 encodings, independent row/column scales, k=31/32 boundary, extreme cancellation and finite/infinity boundaries. | 6 |
| MM-MX4 | Different scales on the two 32-element blocks; all 64 terms, extreme cancellation and finite-range boundaries. | 6 |
| MM-PROTO | First-beat start and ID, in-block credit, pauses, four-slot backpressure, mode changes, runtime reset, no lost/duplicate rows and held payload. | 6 |
| MM-CORNER | NaN/infinity, scale=255, 0×∞, opposite infinities, rounding boundaries and zero high 32 floating output bits. | 8 |
| MM-SYSTOLIC | Continuous 4/8/16-cycle block starts and dual inputs, 4/2/1 steady rows per cycle, ≤64/80-edge first/last row, and automatic registered 16×16 neighbor/accumulator checks. | 25 |

Backpressure matrices use distinct row groups and columns and overlap continuous FP4/MXFP4 blocks with 32-cycle output stalls, so bad staging, selection and group swapping must fail numeric checks. Test at least 256 consecutive FP4/MXFP4 blocks, at least 64 for each mode and a long random mixed-format stream.

The independent acceptance plan includes the following fixed minimum stimuli. These are evaluator checks, not a limit on the candidate's own testing:

| Stream | Stimulus and required observations |
| --- | --- |
| ST-4 | At least 256 blocks each of FP4 and MXFP4, with starts exactly 4 cycles apart; throughout the steady window, `in_ready=1` and `popcount(out_valid)=4` every cycle. |
| ST-8 | At least 64 blocks for each INT8, FP8 and MXFP8 mode, with starts 8 cycles apart; `in_ready=1` and `popcount(out_valid)=2` throughout the window. |
| ST-16 | At least 64 blocks each of INT16, FP16 and BF16, with starts 16 cycles apart; `in_ready=1` and `popcount(out_valid)=1` throughout the window. |
| ST-MIX | At least 512 fixed-seed mixed-mode blocks, including 4→16 and 16→4 transitions and MX scale changes. Each start interval equals the preceding block's `w`; rows must have the correct IDs with no loss, duplication or cross-block mixing. |
| ST-BP/RST | A 128-block INT8/MXFP4 mixed stream with periodic 32-cycle output stalls; the sender inserts one-cycle `in_valid=0` pauses inside some blocks and deliberately changes ID, mode and scales after the first beat. Reset is also applied during input, wavefront processing and pending output. Hold valid output slots under backpressure; allow credit waits only between blocks; maintain block-internal `in_ready`; use only first-beat metadata; complete every accepted block or discard it in full on reset, and recover without deadlock. |

The steady window starts at the 64th rising edge **after** the edge sampling the first beat and runs through the edge sampling the final input beat. Storing a complete block and waiting for all its outputs before accepting the next does not satisfy continuous throughput. Each failed case records the group, seed, block ID, mode, input/output cycle, row/column, expected and actual values, and port handshakes. All 256 results per block are compared.

Numerical coverage includes at least 64 blocks each for INT8/INT16, FP16/BF16 and the two FP8 formats; at least 64 FP4 blocks; at least 64 blocks for each MXFP8 format; and at least 96 MXFP4 blocks. FP4/MXFP4 exercise all 16 element encodings, including `k=0,31,32,63` and the highest input nibble. MX tests exercise scale bytes `0,126,127,128,254,255`, independent row/column scales, the `k=31/32` boundary, cancellation of individually out-of-binary32-range positive and negative terms to a finite final value, and finite/infinity boundaries. FP16/BF16 and FP8 random stimuli sample their full encoding spaces. The corner group also checks a true negative infinity combined with an overflowing positive finite partial sum.

## PPA contract: whole-design cost and PE-internal timing (v16)

Reference v16 incorporates recent frontier AI capabilities to improve PPA evaluation accuracy. Strict V1 `exact-dot-v1` numerical precision and all full-DUT functional, structural, throughput, reset and backpressure requirements remain unchanged. The evaluator discovers the 16-tile/256-PE hierarchy by instance counts, interfaces and connectivity, not fixed names.

**Area** includes all mapped peripheral standard cells plus the leaf standard-cell area of 256 routed PEs. Include actual clock and repair cells; recursively count each internal-macro instance once. Exclude filler and floorplan/macro whitespace. The periphery is not physically optimized, so this is a mapped whole-design cost estimate, not whole-chip post-route area.

**Timing** uses only register-to-register paths inside the candidate's routed PE, including paths through and within any internal macros. Read each seed's real ODB, SDC, extracted SPEF and ASAP7 SS Liberty with propagated clocks. Delay is `1 ns − PE-internal setup WNS`; setup/hold penalties use PE-internal slack. Peripheral, cross-PE and top-level I/O timing do not enter this score. This metric does not establish a 1 GHz full-array implementation.

Use physical seeds 11, 29 and 47, ASAP7 RVT/WC, 1000 ps, 24% utilization and 0.24 placement density with the existing I/O constraints. Signal routing uses M2–M7; clock trunks use M6–M7, with local M2–M5 pin access and no M8/M9 clock nets. Only the PE undergoes placement, CTS, detailed routing and extraction. Internal macros must match the same candidate, seed and complete source dependencies; unsupported hierarchy is an incomplete measurement, never omitted cost.

Each physical seed has a cumulative 7,200-second implementation limit and 40 GiB memory limit. Power-simulation compilation has a separate cumulative 2,400-second limit, including planning, code generation, C++ compilation, linking and SAIF runtime construction. A confirmed compilation timeout for **any** seed zeros PPA and time; infrastructure or compatibility errors require attribution and are not automatically candidate timeouts.

**Energy** covers the whole DUT. Execute the same fixed `T10-power-v1` 200-block full gate workload and require all 51,200 output points, protocol and 1 GHz simulation clocks to pass. Collect actual peripheral and all 256 PE activities in the same window. Whole power is peripheral power plus 256 times the equally averaged PE power plus charging of primary-input receiver capacitance, including the ideal clock. Energy is `whole power × window / 200 completed matrices`.

PE power uses its seed's extracted parasitics. Peripheral power uses ASAP7 TT models, actual gate activity and receiver pin capacitance, with **zero peripheral wire length**. Full-array CTS, actual peripheral wire capacitance, external-driver internal energy and delay-induced glitches are not measured. This is a consistent pre-layout power model, not whole-array post-route power. Match all physical signals by electrical bit identity and require at least 95% sequential annotation; reject missing activity, conflicting aliases, unknown residency or mismatched windows. Avoid double-counting child internal/leakage power; parent reports retain macro output-load switching.

Evaluate all three physical seeds. Confirmed physical timeouts retain valid completed seeds; ordinary tool errors require attribution. Aggregate median whole area, PE-internal delay and whole energy over valid completed seeds, retaining worst PE-internal setup/hold and largest DRC count. Reference qualification requires strict functional acceptance, nonnegative PE-internal setup/hold and zero PE route DRC in every seed, plus complete activity and connectivity evidence. Negative candidate slack and nonzero DRC retain the existing continuous penalties. Keep the same formula and 35-point reference target. Detailed policy: [ppa-policy-v16.json](ppa-policy-v16.json).

The current v16 PPA entry point is `evaluator/t10_hybrid_measure.py`. Records explicitly identify whole-design cost, PE-internal timing and `full_design_routed: false`. Historical single-PE tools and frozen evidence remain for replay. The qualified v16 reference is registered in `benchmark/ppa-baselines.json`, under `tasks.T10`; `score_run.py` validates this measurement scope and its per-seed accounting. Publish model results consistently after qualification; do not mix legacy single-PE and v16 whole-cost results.

### PPA and time score

Use the median area `A`, delay `D` and energy `E` of valid completed seeds, worst setup slack `S`, worst hold slack `H`, and the largest DRC count. The reference tuple uses the same whole-design area/energy scope, PE-internal timing, constraints and workload. All times in the following formula are in ns:

```text
T       = 1
R(x)    = min(2, max(0, x))
D_eff   = D + max(0, -H)
D_setup = T + max(0, -S)
P_base  = min(50, 35 × R(A_ref/A)^0.35 × R(D_ref/D_eff)^0.35 × R(E_ref/E)^0.30)
PPA     = P_base × (T/D_setup)^4 × (0.5 if any DRC, otherwise 1)
```

The reference scores 35/50. Negative hold slack increases effective delay; negative setup slack additionally incurs the fourth-power frequency penalty. Any DRC halves the score once, not once per violation. Time points require full functional credit and strictly positive PPA: `max(0, min(5, 5 × (1 − t/14400)))`, where `t` is development wall-clock seconds. Post-submission evaluation and queue time are excluded. The display score is `max(0, functional + PPA + time − delivery deduction)`, up to 105.

The qualified reference medians are **1,637,022.2795989416 µm², 0.945415 ns, and 34,842.44137964544 pJ per complete matrix block**. Its worst PE-internal setup/hold slack is **+0.052721 / +0.0718 ns**, with zero route DRC in all three seeds. Machine scoring reads the full-precision values from the authoritative baseline.

Format references: [OCP OFP8 1.0](https://www.opencompute.org/documents/ocp-8-bit-floating-point-specification-ofp8-revision-1-0-2023-06-20-pdf), [OCP MX 1.0](https://www.opencompute.org/documents/ocp-microscaling-formats-mx-v1-0-spec-final-pdf). The output-stationary array/wavefront concept is informed by [Gemmini](https://github.com/ucb-bar/gemmini); the sizes, vector PEs, interface, error bound and timing here are benchmark-specific.

## Delivery and evaluation

Deliver synthesizable RTL in `rtl/` and `rtl/files.f` (one source path relative to `rtl/` per line; no absolute paths, `..`, options or macros); an independently written, executable self-checking `verif/`; an executable, non-interactive `run.sh`; a generated `results.json`; and a `README.md` with reproduction commands, tests, limitations, design decisions and actual synthesis/PPA attempts. Preserve supplied license and copyright notices. `run.sh` must return nonzero on failure, require no downloads, pre-existing build or undocumented environment, and support optional `BENCH_SEED` with a documented deterministic default. The generated JSON must contain `tests` entries with unique (name, integer seed), pass status, tool versions and elapsed seconds. Do not fabricate results or mask failed tools.

Independent host-side checks determine functional points. A single missing deliverable or candidate-caused execution error deducts 5 display points; two or more missing items or two distinct errors deduct 10, capped at 10. Repeated symptoms of one root cause count once; infrastructure faults do not incur a deduction. Functional, PPA and time components remain visible and display score is floored at zero. PPA and time points require full functional credit. The public smoke test does not replace independent acceptance.

The model development clock includes reasoning, coding, compilation, simulation and EDA attempts; host preparation, queueing and independent grading are excluded. Token usage is recorded without a token budget. Physical evaluation has a separate cumulative per-seed synthesis-through-report deadline: 60 minutes for T01–T09, 120 minutes for T10; power-simulation compilation has a separate cumulative limit per seed: 20 minutes for T01–T09 and 40 minutes for T10. Timeouts retain artifacts; valid completed measurements determine the score, and no valid measurement yields zero PPA and time points. These evaluation limits do not extend the development deadline.

Benchmark v1 retains the strict exact-dot numerical rules above. The default seed-11 continuous suite contains 2,898 blocks, including 64 cancellation probes and 82 additional range/cancellation probes in MM-F16, MM-MX8 and MM-MX4, plus runtime reset checks. Group weights are unchanged. The separate MMA-inspired envelope is diagnostic only; relaxed official precision is reserved for benchmark v2.
