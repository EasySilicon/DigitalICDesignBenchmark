# T10 clock tree closure record

## Current checkpoint (2026-10-05)

### Distributed output architecture: v107 functional qualification

The user confirmed that both input and output data slices may be physically
distributed. [The new egress record](T10_DISTRIBUTED_EGRESS_20261005.md)
replaces the global four-slot/sixteen-row selection with one output slot
per physical tile row and sixteen local egress controllers. Existing PE,
tile, arithmetic and bank definitions remain byte-identical. The independent
unmodified 2752-case acceptance, all nine groups, reset and 256-PE structure
passed for v107. All fourteen input-bubble phase flags are zero. Non-PE
state is 245444 bits, versus the old reference's 262077 bits.

v103–v106 are rejected intermediate functional candidates. Diagnostics found
that delayed block credit return, rather than local FIFO depth, caused the
remaining FP4/MXFP4 gaps. v107 returns credit only after all sixteen tiles
capture the results into elastic storage, clears local ready flags at
capture rather than later external retirement, and uses one input-full
status register stage. No acceptance criterion or latency limit was relaxed.
v108 synthesis/floorplan completed. Peripheral synthesis cells fell from
167131 (v75) to 95267; macro-inclusive logical area fell only 0.1742%.
v109 and v110 passed native placement and independent zero-overlap checks.
v110 corrected a local-column hierarchy matching error and reduced the
maximum macro read-data branch from 3252.582 to 1029.390 um, with no branch
above 2 mm. Pre-CTS ideal-clock placement setup still fails at -584968.31 ps;
long, unbuffered retired/output-control/queue paths are now limiting.
This is not comparable directly to v93's propagated-clock estimate, and
there is no new routed 1 GHz or PPA qualification claim. v111/v112 prepare
interface buffering and a bounded all-signal repair resource plan.

v114 full signal buffering and native checks completed: 232848 positive
RVT buffers, 23888 independently traced branches, zero standard-cell
overlaps. Same-model ideal-clock placement setup improved from v110's
-584968.31 ps to -22336.27 ps; hold remains -363.59 ps. This is still a
severe failure, not 1 GHz or routed closure. The path is retired row 2
to row 3 eligibility, through central anonymous output mask/valid/accept
gates, back to row 3 local queue. v115-v117 relocate those actual slot
interface cones and rerun the bounded buffered/native/STA sequence.
No CTS or routing run is justified before resolving these data controls.

### Audit of the old −53.41 ns report

[Full-DUT configuration and input/output geometry audit](T10_FULL_DUT_LAYOUT_AUDIT_20261005.md)
reverified all eleven original v93 STA inputs and checked native ps/fF/kohm/um
units, both 1000 ps clocks and sixteen tile macros. Actual A/B data pins are
grouped by row/column; maximum pin-to-ingress-register distances are
107.013/254.245 um. The v93 worst path instead crosses 4748.341 um from a
northern tile result to central gather logic without buffering. Reported
wire delay is 35394.29 ps and AO22 delay is 14681.75 ps. Its input slew,
112002.41 ps, is about 350 times the AO22 Liberty table's 320 ps maximum;
the macro's 790.53 fF load also exceeds its 92.16 fF table maximum. The
numeric WNS is a rejected placement diagnosis with severe extrapolation,
not a reliable silicon-delay prediction or a routed PPA baseline. Default
repair was overridden and selected control-only repairs missed result data
and low-fanout long-distance controls. This is a flow/locality failure.

### New transport RTL: complete-DUT placement v98–v102

The qualified v96 RTL has been synthesized and floorplanned as a complete
sixteen-tile / 256-PE DUT. v98 places all 19712 gather register cells with
their associated logic using actual tile read-data pins, and places the
paired transport banks using the adjacent row-group anchors. Connectivity,
macro geometry and established physical I/O locations are unchanged.
The 222074 standard-cell placement passed native `check_placement` and the
independent overlap audit (zero intersections). Native validation took
16.37 seconds, with 45263056 KiB peak RSS.

