ifndef T10_BACKEND_ROOT
T10_BACKEND_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
endif
include $(T10_BACKEND_ROOT)/config.mk
export PLATFORM = asap7
export DESIGN_NAME = t10_reference_int_group
export VERILOG_FILES = $(T10_REFERENCE_RTL)
export SDC_FILE = $(T10_BACKEND_ROOT)/physical/t10_frozen_int_group/constraint.sdc
export CORE_UTILIZATION = 42
export CORE_ASPECT_RATIO = 1
export CORE_MARGIN = 0.5
export PLACE_DENSITY = 0.42
export SYNTH_USE_SYN = 0
export SYNTH_HIERARCHICAL = 0
export CORNER = WC
export GPL_ROUTABILITY_DRIVEN = 0
export PDN_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_int_group/pdn.tcl
export PRE_CTS_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_int_group/pre_cts_m6_m7.tcl
export IO_PLACER_H = M6
export MAX_ROUTING_LAYER = M7
export MIN_CLK_ROUTING_LAYER = M6
export ROUTING_LAYER_ADJUSTMENT = 0
export GRT_SEED = $(T10_LAYOUT_SEED)
export OR_SEED = $(T10_LAYOUT_SEED)
