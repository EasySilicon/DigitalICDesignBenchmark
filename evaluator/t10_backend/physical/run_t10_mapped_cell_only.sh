#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
result_root=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16
result_dir=$result_root/ic_t10_frozen_top_v75_popcount_synth_m7_wc_p1000_seed11
platform=${T10_ASAP7_PLATFORM}
tile_dir=$orfs_root/flow/results/asap7/t10_reference_tile_4x4/ic_t10_frozen_tile_v54_onehot_slvtclk_wideclk_grt_m7_wc_p1000_seed11
libs=()
for pattern in '*_AO_RVT_SS*' '*_INVBUF_RVT_SS*' '*_OA_RVT_SS*' '*_SEQ_RVT_SS*' '*_SIMPLE_RVT_SS*' '*_INVBUF_SLVT_SS*'; do
  while IFS= read -r path; do libs+=("$path"); done < <(find "$platform/lib/NLDM" -maxdepth 1 -name "$pattern" -type f)
done
[[ ${#libs[@]} == 6 ]]
libs+=("$tile_dir/t10_reference_tile_4x4_wc.lib")
export T10_RETIME_LIBS="${libs[*]}"
lefs=("$platform/lef/asap7_tech_1x_201209.lef" "$platform/lef/asap7sc7p5t_28_R_1x_220121a.lef" "$tile_dir/t10_reference_tile_4x4_m7.lef")
export T10_CELL_ONLY_LEFS="${lefs[*]}"
export T10_CELL_ONLY_NETLIST=$result_dir/1_2_yosys.v
export T10_RETIME_SDC=$result_root/ic_t10_candidate_top_v93_clean_controls_m7_wc_p1000_seed11/4_cts.sdc
export T10_CLOCK_ESTIMATE_REPORT=$result_dir/mapped_cell_only.rpt
t10_require_file "$T10_CELL_ONLY_NETLIST"
source "$backend_root/physical/t10_acquire_openroad_slot.sh"
driver=$result_dir/mapped_cell_only_driver.tcl
cp "$backend_root/physical/t10_frozen_top/estimate_mapped_cell_only.tcl" "$driver"
sha256sum "$T10_CELL_ONLY_NETLIST" "$T10_RETIME_SDC" "$driver" "${libs[@]}" "${lefs[@]}" \
  > "$result_dir/mapped_cell_only_inputs.sha256"
ulimit -v 50331648
/usr/bin/time -v nice -n 10 "${T10_OPENROAD_EXE}" -no_init -exit -threads 2 \
  "$driver" > "${T10_SCRATCH_ROOT}/t10_frozen_top/v75_mapped_cell_only.log" 2>&1
