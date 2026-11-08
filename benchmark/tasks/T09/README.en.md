# T09 · RV32I five-stage CPU

Development time: 120 minutes. Resources: 16 vCPU, 40 GiB RAM and 100 GiB writable disk. Specification: `port_timing_v1`; scoring: `t09_group_cycles10_v1`.

## Architecture and instruction behavior

Implement a single-issue, in-order, 32-bit RV32I processor with distinct IF/ID, ID/EX, EX/MEM and MEM/WB pipeline registers. A single-instruction multicycle controller is not a five-stage implementation. Support all RV32I integer arithmetic, logic, shifts, branches, jumps, byte/halfword/word loads and stores, LUI/AUIPC, FENCE, ECALL and EBREAK, plus all six Zicsr operations and MRET. No M/A/F/D/C extensions, MMU, cache or interrupts; M-mode only. Check instruction and data alignment; misaligned accesses are unsupported. `x0` always reads zero. JALR clears target bit 0. FENCE has no extra visible effect on this in-order, one-outstanding data interface. FENCE.I is unsupported and raises an illegal-instruction exception.

## Clock, reset and buses

Normal CPU state updates at rising `clk`. `rst_n` is asynchronous active-low: assertion immediately flushes the pipeline and outstanding/valid bus state and enters reset PC `0x8000_0000` without waiting for a clock. Deassertion itself fetches and retires nothing and advances no state; operation begins on the next rising edge. Memories reset with the CPU and clear outstanding transactions.

Instruction ports are `imem_valid,imem_addr[31:0],imem_rdata[31:0]`. Valid/address are sampled at a rising edge; corresponding data arrives in the next cycle, at most one request each cycle, in strict order and without fetch errors. Data without a valid request in the preceding cycle is unchecked. Wrong-path responses may return but must be discarded.

Data ports are `dmem_req_valid,dmem_req_ready,dmem_req_write,dmem_req_addr[31:0],dmem_req_wdata[31:0],dmem_req_wstrb[3:0]` and `dmem_rsp_valid,dmem_rsp_ready,dmem_rsp_rdata[31:0],dmem_rsp_err`. Each accepted request receives one held response in 1–8 cycles; at most one request is outstanding. Bus addresses are aligned 32-bit word addresses. For byte/halfword accesses use the low address bits to select byte lanes, write masks and data placement; reads return a complete word, from which the CPU extracts and sign/zero extends. Report misalignment before issuing a request. An error response means the write had **no memory side effect**.

Instruction and data spaces refer to an external 256 KiB image. MMIO `0x8003_F000` is the testbench's `tohost`: writing 1 means PASS, any other nonzero value FAIL. The CPU must not hard-code this address or test-specific behavior. A program either writes a result in finite steps or is judged by its retirement trace; timeout fails.

## Exceptions and CSRs

Illegal instruction, instruction-address misalignment, load/store misalignment, ECALL, EBREAK and data-access errors are precise: the faulting instruction writes neither registers nor memory and all younger instructions are flushed. `mcause`: instruction-address misaligned 0, illegal instruction 2, EBREAK 3, load misaligned 4, load access fault 5, store misaligned 6, store access fault 7, M-mode ECALL 11. Check alignment before issuing a data request, so misalignment takes priority over access fault. `mepc` records the faulting PC; `mtval` records the fault address for address faults, the 32-bit instruction for illegal instructions and zero for ECALL/EBREAK.

Only `mstatus(0x300)` bits MIE 3, MPIE 7 and MPP 12:11 are visible; MPP is always `2'b11`, reset `0x0000_1800`. On trap, `MPIE←MIE, MIE←0, MPP←3`; on MRET, `MIE←MPIE, MPIE←1, MPP←3, PC←mepc`. `mtvec(0x305)` is direct mode only, writes force low two bits to zero, reset `0x8000_0000`. `mscratch(0x340),mepc(0x341),mcause(0x342),mtval(0x343)` are RW and reset to zero; mepc's low two bits are forced zero. `misa(0x301)=0x4000_0100` and `mhartid(0xF14)=0` are read-only. Unknown CSR addresses and writes to read-only CSRs raise illegal instruction. CSRRS/CSRRC with rs1=x0, or immediate source zero, do not write. Other mstatus bits read zero and ignore writes. The locked RISC-V ISA/privileged specification and ACT4 configuration apply.

## Retirement observation