In the same v97 mapped netlist, tile read-data driver-to-load Manhattan
maximum falls from 4748.581 to 1065.666 um; related sum falls from
45940013.184 to 24970093.668 um. All 6360 branches previously longer than
2 mm disappear. These are geometric measurements, not routed timing.
Physical port geometry SHA-256 remains
`9d550e88656d2beed8d8dc5a17506e7f2ec9ed7e5efafb39b9ca421d8ff2a9d7`.
The missing floorplan VDD/VSS ports were copied from the earlier physical
view; no signal ports were added or removed.

The first v98 timing diagnostic incorrectly propagated the unbuilt clock
net before CTS. It completed but is inapplicable for closure: tens of
thousands of sinks on the unbuffered root produce extreme RC and meaningless
clock-tree skew. Its report is retained, not accepted as a CTS result.
`placement_ideal_clocks` was added for pre-CTS data-path diagnosis while
retaining placement parasitics and the unchanged libraries/SDC. This mode
is explicitly not routed or propagated-clock qualification.

v98 pre-CTS data diagnosis gives setup −757974.50 ps and hold −359.66 ps.
The setup path contains an INVx1 driving 1284 loads across the full chip.
v99 adds 6764 positive RVT I/O buffers at the existing physical pins, with
maximum pin-to-buffer Manhattan distance 76.851 um. Every modified input
and output interface is independently retraced to its exact old source net;
all existing instance geometry and unaffected connectivity are preserved.

v100 broad output/control-cone insertion was rejected at the bounded
64-new-Y reserve limit; no accepted ODB was emitted. v101 instead targets
302 measured high-fanout/control networks: 33963 positive RVT buffers,
including 80 local root buffers, 6454 reconnected input branches and 37
local reserve-row fragments. Every input chain passed independent positive
polarity/source/cycle checks, and selected branch maximum is 307.304 um.
Native placement and independent zero-overlap checks passed in 17.21 seconds
at 45802200 KiB peak RSS.

v101 still fails pre-CTS data setup at −681094.94 ps (hold −359.66 ps).
The new worst path runs from `b_ctrl_payload[1][10]` through widely separated
low-fanout top gates to `b_scale_hold[1][1]`. This is not 1 GHz convergence.
v102 is a new locality producer: it places the existing A/B control spines
and scale-hold registers near their actual tile input pins, and lays out
the existing data/scale skew stages between the fixed input ports and tile
pins. Top combinational gates follow those anchors. Logical connectivity,
all helper-module geometry, macro geometry and I/O-buffer geometry remain
fixed. It requires native placement and fresh timing evidence before any
closure claim. No new CTS, GRT or DRT has been run on this transport RTL.

### Complete-DUT update: control geometry and a qualified RTL pipeline

The old-RTL physically validated diagnostic is full top v93, containing
sixteen actual tile macros / 256 PEs and 305741 standard cells. It retains
the v65 pop-count logic candidate; it is **not** the new transport RTL and
does not qualify a PPA baseline. Native placement passed in 23.56 seconds
at 56938768 KiB peak RSS; independent geometry reports zero intersections.
All clock routing remains M6/M7.

| Complete-top experiment | Placement-estimated setup WNS | Routed qualification |
| --- | ---: | --- |
| v81 original control spread | −234623.39 ps | No |
| v82 output control branch repair | −234623.39 ps, masked by the output-valid port path | No |
| v83 plus output metadata cones | −151723.92 ps | No |
| v84 expanded named controls / output data cones | −106486.58 ps | No |
| v87 gather locality plus gather-ready repair | −93712.02 ps | No; native placement passed |
| v89 scalar controller cones | −53483.39 ps | No |
| v93 clean gather / I/O placement followed by one buffer pass | −53413.05 ps | No; native placement passed |

The v93 placement report uses the unchanged 1000 ps clock, SDC, six standard
libraries, v54 tile model and platform RC. Global hold remains −12978.61 ps.
The worst setup path is a tile read-data output into a gather register, with
up to 4748.463 um of unbuffered driver/load Manhattan distance. The census
includes physical ports: 61905 signal branches exceed 300 um, 30480 exceed
1 mm and 9261 exceed 2 mm. Earlier cell-only scans missed cell-to-port wires.
There is one clock port-to-first-buffer branch of 462.657 um; the remaining
cell-driven clock branches satisfy the earlier geometry repair bound.

Specific changes and evidence:

- v82/v83 use positive RVT buffers and verify every reconnected input by
  reverse traversal to its exact old net. Original instance geometry,
  master types, clocks and all unmodified connections are hashed unchanged.
- v85/v91 relocate 83200 gather combinational cells while preserving every
  register, macro, clock and logical connection. v91's legal-row placement
  reduces related driver/load Manhattan sum from 93333338.422 to
  73750082.574 um. This is a geometry metric, not extracted wirelength.
- v90/v92 relocate 6764 existing I/O buffers to actual physical pins,
  reducing maximum cell-to-port distance from 4351.719 to 15.945 um.
  Physical port geometry SHA-256 remains
  `9d550e88656d2beed8d8dc5a17506e7f2ec9ed7e5efafb39b9ca421d8ff2a9d7`.
- v86/v88 are rejected producers: the requested buffer placement exceeded
  their diagnostic movement bounds. They did not emit accepted ODBs.
  v89 restores three local legal row fragments, with a 64-new-Y memory bound,
  and independently checks the actual repaired branch lengths afterward.
- v93 restarts from exact v81 and applies locality / port anchoring before
  buffering, avoiding serial detours through old port-buffer positions.
  It adds 103189 RVT buffers to 6219 nets / 11471 branches. Selected branches
  are at most 335.674 um, but this does not cover all remaining data nets.
- The first v93 STA process was rejected after its live Tcl file was edited
  before exit. The complete diagnostic was rerun from an immutable copied
  driver with source/input/library hashes and exit status 0. The rejected
  log/report remain explicitly named `rejected_live_script_edit`.
- No new PA, GRT or DRT was launched on these still-failing candidates.
  Nine superseded/duplicate ODBs were deleted, freeing 3708346368 allocated
  bytes. Exact v81, v92 and v93 recovery checkpoints, native evidence and
  producer snapshots are retained. Cleanup manifest:
  `${T10_SCRATCH_ROOT}/t10_frozen_top/v93_superseded_checkpoint_cleanup.json`.

The v93 LEF footprint census is 100000000 um² of macro footprints plus
88099.34382 um² of standard cells. The macro figure includes placement
whitespace; it is not the v54 macro's 480138.719 um² logical cell area.
No qualified workload power or PPA score is inferred from these numbers.

Timing decomposition is diagnostic only. v93 without wire parasitics has
global setup/hold −4511.33/−3650.97 ps. With clocks also idealized, setup/hold
is −2426.23/−372.82 ps; long inserted read-pointer chains contribute to the
setup failure. Raw mapped v75, before targeted physical buffers, has
−8205.58 ps setup under ideal clocks/wires, dominated by an INV driving
1281 loads and a NAND driving 194 loads. This proves poor fanout treatment;
it does **not** prove that the intrinsic RTL logic depth alone fails 1 GHz.
Neither idealized report substitutes for routed setup/hold qualification.

The next RTL candidate v94 adds an elastic two-entry packet queue between
gather and output compaction. It cuts the direct final-queue credit to
gather-ready chain and adds one empty-path cycle, sustaining one packet per
cycle. Existing 38-bit local queue-lane modules are reused; every submodule
body, including all tile/PE arithmetic, is byte-identical. Full-DUT acceptance
passed all 2752 stream cases, mixed backpressure, reset, original 64/80-cycle
limits, no input bubbles and 256-PE structure. Top state rises from 262077
to 281961 bits, below the unchanged 306304-bit limit. Candidate source:
`${T10_SCRATCH_ROOT}/t10_qualification/v94_gather_transport/rtl/npu_systolic_matmul_16x16.sv`.
SHA-256: `15af9a93cb6c9e0b0eb2ca4d1bccf18c65f51544eb1414969c148be46553052f`.
It is not yet physically qualified or promoted to the frozen reference.

Candidate v96 merges adjacent row-group encoded vectors by associative OR
before transport storage. Full-DUT functional acceptance has now passed all
2752 cases, mixed backpressure, reset, original 64/80-cycle limits, no input
bubbles and the 256-PE structural check. Top state is 272105 bits, an increase
of 10028 over v65 and below the unchanged 306304-bit cap. Source SHA-256:
`464b779120bba888c86e11b36dfcb759883be20b2119d764d13efd0794fcca1d`.
Qualification receipt SHA-256:
`dfab5a6722a3b55ad99045ee6aa92c225c0f081f66f392d04d61784cc664eeca`.

