ifndef T10_BACKEND_ROOT
T10_BACKEND_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
endif
include $(T10_BACKEND_ROOT)/config.mk
export PLATFORM = asap7
export DESIGN_NAME = t10_reference_pe
export VERILOG_FILES = $(T10_REFERENCE_RTL)
export SDC_FILE = $(T10_BACKEND_ROOT)/physical/t10_frozen_pe/constraint.sdc
export CORE_UTILIZATION = 24
export CORE_ASPECT_RATIO = 1
export CORE_MARGIN = 0.5
export PLACE_DENSITY = 0.24
export DETAIL_PLACEMENT_ARGS = -max_displacement 100
export SYNTH_USE_SYN = 0
export SYNTH_HIERARCHICAL = 0
export CORNER = WC
export GPL_ROUTABILITY_DRIVEN = 0
export SYNTH_BLACKBOXES = t10_reference_fp_quad_class0_exact t10_reference_fp_quad_class1_exact t10_reference_fp_quad_class2_exact t10_reference_int_group t10_reference_cpa_postprocess
export ADDITIONAL_LEFS = \
  $(T10_FP0_LEF) \
  $(T10_FP1_LEF) \
  $(T10_FP2_LEF) \
  $(T10_INT_LEF) \
  $(T10_CPA_LEF)
export ADDITIONAL_LIBS = \
  $(T10_FP0_LIB) \
  $(T10_FP1_LIB) \
  $(T10_FP2_LIB) \
  $(T10_INT_LIB) \
  $(T10_CPA_LIB)
export PDN_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_pe/pdn.tcl
export POST_PDN_TCL = $(T10_BACKEND_ROOT)/physical/t10_pe_post_pdn_four_vss_bridges.tcl
export IO_CONSTRAINTS = $(T10_BACKEND_ROOT)/physical/t10_frozen_pe/io.tcl
export MACRO_PLACEMENT_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_pe/macro_place.tcl
export PRE_GLOBAL_PLACE_SKIP_IO_TCL = $(T10_BACKEND_ROOT)/physical/t10_pe_forwarding_regions.tcl
export PRE_GLOBAL_PLACE_TCL = $(T10_BACKEND_ROOT)/physical/t10_pe_forwarding_regions.tcl
export PRE_CTS_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_pe/pre_cts_m6_m7.tcl
export MAX_ROUTING_LAYER = M7
export MIN_CLK_ROUTING_LAYER = M6
export ROUTING_LAYER_ADJUSTMENT = 0
# Preserve enough global-route margin for the measured detailed-route RC
# delta.  The v14 seed-11 probe lost 57.8 ps setup and 64.0 ps hold between
# GRT and extracted post-route timing.  A 125 ps hold target exhausted the
# CTS buffer limit, while 75 ps still covers the measured 13.9 ps miss.
export HOLD_SLACK_MARGIN = 75
export SETUP_SLACK_MARGIN = 175
export SKIP_INCREMENTAL_REPAIR = 0
export CTS_CLUSTER_SIZE = 64
export CTS_CLUSTER_DIAMETER = 100
export CTS_ARGS = -sink_clustering_enable -repair_clock_nets -sink_clustering_size 64 -sink_clustering_max_diameter 100 -no_insertion_delay
export SKIP_CTS_REPAIR_TIMING = 0
export GRT_SEED = $(T10_LAYOUT_SEED)
export OR_SEED = $(T10_LAYOUT_SEED)
