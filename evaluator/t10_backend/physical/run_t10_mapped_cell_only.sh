#!/usr/bin/env bash
set -euo pipefail
private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
orfs_root=/mnt/ubu_3T/ic_bcmk_orfs_asap7
result_root=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16
result_dir=$result_root/ic_t10_frozen_top_v75_popcount_synth_m7_wc_p1000_seed11
platform=$orfs_root/flow/platforms/asap7
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
test -s "$T10_CELL_ONLY_NETLIST"
source "$private_root/physical/t10_acquire_openroad_slot.sh"
driver=$result_dir/mapped_cell_only_driver.tcl
cp "$private_root/physical/t10_frozen_top/estimate_mapped_cell_only.tcl" "$driver"
sha256sum "$T10_CELL_ONLY_NETLIST" "$T10_RETIME_SDC" "$driver" "${libs[@]}" "${lefs[@]}" \
  > "$result_dir/mapped_cell_only_inputs.sha256"
ulimit -v 50331648
/usr/bin/time -v nice -n 10 /home/reefshark/.local/bin/openroad -no_init -exit -threads 2 \
  "$driver" > /mnt/ubu_3T/ic_bcmk_scratch/t10_frozen_top/v75_mapped_cell_only.log 2>&1