The matching v97 synthesis completed with zero Yosys check problems and
sixteen tile macro instances. Hierarchical mapped cell count is 216693,
compared with 167131 for v75. Logical synthesis area is 7722564.682220,
compared with 7715277.8315 for v75. These figures include the diagnostic tile
Liberty area, not the tile LEF placement footprint; they are not routed PPA.
The new RTL has not completed placement, CTS or routing and is not promoted
to the frozen reference. The v93 physical reports describe the older RTL
only and must not be attributed to v96/v97.

`run_t10_top_transport_synth_probe.sh` requires an exact matching full-DUT
qualification receipt before synthesis. Subsequent work must shorten the
tile-to-gather path using register locality and pipeline stages, then repair
the complete clock tree, interfaces and routed timing. Repeated detailed
routing cannot solve known multi-millimeter single-stage connections.

### Earlier complete-DUT experiments

The complete reference remains a 16×16 DUT: sixteen 4×4 tile macros and
256 PEs. The active RTL SHA-256 is
`0c7646d7019e45477582faba0605f1c3ba557810a61cb617844aeeb24b632622`.
The detailed record below this section describes earlier experiments.

- Tile v54 (`ic_t10_frozen_tile_v54_onehot_slvtclk_wideclk_grt_m7_wc_p1000_seed11`)
  has internal register-to-register GRT setup/hold slack +33.89/+51.10 ps
  and zero global-route overflow. External I/O checks are not all passing;
  this GRT abstract is a probe, not the final extracted three-seed baseline.
- Full top v55/v61 was rejected: the 0.90 GPL stopping threshold retained
  clumped shell placement; GRT failed pin access at `_12088_/SN`.
- Full top v63 uses 0.10 stopping thresholds in both placement and resize.
  Resize converged at iteration 689 and wrote `3_4_place_resized.odb`.
  All 180909 shell cells are outside the 16 tile macros. An independent
  geometric audit nevertheless found 1124131 cell intersection pairs
  involving 156759 cells; v63 is not a legal placement checkpoint.
- Full top v64's group-based OpenDP legalization was stopped after 15 minutes
  without a checkpoint. v66 released the temporary GPL channel groups but
  exited with code 241 and no output ODB. Both are superseded.
- Full top v68 (`ic_t10_frozen_top_v68_tilev54_interval_legal_m7_wc_p1000_seed11`)
  uses actual row fragments and interval occupancy. Placement production took
  49.9 seconds and 822836 KiB peak RSS; all 180909 shell cells were placed.
  Native `check_placement` passed (18.1 seconds, about 43 GiB peak RSS), and
  independent geometry found zero cell/cell and cell/macro intersections.
  This is the verified pre-CTS checkpoint. The CTS runner prefers its legal
  ODB; `T10_REQUIRE_LEGAL_PLACEMENT=1` makes absence an error.
- Full top v70 completed CTS on v68, with M6/M7 and the wide-clock NDR. The
  tree is saved both immediately after topology construction and at the end
  of the stage. Placement-estimated total setup WNS remains -324401.84 ps;
  this is a rejected timing result, not a baseline measurement.
- Full top v71 re-legalized the complete post-CTS shell (191265 standard cells
  plus 16 macros) in 13.1 seconds. Both native and independent geometry checks
  passed with zero overlaps. The GRT attempt passed pin access for all
  660475 standard-cell pins and the macro pins (both missing-access counts
  zero), then exited with code 241 during grid initialization, without a
  `5_1_grt.odb`. Peak RSS was 86254860 KiB; the termination reason is not
  established by the log. Its launch used an 80 GiB minimum MemAvailable.
  The 570 DBU routing grid across a 10500 um scaled die needs investigation
  before repeating this memory-heavy stage. In the installed source,
  `dbBlock::getGCellTileSize()` derives the tile size from track spacing,
  rather than an existing dbGCellGrid pattern; changing the latter alone
  therefore does not establish a smaller global-router memory footprint.
  No final routed timing or PPA pass is claimed yet.
