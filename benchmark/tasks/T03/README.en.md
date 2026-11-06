# T03 · APB4 timer and interrupt peripheral

Development time: 90 minutes. Resources: 16 vCPU, 40 GiB RAM and 100 GiB writable disk.

Implement a 32-bit APB4 slave with `clk,rst_n`, `PSEL,PENABLE,PWRITE,PADDR[11:0],PWDATA[31:0],PSTRB[3:0],PPROT[2:0]`, and outputs `PRDATA[31:0],PREADY,PSLVERR,irq`. All legal `PPROT` values behave identically; there is no permission check. Accept only 4-byte-aligned addresses. `PREADY=1` only in access (`PSEL && PENABLE`); writes commit only on a successful rising edge in access. `PSLVERR=1` only in access for invalid or unaligned addresses. Ignore reserved-bit writes at valid addresses. Valid reads return the pre-edge register value; invalid reads return zero.

Normal state updates on rising `clk`. `rst_n` is asynchronous active-low: assertion immediately clears `CTRL`, `LOAD`, `COUNT` and `pending` and sets `irq=0`, without waiting for a clock edge. Deassertion itself neither counts nor commits an APB transaction; normal operation begins on the next rising edge.

| Offset | Register | Behavior |
| --- | --- | --- |
| `0x000` | CTRL | RW: bit 0 `enable`, bit 1 `auto_reload`, bit 2 `irq_enable`; others read zero. |
| `0x004` | LOAD | RW 32-bit reload value. |
| `0x008` | COUNT | RW 32-bit current count; software may preload it. |
| `0x00C` | STATUS | bit 0 `pending`, readable; write one to clear, zero leaves it unchanged. |

Merge partial writes by `PSTRB` byte. A zero-strobe write changes no register and does not suppress the same-edge timer event. Only `PSTRB[0] && PWDATA[0]` clears STATUS. `irq = pending && irq_enable`; reset clears all registers. On each non-reset edge, if pre-edge `enable=1` and `COUNT>0`, decrement COUNT; if `enable=1` and `COUNT=0`, set pending and either reload COUNT from LOAD when `auto_reload=1` or clear enable. On the same edge, an APB write with nonzero byte enables overrides the timer update to the **same field**; other fields still follow pre-edge state. Thus a nonzero-strobe COUNT write overrides decrement, and a STATUS clear overrides setting pending.

Use four registers and small decode/count logic; no FIFO, ROM or undeclared wait states. APB4 `PSTRB` is mandatory, not APB3.

## Acceptance

Raw 75 points normalize to functional 50: F=60, register/byte writes 20, counting/terminal/reload 20, interrupt/W1C 20; P=15, setup/access and back-to-back 10, reset/invalid addresses/simultaneous-event priority 5.

| ID | Independent check |
| --- | --- |
| AC-16 | All register offsets, reserved bits, strobes, protection values and STATUS W1C. |
| AC-17 | COUNT 3 to 0, LOAD 0/1/arbitrary, reload on/off against a cycle model. |
| AC-18 | Set, hold and clear pending; combinational irq response to irq enable. |
| AC-19 | Multi-cycle setup has no side effect; commit in access; consecutive APB transactions do not lose writes. |
| AC-20 | Asynchronous reset clears state and irq before a clock edge; unaligned/unknown addresses and same-edge terminal versus COUNT/STATUS writes. |

The oracle computes timer events from pre-edge state, then overrides the same fields with nonzero-strobe writes and STATUS W1C. Zero strobes do not suppress timer events. Mutants include setup-phase write, clearing on STATUS write-zero, ignored strobes, late terminal detection and incorrect success on invalid addresses.

## Delivery and evaluation

Deliver synthesizable RTL in `rtl/` and `rtl/files.f` (one source path relative to `rtl/` per line; no absolute paths, `..`, options or macros); an independently written, executable self-checking `verif/`; an executable, non-interactive `run.sh`; a generated `results.json`; and a `README.md` with reproduction commands, tests, limitations, design decisions and actual synthesis/PPA attempts. Preserve supplied license and copyright notices. `run.sh` must return nonzero on failure, require no downloads, pre-existing build or undocumented environment, and support optional `BENCH_SEED` with a documented deterministic default. The generated JSON must contain `tests` entries with unique (name, integer seed), pass status, tool versions and elapsed seconds. Do not fabricate results or mask failed tools.

Independent host-side checks determine functional points. A single missing deliverable or candidate-caused execution error deducts 5 display points; two or more missing items or two distinct errors deduct 10, capped at 10. Repeated symptoms of one root cause count once; infrastructure faults do not incur a deduction. Functional, PPA and time components remain visible and display score is floored at zero. PPA and time points require full functional credit. The public smoke test does not replace independent acceptance.

The model development clock includes reasoning, coding, compilation, simulation and EDA attempts; host preparation, queueing and independent grading are excluded. Token usage is recorded without a token budget. Physical evaluation has a separate cumulative per-seed synthesis-through-report deadline: 60 minutes for T01–T09, 120 minutes for T10; power-simulation compilation has a separate cumulative 40-minute limit per seed. Timeouts retain artifacts; valid completed measurements determine the score, and no valid measurement yields zero PPA and time points. These evaluation limits do not extend the development deadline.
