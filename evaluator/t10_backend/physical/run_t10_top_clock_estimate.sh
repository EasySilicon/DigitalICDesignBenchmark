#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
variant=${T10_FLOW_VARIANT:?name the full-top diagnostic variant}
timing_mode=${T10_PLACEMENT_TIMING_MODE:-placement}
case "$timing_mode" in placement|placement_ideal_clocks|cell_only|ideal_clocks_cell_only) ;; *) echo "invalid diagnostic timing mode" >&2; exit 2;; esac
result_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant
platform=${T10_ASAP7_PLATFORM}
input=${T10_CLOCK_ESTIMATE_ODB:-$result_dir/4_cts_clock_repair_pending.odb}
t10_require_file "$input"
libs=()
for pattern in '*_AO_RVT_SS*' '*_INVBUF_RVT_SS*' '*_OA_RVT_SS*' '*_SEQ_RVT_SS*' '*_SIMPLE_RVT_SS*' '*_INVBUF_SLVT_SS*'; do
  while IFS= read -r path; do libs+=("$path"); done < <(find "$platform/lib/NLDM" -maxdepth 1 -name "$pattern" -type f)
done
[[ ${#libs[@]} == 6 ]]
libs+=("$orfs_root/flow/results/asap7/t10_reference_tile_4x4/ic_t10_frozen_tile_v54_onehot_slvtclk_wideclk_grt_m7_wc_p1000_seed11/t10_reference_tile_4x4_wc.lib")
export T10_RETIME_LIBS="${libs[*]}"
export T10_RETIME_ODB=$input
export T10_RETIME_SDC=$result_dir/4_cts.sdc
export T10_RETIME_SETRC=$platform/setRC.tcl
export T10_CLOCK_ESTIMATE_MODE=$timing_mode
if [[ $timing_mode == placement ]]; then
  report_base=placement_clock_estimate
else
  report_base=${timing_mode}_clock_estimate
fi
export T10_CLOCK_ESTIMATE_REPORT=$result_dir/$report_base.rpt
driver=$result_dir/${report_base}_driver.tcl
cp "$backend_root/physical/t10_frozen_top/estimate_clock_repair.tcl" "$driver"
sha256sum "$input" "$T10_RETIME_SDC" "$driver" "$T10_RETIME_SETRC" "${libs[@]}" \
  > "$result_dir/${report_base}_inputs.sha256"
source "$backend_root/physical/t10_acquire_openroad_slot.sh"
ulimit -v 50331648
/usr/bin/time -v nice -n 10 "${T10_OPENROAD_EXE}" -no_init -exit -threads 2 \
  "$driver" \
  > "${T10_SCRATCH_ROOT}/t10_frozen_top/${variant}_${report_base}.log" 2>&1