- Full top v72 isolated GCell probe changes only the getter's pitch multiplier
  from 15 to 60 (570 to 2280 DBU), with unchanged tracks and capacity code.
  It uses a private hash-guarded executable; the installed tool is untouched.
  `physical/openroad_grid_probe/make_probe.py` records the source equivalent,
  original/executable hashes and all six changed bytes. This is diagnostic
  evidence only; a source-built tool and frozen evaluation policy are required
  before any such configuration becomes release evidence.
  Native PA passed again and now has an atomic `4_cts_pin_access.odb`
  checkpoint plus SDC, completion receipt and SHA-256. GRT passed grid
  initialization. The 30-iteration search was deliberately stopped in favor
  of a bounded diagnostic; this is not an observation-timeout restart.
- Full top v73 resumed that exact verified native PA checkpoint without
  repeating PA; active RSS after GRT initialization was about 26 GiB, compared
  with about 55 GiB in v72 retaining the PA process's allocations. Native
  FastRoute soft-NDR fallback resets its iteration counter to 1, so a nominal
  three-iteration limit does not bound the total run. This probe was stopped
  after repeated retries of local clock nets. Its log and stop reason are
  retained; no routing or timing pass is claimed.
- Full top v74 (`ic_t10_frozen_top_v74_tilev54_gcell60_backbone_m7_wc_p1000_seed11`)
  completed the complete top's diagnostic GRT. It retains wide M6/M7 NDR on 346
  backbone/upper-CTS/macro-input nets, and uses ordinary M6/M7 rules on 5990
  local clock branches. Connectivity, placement, 16 macros, 256 PEs, the SDC
  and the macro timing models are unchanged. The exact net selection is saved
  in `t10_clock_ndr_policy.tsv`. It resumes the same PA checkpoint; narrowing
  local routing rules does not invalidate access legal under the wider rules.
  The route hook now saves the ODB, guides and exact global-route segments
  immediately on successful return, before lengthy STA reports. A full-DUT
  path-class diagnostic follows the ordinary route report. Results remain
  diagnostic, not baseline qualified. GRT took 361 seconds; the complete
  ORFS stage took 467.7 seconds and 31311640 KiB peak RSS (about 29.9 GiB).
  The saved routing covers 208431 nets with 41408 units of overflow.
  Setup WNS is -193462.17 ps, hold WNS -257669.56 ps; timing is rejected.
  The native report's total resource count overflows a signed 32-bit integer;
  use per-layer resources, not its negative aggregate capacity/usage percent.
  ODB, SDC, guides and exact route segments are retained for faithful replay.
  Shell-only vectorless power is about 5.05 W, with macro power absent; this
  is neither a hierarchical DUT total nor qualified activity-based power.
- The original v74 path-class helper rebuilt STA pin patterns from escaped
  OpenDB names and missed macro pins. Its global native WNS/hold report is
  still authoritative, but that original filtered diagnostic is incomplete.
  The helper now selects STA cell/pin objects directly. Replaying saved ODB
  and route segments reproduced both global slacks exactly, with 16 tile
  macros, 28480 macro output pins and 12032 macro data input pins included.
  Corrected reports are under `saved_route_retime/`, separate from the
  original report. The replay completed without new placement or routing.
- A complete-top geometry audit found 2042 cell-driven clock branches longer
  than 1000 um, 1398 longer than 2000 um, and a 7870.058 um maximum. These are
  unbuffered individual driver-to-load branches, not cumulative tree paths.
  `v74_clock_geometry.json` retains every branch and physical endpoint.
  The worst hold endpoint's clock slew is 86823.59 ps; its reported library
  hold time is extrapolated to 239115.83 ps. Clock transition quality must be
  repaired before treating the extreme hold result as a useful margin budget.
  Matching SHA-256 proves v70 CTS really used the verified v68 legal ODB;
  these long branches are not evidence of accidentally selecting v63.
- Full-top pop-count candidate v75 synthesis completed with 16 tile macros
  and zero Yosys check problems. It has 167131 cells including shell helper
  submodules, versus 167225 for frozen v55; the black-boxed tile interiors are
  not included in those counts. `rtl_delta.json` proves the only logic change
  is the top pop predicate and all submodule definitions are byte-identical.
  Its 2752-case functional/reset/256-PE qualification was verified by hash.
  The frozen RTL remains unchanged pending physical qualification.