For each normally retired instruction, pulse `commit_valid` for one cycle and output `commit_pc[31:0],commit_insn[31:0],commit_rd[4:0],commit_wdata[31:0],commit_mem_addr[31:0],commit_mem_wstrb[3:0],commit_mem_wdata[31:0]`. Use `commit_rd=0` when no register is written and `commit_mem_wstrb=0` when there is no store. Exceptions produce separate `trap_valid,trap_pc[31:0],trap_cause[31:0],trap_tval[31:0]` and are not normal retirement. These RTL ports are observed by the evaluator; the candidate need not generate trace files or write a trace collector. Observation ports must not feed execution.

## Pipeline and timing

The register file is limited to 32×32 bits; instruction and data memory are external. For 64 consecutive independent ADDI instructions, with no waits, each fetch sampled at edge `n` must produce the corresponding `commit_valid/commit_pc` at the stable observation point after edge `n+4`: four complete cycles over five edges. Fetches and commits must each occur consecutively at one per cycle. Do not fake stages by delaying commit; register writeback and stores must agree with the retirement trace. This latency gate is not a PPA ranking metric.

Provide necessary forwarding, load-use stalls, branch/jump flushes and data-wait stalls. No branch predictor, cache, multiplier/divider or operating system. Ordinary dependent ALU operations, including adjacent, one-gap, dual-source and x0 cases, must introduce no forwarding bubbles compared with an otherwise identical independent program. A load-use dependency adds at most one cycle relative to an independent control with the same bus timing; external ready/response waits are separate.

The `port_timing_v1` checker uses only fixed ports, not DUT hierarchy or internal stall signals. Its 22 checks comprise consecutive ADDI, six paired ALU/x0 programs, and five load-dependency types under three bus conditions `(response_cycles,ready_delay)=(1,0),(8,0),(1,3)`. Ready delay starts when the request first becomes valid; response delay starts at request handshake and the response is held until accepted. Reset CPU and memory between runs.

Paired dependent/independent programs differ only in the consumer source register and have identical instruction counts, bus timing and control flow. Compare both producer-to-consumer retirement-cycle gap and total retirement span: load-use differences must each be ≤1, ALU differences each ≤0. Faster implementations pass. Additionally, for no-control-flow programs, `last_commit−first_commit+1 ≤ N + M×(response_cycles+ready_delay) + H`, where N is retired instruction count, M is serial memory accesses and H is permitted load-use bubbles (0 for independent, 1 for one dependency). Internal memory preparation or fetch recovery is not external wait. Check actual commit PC/instruction/writeback/stores, real transactions and final memory against an independent oracle; wrong-path data requests and unfinished transactions fail. Branch/JAL/JALR penalties are reported without an added limit; load-to-branch uses only the dependency increment, not the no-control-flow span formula.

## Independent acceptance

Raw 75 points normalize by `50/75` to 50. F=48: integer/control flow 20, memory/byte lanes/sign extension 12, CSR/exceptions/MRET 8, locked ACT4 subset 8. P=27: data-dependency functional results 4.8, randomized data waits/backpressure 4, flush/precise commit/fetch-to-retire latency 3.2, independent cycle checks 15. The original functional groups contribute 40 normalized points; the 22-cycle group contributes 10: 22/22 gives 10, 11–21 gives 5, 0–10 gives 0. A safety violation zeros its associated item. Do not deduct 5 per failing case or double-count cycle failures in the original hazard/latency groups. PPA and time points require full 50/50 functionality.

### Architectural and directed tests

The `CPU-ACT` group uses the locked ACT4 RV32I/Zicsr configuration with `include_priv_tests=false`; all 45 applicable ELFs must pass and are compared against locked Sail-generated commit/store oracles. M-mode CSR, exceptions and MRET are tested separately. ACT4 subset success is not RISC-V certification. The CPU must not recognize test names, PC values or tohost to bypass execution; memory boundary faults are modeled by data response errors.

At least 54 independently reviewable directed templates with value variants cover:

| Group | Minimum templates | Coverage |
| --- | ---: | --- |
| CPU-DIR-INT | 12 | RV32I ALU/shifts, signed/unsigned comparisons, LUI/AUIPC, six branches taken/not taken, JAL/JALR bit 0, ignored x0 writes. |
| CPU-DIR-MEM | 10 | LB/LBU/LH/LHU/LW extension, SB/SH/SW lanes, same-address reads/writes, word and highest address boundaries, waits, FENCE ordering. |
| CPU-DIR-HAZ | 12 | EX→EX and MEM/WB→EX forwarding, dual-source same register, load-use, load→branch/store, repeated writes to one rd, x0 not forwarded. |
| CPU-DIR-TRAP | 12 | Branch/JAL/JALR wrong paths, branch adjacent to load-use, illegal instruction, ECALL/EBREAK, misaligned/access faults, MRET, no younger store. |
| CPU-DIR-CSR | 8 | All six CSR instructions, rd=x0/rs1=x0, illegal writes to read-only CSR, mstatus trap entry/exit, mepc/mtval/mcause and direct mtvec. |

