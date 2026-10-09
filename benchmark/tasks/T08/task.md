# T08 · 1GbE MAC Post-silicon Repair and VLAN Admission

Specification revision: 3.0-frame-transactions.
Status: frozen task in the v0.3 T01–T10 suite.
Language: the English requirements below are normative.
Budget: 120 minutes of candidate execution time.
Token usage: measured, with no token hard limit.
Functional maximum: 50 points, independently measured.
Physical PPA: frozen three-seed 1 GHz reference and workload (2026-10-08).
Physical clock policy: 2.0-lambdapdk-tdp-1ghz (three independent 1 GHz clocks).
The evaluator may automatically map eligible synchronous FIFO arrays to the
pinned 4096x32 dual-clock FakeRAM research model without editing submitted RTL.
Functional behavior and FIFO capacities must remain unchanged; macro area and
activity-based power are included. SRAM timing uses its published TT model,
with WC standard cells, not a full-chip worst-corner silicon signoff claim.
PPA target: 1 GHz (1,000 ps) on logic_clk, tx_clk and rx_clk, with asynchronous clock groups.
This physical timing target does not replace the functional GMII clock profile below.

## 1. Reading contract and mission

### 1.1 What this task asks you to do

This is maintenance of supplied RTL, not a from-scratch Ethernet MAC.
The supplied fixture is an existing full-duplex 1GbE MAC with asynchronous frame FIFOs.
The system interface carries one octet per AXI-Stream transfer.
The physical-side interface is eight-bit GMII at nominally 125 MHz.
Your work has two deliverables: one repair ticket and one feature ticket.
Repair ticket: restore TX/RX frame-atomic retention after a boundary-management regression.
Feature ticket: implement single-C-tag RX admission with frame-atomic terminal metadata.
A repair ticket is not a promise that exactly one source statement is wrong.
The newer fixture replaces the old TX-tail defect with a coupled transaction regression.
The feature is bounded; it is not a VLAN-aware bridge or a complete NIC.
Preserve working TX, RX, FIFO, reset and clock-domain-crossing behavior.
Retain the existing MAC/frame-FIFO architecture.
You may refactor control logic and add synthesizable modules.
Do not replace the fixture with a special-case responder.
Do not download an alternative MAC or an external answer.
Do not inspect other submissions, hidden tests or reference RTL.
Retain upstream copyright notices and LICENSE.upstream.

### 1.2 Self-contained means sufficient to implement

All required byte ordering, CRC conventions and policy decisions appear here.
No external IEEE document is needed to decide an acceptance result.
IEEE names explain the interface family; they do not import unspecified features.
An external standard does not override this task's explicit supported subset.
A diagram, example or glossary entry cannot override an explicit requirement.
Examples use concrete input values to explain requirements, not fixed answer ROMs.
The same rules apply to arbitrary legal addresses, payload bytes and traffic order.
The scenario catalogue is public specification data, not a hidden-test disclosure.
It is not exhaustive; passing only the listed examples is insufficient.
The source is implementation context, not a substitute for the behavior contract.
Where broken starter behavior contradicts this document, repair the behavior.
Where legacy parameter options exceed this document, preserve them when practical.
You need not implement or verify excluded parameter modes.

### 1.3 Requirement language

MUST and MUST NOT identify obligations.
MAY identifies a permitted implementation choice.
SHOULD identifies recommended verification or reporting practice.
An obligation qualified by valid applies only when that valid signal is asserted.
An accepted beat means valid and ready are both high at the sampling edge.
An emitted wire octet means the relevant GMII enable is high at its clock edge.
Invalid-cycle payload values are not an additional correctness obligation.
Unknown stimulus values are not used to define a legal frame.
A checker must not interpret an unqualified output as a meaningful result.
Every comparison in this task is byte-exact unless explicitly stated otherwise.

### 1.4 Revision and experiment boundaries

This revision strengthens the frame-transaction repair ticket and its stress coverage.
It does not broaden GMII, add another protocol feature or change the top ports.
It does not change the 120-minute budget or functional scoring maximum.
Previously launched trials retain their original copied inputs and frozen judges.
Do not compare repair difficulty across revisions as if inputs were identical.
Record the specification revision and starter checksum with every new trial.
A result from the old short specification remains an old-revision pilot result.
Do not silently overwrite it with a result attributed to this revision.
No official routed PPA points exist until a T08 reference is frozen.
Synthesis cell counts are evidence, not routed PPA scores.
The reference and power workload are frozen under the PPA target below.
For PPA, all three clock periods are 1,000 ps; equal frequency does not make them synchronous.
IO timing is constrained to each port's owning domain; asynchronous resets are false paths.
Functional acceptance still uses 125 MHz TX/RX and 80–160 MHz logic_clk.
Already completed trials retain their input files; later PPA evaluation records this policy separately.

### 1.5 FIFO memory implementation and physical evaluation

The physical policy is 2.0-lambdapdk-tdp-1ghz.
The repair and VLAN feature tickets are unchanged by this physical policy.
SRAM integration is not an additional feature ticket or a required hand-written macro wrapper.
You may retain generic synthesizable FIFO memory arrays in your submitted RTL.
The evaluator uses automatic Yosys memory mapping, not edits to a candidate's source.
Eligible synchronous memories use the pinned fakeram7_tdp_4096x32 model from lambdapdk.
The upstream model revision is 15c783cc336ca002d2c31adfd2c2b14b363c66cf.
Each physical macro has 4,096 words of 32 bits and two independent positive-edge clocks.
The evaluation mapping uses one port for writing and the other for reading.
Each TX/RX FIFO must retain its 4,096-entry capacity and all required data and metadata bits.
Physical width padding is charged as macro area and power; unused bits are not free.
Do not shrink a FIFO, remove metadata or add a second frame buffer to obtain a mapping.
Do not introduce an unresolved black box or simulator-only substitute into rtl/files.f.
No external download is needed to use generic arrays or complete the functional task.

The macro's read is synchronous, not a combinational first-word-fall-through read.
Its registered read output can absorb a compatible existing RTL read register.
Mapping must not blindly add another read cycle or misalign valid, last, user and metadata.
The model does not promise output retention when its chip enable is low.
The evaluation mapping keeps the read port enabled and implements required stall retention externally.
Invalid or unwritten memory values must not be consumed as valid frame data.
Cross-port same-address read/write behavior is not a valid-data forwarding mechanism.
Full/empty protection, tentative-frame rollback and publication must remain correct across clocks.
An implementation may adjust pipeline latency only within the existing external behavior contract.
It must preserve throughput, backpressure stability, frame atomicity and the raw-decoder snapshot anchor.
There is still no fixed system-to-wire or receive-to-delivery startup latency requirement.

Functional acceptance retains nominal 125 MHz GMII and the stated 80–160 MHz system-clock profiles.
Physical evaluation constrains logic_clk, tx_clk and rx_clk to independent 1,000 ps periods.
Successful functional simulation or SRAM inference does not prove 1 GHz setup/hold closure.
The evaluator checks mapped behavior before qualifying a reference for physical comparison.
It measures routed timing with parasitics and includes the complete placed macro footprint.
Power uses a checked gate-level activity workload with both standard-cell and SRAM Liberty models.
Standard-cell timing uses WC; SRAM timing uses its published TT 0.7 V/25 C research model.
Power uses TT models; no SRAM SS/FF characterization is invented.
This is mixed-corner predictive research PPA, not a manufacturable SRAM or silicon signoff claim.
DRC covers routed interconnect and macro pin access, not internal SRAM layout DRC or full LVS.
Reference and candidate physical comparisons must use the same model and policy version.
An unsupported mapping is reported with its cause, not silently substituted into a different baseline.
Mapping infrastructure errors do not turn otherwise passing functional tests into functional failures.
The reference completed functional qualification and all three routed/power seeds on 2026-10-08.
No official PPA score may be claimed before that reference is frozen.
Historical trial inputs and functional scores are not rewritten by this policy update.

## 2. Supported Ethernet profile

### 2.1 Wire-side scope

GMII transports one complete octet on each enabled clock cycle.
TX and RX have separate clocks.
Each nominal GMII clock period is 8 ns.
The task is full duplex; TX and RX may be active simultaneously.
There is no collision input and no collision arbitration.
There is no receive-ready signal at the GMII boundary.
There is no source-synchronous nibble mode at the fixed top.
There is no PHY negotiation sequence to implement.
There is no host driver or software register bus to implement.
The system supplies policy inputs directly in the receive clock domain.
Optional upstream functions remain disabled by the fixed wrapper.
Do not infer required PAUSE handling from familiar EtherType values.
Do not infer destination filtering from familiar multicast address values.

### 2.2 Supported fields

The preamble is seven octets of hexadecimal 55.
The start-frame delimiter is one octet of hexadecimal D5.
The body begins with six destination-address octets.
Six source-address octets follow.
The next two octets are the outer type/length field.
An outer field of 8100 identifies the single C-tag format in this task.
A C-tag adds two TCI octets and two inner type octets.
The body includes all application bytes and any MAC padding.
The FCS consists of four CRC octets after the body.
The FCS is not part of the system-side body stream.
Preamble and SFD are not part of the system-side body stream.
All octet offsets in this document are relative to the first body octet.

### 2.3 Deliberate exclusions

No PHY, PCS or PMA implementation is required.
No autonegotiation or link-training state machine is required.
No MDIO register bank or transaction engine is required.
No RGMII double-data-rate interface is required.
No half-duplex backoff or collision behavior is required.
No PAUSE, PFC or traffic-class scheduler is required.
No timestamp insertion or timestamp sideband is required.
No destination-address table or multicast filter is required.
No IPv4, IPv6, TCP or UDP checksum computation is required.
No VLAN insertion, stripping or rewriting is required.
No S-tag or QinQ admission support is required.
No jumbo-frame promise is added.
No multi-queue routing or host DMA feature is added.
No IEEE certification claim is made by passing this task.

### 2.4 Size terminology

L is the submitted TX body length in octets.
W is the transmitted body length after padding.
For a good TX frame, W equals max(L, 60).
The DA-through-FCS length is W + 4.
The enabled GMII burst length is W + 12.
The extra twelve octets are seven preamble, one SFD and four FCS.
The IFG is idle time and is not included in any of those lengths.
Supported good TX inputs have 14 <= L <= 1518.
Supported ordinary RX bodies have 60 <= L <= 1518.
The RX body length includes an existing VLAN tag.
Short RX headers are exercised to define admission parsing and recovery.
They do not create a new general-purpose MAC runt policy.
A tagged body of 1518 produces 1522 DA-through-FCS octets.
The task's body bounds are explicit, not a request for full IEEE length policing.
Do not reject an otherwise allowed body solely by inventing a stricter type-specific maximum.

## 3. Architecture and ownership

### 3.1 Supplied blocks

mac_1g_repair is the frozen public top.
eth_mac_1g_fifo connects system streams to asynchronous frame FIFOs.
eth_mac_1g connects the byte transmit and receive engines.
axis_gmii_tx serializes a committed TX frame onto GMII.
axis_gmii_rx removes wire overhead and reports receive errors.
axis_async_fifo stores bytes and frame commit boundaries across clocks.
axis_async_fifo_adapter adapts the existing FIFO interfaces.
axis_adapter is retained as part of the supplied generic library.
lfsr supplies the existing hardware CRC primitive.
rx_vlan_admission is a deliberately unimplemented feature stub.
The supplied source exceeds 3,000 lines before your changes.
Most of that source is working infrastructure, not missing logic to rewrite.

### 3.2 Fixed wrapper settings

The system data width is eight bits.
There is no external tkeep port; each accepted beat is one whole byte.
TX and RX are configured as frame FIFOs.
TX and RX FIFO depths are each 4,096 byte entries.
TX padding is enabled.
The configured minimum DA-through-FCS frame length is 64 bytes.
The configured TX IFG is twelve TX clock cycles.
TX and RX datapaths are enabled.
The fixed wrapper selects GMII, not MII.
The fixed wrapper enables both GMII clocks continuously.
Oversize-frame and bad-frame dropping remain enabled.
TX does not silently drop a legal frame merely because a ready handshake stalls.
RX can drop a whole incoming frame when the receive queue fills.

### 3.3 Feature integration provided by the fixture

The stub is placed after raw RX decoding and before the RX frame FIFO.
The surrounding RX metadata path has already been widened to eighteen bits.
This wiring is scaffolding, not an implementation of admission.
The feature must supply the decision, snapshot, metadata and event behavior.
A compact feature implementation can be legitimate.
There is no required minimum number of newly written RTL lines.
The complexity being tested is correct integration and verification, not source padding.
Do not mistake a wide FIFO for a separate metadata queue.
Do not bypass the frame FIFO to emit a header early.
Do not clear the raw MAC bad indication to admit a corrupt frame.

### 3.4 Frame ownership stages

A physical RX frame is a GMII enabled burst with its wire overhead.
A decoded RX frame is the body stream produced by the MAC.
A tentative RX frame is data written before its commit decision.
A committed RX frame is an accepted good frame visible to the FIFO read side.
A delivered RX frame is a committed frame fully accepted by the system consumer.
These stages are not interchangeable.
FIFO commit precedes completion of system-side delivery.
A frame can be policy-admitted but later discarded for lack of FIFO capacity.
A policy-denied frame never becomes a committed good frame.
A bad-FCS frame never becomes a committed good frame.
Reset can discard both tentative and committed-but-undelivered state.
No pre-reset fragment may be completed using post-reset bytes.

## 4. Clock and reset contract

### 4.1 Clocks

logic_clk owns the system AXI-Stream interfaces.
tx_clk owns GMII TX outputs.
rx_clk owns GMII RX inputs and direct configuration inputs.
tx_clk and rx_clk are nominally 125 MHz.
Acceptance may vary logic_clk from 80 to 160 MHz.
Clock phases are independent.
Equal nominal frequencies do not imply coincident edges.
A correct design does not require an integer clock ratio.
A correct design does not use the order of testbench always blocks as a CDC mechanism.
Do not create a newly gated or generated clock for the feature.
Use the receive clock for admission state.
Carry terminal metadata through the same CDC path as its frame data.

### 4.2 Reset stimulus

logic_rst, tx_rst and rx_rst are active high.
The environment asserts all three as a coordinated reset.
Assertion lasts at least eight cycles of the slowest active clock.
Each reset is released on its own domain's falling edge.
Release order may differ between runs.
Correctness must not depend on simultaneous release.
The environment leaves a settling interval before starting new traffic.
Independently resetting only one domain is outside the contract.
Do not add a promise about single-domain reset recovery to pass this task.
Configuration pins are environment-owned inputs and are not reset by the DUT.

### 4.3 Reset consequences

Reset defines a new traffic epoch.
All queued pre-reset frames are discarded.
All partial pre-reset frames are discarded.
All saved policy snapshots are discarded.
All partial TCI or header assembly is discarded.
All pending policy rejection state is discarded.
No pre-reset terminal metadata may attach to a new frame.
No pre-reset drop pulse may leak after reset settling.
The environment may assert reset while RX output is stalled.
The environment may assert reset during TX padding or FCS.
An interrupted wire burst is not judged as a completed good packet.
Once the coordinated reset settles, subsequent legal frames must work normally.
A monitor must also clear its pre-reset expected frame queue.
Comparing post-reset bytes against a stale monitor queue is a checker error.

### 4.4 CDC constraints

Do not sample asynchronous TCI bits directly at logic_clk.
Do not synchronize each TCI bit independently and assume a coherent word.
Do not use a free-running RX register as the metadata for a delayed frame.
Do not add an unsynchronized RX pulse as a logic-domain status.
The rx_vlan_drop port is deliberately an RX-domain event.
Existing FIFO status ports retain their existing CDC implementation.
The metadata path must preserve byte ordering and frame association.
A pipeline stage may change latency but must not change throughput or semantics.
Use the supplied proven FIFO machinery unless a necessary change is independently verified.

## 5. System stream protocol

### 5.1 Transfer and stability

A system-side byte transfers on a rising logic_clk edge with valid=1 and ready=1.
No transfer occurs when either condition is false.
tlast marks the last transferred byte of a body.
The producer may pause between successive accepted bytes.
A pause does not terminate a frame.
A stalled producer keeps valid asserted until the beat is accepted or reset intervenes.
Data, last and user remain stable throughout that stall.
For RX output, tagged and TCI are part of the stalled payload bundle.
ready need not remain constant across a frame.
A monitor must index bytes by accepted transfers, not by clock cycles.
A last value on an invalid cycle is not a frame boundary.

### 5.2 TX input

TX bytes begin at the destination address.
TX bytes end at the submitted body end.
The input contains neither preamble nor SFD.
The input contains no externally appended FCS.
If short, the input need not include padding.
The MAC adds required zero padding on the wire.
A good frame has tuser=0 on its accepted terminal beat.
tuser=1 on that beat requests bad-frame discard.
Terminal bad-frame marking is the frame-FIFO contract.
Nonterminal user values are not a new per-byte corruption protocol.
Legal input gaps must not become wire gaps.
The TX frame FIFO provides store-and-forward isolation from those input gaps.

