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
export SYNTH_USE_SYN = 0
export SYNTH_HIERARCHICAL = 0
export CORNER = WC
export GPL_ROUTABILITY_DRIVEN = 0
export SYNTH_BLACKBOXES = t10_reference_fp_quad_class0_exact t10_reference_fp_quad_class1_exact t10_reference_fp_quad_class2_exact t10_reference_int_group t10_reference_cpa_postprocess
export ADDITIONAL_LEFS = \
  $(T10_ORFS_ROOT)/flow/results/asap7/t10_reference_fp_quad_class0_exact/ic_t10_fp_class0_capture_m7_u42_wc_p1000_seed11/t10_reference_fp_quad_class0_exact_m7.lef \
  $(T10_ORFS_ROOT)/flow/results/asap7/t10_reference_fp_quad_class1_exact/ic_t10_fp_class1_capture_m7_u42_wc_p1000_seed11/t10_reference_fp_quad_class1_exact_m7.lef \
  $(T10_ORFS_ROOT)/flow/results/asap7/t10_reference_fp_quad_class2_exact/ic_t10_fp_class2_capture_fp4csa_m7_u42_wc_p1000_seed11/t10_reference_fp_quad_class2_exact_m7.lef \
  $(T10_SCRATCH_ROOT)/t10_frozen_int_group/evidence_seed11/t10_reference_int_group_pinpromoted.lef \
  $(T10_SCRATCH_ROOT)/t10_frozen_cpa_postprocess/evidence_seed11_repaired/t10_reference_cpa_postprocess_pinpromoted.lef
export ADDITIONAL_LIBS = \
  $(T10_ORFS_ROOT)/flow/results/asap7/t10_reference_fp_quad_class0_exact/ic_t10_fp_class0_capture_m7_u42_wc_p1000_seed11/t10_reference_fp_quad_class0_exact_wc.lib \
  $(T10_ORFS_ROOT)/flow/results/asap7/t10_reference_fp_quad_class1_exact/ic_t10_fp_class1_capture_m7_u42_wc_p1000_seed11/t10_reference_fp_quad_class1_exact_wc.lib \
  $(T10_ORFS_ROOT)/flow/results/asap7/t10_reference_fp_quad_class2_exact/ic_t10_fp_class2_capture_fp4csa_m7_u42_wc_p1000_seed11/t10_reference_fp_quad_class2_exact_wc.lib \
  $(T10_SCRATCH_ROOT)/t10_frozen_int_group/evidence_seed11/t10_reference_int_group.lib \
  $(T10_SCRATCH_ROOT)/t10_frozen_cpa_postprocess/evidence_seed11_repaired/t10_reference_cpa_postprocess.lib
export PDN_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_pe/pdn.tcl
export IO_CONSTRAINTS = $(T10_BACKEND_ROOT)/physical/t10_frozen_pe/io.tcl
export MACRO_PLACEMENT_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_pe/macro_place.tcl
export PRE_GLOBAL_PLACE_TCL = $(T10_BACKEND_ROOT)/physical/t10_pe_pin_escape_soft_plus_blockages.tcl
export PRE_CTS_TCL = $(T10_BACKEND_ROOT)/physical/t10_frozen_pe/pre_cts_m6_m7.tcl
export MAX_ROUTING_LAYER = M7
export MIN_CLK_ROUTING_LAYER = M6
export ROUTING_LAYER_ADJUSTMENT = 0
export SKIP_INCREMENTAL_REPAIR = 1
export CTS_CLUSTER_SIZE = 64
export CTS_CLUSTER_DIAMETER = 100
export CTS_ARGS = -sink_clustering_enable -repair_clock_nets -sink_clustering_size 64 -sink_clustering_max_diameter 100 -no_insertion_delay
export SKIP_CTS_REPAIR_TIMING = 1
export GRT_SEED = $(T10_LAYOUT_SEED)
export OR_SEED = $(T10_LAYOUT_SEED)
