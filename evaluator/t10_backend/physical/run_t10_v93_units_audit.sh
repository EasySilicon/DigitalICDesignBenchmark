#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
flow_root=${T10_ORFS_ROOT}/flow
source_dir=$flow_root/results/asap7/npu_systolic_matmul_16x16/ic_t10_candidate_top_v93_clean_controls_m7_wc_p1000_seed11
audit=${T10_SCRATCH_ROOT}/t10_frozen_top/v93_input_configuration_audit
source "$backend_root/physical/t10_acquire_openroad_slot.sh"
sha256sum -c "$source_dir/placement_clock_estimate_inputs.sha256" > "$audit/sta_provenance_check.log"
libs=()
while read -r digest path; do
  if [[ $path == *.lib || $path == *.lib.gz ]]; then libs+=("$path"); fi
done < "$source_dir/placement_clock_estimate_inputs.sha256"
[[ ${#libs[@]} == 7 ]]
export T10_AUDIT_LIBS="${libs[*]}"
export T10_AUDIT_ODB=$source_dir/4_cts_clock_repair_pending.odb
export T10_AUDIT_SDC=$source_dir/4_cts.sdc
export T10_AUDIT_SETRC=$flow_root/platforms/asap7/setRC.tcl
cp "$backend_root/physical/t10_audit_v93_units.tcl" "$audit/units_driver.tcl"
sha256sum "$T10_AUDIT_ODB" "$T10_AUDIT_SDC" "$T10_AUDIT_SETRC" \
  "$audit/units_driver.tcl" "${libs[@]}" > "$audit/units_inputs.sha256"
ulimit -v 4194304
/usr/bin/time -v nice -n 10 "${T10_OPENROAD_EXE}" -no_init -exit -threads 1 \
  "$audit/units_driver.tcl" > "$audit/units.log" 2>&1
printf 'T10_V93_NATIVE_UNITS_AUDIT_FINISHED\n'