### 5.3 RX output

RX bytes contain the decoded body including received padding.
RX bytes contain an admitted VLAN tag unchanged.
RX bytes contain neither preamble nor SFD nor FCS.
A delivered good frame has rx_axis_tuser=0.
A rejected or corrupt frame emits no accepted output bytes.
A rejected or corrupt frame must not appear as a valid output prefix either.
A valid nonterminal beat has tagged=0 and TCI=0.
An admitted single-C-tag terminal beat has tagged=1 and its original TCI.
An untagged terminal beat has tagged=0 and TCI=0.
A bypass terminal beat has tagged=0 and TCI=0 even if its bytes contain a tag.
Metadata is qualified by valid and last.
Invalid-cycle metadata values are not separately constrained.
A terminal beat stalled by ready=0 must retain its complete metadata.

## 6. Frame-integrity repair ticket

### 6.1 Post-silicon symptom dossier

A boundary-management change left a coupled multi-site regression.
Isolated valid TX/RX frames and ordinary padding/CRC tests can pass.
Field captures show a queued good frame disappearing after a later bad frame.
Another capture releases RX backpressure while a following corrupt body is arriving.
That capture can expose data before the following frame's integrity is known.
FIFO-pressure recovery can affect good frames retained before the overflowed frame.
Long-running traffic and circular-address reuse must not change these obligations.
These symptoms require overlapping transactions, not just an unusual packet value.
An isolated smoke pass therefore cannot close this repair ticket.
The starter is intentionally defective; it is not the normative oracle.
No source location, change list or corrected patch is supplied to the candidate.
Do not assume all symptoms arise from one assignment.
Restore atomic retention, publication and discard for both TX and RX.
Preserve padding/FCS, IFG, terminal metadata, reset and cross-clock behavior.
A diagnostic report should distinguish body length, body content and FCS failures.
Do not report every mismatch merely as an opaque CRC failure.

### 6.2 Required TX wire sequence

For each accepted good body, emit seven 55 octets.
Emit D5 immediately after the seventh preamble octet.
Emit every submitted body octet once, in order.
If L < 60, emit exactly 60-L zero octets.
If L >= 60, emit no padding octets.
Emit four FCS octets immediately after the last body or padding octet.
Keep gmii_tx_en high throughout this sequence.
Keep gmii_tx_er low for every octet of a valid transmission.
Do not insert a bubble between payload and padding.
Do not insert a bubble between padding and FCS.
Do not duplicate the last payload byte as the first pad byte.
Do not omit the last payload byte when entering a tail phase.
Do not count FCS octets as padding.
Do not count preamble or SFD toward the minimum body size.
Each frame uses a fresh CRC initial state.
A preceding frame's final CRC state must not seed the next frame.

### 6.3 Length boundaries

At L=14, exactly 46 zero padding bytes are required.
At L=42, exactly 18 zero padding bytes are required.
At L=58, exactly two zero padding bytes are required.
At L=59, exactly one zero padding byte is required.
At L=60, no padding is required.
At L=61, all 61 submitted bytes are body bytes.
The same formulas apply to every intermediate supported length.
Length accounting uses emitted body bytes, not remaining FCS bytes.
Payload values do not change the required padding count.
An all-zero final payload byte is still a payload byte.
A nonzero final payload byte must never be overwritten to make CRC tests pass.
Repeated frames of the same length must produce the same wire content for identical input.
Different preceding frames must not alter that result.

### 6.4 CRC arithmetic

The reflected CRC polynomial is hexadecimal EDB88320.
The initial 32-bit state for each body is FFFFFFFF.
Process body octets in their wire order.
Within each octet, process bit zero first.
For each bit, compute the XOR of the current CRC bit zero and that data bit.
Shift the state right by one.
If the XOR was one, XOR EDB88320 into the shifted state.
Keep the state to 32 bits.
Process every padding zero using exactly the same operation.
Do not process preamble or SFD.
Do not process IFG idle cycles.
Complement all 32 state bits after the last body/pad octet.
The complemented result is the numeric FCS.
Transmit FCS bits 7:0 as the first FCS octet.
Transmit FCS bits 15:8 as the second FCS octet.
Transmit FCS bits 23:16 as the third FCS octet.
Transmit FCS bits 31:24 as the fourth FCS octet.
Do not byte-swap the input addresses to match a software CRC API.
Do not append zeros after computing the FCS.

### 6.5 Neutral CRC pseudocode

This pseudocode describes a mathematical oracle, not a hardware patch.

```text
state = 0xFFFFFFFF
for octet in transmitted_body_including_padding:
    for bit_index in 0..7:
        feedback = (state & 1) XOR ((octet >> bit_index) & 1)
        state = state >> 1
        if feedback == 1:
            state = state XOR 0xEDB88320
        state = state & 0xFFFFFFFF
fcs = state XOR 0xFFFFFFFF
wire_fcs = [(fcs >> (8*k)) & 0xFF for k in 0..3]
```

The oracle must be independent of the DUT lfsr module.
A bit-serial implementation is sufficient for verification.
A software library may be cross-checked against these conventions.
A library's empty-input value does not by itself prove its byte-order convention.
Verification should compare each captured body byte before checking FCS.
Otherwise a mutually compensating body and CRC error can hide a defect.

### 6.6 IFG and queue interaction

After the fourth FCS octet, gmii_tx_en becomes zero.
At least twelve TX clock sampling edges have tx_en=0 before the next preamble.
gmii_tx_er is zero during ordinary idle.
Idle gmii_txd values are not meaningful packet data.
Do not require a fixed system-to-wire start latency.
Asynchronous FIFO synchronization changes that latency.
Preserve the supplied nominal queued-frame throughput.
Do not serialize traffic unnecessarily in a new host-side controller.
A legal complete queued frame must eventually transmit.
A TX frame marked bad is dropped atomically before wire transmission.
The following queued good frame must not inherit the bad frame's state.
A coordinated reset starts a new TX CRC epoch.
No token-budget mechanism is part of the TX RTL contract.

### 6.7 Frame transactions under overlapping traffic

Bytes accepted for an incomplete frame are not a deliverable committed frame.
A terminal bad indication discards only the frame to which it belongs.
Discarding a later frame MUST NOT revoke an earlier complete good frame.
An overflowed RX frame MUST NOT overwrite or revoke previously retained good frames.
An earlier frame's visibility may be delayed by synchronization or backpressure.
Such delay does not turn that complete good frame into disposable speculative data.
After a stalled sink resumes, every retained good frame MUST eventually appear once.
No prefix of a terminally bad, policy-denied or overflowed frame may escape.
No duplicate, splice or stale terminal metadata is permitted after discard recovery.
These rules apply before, across and after circular storage address reuse.
You may redesign boundary management but MUST retain safe clock-domain transfer.
Do not bypass frame atomicity by turning frame FIFOs into cut-through byte FIFOs.
Do not assume identical clocks, coincident edges or an idle cycle between AXI frames.
No requirement depends on a particular internal pointer or register name.
Appendix G defines additional observable stress obligations without prescribing a patch.

## 7. RX decoding and protection

### 7.1 Ordinary wire stimulus

The environment supplies seven 55 octets followed by D5.
It then supplies the body octets and four correct FCS octets.
gmii_rx_dv remains high over the entire burst.
gmii_rx_er is zero for an ordinary good frame.
The environment supplies at least twelve idle RX cycles between frames.
Payload and addresses may contain arbitrary byte values.
Data patterns resembling preamble inside a body are ordinary data.
Data patterns resembling a VLAN tag inside payload are ordinary data.
The task does not require synchronization on arbitrary malformed preambles.
It does not require link recovery after an unmodelled PHY fault.

### 7.2 Corruption

Bad FCS causes whole-frame discard.
A GMII receive error in the body causes whole-frame discard.
Existing error status behavior is preserved.
A GMII error may terminate the decoded raw stream early.
Do not assume a bad raw stream always ends at the physical body's final octet.
Use decoded valid-last to track the internal frame boundary.
A policy decision must never clear a raw MAC bad flag.
A corrupt frame followed by a good frame must not splice into that good frame.
An error does not authorize dropping all subsequent frames.
Do not require a bad-FCS event for every body-error abort.
MAC bad-frame and bad-FCS events are related but not identical.
Policy event precedence uses the raw terminal bad flag, not a delayed logic-domain event.

### 7.3 Short headers

Enabled admission rejects a decoded body shorter than fourteen bytes.
A complete non-C-tag header ends at offset thirteen.
An enabled C-tag requires a body of at least eighteen bytes.
A body ending at offset seventeen has a complete C-tag header.
The last sampled header byte participates in classification.
A body ending at offset sixteen does not have a complete inner type.
A missing header byte is not implicitly zero.
A bypass frame does not acquire these new policy rejections.
Do not add a broader runt filter under the name of VLAN admission.
Existing MAC/FCS protection still applies to short decoded input.

### 7.4 Capacity and ordering

GMII reception cannot be paused by the logic consumer.
The configured receive frame FIFO has finite capacity.
When capacity is sufficient, each admitted good frame is delivered once.
Admitted good frames retain arrival order.
When capacity is exhausted, complete incoming frames may be discarded.
Overflow must not corrupt earlier committed frames.
Overflow must not expose a partial current frame.
Denied frames must not leave uncommitted fragments ahead of a later frame.
The queue must drain after the consumer becomes ready.
No exact number of buffered maximum-size packets is promised by this specification.
RAM capacity, in-flight pipeline bytes and synchronization latency differ.
A capacity test must not invent an exact threshold from a simple 4096/L division.
No new full-packet RAM may be added to avoid the frame-atomic design problem.

## 8. Configuration snapshots

### 8.1 Inputs and packing

cfg_vlan_enable selects enabled policy versus bypass.
cfg_accept_untagged permits enabled untagged frames.
cfg_accept_priority permits enabled single-C-tag VID zero.
cfg_vlan_valid contains four independent validity bits.
cfg_vlan_vids contains four twelve-bit VID entries.
Entry zero occupies bits 11:0.
Entry one occupies bits 23:12.
Entry two occupies bits 35:24.
Entry three occupies bits 47:36.
Validity bit i qualifies entry i.
All configuration inputs are synchronous to rx_clk.
There is no bus transaction, address decode or software-visible commit register.
The environment drives stable values with normal setup and hold.

### 8.2 Snapshot boundary

Snapshot every configuration field together at the first decoded valid body byte.
This is not the SFD edge.
This is not necessarily the first physical GMII body-byte edge.
This is not the first delivered logic-domain output beat.
The snapshot anchor is the supplied raw MAC boundary; new pipelines must not move it.
The snapshot remains authoritative until that decoded frame terminates or reset aborts it.
A decoded-stream bubble does not resnapshot configuration.
A mid-frame policy change affects only the next frame.
A mid-frame list change affects only the next frame.
A mid-frame enable change affects only the next frame.
A change meeting setup and hold on the first-byte edge is visible in that snapshot.
A change after that edge is not retroactive.
Snapshot contents do not depend on whether the frame is later admitted.
A denied or corrupt frame still ends the snapshot's lifetime.

### 8.3 Configuration match rules

The list match is the OR of all qualified equalities.
There is no first-match ordering or priority among slots.
Duplicate valid entries do not create duplicate delivery.
Duplicate valid entries do not create multiple drop pulses.
An invalid matching entry cannot admit a frame.
An invalid entry's value has no effect on matching.
A valid reserved VID entry does not override the reserved-VID rejection.
A valid VID-zero entry does not override the priority flag.
The untagged flag is independent of ordinary VID-list membership.
The priority flag is independent of ordinary VID-list membership.

## 9. Exact VLAN admission decision

### 9.1 Header positions and byte order

Offsets 0 through 5 are DA.
Offsets 6 through 11 are SA.
Offset 12 is the high octet of the outer field.
Offset 13 is the low octet of the outer field.
For a C-tag, offset 14 is the high octet of TCI.
For a C-tag, offset 15 is the low octet of TCI.
Offset 16 is the high octet of the inner type.
Offset 17 is the low octet of the inner type.
The numeric value 8100 appears as bytes 81 then 00.
The numeric value A007 appears as bytes A0 then 07.
Do not apply the FCS little-octet serialization rule to header fields.
Do not search for 8100 at any offset other than the defined outer field.

### 9.2 Ordered enabled policy

First reject if the decoded body has fewer than fourteen bytes.
Then examine the complete outer field.
Outer 88A8 is unsupported S-tag and is rejected.
Outer fields other than 8100 and 88A8 are untagged.
Such untagged frames are admitted exactly when accept_untagged is one.
This includes IEEE type/length values with a numerical length interpretation.
No payload-length validation is added for those values.
Outer 8100 requires at least eighteen decoded body bytes.
An incomplete C-tag is rejected even if its observed TCI happens to match.
Inner 8100 is a nested C-tag and is rejected.
Inner 88A8 is a nested S-tag and is rejected.
Other inner values pass the tag-structure check.
Extract VID from the low twelve TCI bits.
VID 4095 is always rejected.
VID zero is admitted exactly when accept_priority is one.
VIDs one through 4094 are admitted exactly when the qualified list matches.
Later allow conditions cannot override an earlier structural rejection.
No additional address, PCP, DEI or IP policy is introduced.

### 9.3 TCI decomposition

PCP is TCI bits 15:13.
DEI is TCI bit 12.
VID is TCI bits 11:0.
PCP ranges from zero through seven.
DEI is zero or one.
Ordinary VID matching ignores PCP and DEI.
Priority VID-zero admission also ignores PCP and DEI.
Reserved VID rejection also ignores PCP and DEI.
For an admitted C-tag, terminal TCI preserves every original bit.
Do not reconstruct TCI from the matched list entry.
Do not zero PCP or DEI when forwarding terminal metadata.
Do not use tagged=1 for an admitted untagged frame.

### 9.4 Bypass

A snapshot with enable=0 bypasses all admission policy checks.
It does not bypass raw MAC error detection.
It does not bypass FIFO capacity and oversize protection.
It preserves all body bytes, including tags.
It reports tagged=0 and TCI=0.
It emits no VLAN-drop event.
A bypass S-tag is not rejected by this feature.
A bypass nested tag is not rejected by this feature.
A mid-frame change to enable=1 cannot convert that frame into an enabled frame.
The next decoded frame takes its own snapshot.

## 10. Atomic drop and metadata

### 10.1 Internal user bundle

The RX feature/FIFO user bundle has eighteen bits.
Bit 17 is terminal tagged.
Bits 16:1 are terminal TCI.
Bit zero is the bad-frame marker.
The symbolic packing is {tagged, TCI[15:0], bad}.
Only bit zero is the bad-frame mask.
A nonzero TCI is not a bad-frame condition.
An asserted tagged bit is not a bad-frame condition.
Admitted valid nonterminal bytes have no terminal metadata.
A terminal policy rejection sets bad in addition to any raw MAC bad flag.
The exact internal module hierarchy is not a functional acceptance condition.
The frozen top names and widths are a condition.

### 10.2 Rollback semantics

Raw RX bytes may be written tentatively before the policy is fully known.
The existing frame FIFO commits only a good terminal frame.
Mark a rejected frame bad at its terminal boundary.
The FIFO then discards all of that tentative frame.
Do not suppress only the terminal byte.
Do not suppress all raw valid bytes while leaving stale FIFO frame state.
Do not output a denied header and retract it later.
Do not leak a denied prefix during system-side ready=1.
Do not merge two tentative frames into one committed frame.
A bounded pipeline may delay the terminal marker with its data.
It must preserve all boundaries and sustain one decoded byte per RX cycle.
There is no raw ready input that can pause the MAC.

### 10.3 VLAN-drop event

rx_vlan_drop is sampled in the receive clock domain.
For a policy-rejected frame with raw terminal bad=0, emit exactly one cycle high.
The event may align with the terminal byte.
Alternatively it may have a fixed delay of at most two RX cycles.
Do not emit a pulse when the first forbidden field is merely observed.
A later raw MAC error can still take precedence.
A policy-denied and MAC-bad frame emits no VLAN-drop event.
A bad-FCS and policy-denied frame emits no VLAN-drop event.
A FIFO overflow alone need not emit a VLAN event.
A policy event is not a proof that the FIFO had free space.
Admitted frames emit no VLAN event.
Bypass frames emit no VLAN event.
Idle cycles emit no VLAN event.
Reset-aborted frames emit no VLAN event after reset settling.
Continuous high over two cycles counts as two samples and violates the one-cycle rule.

### 10.4 Metadata and backpressure

Metadata crosses with the terminal byte's frame commit.
A later RX frame cannot replace metadata on an earlier stalled output frame.
TCI must not be read from the live configuration list on delivery.
TCI must not be read from a global most-recent-frame register on delivery.
A terminal byte presented with ready=0 remains terminal.
Its data, user, tagged and TCI remain stable.
When ready becomes one, that same byte and metadata transfer once.
The next output frame begins with zero terminal metadata.
Reset cancels a stalled terminal beat and its old metadata.
No metadata-only output transaction exists.

