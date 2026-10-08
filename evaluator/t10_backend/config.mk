# Shared path defaults. Also works when invoked directly by GNU make.
T10_REPO_ROOT ?= $(abspath $(T10_BACKEND_ROOT)/../..)
T10_EVALUATOR_ROOT ?= $(T10_REPO_ROOT)/evaluator
T10_REFERENCE_ROOT ?= $(T10_EVALUATOR_ROOT)/reference
T10_REFERENCE_RTL ?= $(T10_REFERENCE_ROOT)/T10/rtl/npu_systolic_matmul_16x16.sv
T10_ORFS_ROOT ?= $(T10_REPO_ROOT)/third_party/OpenROAD-flow-scripts
T10_SCRATCH_ROOT ?= $(T10_REPO_ROOT)/work/t10_backend
T10_ASAP7_PLATFORM ?= $(T10_REPO_ROOT)/vendor/asap7
export T10_BACKEND_ROOT T10_REPO_ROOT T10_REFERENCE_RTL T10_ORFS_ROOT
export T10_SCRATCH_ROOT T10_ASAP7_PLATFORM
export PLATFORM_DIR = $(T10_ASAP7_PLATFORM)