- Full top v76 repairs the verified v72 post-CTS clock geometry without
  moving or replacing any of the original 191281 instances. All original
  non-clock pin connectivity and clock load/driver sets are preserved; every
  inserted chain is checked to return to its exact original driver through
  positive BUFx24 buffers. It repairs 2598 branches with 15709 new buffers,
  sharing identical route prefixes. The longest driver/load Manhattan branch
  falls from 7870.058 to 299.798 um; none remains above 300 um. These are
  geometry results, not a routed timing pass. Because existing stride-16 rows
  were locally full, 2929 row fragments at 613 additional Y coordinates were
  restored at 17.28 um reserve pitch, keeping all original cells unchanged.
  OpenROAD's native placement check passed in 19.76 seconds at 56635592 KiB
  peak RSS; independent geometry reports 206974 cells, zero intersection
  pairs, and sixteen fixed macros. The producer took 9.18 seconds and under
  0.9 GiB. Fresh native PA passed with zero inaccessible cell or macro pins
  in 101.40 seconds at 71244120 KiB peak RSS. It ended at an atomic recovery
  checkpoint to release PA allocations before global routing; redundant ODBs
  were removed, freeing 1168162816 allocated bytes while retaining the native
  placement and PA checkpoints.
  CTS remains on M6/M7, and this mixed-SLVT/coarse-grid candidate remains a
  diagnostic, not an RVT three-seed release baseline.