## 11. Resource and implementation constraints

### 11.1 Storage

Reuse the existing 4,096-byte TX and RX frame FIFOs.
Do not add another full-frame buffer inside the new feature.
At most 32 additional data bytes may be retained for header or pipeline state.
Configuration snapshot bits are allowed separately.
Finite byte counters and control-state bits are allowed separately.
A full input packet stored in a register array is still a full-frame buffer.
An answer table indexed by test identifiers is forbidden.
A header counter must stop or saturate after the useful header range.
It must not wrap during a long payload and reinterpret later bytes as a new header.
Metadata widening of the existing FIFO is not a new second packet RAM.
Document added storage and the reasoning for its size.
Do not claim a payload RAM is merely configuration storage.

### 11.2 Synthesis

All active design RTL must be synthesizable.
rtl/files.f must contain complete relative source paths.
Verilator must elaborate the fixed top.
Yosys hierarchy -check and check must succeed.
No functional delays are permitted in design RTL.
No DPI or host calls are permitted in design RTL.
No simulator-only functional bypass is permitted.
No undefined-valued outputs may replace required behavior.
Legacy upstream initial parameter checks are intentionally supplied.
New feature state requires explicit reset.
Do not remove required source files to hide unresolved instances.
Do not count a testbench-only implementation as an RTL feature.
Do not mutate public tests to make the DUT appear correct.

### 11.3 Change discipline

There is no brittle maximum changed-line count.
There is no minimum changed-line count either.
A compact correct implementation is acceptable.
A distributed correction is acceptable.
A broad rewrite must still preserve architecture and all obligations.
Name and explain changes in the delivery README.
Separate a necessary fix from an optional cleanup in that explanation.
Avoid destabilizing unrelated generic parameter modes without reason.
Do not submit a working simulation with a known synthesis failure as complete.
Do not silently relax the protocol to match broken starter behavior.

## 12. Delivery and evidence

### 12.1 Required artefacts

Deliver edited rtl/ and its complete relative files.f.
Deliver an independent self-checking verification environment under verif/.
Deliver an executable root run.sh.
Deliver a root results.json generated from real verification outcomes.
Deliver a README with repair cause, feature design and reproduction instructions.
Retain LICENSE.upstream and upstream notices.
The final message is not a replacement for these files.
A self-reported success without runnable evidence is not complete delivery.
A simulator crash must propagate a failing exit status.
A failed check must not be converted to success by unconditional shell exit zero.

### 12.2 Reproduction

run.sh must run from the submission root.
It must not require undocumented custom environment variables.
It must not require a caller-supplied object-cache path.
It must not require network access.
It must not rely on pre-existing build outputs.
It may create its own build directory.
It may accept optional BENCH_SEED with a documented default.
It must report the effective seed.
It must regenerate results from the tools it actually ran.
It should record tool versions and commands.
Keep verification input generation independent of the DUT's internal state names.
Reference bytes and policy decisions must not come from the implementation itself.

### 12.3 Verification minimum

Check TX lengths fourteen, forty-two, fifty-eight, fifty-nine, sixty and sixty-one.
Check long TX frames.
Check queued frames with different preceding bodies.
Check AXI input gaps and stalls.
Check TX bad-frame discard followed by a good frame.
Check RX correct FCS, corrupt FCS and GMII body errors.
Check all four VID-list positions and validity masks.
Check untagged, priority and reserved VID behavior.
Check PCP/DEI preservation.
Check nested and truncated header rejection.
Check a terminal header byte's participation.
Check mid-frame configuration updates.
Check bypass transitions on successive frames.
Check RX backpressure including a stalled tagged terminal beat.
Check independent clock ratios and phases.
Check coordinated reset with pending traffic.
Check mixed admitted, denied and corrupt frame recovery.
A public smoke pass does not imply full acceptance.

### 12.4 Measurement

Record actual candidate elapsed time.
Record EDA wall time separately from candidate elapsed time.
EDA includes EDA commands, compilation and simulation executables.
Aggregate EDA time is the union of busy intervals, not the sum of parallel CPU time.
Keep per-process measurements when available.
A sampled measurement can miss very short commands; disclose that limitation.
Judge execution after submission is not candidate EDA time.
Preparation and reference execution are not candidate EDA time.
Token counts may be recorded but must not stop execution.
Do not invent a T08 physical score from generic cell counts.
Do not invent a time bonus from a partial public smoke run.
See acceptance.md for the functional-group point allocation.

## 13. How to use the detailed appendices

Appendix A specifies every frozen port.
Appendix B gives byte layouts and exact CRC/TCI arithmetic examples.
Appendix C gives concrete policy and traffic scenarios with expected results.
Appendix D gives event-order traces and interface corner cases.
Appendix E provides verification obligation cards.
Appendix F defines terms and explicitly unconstrained behavior.
Read the relevant appendix when implementing or testing a boundary case.
The appendices explain the same bounded feature, not additional product requirements.
No appendix supplies a corrected TX RTL implementation.
No appendix introduces an external standards dependency.


## Appendix A. Frozen port reference

There are 39 ports; names and widths MUST remain unchanged.
Clock-domain labels describe sampling ownership, not package pin locations.
Status ports keep the supplied synchronization behavior; no arbitrary fixed CDC latency is promised.

### A.1. logic_clk
Port ID: T08-PORT-01.
Direction: input.
Width: 1 bit.
Owning domain: system.
Qualifier: continuous clock.
Sampling rule: rising edge.
Meaning: owns both external AXI-Stream interfaces.
Temporal rule: clock continues during reset and stalls.
Reset/epoch rule: no DUT-driven reset value.
Related interface: logic_rst.
Concrete example: 80, 100, 120 or 160 MHz.
Misinterpretation to avoid: equal frequencies do not imply aligned clocks.
Verification observation: change phase and frequency independently.

### A.2. logic_rst
Port ID: T08-PORT-02.
Direction: input.
Width: 1 bit.
Owning domain: system.
Qualifier: active-high reset.
Sampling rule: logic clock reset behavior.
Meaning: coordinated traffic-epoch reset.
Temporal rule: hold asserted for the specified coordinated interval.
Reset/epoch rule: assertion cancels system stream obligations.
Related interface: tx_rst and rx_rst.
Concrete example: release on a falling logic edge.
Misinterpretation to avoid: single-domain reset is outside scope.
Verification observation: clear monitor epoch on coordinated reset.

### A.3. tx_clk
Port ID: T08-PORT-03.
Direction: input.
Width: 1 bit.
Owning domain: TX.
Qualifier: continuous clock.
Sampling rule: rising edge.
Meaning: owns GMII transmit octets.
Temporal rule: nominal 125 MHz throughout traffic.
Reset/epoch rule: clock continues during reset.
Related interface: tx_rst.
Concrete example: period 8 ns with independent phase.
Misinterpretation to avoid: not the logic clock by definition.
Verification observation: sample TX only on this clock.

### A.4. tx_rst
Port ID: T08-PORT-04.
Direction: input.
Width: 1 bit.
Owning domain: TX.
Qualifier: active-high reset.
Sampling rule: TX clock reset behavior.
Meaning: aborts an in-flight TX wire frame.
Temporal rule: coordinated assertion; local falling-edge release.
Reset/epoch rule: starts a fresh TX traffic epoch.
Related interface: logic_rst and rx_rst.
Concrete example: release before or after logic_rst.
Misinterpretation to avoid: an aborted burst is not a completed good frame.
Verification observation: send a new good frame after settling.

### A.5. rx_clk
Port ID: T08-PORT-05.
Direction: input.
Width: 1 bit.
Owning domain: RX.
Qualifier: continuous clock.
Sampling rule: rising edge.
Meaning: owns receive octets and policy snapshots.
Temporal rule: nominal 125 MHz with independent phase.
Reset/epoch rule: clock continues during reset.
Related interface: rx_rst and configuration ports.
Concrete example: independent phase from tx_clk.
Misinterpretation to avoid: not a source for combinational logic-domain metadata.
Verification observation: sample policy event in this domain.

### A.6. rx_rst
Port ID: T08-PORT-06.
Direction: input.
Width: 1 bit.
Owning domain: RX.
Qualifier: active-high reset.
Sampling rule: RX clock reset behavior.
Meaning: cancels decoded-frame and snapshot state.
Temporal rule: coordinated assertion; local falling-edge release.
Reset/epoch rule: no old snapshot or drop event survives settling.
Related interface: logic_rst and tx_rst.
Concrete example: reset in the middle of a C-tag header.
Misinterpretation to avoid: configuration pins remain environment-owned.
Verification observation: verify next frame takes a new snapshot.

### A.7. tx_axis_tdata
Port ID: T08-PORT-07.
Direction: input.
Width: 8 bits.
Owning domain: system.
Qualifier: tx_axis_tvalid.
Sampling rule: valid and ready on rising logic edge.
Meaning: next submitted body octet.
Temporal rule: stable while valid and not ready.
Reset/epoch rule: old partial input discarded.
Related interface: tx_axis_tlast.
Concrete example: byte 03 at body offset zero.
Misinterpretation to avoid: not preamble and not FCS.
Verification observation: compare accepted input bytes to wire body.

### A.8. tx_axis_tvalid
Port ID: T08-PORT-08.
Direction: input.
Width: 1 bit.
Owning domain: system.
Qualifier: asserted for a presented byte.
Sampling rule: rising logic edge with ready.
Meaning: producer presents one body beat.
Temporal rule: must remain asserted during a stall.
Reset/epoch rule: environment may cancel on coordinated reset.
Related interface: tx_axis_tready.
Concrete example: gaps between accepted bytes are legal.
Misinterpretation to avoid: a gap is not an end-of-frame marker.
Verification observation: scoreboard counts only handshakes.

### A.9. tx_axis_tlast
Port ID: T08-PORT-09.
Direction: input.
Width: 1 bit.
Owning domain: system.
Qualifier: tx_axis_tvalid.
Sampling rule: accepted logic-domain beat.
Meaning: marks submitted body end.
Temporal rule: stable with data under a stall.
Reset/epoch rule: old frame boundary is discarded.
Related interface: tx_axis_tdata and tx_axis_tuser.
Concrete example: last on accepted offset 41 for L=42.
Misinterpretation to avoid: invalid-cycle last has no meaning.
Verification observation: confirm exactly one terminal beat per input frame.

### A.10. tx_axis_tuser
Port ID: T08-PORT-10.
Direction: input.
Width: 1 bit.
Owning domain: system.
Qualifier: accepted terminal input beat.
Sampling rule: valid, ready and last on logic edge.
Meaning: one marks a bad TX frame for discard.
Temporal rule: stable with a stalled input beat.
Reset/epoch rule: partial old frame cannot later commit.
Related interface: tx_fifo_bad_frame.
Concrete example: bad terminal followed by a good frame.
Misinterpretation to avoid: not a request for VLAN metadata.
Verification observation: check zero wire frames for bad submission.

### A.11. tx_axis_tready
Port ID: T08-PORT-11.
Direction: output.
Width: 1 bit.
Owning domain: system.
Qualifier: pairs with tx_axis_tvalid.
Sampling rule: rising logic edge.
Meaning: indicates capacity to accept this input beat.
Temporal rule: may change as queue capacity changes.
Reset/epoch rule: no pre-reset partial frame survives.
Related interface: TX frame FIFO.
Concrete example: deassertion while the queue is occupied.
Misinterpretation to avoid: ready is not a proof of wire transmission.
Verification observation: exercise producer stability while ready is low.

### A.12. rx_axis_tdata
Port ID: T08-PORT-12.
Direction: output.
Width: 8 bits.
Owning domain: system.
Qualifier: rx_axis_tvalid.
Sampling rule: valid and ready on rising logic edge.
Meaning: delivered body octet including tag and padding.
Temporal rule: stable while valid and not ready.
Reset/epoch rule: no pre-reset body fragment survives.
Related interface: rx_axis_tlast.
Concrete example: offset 14 remains original TCI high byte.
Misinterpretation to avoid: not the stripped FCS.
Verification observation: compare every accepted byte.

### A.13. rx_axis_tvalid
Port ID: T08-PORT-13.
Direction: output.
Width: 1 bit.
Owning domain: system.
Qualifier: asserted for a presented output byte.
Sampling rule: rising logic edge with ready.
Meaning: a committed frame byte is available.
Temporal rule: stays asserted for an outstanding stalled beat.
Reset/epoch rule: cancelled old beat must not leak into new epoch.
Related interface: rx_axis_tready.
Concrete example: ready zero while tagged terminal is presented.
Misinterpretation to avoid: policy-denied frames cannot expose a valid prefix.
Verification observation: monitor valid during rejection as well as handshakes.

### A.14. rx_axis_tlast
Port ID: T08-PORT-14.
Direction: output.
Width: 1 bit.
Owning domain: system.
Qualifier: rx_axis_tvalid.
Sampling rule: accepted logic-domain beat.
Meaning: last body byte, not FCS.
Temporal rule: stable while its valid byte is stalled.
Reset/epoch rule: old terminal cannot complete after reset.
Related interface: rx_axis_tagged and rx_axis_tci.
Concrete example: last at body offset 79 for L=80.
Misinterpretation to avoid: last alone on invalid cycles is unqualified.
Verification observation: verify frame count and length from accepted last.

### A.15. rx_axis_tuser
Port ID: T08-PORT-15.
Direction: output.
Width: 1 bit.
Owning domain: system.
Qualifier: rx_axis_tvalid.
Sampling rule: accepted logic-domain beat.
Meaning: bad-frame bit; delivered good frames use zero.
Temporal rule: stable with stalled output.
Reset/epoch rule: no old bad indication leaks into a new good frame.
Related interface: RX FIFO bad mask.
Concrete example: zero on every delivered good byte.
Misinterpretation to avoid: nonzero TCI must not set this bit.
Verification observation: assert zero on all delivered frames.

### A.16. rx_axis_tready
Port ID: T08-PORT-16.
Direction: input.
Width: 1 bit.
Owning domain: system.
Qualifier: logic consumer willingness.
Sampling rule: rising logic edge.
Meaning: permits one delivered byte transfer.
Temporal rule: may change on successive legal edges.
Reset/epoch rule: environment may hold zero through reset.
Related interface: rx_axis_tvalid.
Concrete example: random pauses, including terminal pauses.
Misinterpretation to avoid: cannot backpressure the GMII wire directly.
Verification observation: verify eventual draining after ready returns.

### A.17. rx_axis_tagged
Port ID: T08-PORT-17.
Direction: output.
Width: 1 bit.
Owning domain: system.
Qualifier: valid terminal output; zero on valid nonterminal.
Sampling rule: rising logic edge with ready for delivery.
Meaning: one only for an admitted enabled single C-tag.
Temporal rule: stable with stalled terminal byte.
Reset/epoch rule: old classification must not survive reset.
Related interface: rx_axis_tci.
Concrete example: one at terminal for admitted TCI A007.
Misinterpretation to avoid: bypass C-tag still reports zero.
Verification observation: check terminal and every nonterminal beat.

### A.18. rx_axis_tci
Port ID: T08-PORT-18.
Direction: output.
Width: 16 bits.
Owning domain: system.
Qualifier: valid terminal output; zero on valid nonterminal.
Sampling rule: rising logic edge with ready for delivery.
Meaning: numeric original TCI of admitted enabled C-tag.
Temporal rule: all sixteen bits stable during terminal stall.
Reset/epoch rule: old TCI must not survive reset.
Related interface: rx_axis_tagged.
Concrete example: A007 includes PCP=5, DEI=0, VID=7.
Misinterpretation to avoid: not just the twelve-bit VID.
Verification observation: check all PCP and DEI combinations.

### A.19. gmii_rxd
Port ID: T08-PORT-19.
Direction: input.
Width: 8 bits.
Owning domain: RX.
Qualifier: gmii_rx_dv.
Sampling rule: rising rx_clk edge.
Meaning: next physical receive octet.
Temporal rule: one octet per enabled receive cycle.
Reset/epoch rule: environment aborts old burst on reset.
Related interface: gmii_rx_er.
Concrete example: 81 then 00 at outer C-tag positions.
Misinterpretation to avoid: header numeric fields are network order.
Verification observation: build wire stimulus independently.

### A.20. gmii_rx_dv
Port ID: T08-PORT-20.
Direction: input.
Width: 1 bit.
Owning domain: RX.
Qualifier: receive burst qualifier.
Sampling rule: rising rx_clk edge.
Meaning: high throughout preamble, body and FCS.
Temporal rule: continuous over an ordinary good frame.
Reset/epoch rule: environment ends interrupted traffic on reset.
Related interface: gmii_rxd.
Concrete example: low for twelve or more inter-frame cycles.
Misinterpretation to avoid: an internal decoded bubble is not this signal.
Verification observation: verify body decoding separately from wire overhead.