Tests check memory side effects, final register values and individual retirement, not just tohost. The task card explicitly requires illegal instruction for writes to misa and FENCE.I; the locked Sail configuration ignores the former and executes the latter. Independent task-specific oracles, not Sail's behavior on these boundaries, judge these cases.

### Random differential and pipeline tests

`CPU-DIFF` comprises separate `CPU-DIFF-INT`, `CPU-DIFF-MEM`, `CPU-DIFF-TRAP` categories. Generate at least 100 fixed-seed bounded programs, each retiring at least 1,000 instructions, at least 100,000 in total. Control addresses, initialized registers, loop bounds, CSR masks and exception modes explicitly; execute the same ELF in a configured Sail model. Compare in retirement order PC, instruction, destination register/value, store address/strobes/data and trap tuple, without requiring equal cycles. Check no duplicated/skipped/wrong-path retirements, exactly one response per accepted memory request and equal final memory. On first mismatch record seed, ELF hash, 20 surrounding commits on either side and bus transactions. Candidate-selected seeds are not permitted.

`CPU-PIPE-CYCLES` is the independent 22-case cycle-scoring group described above. `CPU-PIPE-LAT` checks every PC in the 64-instruction n+4 stream; sample fetch before edge n and commit after nonblocking assignments settle. `CPU-PIPE-HAZ` checks dependency functional results and cycle budgets. `CPU-PIPE-MEM` varies response/ready waits, requires held requests and no replay. `CPU-PIPE-FLUSH` uses different store markers on correct and wrong paths. `CPU-PIPE-RESET` injects reset in idle, ALU streams, load waits and near branches with bus state cleared, then checks restart at reset PC and no old commits. Retirement stores must agree with actual bus writes and leave no outstanding writes at completion.

Use at least 20 random wait seeds; per-program simulation timeout is 100 times Sail retirement steps plus 10,000 cycles unless a long-program limit was fixed in the manifest beforehand. Timeout is failure, not a specific diagnosis. Fixed observed latency alone cannot mathematically prove internal pipeline stages: automated grading checks observable latency, hazards, flushes, waits and commit traces; the four pipeline-register groups remain a design requirement, not an additional manually assigned structural score.

## Evaluation resources

The public smoke test is `public/tb.sv`; independently scored ELF programs and hidden reference data are excluded from the candidate workspace. The qualification uses 45 locked ACT4 ELFs, 108 directed-program variants, 100 fixed-seed long programs and independent wait/reset tests. Qualification of the reference, mutant detection, locked ISA/configuration artifacts and matching DUT/Sail regression precede publication; these checks do not imply full RISC-V certification or production signoff.

## Delivery and evaluation

Deliver synthesizable RTL in `rtl/` and `rtl/files.f` (one source path relative to `rtl/` per line; no absolute paths, `..`, options or macros); an independently written, executable self-checking `verif/`; an executable, non-interactive `run.sh`; a generated `results.json`; and a `README.md` with reproduction commands, tests, limitations, design decisions and actual synthesis/PPA attempts. Preserve supplied license and copyright notices. `run.sh` must return nonzero on failure, require no downloads, pre-existing build or undocumented environment, and support optional `BENCH_SEED` with a documented deterministic default. The generated JSON must contain `tests` entries with unique (name, integer seed), pass status, tool versions and elapsed seconds. Do not fabricate results or mask failed tools.

Independent host-side checks determine functional points. A single missing deliverable or candidate-caused execution error deducts 5 display points; two or more missing items or two distinct errors deduct 10, capped at 10. Repeated symptoms of one root cause count once; infrastructure faults do not incur a deduction. Functional, PPA and time components remain visible and display score is floored at zero. PPA and time points require full functional credit. The public smoke test does not replace independent acceptance.

The model development clock includes reasoning, coding, compilation, simulation and EDA attempts; host preparation, queueing and independent grading are excluded. Token usage is recorded without a token budget. Physical evaluation has a separate cumulative per-seed synthesis-through-report deadline: 60 minutes for T01–T09, 120 minutes for T10; power-simulation compilation has a separate cumulative limit per seed: 20 minutes for T01–T09 and 40 minutes for T10. Timeouts retain artifacts; valid completed measurements determine the score, and no valid measurement yields zero PPA and time points. These evaluation limits do not extend the development deadline.