- Full-top v77 resumed the exact v76 PA checkpoint and completed diagnostic
  GRT with 224140 nets. Overflow fell to 14837 (v74: 41408), setup-clock skew
  magnitude to 2814.95 ps (v74: 49320.93), and internal hold WNS to -2457.66 ps
  (v74's global hold: -257669.56). Global hold WNS is now -16343.19 ps, on
  input b_scale[165] to ingress_b_scale[165]; common clock insertion latency
  dominates this I/O check. Setup remains rejected at -197520.08 ps: the
  output-valid/final_pop data cone has 50560.31 ps and 69393.46 ps wire arcs
  and out-of-range data slew. Shell-only vectorless power falls from 5.05357
  to 0.77372 W; neither measurement includes macro internals or qualifies
  workload power. Original clock/data geometry, constraints and macro views
  remain unchanged. Soft-NDR fallback still reset routing iteration counts;
  native GRT took 11:06. These improvements do not qualify a baseline.
- v77 also exposed a defect in the v76 channel-path producer: points on the
  same channel were forced through a grid intersection, so some ~300 um
  source-trunk connections detoured by up to 8.57x. v78 adds direct legal
  channel and orthogonal paths. v79 additionally uses fixed 200 um distances
  from shared origins; subdividing each load's length evenly had destroyed
  shared prefixes. The v79 producer preserves the same original geometry and
  data hash, repairs the same 2598 branches with only 11287 new buffers, and
  retains the 299.798 um maximum. v79 native placement validation passed in
  19.51 seconds at 56624316 KiB RSS; independent geometry confirms 202552
  cells with zero overlaps and sixteen macros. Same-library/same-SDC
  placement-RC diagnostics show global hold WNS improving from v76's
  -24973.67 to v79's -12977.07 ps, but setup-clock skew remains about 4.7 ns.
  These estimates are not routed timing. Fresh PA/GRT has intentionally not
  been repeated while known output control data paths still fail badly.
  v78 is superseded; its ODB was deleted (391569408 bytes freed), retaining
  mutation reports and source snapshots. Exact producer snapshots for
  v76/v78/v79 were reconstructed/retained and match their recorded SHA-256.
- Diagnostic candidate v80 implements the prequalified v65 pop-count
  predicate in the mapped full top by rewiring only `_05961_/B` from the
  OR4 output to existing queue nonempty decoder `_06006_/Y`. The producer
  asserts the NAND/BUF/count-flop cone and preserves all geometry, clocks,
  masters and every other connection by hash. It is not yet a mapped full-DUT
  functional qualification and does not change the frozen reference. The
  same placement-RC model's setup WNS improves from -312920.25 (v79) to
  -250874.17 ps; the worst path moves to final_push, with a 135735.06 ps
  wire arc into its first lane repeater. Diagnostic v81 spreads all 2304
  existing positive lane repeaters in 192 chains across their legal channel
  paths. Every register, macro, clock and net connection remains unchanged;
  setup estimate improves to -234623.39 ps, still rejected. Last-stage
  fanout remains geographically split, with a 5186.95 um maximum branch.
  The next data correction must split those physical fanout branches and
  address controller locality; moving a serial chain toward one median load
  does not solve its other remote loads. v81 has not passed native placement
  or routed timing, so no heavy routing/release pass is claimed.
- The v63 placement timing report also shows a long `final_pop` control path:
  serial lane repeaters have clustered near their sinks rather than being
  distributed along the long branch. Legalization does not by itself prove
  this RC problem solved. Inspect physical segment lengths and then routed
  timing before choosing the next correction.
- The pop-count RTL candidate SHA-256
  `68da56e51120c4dd6b34cfd7100409c47b13d661cb97845acd8a2566c2805531`
  replaces the four-slot output-valid reduction in `final_pop` with nonempty
  queue occupancy. Exhaustive queue-state exploration checked 1381 reachable
  states and 44192 transitions. Full-DUT qualification passed 2752 streaming
  cases with mixed backpressure, the reset probe, and 256-PE structure checks.
  Candidate and reports are in
  `${T10_SCRATCH_ROOT}/t10_qualification/v65_popcount`.
  It has not replaced the frozen reference or physical source hash above.

Only one T10 OpenROAD process may run. Admit a stage only with at least
50 GiB MemAvailable and no active OpenROAD process. Keep CTS on M6/M7;
clock use of M8/M9 is forbidden. The official baseline still requires all
three physical levels, the full-DUT gates, three seeds, and activity-based
hierarchical power evidence in the public T10 PPA contract.

## Historical closure investigations

This record governs the 1 GHz ASAP7/WC physical reference. Placement-only
slack is a diagnostic; the acceptance point is routed, extracted STA with
all internal and interface setup/hold checks active.

## Current design and measured failure

The 4×4 tile floorplan is about 2.1 mm square. It contains 16 PE macros,
four result-bank macros, and 535 ordinary clock sinks. The tested clock port
is near the bottom edge at (500.46, 0) µm. The original OpenROAD CTS split
macro and register sinks into separate subtrees. The macro branch had about
3072 µm mean sink wire length and 9 buffer stages; the register branch had
about 834 µm and 9–10 stages.

| Check | Measured value | Consequence |
| --- | ---: | --- |
| Tile placement, ideal clock | +62.97 ps setup slack | Diagnostic only |
| Original CTS, propagated clock | −3493.04 ps setup slack | Rejected |
| Original CTS, internal PE→bank | −1183.86 ps setup slack | Rejected independently of virtual I/O clock |
| Original CTS hold repair | 22401 inserted buffers; maximum reached | Flow failed |
| Best tested macro cluster 2, 100 µm buffer pitch, old PE view | −757.98 ps worst internal setup slack | Still rejected |
| Clock entry moved from x≈500 to x≈1050 µm in that experiment | −2425.60 ps total WNS | Improves I/O comparison; internal setup still fails |

The current SDC uses a 1000 ps real clock plus a zero-latency virtual clock
for 200 ps input and output delays. This models data launched and captured
relative to the tile clock pin. A system integration contract with upstream
and downstream clock insertion may use a different **predeclared** virtual
clock source latency, but changing that number after seeing WNS would mask
the failure. The internal paths above remain failing either way.

## Closure method

1. **Characterize each hard macro.** Verify final routed Liberty clock input
   capacitance, min/max internal clock-tree path, output clock-to-Q, input
   setup/hold, and matching LEF pin geometry. Keep the model and physical
   view from the same ODB/SPEF. Reject provisional placement models for final
   tile scoring.
2. **Budget each path class.** Check PE→PE horizontal and vertical links,
   PE→bank result links, local hop registers, guard→bank control, macro→port,
   and port→macro separately. A path whose launch clock-to-Q plus wire plus
   capture setup exceeds 1000 ps at zero skew requires data-path or interface
   redesign before CTS tuning.
3. **Design the clock distribution.** Place the clock entry deliberately;
   select clock routing layers, buffer cells, macro clustering and tap sites
   from measured sink positions and load. Inspect branch insertion delay,
   effective macro internal latency, transition/capacitance, and launch-to-
   capture skew for each path class. OpenROAD's macro insertion-delay balance
   alone is not a timing-driven useful-skew solution.
4. **Run CTS with active setup and hold.** Preserve both max and min timing
   checks; do not add false paths or multicycle paths to make a one-cycle
   systolic link pass. Measure port paths under the frozen interface contract.
   Stop before detailed route if large internal violations persist.
5. **Route and extract.** Require zero global-route overflow, successful
   detailed route, zero reported route DRC and antenna violations, zero setup
   and hold violations from extracted SPEF, and valid VDD/VSS connectivity.
   Record clock insertion, skew, buffer count, cell area, routed wire area,
   power estimate and WNS/TNS alongside the exact SDC, Liberty and LEF hashes.

The `bt_out` cone-guided PE reproduces with +103.22 ps placement-estimated
setup slack and legal post-CTS placement, but its propagated-clock WNS is
−377.16 ps at `a_out[5]`: about 697 ps register clock insertion followed
by a 565 fF output-wire segment. Moving the full `a_out` and `at_out`
register/buffer cones changes the standalone PE CTS WNS to −271.18 ps;
the worst remaining endpoints are `a_out` and `b_out` ports. This confirms
that output-cone wire load and clock insertion must be treated together.
Those experiments do not replace the provisional PE view. The `bt_out`
variant global route was stopped after fourteen extra overflow iterations:
the −377.16 ps post-CTS result had already rejected it. The original PE
detail route was later stopped at 2579 provisional DRT violations after
three hours because that superseded version had post-GRT WNS −43.63 ps.
No 4×4 tile or full 16×16 design has passed the clock-tree closure gate yet.

An M8-equivalent **estimated** clock RC sensitivity on the PE reduced
propagated-clock WNS from −271.18 to −169.72 ps on the bt+a+at boundary
placement; moving complete b_out cones brought it to −160.82 ps. It is
not signoff evidence until the clock is actually routed on the intended
high layers and extracted. A trial relocation of the `at_out[27]` valid
FF worsened WNS to −296.24 ps because that FF also feeds internal logic.
This path requires a dedicated output driver/registered copy or a different
physical topology; moving a shared FF alone is rejected.

The PE now has an explicit M8–M9 global-routing experiment. It is a
candidate, not a fixed CTS prescription: the final layer choice must
compare M6–M9, M7–M9, and M8–M9 from the same pre-CTS placement, with each
clock RC estimate matched to its tested layer range. The comparison must
record actual clock route layer usage, via count, insertion-delay spread,
skew, setup/hold, overflow, detail-route DRC and extracted STA. M9 power
grid occupancy and lower-layer clock-pin access must be included. All
other CTS, placement and SDC settings remain frozen across this sweep.
`physical/t10_clock_route_audit.tcl` is staged for sourcing after final
parasitic extraction. It tallies actual OpenDB CLOCK-net segments, via
shapes and per-layer routed span; it does not treat global-route guides as
physical clock usage. It must be run and checked against the final routed
ODB before selecting a layer range.
The installed ASAP7 OpenROAD platform defaults to M4–M7 for clock routing
(`MIN_CLK_ROUTING_LAYER=M4`, `MAX_ROUTING_LAYER=M7`); M8–M9 is an intentional
experiment beyond that default. The technology LEF defines M8 as horizontal
and M9 as vertical routing layers, while this PE's M9 also carries PDN
stripes. Do not call the upper-layer experiment standard ASAP7 CTS practice
or accept estimated M8 clock RC as extracted routed timing.

OpenROAD command behavior is documented in the upstream
[CTS](https://openroad.readthedocs.io/en/latest/main/src/cts/README.html)
and [repair-clock-nets](https://openroad.readthedocs.io/en/latest/main/src/rsz/README.html#repair-clock-nets)
manuals. A current upstream [macro-latency issue](https://github.com/The-OpenROAD-Project/OpenROAD/issues/10901)
also describes why fixed insertion-delay balancing can mishandle macros
that both launch and capture data; that issue is background, not proof that
this T10 design passes timing.