### A.21. gmii_rx_er
Port ID: T08-PORT-21.
Direction: input.
Width: 1 bit.
Owning domain: RX.
Qualifier: enabled receive body for error tests.
Sampling rule: rising rx_clk edge.
Meaning: marks physical receive error.
Temporal rule: normally zero; inject a selected body error.
Reset/epoch rule: environment restores legal stimulus after reset.
Related interface: rx_error_bad_frame.
Concrete example: one on body offset 22 of a test frame.
Misinterpretation to avoid: not a policy rejection input.
Verification observation: expect atomic discard and later recovery.

### A.22. gmii_txd
Port ID: T08-PORT-22.
Direction: output.
Width: 8 bits.
Owning domain: TX.
Qualifier: gmii_tx_en.
Sampling rule: rising tx_clk edge.
Meaning: serialized preamble, SFD, body, padding or FCS.
Temporal rule: one meaningful octet per enabled cycle.
Reset/epoch rule: interrupted burst is abandoned.
Related interface: gmii_tx_er.
Concrete example: D5 after exactly seven 55 octets.
Misinterpretation to avoid: idle data need not have a specified value.
Verification observation: capture wire before calculating expected CRC.

### A.23. gmii_tx_en
Port ID: T08-PORT-23.
Direction: output.
Width: 1 bit.
Owning domain: TX.
Qualifier: wire burst qualifier.
Sampling rule: rising tx_clk edge.
Meaning: high from first preamble through fourth FCS.
Temporal rule: continuous within a valid burst.
Reset/epoch rule: no completed old burst is required after abort.
Related interface: gmii_txd.
Concrete example: at least twelve low samples between bursts.
Misinterpretation to avoid: AXI producer gaps cannot create wire gaps.
Verification observation: count enabled octets and idle cycles.

### A.24. gmii_tx_er
Port ID: T08-PORT-24.
Direction: output.
Width: 1 bit.
Owning domain: TX.
Qualifier: transmit error indication.
Sampling rule: rising tx_clk edge.
Meaning: zero for valid transmissions and ordinary idle.
Temporal rule: must not assert during a valid frame.
Reset/epoch rule: reset cancels an interrupted transfer.
Related interface: tx_error_underflow.
Concrete example: zero for a good short padded body.
Misinterpretation to avoid: do not hide CRC failure by declaring the frame erroneous.
Verification observation: assert zero for every expected good burst.

### A.25. cfg_vlan_enable
Port ID: T08-PORT-25.
Direction: input.
Width: 1 bit.
Owning domain: RX.
Qualifier: snapshot at first decoded valid body byte.
Sampling rule: rising rx_clk edge with normal setup/hold.
Meaning: one enables policy; zero bypasses policy.
Temporal rule: may change mid-frame but snapshot remains authoritative.
Reset/epoch rule: pin value is not reset by DUT.
Related interface: all other cfg ports.
Concrete example: one before frame A, zero before frame B.
Misinterpretation to avoid: sampling at delivered output is too late.
Verification observation: update after first decoded byte and verify next-frame effect.

### A.26. cfg_accept_untagged
Port ID: T08-PORT-26.
Direction: input.
Width: 1 bit.
Owning domain: RX.
Qualifier: enabled frame snapshot.
Sampling rule: first decoded valid body-byte edge.
Meaning: permits outer fields other than 8100 and 88A8.
Temporal rule: mid-frame changes affect only later frames.
Reset/epoch rule: new frame obtains new value after reset.
Related interface: cfg_vlan_enable.
Concrete example: one admits outer 0800.
Misinterpretation to avoid: does not admit S-tag or truncated header.
Verification observation: pair allow and deny tests with identical body.

### A.27. cfg_accept_priority
Port ID: T08-PORT-27.
Direction: input.
Width: 1 bit.
Owning domain: RX.
Qualifier: enabled frame snapshot.
Sampling rule: first decoded valid body-byte edge.
Meaning: permits C-tag VID zero independently of list.
Temporal rule: mid-frame changes affect only later frames.
Reset/epoch rule: snapshot state is cleared, not the pin.
Related interface: cfg_vlan_valid and cfg_vlan_vids.
Concrete example: one with empty valid mask still admits VID zero.
Misinterpretation to avoid: list VID zero cannot override a cleared flag.
Verification observation: test both directions of flag/list independence.

### A.28. cfg_vlan_valid
Port ID: T08-PORT-28.
Direction: input.
Width: 4 bits.
Owning domain: RX.
Qualifier: enabled frame snapshot.
Sampling rule: first decoded valid body-byte edge.
Meaning: bit i qualifies VID slot i.
Temporal rule: snapshot all bits with flags and list.
Reset/epoch rule: new frame obtains environment value.
Related interface: cfg_vlan_vids.
Concrete example: 1000 enables only slot three.
Misinterpretation to avoid: do not treat the mask as a numeric slot index.
Verification observation: exercise all sixteen mask values.

### A.29. cfg_vlan_vids
Port ID: T08-PORT-29.
Direction: input.
Width: 48 bits.
Owning domain: RX.
Qualifier: enabled frame snapshot.
Sampling rule: first decoded valid body-byte edge.
Meaning: four packed twelve-bit VID entries.
Temporal rule: snapshot all forty-eight bits together.
Reset/epoch rule: new frame obtains environment value.
Related interface: cfg_vlan_valid.
Concrete example: 003_002_001_007 has slot zero VID 7.
Misinterpretation to avoid: slot zero is the low twelve bits.
Verification observation: test matches in each independently valid slot.

### A.30. rx_vlan_drop
Port ID: T08-PORT-30.
Direction: output.
Width: 1 bit.
Owning domain: RX.
Qualifier: policy-denied raw-MAC-good terminal frame.
Sampling rule: rising rx_clk edge.
Meaning: one-cycle policy rejection event.
Temporal rule: not a ready/valid level; pulse must not stretch.
Reset/epoch rule: no reset-aborted event survives settling.
Related interface: raw terminal bad and snapshot policy.
Concrete example: one event for denied untagged good-FCS frame.
Misinterpretation to avoid: MAC-bad denied frame generates no policy event.
Verification observation: count RX-domain samples around terminal boundaries.

### A.31. tx_error_underflow
Port ID: T08-PORT-31.
Direction: output.
Width: 1 bit.
Owning domain: system.
Qualifier: existing synchronized MAC event.
Sampling rule: rising logic_clk edge.
Meaning: upstream TX starvation/error event.
Temporal rule: event, not a stalled payload field.
Reset/epoch rule: old events cleared through coordinated reset.
Related interface: TX raw MAC event crossing.
Concrete example: no underflow from legal AXI input gaps.
Misinterpretation to avoid: committed frame FIFO should isolate input gaps.
Verification observation: check absence under store-and-forward traffic.

### A.32. rx_error_bad_frame
Port ID: T08-PORT-32.
Direction: output.
Width: 1 bit.
Owning domain: system.
Qualifier: existing synchronized MAC event.
Sampling rule: rising logic_clk edge.
Meaning: raw receive frame error indication.
Temporal rule: event, not a stalled payload field.
Reset/epoch rule: no stale event after reset settling.
Related interface: gmii_rx_er and raw RX decoder.
Concrete example: body error can generate bad-frame event.
Misinterpretation to avoid: policy denial is not itself a MAC error.
Verification observation: separate physical error count from policy drop count.

### A.33. rx_error_bad_fcs
Port ID: T08-PORT-33.
Direction: output.
Width: 1 bit.
Owning domain: system.
Qualifier: existing synchronized MAC event.
Sampling rule: rising logic_clk edge.
Meaning: raw receive FCS mismatch indication.
Temporal rule: event, not a stalled payload field.
Reset/epoch rule: no stale event after reset settling.
Related interface: RX CRC checker.
Concrete example: flip a received FCS bit.
Misinterpretation to avoid: GMII body abort need not also produce bad-FCS.
Verification observation: check a pure FCS corruption separately.

### A.34. tx_fifo_overflow
Port ID: T08-PORT-34.
Direction: output.
Width: 1 bit.
Owning domain: system.
Qualifier: TX FIFO source status.
Sampling rule: rising logic_clk edge.
Meaning: legacy whole-frame overflow/oversize report.
Temporal rule: retain upstream status semantics.
Reset/epoch rule: old epoch cannot affect new queue.
Related interface: TX FIFO capacity handling.
Concrete example: oversize stress separate from legal L<=1518 tests.
Misinterpretation to avoid: not a reason to ignore ready during legal traffic.
Verification observation: verify preservation without imposing a new overflow threshold.

### A.35. tx_fifo_bad_frame
Port ID: T08-PORT-35.
Direction: output.
Width: 1 bit.
Owning domain: system.
Qualifier: TX FIFO source status.
Sampling rule: rising logic_clk edge.
Meaning: terminal bad-frame discard report.
Temporal rule: retain upstream status semantics.
Reset/epoch rule: old epoch state discarded.
Related interface: tx_axis_tuser.
Concrete example: bad terminal followed by accepted good terminal.
Misinterpretation to avoid: not a count of transmitted error-marked packets.
Verification observation: verify discard with wire capture.

### A.36. tx_fifo_good_frame
Port ID: T08-PORT-36.
Direction: output.
Width: 1 bit.
Owning domain: system.
Qualifier: TX FIFO source status.
Sampling rule: rising logic_clk edge.
Meaning: successful good-frame FIFO commit report.
Temporal rule: retain upstream status semantics.
Reset/epoch rule: old committed-but-undelivered traffic discarded.
Related interface: TX frame FIFO.
Concrete example: commit may precede wire start.
Misinterpretation to avoid: not proof the fourth FCS was already emitted.
Verification observation: measure commit and wire completion separately.

### A.37. rx_fifo_overflow
Port ID: T08-PORT-37.
Direction: output.
Width: 1 bit.
Owning domain: system.
Qualifier: RX FIFO destination synchronized status.
Sampling rule: rising logic_clk edge.
Meaning: legacy receive capacity/oversize event.
Temporal rule: retain upstream status semantics.
Reset/epoch rule: old status cleared through reset crossing.
Related interface: RX FIFO capacity handling.
Concrete example: long consumer stall with incoming frames.
Misinterpretation to avoid: not a required VLAN-drop event.
Verification observation: check already committed frames remain intact.

### A.38. rx_fifo_bad_frame
Port ID: T08-PORT-38.
Direction: output.
Width: 1 bit.
Owning domain: system.
Qualifier: RX FIFO destination synchronized status.
Sampling rule: rising logic_clk edge.
Meaning: bad-marked tentative frame discard report.
Temporal rule: retain upstream status semantics.
Reset/epoch rule: old epoch state discarded.
Related interface: RX user bit zero.
Concrete example: raw MAC bad or policy bad can reach this cause.
Misinterpretation to avoid: nonzero TCI alone must not cause this event.
Verification observation: pair admitted nonzero TCI with successful output.

### A.39. rx_fifo_good_frame
Port ID: T08-PORT-39.
Direction: output.
Width: 1 bit.
Owning domain: system.
Qualifier: RX FIFO destination synchronized status.
Sampling rule: rising logic_clk edge.
Meaning: successful RX frame commit report.
Temporal rule: retain upstream status semantics.
Reset/epoch rule: reset discards old committed traffic.
Related interface: RX frame FIFO.
Concrete example: may pulse while consumer ready remains zero.
Misinterpretation to avoid: not completion of system-side delivery.
Verification observation: distinguish commit, presentation and accepted last.


## Appendix B. Byte layouts and arithmetic vectors

### B.1 Untagged body map

| Body offsets | Count | Meaning | Wire order |
| --- | ---: | --- | --- |
| 0–5 | 6 | Destination address | As submitted |
| 6–11 | 6 | Source address | As submitted |
| 12–13 | 2 | Outer type/length | High octet first |
| 14 onward | Variable | Payload, then any received padding | As transmitted |

The MAC does not interpret upper-layer payload for this feature.
Payload can itself contain 81 00 or 88 A8 without affecting classification.
The outer type/length field must be complete before classifying it.
A terminal low field byte is still part of the current frame.
An enabled body shorter than fourteen bytes is rejected.
A complete untagged header is not implicitly a complete C-tag.
The absence of a C-tag does not create a TCI value from payload bytes.
An allowed untagged frame keeps tagged and TCI zero at every valid beat.

### B.2 Single C-tag body map

| Body offsets | Count | Meaning | Numeric interpretation |
| --- | ---: | --- | --- |
| 0–5 | 6 | Destination address | Opaque octets |
| 6–11 | 6 | Source address | Opaque octets |
| 12–13 | 2 | Outer field | 81 00 |
| 14–15 | 2 | TCI | (body[14]<<8) OR body[15] |
| 16–17 | 2 | Inner type | (body[16]<<8) OR body[17] |
| 18 onward | Variable | Payload and padding | Opaque octets |

The tag is four bytes relative to the untagged header.
The original bytes at offsets 12–17 remain in the delivered body.
The feature is admission, not decapsulation.
For TCI A007, the on-wire TCI bytes are A0 then 07.
PCP is five, DEI is zero and VID is seven.
If admitted, output terminal TCI is the numeric value A007.
FCS serialization uses a different byte-order convention from this header.
Do not use the FCS convention to reverse the TCI bytes.

### B.3 Metadata bit map

| Internal user bits | Width | Meaning |
| --- | ---: | --- |
| 17 | 1 | Admitted enabled single-C-tag terminal |
| 16:1 | 16 | Original terminal TCI |
| 0 | 1 | Raw MAC bad OR policy rejection |

TCI bit zero is stored in internal user bit one.
TCI bit fifteen is stored in internal user bit sixteen.
The tagged flag is independent of TCI bit fifteen.
The bad flag is independent of TCI bit zero.
The RX FIFO mask tests only bit zero.
For a good admitted TCI A007 terminal, user is (1<<17) OR (A007<<1).
For valid nonterminal bytes, no terminal TCI or tagged bits are reported.
A bad frame's terminal metadata does not create an output transaction.
These examples describe packing, not a requirement to preserve local signal names.

### B.4 Packed list examples

Entry i is extracted as (cfg_vlan_vids >> (12*i)) AND FFF.
The following examples distinguish integer packing from network-order bytes.
The configuration pins are a packed word, not a serial network field.

| Slots [0,1,2,3] | Packed hexadecimal value | Valid mask example | Meaning |
| --- | --- | --- | --- |
| [7,22,333,4094] | FFE14D016007 | 0001 | Only VID seven qualifies |
| [7,22,333,4094] | FFE14D016007 | 0010 | Only VID twenty-two qualifies |
| [7,22,333,4094] | FFE14D016007 | 0100 | Only VID 333 qualifies |
| [7,22,333,4094] | FFE14D016007 | 1000 | Only VID 4094 qualifies |
| [7,7,7,7] | 007007007007 | 1111 | Four equal qualified entries, one match decision |
| [0,22,333,4094] | FFE14D016000 | 0001 | Priority flag still controls VID zero |
| [4095,22,333,4094] | FFE14D016FFF | 0001 | Reserved VID still rejected |
| [1,2,3,4] | 004003002001 | 1111 | Four ordinary low VID values |

Do not treat 0001 as slot one; it means slot zero is valid.
Do not treat FFE as a reserved VID; it is decimal 4094.
FFF is decimal 4095 and is reserved by this policy.
A packed list alone cannot override structural tag checks.

### B.5 All validity masks with one unique matching slot

This table uses slots [7,22,333,4094].
A row lists ordinary VIDs admitted by the list alone.
Untagged and priority flags are not represented by that list.
Reserved VID 4095 is never represented as an ordinary allowed value.

| Mask bits 3:0 | Ordinary admitted VIDs |
| --- | --- |
| 0000 | None |
| 0001 | 7 |
| 0010 | 22 |
| 0011 | 7, 22 |
| 0100 | 333 |
| 0101 | 7, 333 |
| 0110 | 22, 333 |
| 0111 | 7, 22, 333 |
| 1000 | 4094 |
| 1001 | 7, 4094 |
| 1010 | 22, 4094 |
| 1011 | 7, 22, 4094 |
| 1100 | 333, 4094 |
| 1101 | 7, 333, 4094 |
| 1110 | 22, 333, 4094 |
| 1111 | 7, 22, 333, 4094 |

### B.6 All PCP/DEI values with ordinary VID seven

The list contains a qualified VID seven.
All rows therefore have the same admission result.
Each row has a different full TCI that must be preserved.

