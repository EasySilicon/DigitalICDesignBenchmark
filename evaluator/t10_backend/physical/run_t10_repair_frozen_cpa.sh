#!/usr/bin/env bash
set -euo pipefail

repo=/home/reefshark/research/agent_os/ic_bcmk_eval_private
seed=${T10_LAYOUT_SEED:-11}
source_root=/mnt/ubu_3T/ic_bcmk_orfs_asap7/flow/results/asap7/t10_reference_cpa_postprocess/ic_t10_frozen_cpa_postprocess_exact_v2_m7_wc_p1000_seed${seed}
scratch=${T10_SCRATCH_ROOT:-/mnt/ubu_3T/ic_bcmk_scratch/t10_frozen_cpa_postprocess/repair_seed${seed}}
openroad=${T10_OPENROAD:-/home/reefshark/.local/bin/openroad}
mkdir -p "$scratch"

source "$repo/physical/t10_acquire_openroad_slot.sh"
for path in "$source_root/4_cts.odb" "$source_root/4_cts.sdc"; do test -s "$path"; done

export T10_INPUT_ODB="$source_root/4_cts.odb"
export T10_INPUT_SDC="$source_root/4_cts.sdc"
export T10_OUTPUT_ODB="$scratch/cpa_setup_repaired_unrouted.odb"
export T10_OUTPUT_SDC="$scratch/cpa_setup_repaired_unrouted.sdc"
repair_log="$scratch/cpa_setup_repair.log"
"$openroad" -no_init -exit "$repo/physical/t10_repair_frozen_cpa_setup.tcl" >"$repair_log" 2>&1

export T10_INPUT_ODB="$T10_OUTPUT_ODB"
export T10_INPUT_SDC="$T10_OUTPUT_SDC"
export T10_OUTPUT_ODB="$scratch/cpa_setup_repaired_routed.odb"
export T10_OUTPUT_SDC="$scratch/cpa_setup_repaired_routed.sdc"
export T10_OUTPUT_SPEF="$scratch/cpa_setup_repaired_routed.spef"
export T10_DRC_REPORT="$scratch/cpa_setup_repaired_routed.drc"
export T10_MAZE_REPORT="$scratch/cpa_setup_repaired_routed.maze"
export T10_ROUTE_SEED=${T10_ROUTE_SEED:-$seed}
route_log="$scratch/cpa_setup_repaired_route.log"
ulimit -v 31457280
"$openroad" -no_init -exit "$repo/physical/t10_route_repaired_cpa.tcl" >"$route_log" 2>&1
