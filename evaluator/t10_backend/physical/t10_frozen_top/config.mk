export PLATFORM = asap7
export DESIGN_NAME = npu_systolic_matmul_16x16
export VERILOG_FILES = /home/reefshark/research/agent_os/ic_bcmk_eval_private/refs/T10/rtl/npu_systolic_matmul_16x16.sv
export SDC_FILE = /home/reefshark/research/agent_os/ic_bcmk_eval_private/physical/t10_frozen_top/constraint.sdc

# Complete 16x16 DUT as sixteen routed 4x4 tile macros.  Each routed tile is
# 2500 um square.  The 10500 um top leaves 100 um channels between tiles and
# 100 um of perimeter room for I/O and top-shell logic.
export DIE_AREA = 0 0 10500 10500
export CORE_AREA = 0.54 0.54 10499.46 10499.46
export PLACE_DENSITY = 0.60
export SYNTH_USE_SYN = 0
export SYNTH_HIERARCHICAL = 0
export CORNER = WC
export GPL_ROUTABILITY_DRIVEN = 0
# Timing-driven RePlAce calls the generic repair_design pass before placement.
# The routed tile timing model contains conservative macro-boundary arcs; on
# this 16-tile parent that pass interpreted them as long ordinary nets and
# created 364k cells (+238%) while worsening estimated WNS to -12.94 ns.
# Keep parent placement wirelength-driven and repair only measured shell paths
# after placement/CTS.
export GPL_TIMING_DRIVEN = 0
# RePlAce reports 0.84 initial overflow in the central shell channel.  A 0.90
# stopping threshold accepted the unspread initial solution and left many
# standard cells coincident near the array centre.  Continue density solving
# until the channel placement is suitable for pin access and global routing.
export GLOBAL_PLACEMENT_ARGS = -bin_grid_count 128 -overflow 0.10
export DONT_BUFFER_PORTS = 1
export SYNTH_BLACKBOXES = t10_reference_tile_4x4
export ADDITIONAL_LEFS = $(T10_TILE_LEF) $(T10_CTS_CELL_LEF)
export ADDITIONAL_LIBS = $(T10_TILE_LIB) $(T10_POST_CTS_CELL_LIB)
export PDN_TCL = /home/reefshark/research/agent_os/ic_bcmk_eval_private/physical/t10_frozen_top/pdn.tcl
export IO_CONSTRAINTS = /home/reefshark/research/agent_os/ic_bcmk_eval_private/physical/t10_frozen_top/io.tcl
export MACRO_PLACEMENT_TCL = /home/reefshark/research/agent_os/ic_bcmk_eval_private/physical/t10_frozen_top/macro_place.tcl
export POST_GLOBAL_PLACE_SKIP_IO_TCL = /home/reefshark/research/agent_os/ic_bcmk_eval_private/physical/t10_frozen_top/top_shell_regions.tcl
export TAPCELL_TCL = /home/reefshark/research/agent_os/ic_bcmk_eval_private/physical/t10_frozen_top/tapcell_reference.tcl
export PRE_FLOORPLAN_TCL = /home/reefshark/research/agent_os/ic_bcmk_eval_private/physical/t10_frozen_top/skip_floorplan_timing_reference.tcl
export PRE_RESIZE_TCL = /home/reefshark/research/agent_os/ic_bcmk_eval_private/physical/t10_frozen_top/skip_resize_reference.tcl
export PRE_DETAIL_PLACE_TCL = /home/reefshark/research/agent_os/ic_bcmk_eval_private/physical/t10_frozen_top/pre_detail_place_sparse_rows.tcl
# The stride-16 sparse row map keeps the 10.5 mm top-level OpenDP footprint
# below host memory, but the default 100-row vertical search left one shell
# gather cell unplaced in v44.  Search farther within the same sparse map;
# this changes neither row capacity nor the macro/channel floorplan.
ifneq ($(strip $(T10_DETAIL_PLACEMENT_ARGS_OVERRIDE)),)
export DETAIL_PLACEMENT_ARGS = $(T10_DETAIL_PLACEMENT_ARGS_OVERRIDE)
else
export DETAIL_PLACEMENT_ARGS = -max_displacement {500 1000}
endif
export T10_REFERENCE_RELEASE_GPL_REGIONS ?= 0
export PRE_CTS_TCL = /home/reefshark/research/agent_os/ic_bcmk_eval_private/physical/t10_frozen_top/pre_cts_m6_m7.tcl
export POST_CTS_TCL = /home/reefshark/research/agent_os/ic_bcmk_eval_private/physical/t10_frozen_tile/post_cts_wide_clock_ndr.tcl
ifeq ($(T10_REFERENCE_GRID_PROBE),1)
export PRE_GLOBAL_ROUTE_TCL = /home/reefshark/research/agent_os/ic_bcmk_eval_private/physical/t10_frozen_top/pre_global_route_checkpoint.tcl
export POST_GLOBAL_ROUTE_TCL = /home/reefshark/research/agent_os/ic_bcmk_eval_private/physical/t10_frozen_top/post_global_route_diagnostic.tcl
endif
export IO_PLACER_H = M6
export MAX_ROUTING_LAYER = M7
export MIN_CLK_ROUTING_LAYER = M6
export ROUTING_LAYER_ADJUSTMENT = 0
export HOLD_SLACK_MARGIN = 0
export SETUP_SLACK_MARGIN = 0
export SKIP_INCREMENTAL_REPAIR = 1
export SKIP_ANTENNA_REPAIR = 1
export CTS_CLUSTER_SIZE = 64
export CTS_CLUSTER_DIAMETER = 150
# Build the parent tree on M6/M7 with normal insertion delay.  The sixteen
# routed tile macros are clustered in small local groups so their clock pins
# do not become one long high-fanout branch across the 9.5 mm top level.
# The default ORFS -repair_clock_nets pass scans the complete 10.5 mm parent
# clock network after topology generation.  With 55k register sinks it spent
# more than 15 minutes without producing a checkpoint.  CTS already buffers
# both parent clocks; skip that redundant pre-repair operation for this
# hierarchical reference probe and measure the resulting tree directly.
ifneq ($(strip $(T10_CTS_ARGS_OVERRIDE)),)
export CTS_ARGS = $(T10_CTS_ARGS_OVERRIDE)
else
export CTS_ARGS = -sink_clustering_enable -distance_between_buffers 200 -macro_clustering_size 2 -macro_clustering_max_diameter 400 -balance_levels -apply_ndr half
endif
export SKIP_CTS_REPAIR_TIMING = 1
export T10_REFERENCE_SKIP_CTS_DPL = 1
export T10_REFERENCE_DPL_ROW_STRIDE = 16
export T10_REFERENCE_CTS_ROW_STRIDE = 1
export T10_REFERENCE_CLOCK_TRUNK = 1
export T10_REFERENCE_CLOCK_TRUNK_CELL ?= BUFx24_ASAP7_75t_R
# Bound detailed routing for this benchmark reference run.  The emitted DRC
# report remains part of the evidence; the full 16x16 PPA baseline must not be
# delayed by the default 64-iteration tapeout-oriented search.
export DETAILED_ROUTE_END_ITERATION = 1
export GRT_SEED = $(T10_LAYOUT_SEED)
export OR_SEED = $(T10_LAYOUT_SEED)
