#!/usr/bin/env bash
set -euo pipefail
private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
orfs_root=/mnt/ubu_3T/ic_bcmk_orfs_asap7
variant=${T10_FLOW_VARIANT:?Select the complete-DUT measured checkpoint}
result=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant
export T10_RETIME_ODB=$result/3_5_place_native_checked.odb
export T10_RETIME_SDC=$result/4_cts.sdc
export T10_RETIME_SETRC=$orfs_root/flow/platforms/asap7/setRC.tcl
export T10_TOP_PATH_AUDIT_ROOT=$result/top_path_audit
test -s "$T10_RETIME_ODB"
test ! -e "$T10_TOP_PATH_AUDIT_ROOT/summary.rpt"
libs=()
for pattern in '*_AO_RVT_SS*' '*_INVBUF_RVT_SS*' '*_OA_RVT_SS*' '*_SEQ_RVT_SS*' '*_SIMPLE_RVT_SS*' '*_INVBUF_SLVT_SS*'; do
    while IFS= read -r path; do libs+=("$path"); done < <(find "$orfs_root/flow/platforms/asap7/lib/NLDM" -maxdepth 1 -name "$pattern" -type f)
done
[[ ${#libs[@]} == 6 ]]
libs+=("$orfs_root/flow/results/asap7/t10_reference_tile_4x4/ic_t10_frozen_tile_v54_onehot_slvtclk_wideclk_grt_m7_wc_p1000_seed11/t10_reference_tile_4x4_wc.lib")
export T10_RETIME_LIBS="${libs[*]}"
source "$private_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$T10_TOP_PATH_AUDIT_ROOT"
cp "$private_root/physical/t10_full_dut_path_audit.tcl" "$T10_TOP_PATH_AUDIT_ROOT/driver.tcl"
sha256sum "$T10_RETIME_ODB" "$T10_RETIME_SDC" "$T10_RETIME_SETRC" \
    "$T10_TOP_PATH_AUDIT_ROOT/driver.tcl" "${libs[@]}" > "$T10_TOP_PATH_AUDIT_ROOT/inputs.sha256"
ulimit -v 50331648
/usr/bin/time -v nice -n 10 /home/reefshark/.local/bin/openroad -no_init -exit -threads 2 \
    "$T10_TOP_PATH_AUDIT_ROOT/driver.tcl" > "$T10_TOP_PATH_AUDIT_ROOT/run.log" 2>&1
