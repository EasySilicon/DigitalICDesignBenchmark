ifndef T10_BACKEND_ROOT
T10_BACKEND_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
endif
include $(T10_BACKEND_ROOT)/config.mk
export PLATFORM = asap7
export DESIGN_NAME = $(T10_FP_DESIGN_NAME)
export VERILOG_FILES = $(T10_REFERENCE_RTL)
export SDC_FILE = $(T10_FP_CONSTRAINT)
export CORE_UTILIZATION = 42
export CORE_ASPECT_RATIO = 1
export CORE_MARGIN = 0.5
export PLACE_DENSITY = 0.42
export SYNTH_USE_SYN = 0
export SYNTH_HIERARCHICAL = 0
export CORNER = WC
export GPL_ROUTABILITY_DRIVEN = 0
export PDN_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_fp_quad/pdn.tcl
export PRE_CTS_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_fp_quad/pre_cts_m6_m7.tcl
ifneq ($(strip $(T10_FP_IO_CONSTRAINTS)),)
export IO_CONSTRAINTS = $(T10_FP_IO_CONSTRAINTS)
endif
export IO_PLACER_H = M6
export MAX_ROUTING_LAYER = M7
export MIN_CLK_ROUTING_LAYER = M6
export ROUTING_LAYER_ADJUSTMENT = 0
ifneq ($(strip $(T10_FP_HOLD_SLACK_MARGIN)),)
export HOLD_SLACK_MARGIN = $(T10_FP_HOLD_SLACK_MARGIN)
export SKIP_INCREMENTAL_REPAIR = 0
else
export SKIP_INCREMENTAL_REPAIR = 1
endif
export CTS_CLUSTER_SIZE = 64
export CTS_CLUSTER_DIAMETER = 100
export CTS_ARGS = -sink_clustering_enable -repair_clock_nets -sink_clustering_size 64 -sink_clustering_max_diameter 100 -no_insertion_delay
export SKIP_CTS_REPAIR_TIMING = 1
export GRT_SEED = $(T10_LAYOUT_SEED)
export OR_SEED = $(T10_LAYOUT_SEED)
