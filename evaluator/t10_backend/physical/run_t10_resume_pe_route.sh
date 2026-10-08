#!/usr/bin/env bash
set -euo pipefail

scratch=${T10_SCRATCH_ROOT:-/mnt/ubu_3T/ic_bcmk_scratch/t10_pe_m6m7_baseline}
input=${T10_INPUT_ODB:-/mnt/ubu_3T/ic_bcmk_scratch/t10_pe_low_skew_cts/low_skew_cts_c16_edges16_final16_drt_i3.odb}
repo=/home/reefshark/research/agent_os/ic_bcmk_eval_private
driver=$repo/physical/t10_resume_pe_route.tcl
mkdir -p "$scratch"

source "$repo/physical/t10_acquire_openroad_slot.sh"
test -s "$input"

stamp=$(date -u +%Y%m%dT%H%M%SZ)
output="$scratch/pe_m6m7_seed31_i22_${stamp}.odb"
log="$scratch/pe_m6m7_seed31_i22_${stamp}.log"
export T10_INPUT_ODB="$input"
export T10_OUTPUT_ODB="$output"
export T10_DRC_REPORT="$scratch/pe_m6m7_seed31_i22_${stamp}.drc"
export T10_MAZE_REPORT="$scratch/pe_m6m7_seed31_i22_${stamp}.maze"
export T10_THREADS=${T10_THREADS:-2}
export T10_DRT_ITERATIONS=${T10_DRT_ITERATIONS:-22}
export T10_ROUTE_SEED=${T10_ROUTE_SEED:-31}

printf 'log=%s\noutput=%s\n' "$log" "$output" | tee "$scratch/ACTIVE_RUN"
ulimit -v 31457280
set +e
/usr/bin/time -v /home/reefshark/.local/bin/openroad -no_init -exit "$driver" >"$log" 2>&1
status=$?
set -e
printf '%s\n' "$status" >"$log.exit"
exit "$status"