| PCP | DEI | TCI | Wire TCI bytes | Terminal tagged |
| ---: | ---: | --- | --- | ---: |
| 0 | 0 | 0007 | 00 07 | 1 |
| 0 | 1 | 1007 | 10 07 | 1 |
| 1 | 0 | 2007 | 20 07 | 1 |
| 1 | 1 | 3007 | 30 07 | 1 |
| 2 | 0 | 4007 | 40 07 | 1 |
| 2 | 1 | 5007 | 50 07 | 1 |
| 3 | 0 | 6007 | 60 07 | 1 |
| 3 | 1 | 7007 | 70 07 | 1 |
| 4 | 0 | 8007 | 80 07 | 1 |
| 4 | 1 | 9007 | 90 07 | 1 |
| 5 | 0 | A007 | A0 07 | 1 |
| 5 | 1 | B007 | B0 07 | 1 |
| 6 | 0 | C007 | C0 07 | 1 |
| 6 | 1 | D007 | D0 07 | 1 |
| 7 | 0 | E007 | E0 07 | 1 |
| 7 | 1 | F007 | F0 07 | 1 |

PCP equality with a preceding frame is not relevant.
DEI equality with a preceding frame is not relevant.
The terminal metadata is the input TCI, not a synthesized list value.
No QoS scheduling behavior is implied by PCP.
No congestion discard behavior is implied by DEI.

### B.7 CRC check vectors

These are arithmetic test vectors, not precomputed RTL answers.
The ASCII vector validates the CRC convention only; it is not a legal TX body.
TX vectors use byte i = (17*i+3) modulo 256.
TX vectors include zero padding only when the submitted body is shorter than sixty.
The CRC integer and four FCS octets are stated separately.

#### B.7.1. ASCII-123456789
Vector kind: arithmetic.
Submitted octets: 9.
Padding octets: 0.
CRC-covered octets: 9.
Numeric CRC/FCS: 0xCBF43926.
Serialized FCS: 26 39 F4 CB.
Enabled GMII octets: not a wire-frame example.
First data octets: 31 32 33 34 35 36 37 38.
Last submitted data octet: 39.

#### B.7.2. TX-pattern-14
Vector kind: TX.
Submitted octets: 14.
Padding octets: 46.
CRC-covered octets: 60.
Numeric CRC/FCS: 0x42A3B4C7.
Serialized FCS: C7 B4 A3 42.
Enabled GMII octets: 72.
First data octets: 03 14 25 36 47 58 69 7A.
Last submitted data octet: E0.

#### B.7.3. TX-pattern-15
Vector kind: TX.
Submitted octets: 15.
Padding octets: 45.
CRC-covered octets: 60.
Numeric CRC/FCS: 0x2CD3577C.
Serialized FCS: 7C 57 D3 2C.
Enabled GMII octets: 72.
First data octets: 03 14 25 36 47 58 69 7A.
Last submitted data octet: F1.

#### B.7.4. TX-pattern-42
Vector kind: TX.
Submitted octets: 42.
Padding octets: 18.
CRC-covered octets: 60.
Numeric CRC/FCS: 0x49F88F4B.
Serialized FCS: 4B 8F F8 49.
Enabled GMII octets: 72.
First data octets: 03 14 25 36 47 58 69 7A.
Last submitted data octet: BC.

#### B.7.5. TX-pattern-58
Vector kind: TX.
Submitted octets: 58.
Padding octets: 2.
CRC-covered octets: 60.
Numeric CRC/FCS: 0xE6F55CFF.
Serialized FCS: FF 5C F5 E6.
Enabled GMII octets: 72.
First data octets: 03 14 25 36 47 58 69 7A.
Last submitted data octet: CC.

#### B.7.6. TX-pattern-59
Vector kind: TX.
Submitted octets: 59.
Padding octets: 1.
CRC-covered octets: 60.
Numeric CRC/FCS: 0xD263E7AD.
Serialized FCS: AD E7 63 D2.
Enabled GMII octets: 72.
First data octets: 03 14 25 36 47 58 69 7A.
Last submitted data octet: DD.

#### B.7.7. TX-pattern-60
Vector kind: TX.
Submitted octets: 60.
Padding octets: 0.
CRC-covered octets: 60.
Numeric CRC/FCS: 0x95D128D2.
Serialized FCS: D2 28 D1 95.
Enabled GMII octets: 72.
First data octets: 03 14 25 36 47 58 69 7A.
Last submitted data octet: EE.

#### B.7.8. TX-pattern-61
Vector kind: TX.
Submitted octets: 61.
Padding octets: 0.
CRC-covered octets: 61.
Numeric CRC/FCS: 0x974862D0.
Serialized FCS: D0 62 48 97.
Enabled GMII octets: 73.
First data octets: 03 14 25 36 47 58 69 7A.
Last submitted data octet: FF.

#### B.7.9. TX-pattern-64
Vector kind: TX.
Submitted octets: 64.
Padding octets: 0.
CRC-covered octets: 64.
Numeric CRC/FCS: 0x056ACB21.
Serialized FCS: 21 CB 6A 05.
Enabled GMII octets: 76.
First data octets: 03 14 25 36 47 58 69 7A.
Last submitted data octet: 32.

#### B.7.10. TX-pattern-100
Vector kind: TX.
Submitted octets: 100.
Padding octets: 0.
CRC-covered octets: 100.
Numeric CRC/FCS: 0xE8F3D600.
Serialized FCS: 00 D6 F3 E8.
Enabled GMII octets: 112.
First data octets: 03 14 25 36 47 58 69 7A.
Last submitted data octet: 96.

#### B.7.11. TX-pattern-256
Vector kind: TX.
Submitted octets: 256.
Padding octets: 0.
CRC-covered octets: 256.
Numeric CRC/FCS: 0x8C70078C.
Serialized FCS: 8C 07 70 8C.
Enabled GMII octets: 268.
First data octets: 03 14 25 36 47 58 69 7A.
Last submitted data octet: F2.

#### B.7.12. TX-pattern-1518
Vector kind: TX.
Submitted octets: 1518.
Padding octets: 0.
CRC-covered octets: 1518.
Numeric CRC/FCS: 0xD4ED7F1F.
Serialized FCS: 1F 7F ED D4.
Enabled GMII octets: 1530.
First data octets: 03 14 25 36 47 58 69 7A.
Last submitted data octet: C0.

A checker can recompute every number above without reading the DUT.
The 59-byte vector isolates the one-padding-byte boundary.
The 60-byte vector distinguishes padding state from an unpadded tail.
The 61-byte vector ensures extra real data is not truncated to sixty.
The 42-byte vector reproduces the original field-body pattern.
The long vectors exercise fresh CRC state beyond the header.
A correct isolated vector does not prove correct CRC reset between queued frames.
The next appendix supplies queue and reset scenarios.


## Appendix C. Concrete frame and policy scenarios

### C.1 Reading scenario cards

All RX cards use nominal 125 MHz GMII and legal preamble/SFD/IFG.
Unless stated otherwise, queue capacity is sufficient and reset is settled.
Base body byte i is (17*i+3) modulo 256.
Header bytes that exist are overwritten by the stated network-order fields.
For outer 8100, existing offsets 14–17 are overwritten with TCI and inner type.
The FCS is computed independently over that body; it is never sent as AXI payload.
A bad-FCS card flips one transmitted FCS bit after computing the correct FCS.
A GMII-error card asserts rx_er on body offset 22.
No short-header card assumes an unobserved byte value.
A policy decision and final delivery outcome are distinguished below.
All delivered valid nonterminal metadata is zero.
A zero-frame outcome means no valid output prefix, not merely no accepted last.
Mid-frame update cards change pins after the decoded first-byte snapshot.
The catalogue does not imply a required internal counter or FSM encoding.

### C.R001. ordinary-listed-C-tag
Scenario ID: T08-RX-001.
Purpose: baseline admission and original TCI preservation.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R002. untagged-allowed
Scenario ID: T08-RX-002.
Purpose: untagged flag admits a complete non-tag header.
Body length: 80 octets.
Outer field: 0x0800; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/1/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_UNTAGGED.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0xE695DD9C; FCS octets: 9C DD 95 E6.

### C.R003. untagged-denied
Scenario ID: T08-RX-003.
Purpose: denied good frame creates one policy event and no output.
Body length: 80 octets.
Outer field: 0x0800; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_UNTAGGED.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0xE695DD9C; FCS octets: 9C DD 95 E6.

### C.R004. ARP-untagged
Scenario ID: T08-RX-004.
Purpose: admission does not depend on upper-layer payload interpretation.
Body length: 80 octets.
Outer field: 0x0806; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/1/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_UNTAGGED.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x7FF388CE; FCS octets: CE 88 F3 7F.

### C.R005. IPv6-untagged
Scenario ID: T08-RX-005.
Purpose: a different EtherType is still untagged.
Body length: 80 octets.
Outer field: 0x86DD; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/1/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_UNTAGGED.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x274A6887; FCS octets: 87 68 4A 27.

### C.R006. length-field-untagged
Scenario ID: T08-RX-006.
Purpose: outer length encoding adds no new length validation.
Body length: 80 octets.
Outer field: 0x002E; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/1/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_UNTAGGED.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0xF8E3A5C1; FCS octets: C1 A5 E3 F8.

### C.R007. unknown-type-untagged
Scenario ID: T08-RX-007.
Purpose: unknown outer types are not automatically denied.
Body length: 80 octets.
Outer field: 0x1234; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/1/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_UNTAGGED.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x1E0C999A; FCS octets: 9A 99 0C 1E.

### C.R008. reversed-tag-bytes
Scenario ID: T08-RX-008.
Purpose: byte-swapped 8100 is not a C-tag.
Body length: 80 octets.
Outer field: 0x0081; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/1/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_UNTAGGED.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x3D96A1F9; FCS octets: F9 A1 96 3D.

### C.R009. S-tag-denied
Scenario ID: T08-RX-009.
Purpose: untagged allow cannot override unsupported outer S-tag.
Body length: 80 octets.
Outer field: 0x88A8; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/1/1.
Snapshot valid mask: 0b1111.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_S_TAG.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0x71679A82; FCS octets: 82 9A 67 71.

### C.R010. nested-C-tag
Scenario ID: T08-RX-010.
Purpose: VID match cannot override nested-tag structure rejection.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x8100 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b1111.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_NESTED.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0x425F7BF5; FCS octets: F5 7B 5F 42.

### C.R011. nested-S-tag
Scenario ID: T08-RX-011.
Purpose: nested S-tag rejection is independent of outer admission.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x88A8 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b1111.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_NESTED.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0xCA23FF5B; FCS octets: 5B FF 23 CA.

### C.R012. ordinary-inner-unknown
Scenario ID: T08-RX-012.
Purpose: unknown non-tag inner types remain admissible.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x1234 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x3A592540; FCS octets: 40 25 59 3A.

### C.R013. ordinary-inner-length
Scenario ID: T08-RX-013.
Purpose: inner numeric length adds no separate length checker.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x002E when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x2322BBAA; FCS octets: AA BB 22 23.

### C.R014. slot-one-match
Scenario ID: T08-RX-014.
Purpose: slot one uses bits 23:12 and validity bit one.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0016; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0010.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0016.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0xA4CECBEB; FCS octets: EB CB CE A4.

### C.R015. slot-two-match
Scenario ID: T08-RX-015.
Purpose: slot two uses bits 35:24 and validity bit two.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x014D; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0100.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x014D.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x5D951CF1; FCS octets: F1 1C 95 5D.

### C.R016. slot-three-match
Scenario ID: T08-RX-016.
Purpose: slot three covers the highest ordinary VID.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0FFE; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b1000.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0FFE.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x448A773F; FCS octets: 3F 77 8A 44.

### C.R017. matching-slot-invalid
Scenario ID: T08-RX-017.
Purpose: invalid slot zero cannot admit VID seven.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b1110.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_LIST.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R018. wrong-slot-valid
Scenario ID: T08-RX-018.
Purpose: validity cannot be borrowed from a different slot.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0016; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_LIST.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0xA4CECBEB; FCS octets: EB CB CE A4.

### C.R019. empty-valid-mask
Scenario ID: T08-RX-019.
Purpose: ordinary VID denied even when value exists in an invalid entry.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0000.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_LIST.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R020. all-valid-no-match
Scenario ID: T08-RX-020.
Purpose: valid mask alone is not an allow-all policy.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0008; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b1111.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_LIST.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0xAFBDA8A6; FCS octets: A6 A8 BD AF.

### C.R021. duplicate-valid-entries
Scenario ID: T08-RX-021.
Purpose: multiple matches cause one delivered frame.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b1111.
Snapshot slots [0,1,2,3]: [7,7,7,7].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R022. duplicate-only-invalid
Scenario ID: T08-RX-022.
Purpose: duplicate invalid values cannot admit.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b1100.
Snapshot slots [0,1,2,3]: [7,7,22,333].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_LIST.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R023. duplicate-one-valid
Scenario ID: T08-RX-023.
Purpose: any one qualified duplicate match is enough.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0010.
Snapshot slots [0,1,2,3]: [7,7,22,333].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R024. priority-flag-on-empty-list
Scenario ID: T08-RX-024.
Purpose: priority flag is independent of list presence.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0000; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/1.
Snapshot valid mask: 0b0000.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_PRIORITY.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x73C92A10; FCS octets: 10 2A C9 73.

