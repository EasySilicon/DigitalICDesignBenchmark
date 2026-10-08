ifndef T10_BACKEND_ROOT
T10_BACKEND_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
endif
include $(T10_BACKEND_ROOT)/config.mk
export PLATFORM = asap7
export DESIGN_NAME = t10_reference_tile_4x4
export VERILOG_FILES = $(T10_REFERENCE_RTL)
export SDC_FILE = $(T10_BACKEND_ROOT)/physical/t10_frozen_tile/constraint.sdc

# Fixed 2500 um square tile. Sixteen 493.326 um PE macros occupy about 62%
# of the die and leave 100 um internal routing channels for the 92-bit
# systolic links, result banks, and the M6/M7 clock tree.
export DIE_AREA = 0 0 2500 2500
export CORE_AREA = 0.54 0.54 2499.48 2499.56
export PLACE_DENSITY = 0.32
export SYNTH_USE_SYN = 0
export SYNTH_HIERARCHICAL = 0
export CORNER = WC
export GPL_ROUTABILITY_DRIVEN = 0
# Timing driven RePlAce diverges when the 48 small physical guide regions are
# active.  The guides already encode the critical locality; post-place timing
# repair remains enabled below.
export GPL_TIMING_DRIVEN = 0
export GLOBAL_PLACEMENT_ARGS = -bin_grid_count 128
export SYNTH_BLACKBOXES = t10_reference_pe
export ADDITIONAL_LEFS = $(T10_PE_LEF) $(T10_CTS_CELL_LEF)
export ADDITIONAL_LIBS = $(T10_PE_LIB) $(T10_POST_CTS_CELL_LIB)
export PDN_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_tile/pdn.tcl
export IO_CONSTRAINTS = $(T10_BACKEND_ROOT)/physical/t10_frozen_tile/io.tcl
export MACRO_PLACEMENT_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_tile/macro_place.tcl
export PRE_GLOBAL_PLACE_SKIP_IO_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_tile/bank_regions_direct.tcl
export PRE_RESIZE_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_tile/pre_resize_m7.tcl
export PRE_DETAIL_PLACE_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_tile/pre_detail_place.tcl
export PRE_CTS_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_tile/pre_cts_m6_m7.tcl
export POST_CTS_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_tile/post_cts_wide_clock_ndr.tcl
export IO_PLACER_H = M6
export MAX_ROUTING_LAYER = M7
export MIN_CLK_ROUTING_LAYER = M6
export ROUTING_LAYER_ADJUSTMENT = 0
# Five iterations are sufficient for this macro-dominated design: a 30-pass
# probe showed no monotonic reduction after pass 5 because the remaining
# reports sit in zero-capacity macro grids.  Let detailed routing arbitrate
# those local guide overlaps instead of repeating an unproductive GRT search.
export GLOBAL_ROUTE_ARGS = -congestion_iterations 5 -congestion_report_iter_step 1 -allow_congestion -verbose
export HOLD_SLACK_MARGIN = 0
export SETUP_SLACK_MARGIN = 0
# The PE macros already carry extracted timing.  Post-GRT repair_design sees
# their blocked interiors as 84k long nets and attempts a large, congesting
# buffer expansion before detailed routing.  Preserve the placed/CTS netlist
# here; timing is evaluated again from the routed tile abstraction at top.
export SKIP_INCREMENTAL_REPAIR = 1
export SKIP_ANTENNA_REPAIR = 1
# This hierarchy is an evaluator reference macro, not a tapeout block.  Bound
# TritonRoute so a congested tile still yields a routed ODB and an auditable
# DRC report instead of spending hours in the default 64-iteration search.
export DETAILED_ROUTE_END_ITERATION = 1
export CTS_CLUSTER_SIZE = 64
export CTS_CLUSTER_DIAMETER = 150
# The production candidate honors the routed PE clock insertion model.  The
# no-insertion-delay switch is reserved for a checkpointed A/B experiment at
# the tile boundary; it never changes or rebuilds the frozen PE macro.
ifneq ($(strip $(T10_CTS_ARGS_OVERRIDE)),)
export CTS_ARGS = $(T10_CTS_ARGS_OVERRIDE)
else ifeq ($(T10_CTS_NO_INSERTION_DELAY),1)
export CTS_ARGS = -sink_clustering_enable -repair_clock_nets -distance_between_buffers 100 -macro_clustering_size 2 -macro_clustering_max_diameter 100 -apply_ndr half -no_insertion_delay $(T10_CTS_EXTRA_ARGS)
else
export CTS_ARGS = -sink_clustering_enable -repair_clock_nets -distance_between_buffers 100 -macro_clustering_size 2 -macro_clustering_max_diameter 100 -apply_ndr half $(T10_CTS_EXTRA_ARGS)
endif
ifeq ($(T10_SKIP_CTS_REPAIR_TIMING),1)
export SKIP_CTS_REPAIR_TIMING = 1
else
export SKIP_CTS_REPAIR_TIMING = 0
endif
export GRT_SEED = $(T10_LAYOUT_SEED)
export OR_SEED = $(T10_LAYOUT_SEED)
