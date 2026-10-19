# Map the full-DUT shell; the PE is supplied by its routed gate netlist.
include $(T10_V1_ROOT)/common.mk
export PLATFORM = asap7
export DESIGN_NAME = npu_systolic_matmul_16x16
export VERILOG_FILES = $(T10_V1_RTL)
export SDC_FILE = $(T10_V1_ROOT)/power_gate.sdc
export CORE_UTILIZATION = 24
export PLACE_DENSITY = 0.24
export SYNTH_USE_SYN = 0
export SYNTH_HIERARCHICAL = 0
export SYNTH_KEEP_MODULES = t10_reference_tile_4x4
export CORNER = WC
export SYNTH_BLACKBOXES = t10_reference_pe
export ADDITIONAL_LIBS = $(T10_POWER_PE_LIB)
export ADDITIONAL_LEFS = $(T10_POWER_PE_LEF)