### C.R025. priority-flag-off-listed-zero
Scenario ID: T08-RX-025.
Purpose: list membership cannot override cleared priority flag.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0000; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [0,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_PRIORITY.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0x73C92A10; FCS octets: 10 2A C9 73.

### C.R026. priority-nonzero-PCP
Scenario ID: T08-RX-026.
Purpose: PCP seven is preserved for admitted VID zero.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0xE000; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/1.
Snapshot valid mask: 0b0000.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_PRIORITY.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0xE000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x75479C16; FCS octets: 16 9C 47 75.

### C.R027. priority-DEI-set
Scenario ID: T08-RX-027.
Purpose: DEI one does not change priority admission.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x1000; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/1.
Snapshot valid mask: 0b0000.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_PRIORITY.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x1000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x3675EE66; FCS octets: 66 EE 75 36.

### C.R028. priority-all-upper-bits
Scenario ID: T08-RX-028.
Purpose: full upper TCI nibble preserved with VID zero.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0xF000; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/1.
Snapshot valid mask: 0b0000.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_PRIORITY.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0xF000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x30FB5860; FCS octets: 60 58 FB 30.

### C.R029. reserved-listed
Scenario ID: T08-RX-029.
Purpose: reserved VID denial precedes list or priority allowance.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0FFF; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/1.
Snapshot valid mask: 0b1111.
Snapshot slots [0,1,2,3]: [4095,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_RESERVED.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0xC46025D9; FCS octets: D9 25 60 C4.

### C.R030. reserved-upper-bits
Scenario ID: T08-RX-030.
Purpose: PCP and DEI cannot rescue reserved VID.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0xFFFF; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/1.
Snapshot valid mask: 0b1111.
Snapshot slots [0,1,2,3]: [4095,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_RESERVED.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0x875257A9; FCS octets: A9 57 52 87.

### C.R031. lowest-ordinary-VID
Scenario ID: T08-RX-031.
Purpose: VID one is ordinary, not priority-tagged.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0001; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [1,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0001.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0xF32378F6; FCS octets: F6 78 23 F3.

### C.R032. highest-ordinary-VID
Scenario ID: T08-RX-032.
Purpose: VID 4094 is ordinary, not reserved.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0FFE; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [4094,22,333,7].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0FFE.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x448A773F; FCS octets: 3F 77 8A 44.

### C.R033. nonzero-PCP
Scenario ID: T08-RX-033.
Purpose: PCP five does not affect VID seven admission.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0xA007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0xA007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x8CB03BBF; FCS octets: BF 3B B0 8C.

### C.R034. DEI-set
Scenario ID: T08-RX-034.
Purpose: DEI one does not affect ordinary admission.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x1007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x1007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x02005E56; FCS octets: 56 5E 00 02.

### C.R035. all-upper-TCI-bits
Scenario ID: T08-RX-035.
Purpose: terminal metadata must carry all sixteen TCI bits.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0xF007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0xF007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x048EE850; FCS octets: 50 E8 8E 04.

### C.R036. wrong-VID-with-PCP
Scenario ID: T08-RX-036.
Purpose: PCP equality is not a substitute for VID equality.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0xA008; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_LIST.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0x64B10939; FCS octets: 39 09 B1 64.

### C.R037. bypass-C-tag
Scenario ID: T08-RX-037.
Purpose: bypass preserves tag bytes but emits zero tag metadata.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 0/0/0.
Snapshot valid mask: 0b0000.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: BYPASS.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R038. bypass-untagged
Scenario ID: T08-RX-038.
Purpose: bypass ignores the untagged flag.
Body length: 80 octets.
Outer field: 0x0800; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 0/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: BYPASS.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0xE695DD9C; FCS octets: 9C DD 95 E6.

### C.R039. bypass-S-tag
Scenario ID: T08-RX-039.
Purpose: unsupported policy format is transparent in bypass.
Body length: 80 octets.
Outer field: 0x88A8; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 0/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: BYPASS.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x71679A82; FCS octets: 82 9A 67 71.

### C.R040. bypass-nested-tag
Scenario ID: T08-RX-040.
Purpose: bypass does not enforce enabled structural policy.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x8100 when present.
Snapshot enable/untagged/priority: 0/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: BYPASS.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x425F7BF5; FCS octets: F5 7B 5F 42.

### C.R041. bypass-reserved-VID
Scenario ID: T08-RX-041.
Purpose: bypass does not enforce enabled reserved VID policy.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0FFF; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 0/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: BYPASS.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0xC46025D9; FCS octets: D9 25 60 C4.

### C.R042. short-12-byte-body
Scenario ID: T08-RX-042.
Purpose: enabled incomplete address/type header is rejected.
Body length: 12 octets.
Outer field: 0x0800; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/1/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_SHORT_HEADER.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0xB0E13443; FCS octets: 43 34 E1 B0.

### C.R043. short-13-byte-body
Scenario ID: T08-RX-043.
Purpose: outer field low byte must actually exist.
Body length: 13 octets.
Outer field: 0x0800; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/1/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_SHORT_HEADER.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0x33BC96A1; FCS octets: A1 96 BC 33.

### C.R044. terminal-untagged-low-byte
Scenario ID: T08-RX-044.
Purpose: terminal offset thirteen participates in classification.
Body length: 14 octets.
Outer field: 0x0800; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/1/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_UNTAGGED.
Delivered complete frames: 1; delivered body bytes: 14.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x73E0C065; FCS octets: 65 C0 E0 73.

### C.R045. terminal-S-tag-low-byte
Scenario ID: T08-RX-045.
Purpose: terminal offset thirteen can complete an unsupported S-tag.
Body length: 14 octets.
Outer field: 0x88A8; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/1/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_S_TAG.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0x906E73F4; FCS octets: F4 73 6E 90.

### C.R046. C-tag-without-TCI
Scenario ID: T08-RX-046.
Purpose: seeing outer C-tag does not imply a complete tag.
Body length: 14 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_SHORT_C_TAG.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0x99A1E367; FCS octets: 67 E3 A1 99.

### C.R047. C-tag-one-TCI-byte
Scenario ID: T08-RX-047.
Purpose: partial TCI cannot be zero-extended into a match.
Body length: 15 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_SHORT_C_TAG.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0x014DBA95; FCS octets: 95 BA 4D 01.

### C.R048. C-tag-without-inner-type
Scenario ID: T08-RX-048.
Purpose: complete TCI is insufficient without complete inner type.
Body length: 16 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_SHORT_C_TAG.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0xCC02505F; FCS octets: 5F 50 02 CC.

### C.R049. C-tag-one-inner-byte
Scenario ID: T08-RX-049.
Purpose: inner high byte alone cannot establish tag structure.
Body length: 17 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_SHORT_C_TAG.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0x27C1298A; FCS octets: 8A 29 C1 27.

### C.R050. terminal-inner-low-byte-allowed
Scenario ID: T08-RX-050.
Purpose: terminal offset seventeen completes an admissible C-tag.
Body length: 18 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 18.
Terminal delivered metadata: tagged=1, TCI=0x0007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0xDF48449A; FCS octets: 9A 44 48 DF.

### C.R051. terminal-inner-low-byte-nested
Scenario ID: T08-RX-051.
Purpose: latest byte rejects nested type without a stale-register delay.
Body length: 18 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x8100 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_NESTED.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0x35096798; FCS octets: 98 67 09 35.

### C.R052. terminal-inner-low-byte-S-tag
Scenario ID: T08-RX-052.
Purpose: latest byte completes unsupported nested S-tag.
Body length: 18 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x88A8 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_NESTED.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0x3CC6F70B; FCS octets: 0B F7 C6 3C.

### C.R053. bypass-short-header
Scenario ID: T08-RX-053.
Purpose: no extra policy runt rejection in bypass.
Body length: 13 octets.
Outer field: 0x0800; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 0/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: BYPASS.
Delivered complete frames: 1; delivered body bytes: 13.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x33BC96A1; FCS octets: A1 96 BC 33.

### C.R054. bypass-incomplete-C-tag
Scenario ID: T08-RX-054.
Purpose: bypass does not invent missing TCI metadata.
Body length: 16 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 0/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: BYPASS.
Delivered complete frames: 1; delivered body bytes: 16.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0xCC02505F; FCS octets: 5F 50 02 CC.

### C.R055. minimum-ordinary-body
Scenario ID: T08-RX-055.
Purpose: ordinary minimum RX body works without extra padding.
Body length: 60 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 60.
Terminal delivered metadata: tagged=1, TCI=0x0007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x0B80D7F5; FCS octets: F5 D7 80 0B.

### C.R056. long-tagged-body
Scenario ID: T08-RX-056.
Purpose: header index cannot wrap and reparse payload.
Body length: 1518 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0xA007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 1518.
Terminal delivered metadata: tagged=1, TCI=0xA007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x53421961; FCS octets: 61 19 42 53.

### C.R057. long-untagged-body
Scenario ID: T08-RX-057.
Purpose: long untagged body remains byte-transparent.
Body length: 1518 octets.
Outer field: 0x0800; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/1/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_UNTAGGED.
Delivered complete frames: 1; delivered body bytes: 1518.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x5E8854FF; FCS octets: FF 54 88 5E.

### C.R058. bad-FCS-admitted-policy
Scenario ID: T08-RX-058.
Purpose: CRC protection is preserved after policy match.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: bad_fcs.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R059. bad-FCS-denied-policy
Scenario ID: T08-RX-059.
Purpose: MAC/FCS precedence suppresses a policy event.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0008; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: bad_fcs.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_LIST.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0xAFBDA8A6; FCS octets: A6 A8 BD AF.

### C.R060. bad-FCS-bypass
Scenario ID: T08-RX-060.
Purpose: bypass is not a corruption bypass.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 0/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: bad_fcs.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: BYPASS.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R061. GMII-error-admitted-policy
Scenario ID: T08-RX-061.
Purpose: raw MAC error is never cleared by admission.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: gmii_error.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R062. GMII-error-denied-policy
Scenario ID: T08-RX-062.
Purpose: early MAC abort must not create policy-drop reporting.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0008; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: gmii_error.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: DENY_LIST.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0xAFBDA8A6; FCS octets: A6 A8 BD AF.

### C.R063. GMII-error-bypass
Scenario ID: T08-RX-063.
Purpose: bypass preserves GMII error protection.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 0/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: gmii_error.
Timing or predecessor: no mid-frame configuration change; consumer ready after commit.
Policy result before MAC precedence: BYPASS.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R064. snapshot-enable-one-to-zero
Scenario ID: T08-RX-064.
Purpose: enabled denial/admission does not become bypass mid-frame.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: after decoded offset 20: change enable to zero; current frame retains original snapshot.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R065. snapshot-enable-zero-to-one
Scenario ID: T08-RX-065.
Purpose: bypass remains bypass through a mid-frame enable update.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 0/0/0.
Snapshot valid mask: 0b0000.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: after decoded offset 20: change enable to one; next frame takes new snapshot.
Policy result before MAC precedence: BYPASS.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R066. snapshot-untagged-one-to-zero
Scenario ID: T08-RX-066.
Purpose: current untagged admission uses its original flag.
Body length: 80 octets.
Outer field: 0x0800; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/1/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: after decoded offset 20: clear accept_untagged; later frames use zero.
Policy result before MAC precedence: ADMIT_UNTAGGED.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0xE695DD9C; FCS octets: 9C DD 95 E6.

### C.R067. snapshot-priority-one-to-zero
Scenario ID: T08-RX-067.
Purpose: current priority admission uses its original flag.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0000; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/1.
Snapshot valid mask: 0b0000.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: after decoded offset 20: clear accept_priority; later frames use zero.
Policy result before MAC precedence: ADMIT_PRIORITY.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x73C92A10; FCS octets: 10 2A C9 73.

### C.R068. snapshot-matching-entry-removed
Scenario ID: T08-RX-068.
Purpose: live list edits cannot deny the current matched frame.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: after decoded offset 20: replace slot zero VID seven by eight.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R069. snapshot-matching-entry-added
Scenario ID: T08-RX-069.
Purpose: a late list edit cannot rescue the current denied frame.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0008; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: after decoded offset 20: replace slot zero VID seven by eight.
Policy result before MAC precedence: DENY_LIST.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0xAFBDA8A6; FCS octets: A6 A8 BD AF.

### C.R070. snapshot-valid-mask-cleared
Scenario ID: T08-RX-070.
Purpose: mask is part of the same atomic snapshot.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: after decoded offset 20: clear all validity bits.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R071. snapshot-valid-mask-enabled
Scenario ID: T08-RX-071.
Purpose: late valid bit cannot rescue current ordinary VID.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0000.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: after decoded offset 20: set validity bit zero.
Policy result before MAC precedence: DENY_LIST.
Delivered complete frames: 0; delivered body bytes: 0.
Terminal delivered metadata: no terminal output beat.
VLAN-drop samples for this frame: 1.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R072. terminal-backpressure
Scenario ID: T08-RX-072.
Purpose: metadata must remain associated with the pending last beat.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0xA007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: hold ready low for eleven logic cycles on valid last, then accept it.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0xA007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x8CB03BBF; FCS octets: BF 3B B0 8C.

### C.R073. full-frame-backpressure
Scenario ID: T08-RX-073.
Purpose: FIFO commit and delivery are different events.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x1007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: hold ready low until the complete frame commits, then drain with pauses.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x1007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x02005E56; FCS octets: 56 5E 00 02.

### C.R074. address-looks-like-tag
Scenario ID: T08-RX-074.
Purpose: address bytes must not be searched as VLAN headers.
Body length: 80 octets.
Outer field: 0x0800; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/1/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: set DA bytes zero and one to 81 and 00; the outer field stays 0800.
Policy result before MAC precedence: ADMIT_UNTAGGED.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x86BB6EAD; FCS octets: AD 6E BB 86.

### C.R075. payload-looks-like-tag
Scenario ID: T08-RX-075.
Purpose: payload 8100/88A8 patterns cannot restart header parsing.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: insert 81 00 and 88 A8 after offset 64; policy remains header-based.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x5D282B5A; FCS octets: 5A 2B 28 5D.

### C.R076. bypass-metadata-after-tagged
Scenario ID: T08-RX-076.
Purpose: previous enabled metadata must not leak into bypass output.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0xA007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 0/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: precede with admitted enabled TCI F007; next bypass terminal reports zero.
Policy result before MAC precedence: BYPASS.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x8CB03BBF; FCS octets: BF 3B B0 8C.

### C.R077. untagged-after-tagged
Scenario ID: T08-RX-077.
Purpose: previous TCI must clear at the next frame boundary.
Body length: 80 octets.
Outer field: 0x0800; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/1/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: precede with admitted tagged TCI A007; current terminal reports zero.
Policy result before MAC precedence: ADMIT_UNTAGGED.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=0, TCI=0x0000.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0xE695DD9C; FCS octets: 9C DD 95 E6.

### C.R078. admitted-after-denied
Scenario ID: T08-RX-078.
Purpose: terminal rollback must not poison the next frame.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: precede with a denied VID eight frame at the minimum legal IFG.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R079. admitted-after-corrupt
Scenario ID: T08-RX-079.
Purpose: a raw bad frame cannot splice into a later good frame.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0x0007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: precede with a bad-FCS frame at the minimum legal IFG.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0x0007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x47BC9A20; FCS octets: 20 9A BC 47.

### C.R080. matched-header-at-slow-logic
Scenario ID: T08-RX-080.
Purpose: policy and metadata are independent of a slower output clock.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0xA007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: logic clock 80 MHz; TX/RX 125 MHz; consumer stalls periodically.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0xA007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x8CB03BBF; FCS octets: BF 3B B0 8C.

### C.R081. matched-header-at-fast-logic
Scenario ID: T08-RX-081.
Purpose: fast logic edges cannot tear RX metadata.
Body length: 80 octets.
Outer field: 0x8100; incomplete bytes remain genuinely absent.
TCI: 0xF007; inner field: 0x0800 when present.
Snapshot enable/untagged/priority: 1/0/0.
Snapshot valid mask: 0b0001.
Snapshot slots [0,1,2,3]: [7,22,333,4094].
Raw integrity stimulus: good.
Timing or predecessor: logic clock 160 MHz; TX/RX 125 MHz with unrelated phase.
Policy result before MAC precedence: ADMIT_LIST.
Delivered complete frames: 1; delivered body bytes: 80.
Terminal delivered metadata: tagged=1, TCI=0xF007.
VLAN-drop samples for this frame: 0.
Independent correct-body CRC: 0x048EE850; FCS octets: 50 E8 8E 04.


### C.2 TX repair scenarios

The arithmetic pattern is byte i = (17*i+3) modulo 256 unless overridden.
These scenarios assume adequate capacity unless a stall is explicitly requested.
A queued sequence keeps inputs available without forcing the wire to begin before commit.
At least twelve idle TX cycles separate successive completed bursts.
CRC is checked against captured bytes and against expected source bytes independently.

#### C.T001. isolated-length-14
Scenario ID: T08-TX-001.
Purpose: separate length accounting from CRC arithmetic.
Subject input length: 14 octets.
Stimulus variation: one complete good arithmetic-pattern input frame.
Expected outcome: one good frame; 60 body octets; 46 zero pad octets.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T002. isolated-length-15
Scenario ID: T08-TX-002.
Purpose: separate length accounting from CRC arithmetic.
Subject input length: 15 octets.
Stimulus variation: one complete good arithmetic-pattern input frame.
Expected outcome: one good frame; 60 body octets; 45 zero pad octets.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T003. isolated-length-42
Scenario ID: T08-TX-003.
Purpose: separate length accounting from CRC arithmetic.
Subject input length: 42 octets.
Stimulus variation: one complete good arithmetic-pattern input frame.
Expected outcome: one good frame; 60 body octets; 18 zero pad octets.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T004. isolated-length-58
Scenario ID: T08-TX-004.
Purpose: separate length accounting from CRC arithmetic.
Subject input length: 58 octets.
Stimulus variation: one complete good arithmetic-pattern input frame.
Expected outcome: one good frame; 60 body octets; 2 zero pad octets.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T005. isolated-length-59
Scenario ID: T08-TX-005.
Purpose: separate length accounting from CRC arithmetic.
Subject input length: 59 octets.
Stimulus variation: one complete good arithmetic-pattern input frame.
Expected outcome: one good frame; 60 body octets; 1 zero pad octets.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T006. isolated-length-60
Scenario ID: T08-TX-006.
Purpose: separate length accounting from CRC arithmetic.
Subject input length: 60 octets.
Stimulus variation: one complete good arithmetic-pattern input frame.
Expected outcome: one good frame; 60 body octets; 0 zero pad octets.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T007. isolated-length-61
Scenario ID: T08-TX-007.
Purpose: separate length accounting from CRC arithmetic.
Subject input length: 61 octets.
Stimulus variation: one complete good arithmetic-pattern input frame.
Expected outcome: one good frame; 61 body octets; 0 zero pad octets.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T008. isolated-length-64
Scenario ID: T08-TX-008.
Purpose: separate length accounting from CRC arithmetic.
Subject input length: 64 octets.
Stimulus variation: one complete good arithmetic-pattern input frame.
Expected outcome: one good frame; 64 body octets; 0 zero pad octets.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T009. isolated-length-100
Scenario ID: T08-TX-009.
Purpose: separate length accounting from CRC arithmetic.
Subject input length: 100 octets.
Stimulus variation: one complete good arithmetic-pattern input frame.
Expected outcome: one good frame; 100 body octets; 0 zero pad octets.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T010. isolated-length-1518
Scenario ID: T08-TX-010.
Purpose: separate length accounting from CRC arithmetic.
Subject input length: 1518 octets.
Stimulus variation: one complete good arithmetic-pattern input frame.
Expected outcome: one good frame; 1518 body octets; 0 zero pad octets.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T011. all-zero-short-body
Scenario ID: T08-TX-011.
Purpose: zero data must not conceal a missed CRC update.
Subject input length: 42 octets.
Stimulus variation: all forty-two submitted bytes are zero.
Expected outcome: one good sixty-byte body with eighteen added zeros.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T012. nonzero-final-payload
Scenario ID: T08-TX-012.
Purpose: final payload and first pad must remain distinct.
Subject input length: 59 octets.
Stimulus variation: arithmetic pattern; overwrite terminal input byte with FF.
Expected outcome: one good sixty-byte body ending FF then 00.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T013. input-gaps-through-header
Scenario ID: T08-TX-013.
Purpose: input gaps are legal and must not cause TX underflow.
Subject input length: 42 octets.
Stimulus variation: pause three logic cycles after every seventh accepted input byte.
Expected outcome: one complete correct wire burst after FIFO commit.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T014. gap-before-terminal
Scenario ID: T08-TX-014.
Purpose: frame commit must wait for a real accepted terminal.
Subject input length: 59 octets.
Stimulus variation: pause seventeen logic cycles before presenting accepted last.
Expected outcome: one correct padded burst, not an early partial burst.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T015. stalled-terminal-input
Scenario ID: T08-TX-015.
Purpose: ready=0 is not acceptance.
Subject input length: 60 octets.
Stimulus variation: fill queue until ready stalls; hold valid terminal payload unchanged.
Expected outcome: each accepted good frame eventually transmits once.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T016. queued-identical-short
Scenario ID: T08-TX-016.
Purpose: preceding CRC state must not affect the second frame.
Subject input length: 42 octets.
Stimulus variation: queue two identical complete frames while the first transmits.
Expected outcome: two independently initialized identical wire frames.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T017. queued-long-then-short
Scenario ID: T08-TX-017.
Purpose: long-frame tail state must not seed a later short frame.
Subject input length: 42 octets.
Stimulus variation: queue a 100-byte good frame followed by the 42-byte subject.
Expected outcome: both correct; subject identical to isolated 42-byte result.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T018. queued-short-then-long
Scenario ID: T08-TX-018.
Purpose: padding state must not seed or shorten a later long frame.
Subject input length: 100 octets.
Stimulus variation: queue a 42-byte good frame followed by the 100-byte subject.
Expected outcome: both correct; subject has no padding.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T019. queued-boundary-alternation
Scenario ID: T08-TX-019.
Purpose: tail boundary transitions must be independent per frame.
Subject input length: 59 octets.
Stimulus variation: queue lengths 59,60,61,58 without unnecessary inter-input delay.
Expected outcome: all four frames have independent correct lengths and FCS.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T020. bad-short-then-good
Scenario ID: T08-TX-020.
Purpose: discarded input must not poison the next committed frame.
Subject input length: 42 octets.
Stimulus variation: mark first short frame bad at accepted last; then submit a good subject.
Expected outcome: bad frame absent; one correct good subject on GMII.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T021. reset-during-tail
Scenario ID: T08-TX-021.
Purpose: reset and frame-start both establish a fresh CRC epoch.
Subject input length: 42 octets.
Stimulus variation: assert coordinated reset during padding; settle; submit the subject again.
Expected outcome: old partial burst abandoned; new complete good frame.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.

#### C.T022. simultaneous-TX-RX
Scenario ID: T08-TX-022.
Purpose: full-duplex activity cannot share mutable CRC state.
Subject input length: 61 octets.
Stimulus variation: send good RX traffic while queuing this TX input.
Expected outcome: independent correct TX wire burst and RX delivery.
CRC coverage: all emitted subject body and zero padding, excluding preamble/SFD.
CRC epoch: FFFFFFFF at the start of each completed subject body.
Wire qualification: continuous tx_en; tx_er=0 for every expected good burst.
IFG check: count low tx_en samples after the preceding completed fourth FCS.
Boundary observation: compare final submitted byte, any padding, then all four FCS bytes.
Failure evidence: report the first incorrect body offset or FCS octet separately.
Follow-up: drain all accepted good frames; do not infer success from a single public smoke.


## Appendix D. Event-order traces

### D.1 Trace notation

Rows describe successive sampling events, not implementation state names.
L:n means the nth relevant rising logic clock edge.
R:n means the nth relevant rising receive clock edge.
T:n means the nth relevant rising transmit clock edge.
Cross-domain numbers do not imply coincident edges.
A star marks a beat that is accepted by valid and ready.
A dash means the field is unqualified or outside the local observation.
A trace may omit idle intervals that do not change the described obligation.
The legal environment drives input changes away from their sampling edge.
Reset rows intentionally cancel earlier traffic obligations.
These traces are examples of event ordering, not fixed DUT latency requirements.

### D.2 TX producer stall at a terminal byte

| Logic event | valid | ready | data | last | user | Accepted action |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| L:0 | 1 | 1 | penultimate | 0 | 0 | Append penultimate body byte |
| L:1 | 1 | 0 | terminal | 1 | 0 | No transfer |
| L:2 | 1 | 0 | terminal | 1 | 0 | No transfer |
| L:3 | 1 | 0 | terminal | 1 | 0 | No transfer |
| L:4 | 1 | 1 | terminal | 1 | 0 | Append and commit terminal byte |
| L:5 | 0 | - | - | - | - | No transfer |

There is only one terminal-byte transfer.
The producer must not withdraw valid in rows L:2 or L:3.
The FIFO must not commit at L:1 merely because last is visible.
The accepted body length is unchanged by the three-cycle stall.
The resulting wire burst contains neither duplicate terminal bytes nor a wire bubble.
Its eventual start time is not fixed by this table.

### D.3 RX terminal stall with two frames queued

Frame A is admitted C-tag TCI A007.
Frame B is admitted C-tag TCI 1016.
The list snapshot for B includes VID twenty-two.
Both complete frames have already committed to the RX FIFO.

| Logic event | valid | ready | last | tagged | TCI | Observation |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| L:0 | 1 | 1 | 0 | 0 | 0000 | A nonterminal byte transfers |
| L:1 | 1 | 0 | 1 | 1 | A007 | A terminal is presented, not accepted |
| L:2 | 1 | 0 | 1 | 1 | A007 | Entire A terminal payload stable |
| L:3 | 1 | 0 | 1 | 1 | A007 | B cannot overwrite A metadata |
| L:4 | 1 | 1 | 1 | 1 | A007 | A terminal transfers exactly once |
| later | 1 | 1 | 0 | 0 | 0000 | B begins after A |
| later | 1 | 1 | 1 | 1 | 1016 | B terminal carries B's original TCI |

TCI stability is checked while valid is high, not only on transfer.
A latest-RX-TCI side register cannot satisfy this trace.
A valid terminal output may be stalled for arbitrarily many legal logic cycles.
The test must keep queue capacity sufficient if it expects both frames.
No required number of empty output cycles between A and B is implied.

### D.4 Configuration snapshot and decoded latency

| RX event | Raw decoded valid | Raw offset | Configuration | Obligation |
| --- | ---: | --- | --- | --- |
| R:0 | 0 | - | Old | No frame snapshot yet |
| R:1 | 1 | 0 | Old | Snapshot all policy inputs together |
| R:2 | 1 | 1 | Old | Retain that snapshot |
| R:3 | 0 | - | New | Bubble does not end frame or resnapshot |
| R:4 | 1 | 2 | New | Continue using old snapshot |
| later | 1 | terminal | New | Current frame decides under old snapshot |
| later | 1 | 0 of next frame | New | Next frame takes new snapshot |

SFD may have occurred several RX cycles before R:1.
No implementation may substitute the SFD edge for R:1.
Do not drive a configuration update in a zero-delay race with a sampling edge.
A legal update is stable before the edge at which it is intended to be observed.
The table's decoded bubble is an internal-interface corner case.
It does not authorize a bubble inside an ordinary continuous GMII frame.

### D.5 Terminal-byte classification at offset seventeen

A C-tag frame has exactly eighteen decoded body octets.
Its outer field is 8100.
Its TCI is 0007 and a valid slot contains VID seven.

| Decoded offset | Octet | last | Information newly available |
| ---: | --- | ---: | --- |
| 12 | 81 | 0 | Outer high byte |
| 13 | 00 | 0 | Complete outer C-tag field |
| 14 | 00 | 0 | TCI high byte |
| 15 | 07 | 0 | Complete TCI and VID |
| 16 | 08 | 0 | Inner high byte |
| 17 | 00 | 1 | Complete inner type 0800; admissible header |

The terminal result is admit with tagged=1 and TCI=0007.
If offset sixteen is 81 instead, offset seventeen 00 completes nested 8100.
That otherwise identical frame is rejected.
A previous frame's low inner-type byte must not complete this header.
Waiting one cycle to inspect an old registered low byte gives the wrong frame result.
A pipeline can delay the complete terminal beat, but must decide using its actual octet.

### D.6 Rejection, CRC error and event precedence

| Frame | Enabled policy | Raw terminal bad | Committed output | VLAN-drop samples |
| --- | --- | ---: | --- | ---: |
| A | Admit | 0 | One complete frame if capacity permits | 0 |
| B | Deny | 0 | None | 1 |
| C | Admit | 1 | None | 0 |
| D | Deny | 1 | None | 0 |
| E | Bypass | 0 | One complete frame if capacity permits | 0 |
| F | Bypass | 1 | None | 0 |

Policy result alone does not determine integrity.
Frame D is not counted once for policy and once for FCS.
The VLAN event uses the raw terminal bad flag.
The synchronized logic-domain bad-FCS event can arrive later.
Do not wait for that delayed status to decide a receive-domain policy pulse.
No valid prefix from B, C, D or F may be visible at the output.

### D.7 FIFO rollback followed by an admitted frame

| RX-side phase | Data status | Frame-FIFO implication |
| --- | --- | --- |
| A header | Tentative A bytes written | Not committed |
| A payload | More tentative A bytes written | Not committed |
| A terminal | Policy bad set | Roll back A |
| Next legal frame B header | B bytes written | New tentative frame |
| B terminal | Raw and policy good | Commit B |
| Logic consumer resumes | B bytes accepted | Exactly B, no A prefix |

Suppressing A's terminal can leave a stale uncommitted fragment.
Suppressing A's early bytes can break boundary association.
The correct externally observable result is frame-atomic.
The implementation may use a bounded pipeline, not an extra packet buffer.
A ready consumer during A still must not see any A valid output bytes.

### D.8 Coordinated reset with stalled metadata

| Phase | Consumer | Queue state | Expected epoch behavior |
| --- | --- | --- | --- |
| Before reset | ready=0 | A terminal presented with A007 | Old epoch outstanding |
| Reset asserted | don't care | Old queue discarded | No completion obligation for A |
| Resets released in local order | ready=0 | Synchronizers settle | No old-event leakage |
| New B received | ready=0 | B commits under new snapshot | New epoch |
| Consumer resumes | ready=1 | B drains | Only B's body and metadata |

The monitor clears A from its expected queue at reset.
The DUT clears both stored frame data and metadata association.
The environment may hold the same configuration pins across reset.
That does not make the old snapshot or old partial header valid.
The next frame must sample a new first-byte snapshot.

### D.9 TX body and wire accounting ledger

| Quantity | L=42 | L=59 | L=60 | L=61 |
| --- | ---: | ---: | ---: | ---: |
| Accepted input bytes | 42 | 59 | 60 | 61 |
| Preamble bytes | 7 | 7 | 7 | 7 |
| SFD bytes | 1 | 1 | 1 | 1 |
| Copied body bytes | 42 | 59 | 60 | 61 |
| Added zero bytes | 18 | 1 | 0 | 0 |
| CRC-covered bytes | 60 | 60 | 60 | 61 |
| FCS bytes | 4 | 4 | 4 | 4 |
| Enabled GMII bytes | 72 | 72 | 72 | 73 |
| Minimum idle TX samples after burst | 12 | 12 | 12 | 12 |

Changing one ledger quantity to hide another mismatch is not a repair.
A sixty-byte wire body can still have an incorrect final input byte.
A correct body can still have a missing CRC update.
A correct isolated CRC can still have a broken next-frame initial state.
A repair must satisfy all ledgers in every queued frame.

### D.10 Queued frame epoch check

Submit A and B as separate complete good TX bodies.
Allow B to remain available while A is being transmitted.
Capture A and B as distinct enabled wire bursts.
Compute CRC(A body plus A pad) from FFFFFFFF.
Compute CRC(B body plus B pad) from FFFFFFFF independently.
Compare B with an isolated transmission of the identical B input.
B must be identical regardless of A's length and payload.
The test must not artificially insert a long FIFO-empty interval before B.
The IFG is still at least twelve idle TX samples.
There is no requirement for a new configuration handshake between A and B.
The correct repair must not depend on a host forcing the controller idle longer.

### D.11 Full-duplex independence

Drive receive traffic while transmitting queued frames.
Use unrelated TX and RX phases.
Use an RX policy that alternates admitted and denied frames.
Stall the logic RX consumer while TX continues.
Check TX CRC from TX bytes only.
Check RX CRC and policy from RX bytes and its snapshot only.
A receive drop must not perturb transmit CRC state.
A transmit bad-frame discard must not perturb receive metadata state.
Only coordinated reset intentionally cancels both traffic directions.
The fixed wrapper supplies distinct TX and RX clocks for this reason.


## Appendix E. Verification obligation cards

These cards define evidence to collect, not additional implementation features.
A candidate may choose its own testbench language and organization.
A failing check must carry enough context to reproduce the failing frame.
Use a reference frame record with bytes, snapshot, integrity and expected terminal metadata.
Keep expected records independent of the DUT's internal state or decision signals.

### E.1. TX length accounting
Evidence ID: T08-VERIFY-01.
Stimulus construction: capture each complete enabled burst.
Independent check: count preamble, SFD, source body, pad and FCS separately.
Important boundary: 42, 58, 59, 60 and 61.
Failure pattern to distinguish: treating a correct total length as proof that each region is correct.

### E.2. TX final input preservation
Evidence ID: T08-VERIFY-02.
Stimulus construction: retain a copy of accepted input bytes.
Independent check: compare every body byte before calculating FCS.
Important boundary: a nonzero final byte followed by one zero pad.
Failure pattern to distinguish: overwriting the final input with a pad zero.

### E.3. TX padding CRC coverage
Evidence ID: T08-VERIFY-03.
Stimulus construction: compute CRC over captured expected body plus zero padding.
Independent check: use a separate bit-serial CRC implementation.
Important boundary: all short lengths, not only the 42-byte capture.
Failure pattern to distinguish: reusing DUT lfsr output as the expected FCS.

### E.4. TX fresh per-frame CRC
Evidence ID: T08-VERIFY-04.
Stimulus construction: queue different bodies without forcing an empty interval.
Independent check: recompute each frame from FFFFFFFF and compare to isolated transmission.
Important boundary: long then short, short then long and identical repeats.
Failure pattern to distinguish: allowing the previous final CRC to seed the next frame.

### E.5. TX IFG
Evidence ID: T08-VERIFY-05.
Stimulus construction: count tx_en=0 sampling edges between complete bursts.
Independent check: require at least twelve idle TX cycles.
Important boundary: queued minimum-size traffic.
Failure pattern to distinguish: counting a final FCS edge as an idle edge.

### E.6. TX input gaps
Evidence ID: T08-VERIFY-06.
Stimulus construction: insert pauses between accepted body bytes.
Independent check: check that the committed frame still forms a continuous wire burst.
Important boundary: pause immediately before accepted last.
Failure pattern to distinguish: assuming every logic cycle is a byte.

### E.7. TX bad input discard
Evidence ID: T08-VERIFY-07.
Stimulus construction: mark the terminal accepted input bad.
Independent check: expect no wire frame and then correct following good traffic.
Important boundary: bad short followed by good long.
Failure pattern to distinguish: declaring bad-frame rejection a GMII transmission with tx_er set.

### E.8. RX body oracle
Evidence ID: T08-VERIFY-08.
Stimulus construction: generate body and FCS independently before injection.
Independent check: compare every delivered body octet including tag and padding.
Important boundary: distinct payload patterns and repeated equal bodies.
Failure pattern to distinguish: stripping a VLAN tag while still counting metadata as correct.

### E.9. RX FCS corruption
Evidence ID: T08-VERIFY-09.
Stimulus construction: flip a selected FCS bit only.
Independent check: expect no valid output prefix and preserve bad-FCS reporting.
Important boundary: admitted policy, denied policy and bypass.
Failure pattern to distinguish: using a policy drop to conceal missing MAC FCS checking.

### E.10. RX GMII error
Evidence ID: T08-VERIFY-10.
Stimulus construction: assert receive error on a body byte.
Independent check: expect atomic discard and subsequent recovery.
Important boundary: error before or after complete tag parsing.
Failure pattern to distinguish: assuming all error paths reach the physical terminal offset.

### E.11. RX list packing
Evidence ID: T08-VERIFY-11.
Stimulus construction: put distinct VIDs in the four slots.
Independent check: match each slot with only its own validity bit set.
Important boundary: slot zero and slot three extremes.
Failure pattern to distinguish: reversing slot order while a duplicate-entry test accidentally passes.

### E.12. RX validity mask
Evidence ID: T08-VERIFY-12.
Stimulus construction: hold list contents fixed while changing the mask.
Independent check: apply validity to the corresponding slot only.
Important boundary: all sixteen masks with unique VIDs.
Failure pattern to distinguish: using any-valid as allow-all.

### E.13. RX priority independence
Evidence ID: T08-VERIFY-13.
Stimulus construction: separate VID-zero flag tests from ordinary matches.
Independent check: list zero cannot override flag zero; empty list cannot block flag one.
Important boundary: PCP and DEI nonzero on VID zero.
Failure pattern to distinguish: routing VID zero through the ordinary lookup.

### E.14. RX reserved precedence
Evidence ID: T08-VERIFY-14.
Stimulus construction: list VID 4095 in a valid entry.
Independent check: still reject that tagged frame.
Important boundary: TCI 0FFF and FFFF.
Failure pattern to distinguish: masking away an upper bit and turning reserved into ordinary VID.

### E.15. RX tag structure
Evidence ID: T08-VERIFY-15.
Stimulus construction: vary outer and inner type independently.
Independent check: reject enabled S-tag and nested 8100/88A8 before list lookup.
Important boundary: nested tag with an otherwise matching VID.
Failure pattern to distinguish: accepting by VID before checking the complete inner field.

### E.16. RX short headers
Evidence ID: T08-VERIFY-16.
Stimulus construction: vary actual body length around offsets thirteen and seventeen.
Independent check: unknown absent bytes do not complete fields.
Important boundary: 13, 14, 15, 16, 17 and 18 bytes.
Failure pattern to distinguish: zero-extending missing bytes into a seemingly legal tag.

### E.17. RX final header byte
Evidence ID: T08-VERIFY-17.
Stimulus construction: end the body exactly at a field-completion byte.
Independent check: include that byte in the same frame's decision.
Important boundary: complete 0800 versus complete 8100 at offset seventeen.
Failure pattern to distinguish: using only old registered header state at last.

### E.18. RX snapshot
Evidence ID: T08-VERIFY-18.
Stimulus construction: schedule an update after the decoded first byte.
Independent check: hold all original flags, mask and VIDs for the current frame.
Important boundary: enable, untagged, priority, valid and list changes.
Failure pattern to distinguish: snapshotting only enable while consulting a live VID list.

### E.19. RX snapshot edge
Evidence ID: T08-VERIFY-19.
Stimulus construction: observe the actual decoded first-byte event.
Independent check: drive configuration early enough to meet setup/hold at that edge.
Important boundary: independent phases and known MAC pipeline latency.
Failure pattern to distinguish: updating on the physical first byte and assuming it is the decoded first byte.

### E.20. RX bypass
Evidence ID: T08-VERIFY-20.
Stimulus construction: feed tags and unsupported structures while disabled.
Independent check: preserve bytes and emit zero tag metadata and no policy event.
Important boundary: C-tag, S-tag, nested, reserved and incomplete tag.
Failure pattern to distinguish: allowing bypass to disable CRC protection.

### E.21. RX metadata association
Evidence ID: T08-VERIFY-21.
Stimulus construction: queue two admitted tags with different TCI.
Independent check: compare each terminal metadata value to its own frame record.
Important boundary: earlier frame stalled while later frame arrives.
Failure pattern to distinguish: using a global most-recent-TCI register.

### E.22. RX metadata stability
Evidence ID: T08-VERIFY-22.
Stimulus construction: stall a valid terminal output beat.
Independent check: check data, last, user, tagged and TCI every stalled edge.
Important boundary: eleven cycles or longer of terminal stall.
Failure pattern to distinguish: checking metadata only when ready returns.

### E.23. RX nonterminal metadata
Evidence ID: T08-VERIFY-23.
Stimulus construction: inspect every valid nonterminal output beat.
Independent check: require tagged=0 and TCI=0.
Important boundary: long tag followed by untagged frame.
Failure pattern to distinguish: leaking cached TCI throughout a body.

### E.24. RX policy event timing
Evidence ID: T08-VERIFY-24.
Stimulus construction: count RX-domain high samples around terminal.
Independent check: one sample for denied raw-good; none for denied raw-bad.
Important boundary: pure policy denial versus denial plus bad FCS.
Failure pattern to distinguish: emitting early at a forbidden header byte before integrity is known.

### E.25. RX rollback
Evidence ID: T08-VERIFY-25.
Stimulus construction: keep the logic consumer ready during denied input.
Independent check: no output prefix; next admitted frame intact.
Important boundary: denied then admitted at legal minimum IFG.
Failure pattern to distinguish: suppressing last and leaving an unterminated FIFO fragment.

### E.26. RX overflow
Evidence ID: T08-VERIFY-26.
Stimulus construction: stall consumer through sustained receive traffic.
Independent check: earlier committed frames stay whole and ordered; queue later drains.
Important boundary: capacity exhaustion with mixed tags.
Failure pattern to distinguish: requiring an exact packet threshold not defined by the interface.

### E.27. Clock variation
Evidence ID: T08-VERIFY-27.
Stimulus construction: vary logic frequency and independent clock phases.
Independent check: same body, policy and metadata results at every supported setting.
Important boundary: 80, 100, 120 and 160 MHz logic.
Failure pattern to distinguish: using aligned clocks to hide a CDC word-tearing defect.

### E.28. Reset with pending traffic
Evidence ID: T08-VERIFY-28.
Stimulus construction: assert coordinated reset during frame or terminal stall.
Independent check: clear expected epoch; new good traffic works without stale bytes or events.
Important boundary: TX padding, RX partial tag and queued output.
Failure pattern to distinguish: retaining old expected frames and misclassifying monitor errors.

### E.29. Synthesis closure
Evidence ID: T08-VERIFY-29.
Stimulus construction: elaborate all relative files under the fixed top.
Independent check: check hierarchy and synthesis diagnostics independently of simulation.
Important boundary: new state, added files and widened sideband.
Failure pattern to distinguish: assuming simulator support implies synthesizability.

### E.30. Resource accounting
Evidence ID: T08-VERIFY-30.
Stimulus construction: enumerate added byte-retaining state.
Independent check: respect 32-byte new-data allowance and avoid another packet RAM.
Important boundary: header buffer versus full-frame register array.
Failure pattern to distinguish: renaming a packet buffer to a snapshot.

### E.31. Delivery reproducibility
Evidence ID: T08-VERIFY-31.
Stimulus construction: run root run.sh with a clean build directory.
Independent check: no external cache, custom mandatory variable or network.
Important boundary: unset optional BENCH_SEED and then set another seed.
Failure pattern to distinguish: a script that only works in the author's populated build tree.

### E.32. Measurement separation
Evidence ID: T08-VERIFY-32.
Stimulus construction: record candidate, EDA and judge intervals separately.
Independent check: aggregate EDA union intervals without double-counting children.
Important boundary: parallel compilation plus simulation.
Failure pattern to distinguish: reporting cumulative CPU time as elapsed wall time.

### E.33. Suggested frame record schema
A verification record may include a local frame number and reset epoch.
Include the exact body bytes before wire injection.
Include original length and any intentionally added TX padding.
Include a complete copy of the first-byte policy snapshot.
Include planned FCS corruption or GMII error location.
Include the expected policy result independent of MAC integrity.
Include expected delivery count and byte count.
Include expected terminal tagged and TCI when delivery is expected.
Include expected VLAN-drop sample count.
Include accepted-byte and observed-wire timestamps when useful.
The schema is guidance, not a required results.json format.
Do not put expected results into the synthesizable design.

### E.34. Useful failure reports
A TX mismatch should report frame number, input length and wire-body length.
Report the first differing body offset and both byte values.
For CRC mismatch report expected and captured four-octet FCS separately.
For queue dependence report the preceding frame's length and the subject frame's length.
An RX mismatch should report snapshot flags, valid mask and list slots.
Report outer type, original TCI, inner type and actual decoded body length.
For unexpected policy events report raw terminal bad and event sampling domain.
For metadata mismatch report the frame's expected TCI, not only the most recently received TCI.
For a stalled-bundle change report values before and after the offending edge.
For reset failures report epoch boundaries and local reset-release ordering.
Keep the effective seed and reproduction command.
Do not suppress a simulator's error exit code in the reproduction script.

### E.35. Results honesty
Functional self-tests and official independent acceptance are different evidence.
A self-reported pass does not award points.
A public smoke pass covers only a small subset.
A synthesis pass does not prove CRC or policy correctness.
A simulation pass does not prove synthesis or CDC correctness.
Generic cell counts do not establish routed timing or power.
An infrastructure failure must be identified separately from a candidate logic failure.
An unmet obligation must remain visible in the final README.
A partially delivered experiment must not be labelled complete.
Measurements from different specification revisions need separate labels.


## Appendix F. Glossary and unconstrained behavior

### F.1. Accepted beat
Definition: A rising logic edge at which valid and ready are both one.
Consequence: Only accepted beats increment external stream byte counts.

### F.2. Presented beat
Definition: A byte with valid asserted, whether or not ready is high.
Consequence: A presented stalled RX byte must already have correct stable metadata.

### F.3. Body
Definition: Bytes from destination address through payload and any padding.
Consequence: Preamble, SFD and FCS are excluded.

### F.4. Submitted body
Definition: TX body bytes actually accepted from the system producer.
Consequence: The MAC can extend it with zero padding.

### F.5. Transmitted body
Definition: Body bytes actually emitted on GMII before FCS.
Consequence: It is the entire TX CRC coverage region.

### F.6. Terminal byte
Definition: The final qualified decoded or system body byte.
Consequence: It is not the fourth FCS octet.

### F.7. Frame atomicity
Definition: A rejected frame contributes no output bytes or valid prefix.
Consequence: Marking only a delivered terminal byte bad is insufficient.

### F.8. Tentative write
Definition: A frame-FIFO write before the terminal commit decision.
Consequence: It can be rolled back without exposing a frame.

### F.9. Commit
Definition: Making a complete good frame available to the FIFO reader.
Consequence: It does not mean the consumer has already accepted every byte.

### F.10. Rollback
Definition: Discarding an uncommitted frame from its tentative start.
Consequence: It must not damage earlier committed frames.

### F.11. Delivered frame
Definition: A committed frame whose terminal output beat has been accepted.
Consequence: Its byte sequence is measured using handshakes.

### F.12. Bypass
Definition: Admission disabled by the frame's frozen snapshot.
Consequence: MAC integrity and FIFO protections remain active.

### F.13. Policy denial
Definition: Enabled admission rejects the header or VID.
Consequence: A MAC-bad denied frame has no VLAN policy pulse.

### F.14. MAC bad
Definition: The existing receive decoder marks the raw terminal bad.
Consequence: It takes precedence over policy-drop reporting.

### F.15. Overflow
Definition: Queue capacity or legacy oversize protection discards traffic.
Consequence: It is not by itself a VLAN policy rejection.

### F.16. C-tag
Definition: Outer network-order field 8100 with TCI and inner type.
Consequence: This task supports exactly one enabled C-tag.

### F.17. S-tag
Definition: Outer network-order field 88A8.
Consequence: Enabled policy rejects it; bypass does not add a rejection.

### F.18. Nested tag
Definition: C-tag inner type 8100 or 88A8.
Consequence: It is structurally rejected before VID admission.

### F.19. TCI
Definition: The sixteen-bit tag control information field.
Consequence: PCP, DEI and VID bits are preserved as one numeric word.

### F.20. PCP
Definition: TCI bits 15:13, a value from zero to seven.
Consequence: No scheduler or QoS policy is added.

### F.21. DEI
Definition: TCI bit twelve.
Consequence: No congestion policy is added.

### F.22. VID
Definition: TCI bits 11:0.
Consequence: Zero is priority, 4095 is reserved, others use the list.

### F.23. Qualified slot
Definition: A VID-list entry whose corresponding validity bit is one.
Consequence: Invalid slot contents cannot match.

### F.24. Snapshot
Definition: All policy fields copied at first decoded valid body byte.
Consequence: It governs the entire decoded frame.

### F.25. Network order
Definition: The high octet of a multi-octet header field appears first.
Consequence: 8100 is transmitted as 81 then 00.

### F.26. FCS octet order
Definition: The least-significant complemented CRC octet appears first.
Consequence: This differs from numeric header field order.

### F.27. IFG
Definition: Idle GMII clock samples between enabled frame bursts.
Consequence: It is not CRC-covered body data.

### F.28. Bubble
Definition: A cycle without a qualified internal or stream byte.
Consequence: It does not by itself terminate the current frame.

### F.29. Traffic epoch
Definition: The interval after one settled coordinated reset and before the next.
Consequence: Old frame state cannot cross into the next epoch.

### F.30. CDC
Definition: Transfer of data or events between independently clocked domains.
Consequence: A synchronized word must remain coherently associated with its frame.

### F.31. EDA wall time
Definition: Union of wall-clock intervals occupied by relevant tools.
Consequence: Parallel child CPU times are not added as elapsed time.

### F.32. Experimental PPA
Definition: A pending measurement without a frozen physical reference.
Consequence: It is not automatically zero or full score.

### F.33. Values intentionally not specified
Invalid-cycle AXI data values are unqualified.
Invalid-cycle AXI last values are unqualified.
Invalid-cycle RX metadata values are unqualified.
Idle GMII TX data values are unqualified.
Exact system-to-wire startup latency is not fixed.
Exact receive-to-delivery startup latency is not fixed.
Exact synchronized legacy-status latency is not fixed.
An exact maximum queued-packet count is not promised.
Behavior for independent single-domain reset is outside scope.
Behavior for unmodelled PHY faults is outside scope.
Behavior for jumbo traffic is not promoted to a new supported feature.
Correctness is still required for every explicitly supported input.

### F.34. Requirements that must not be invented
Do not add destination filtering because the source contains addresses.
Do not add a host register bus because the feature has configuration.
Do not add PAUSE processing because its EtherType is familiar.
Do not add VLAN stripping because metadata already identifies the tag.
Do not add PCP-based denial or scheduling.
Do not add DEI-based denial.
Do not accept reserved VID merely because it appears in the list.
Do not treat a list VID-zero match as a priority-flag override.
Do not reject a bypass tag using enabled-policy structural rules.
Do not define bubbles as frame boundaries.
Do not define timer or token limits inside the RTL.
Do not widen the task into full IEEE compliance without a new specification revision.

### F.35. Submission close-out checklist
All required top names and widths remain unchanged.
Every active RTL file is listed by a relative path.
The frame repair works for isolated, overlapping, wraparound and reset-separated frames.
VLAN admission follows the complete ordered decision.
No denied or corrupt RX prefix escapes.
Terminal metadata is frame-associated and stable under stalls.
Policy pulse counting uses the receive domain and MAC-error precedence.
Added data storage respects the allowance.
Self-tests and synthesis were actually executed.
run.sh reproduces results without external cache or custom mandatory settings.
README documents limitations and measured evidence honestly.
No PPA points are claimed before reference freeze.
The submitted revision and starter input identity are recorded.

## Appendix G. Frame-transaction stress obligations

### G.1 Retained frames are not the current transaction

Provide a good frame A followed by another complete good frame B.
Delay delivery of A so that B can complete before A has fully drained.
Follow B with frame C whose terminal indication requires atomic discard.
On TX, C may carry a terminal input bad flag.
On RX, C may have incorrect FCS or be denied by enabled VLAN policy.
A and B remain deliverable in order; C contributes no output bytes.
An implementation cannot silently merge B and a following good frame D.
Frame D must survive discard recovery with its own payload and terminal metadata.
CRC validity alone is insufficient evidence: every body byte and boundary matters.

### G.2 Backpressure release during an incomplete frame

Hold the RX sink while A and B complete and are retained.
Begin receiving C and release the sink before C's final integrity result exists.
The sink may consume A and B while C continues arriving.
It MUST NOT consume even one body byte from C unless C later commits as good.
In the corrupt-C variant, total delivered bytes equal exactly A plus B.
Do not declare success merely because C never produces a terminal output beat.
The terminal metadata of A and B must remain associated with those frames.
Synchronization latency may delay A or B; it cannot justify publishing C's prefix.

### G.3 Exhaustion and discard recovery

Hold the RX sink long enough to exhaust the configured FIFO capacity.
Use supported-length frames; oversized or malformed wire traffic is not required.
An overflow may discard the arriving frame that cannot be retained in full.
Frames already retained before that overflow MUST remain byte-exact and ordered.
After release and drain, a subsequent supported good frame must be deliverable.
Ordinary capacity overflow alone does not generate a VLAN-policy-drop event.
Do not infer a fixed maximum packet count from the FIFO depth.
Prefetch and output registers can change occupied capacity by a small amount.
Verification must choose enough incoming data to force exhaustion regardless.

### G.4 Reuse, clocks and reset

Repeat admitted and discarded transactions without resetting between repetitions.
Transfer more than two FIFO capacities of retained body data over the sequence.
Drain between batches as needed; wrapping addresses is not itself an overflow.
Vary payloads, lengths, stall duration and supported system-clock phase/rate.
The same invariants apply on both sides of the circular address wrap.
Do not discard the FIFO's full/empty epoch information to simplify address arithmetic.
Accepted-beat count, complete-frame count and publication timing are different facts.
Coordinated reset clears queued and incomplete transactions as specified in section 4.
Independent single-domain reset remains outside this task's supported contract.

### G.5 Repair evidence

Supply self-checking tests for the overlapping cases, not only isolated good packets.
Document the failing external symptom and the repaired transaction invariant.
Explain why a change does not revoke earlier retained frames or expose later prefixes.
Re-run padding/FCS, VLAN decisions, snapshot and metadata regressions after the repair.
Do not count implementation-internal assertions as an independent wire/body scoreboard.
Test cases may use any legal values; the catalogue does not authorize special cases.
No corrected source, internal signal trace or hidden judge is supplied as the answer.
