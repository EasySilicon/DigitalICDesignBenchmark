#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch

backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
seed=${T10_LAYOUT_SEED:-11}
variant=ic_t10_frozen_pe_exact_v13_macro_sample_m7_wc_p1000_seed${seed}
result_dir=$orfs_root/flow/results/asap7/t10_reference_pe/$variant
scratch=${T10_PE_CHECKPOINT_ROOT:-${T10_SCRATCH_ROOT}/t10_frozen_pe_exact_checkpoint_v11/seed${seed}}
state=$scratch/state.json
driver=$backend_root/physical/t10_frozen_pe_checkpoint_route.tcl
mode=${1:-status}
vm_limit_gib=${T10_VM_LIMIT_GIB:-30}

die() {
  echo "ERROR: $*" >&2
  exit 2
}

state_value() {
  python3 - "$state" "$1" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1]))[sys.argv[2]])
PY
}

case "$mode" in
  status)
    if [[ -s $state ]]; then
      cat "$state"
    else
      printf '{"status":"not_started","seed":%s}\n' "$seed"
    fi
    exit 0
    ;;
  initial|restart|repair|promote) ;;
  *) die "usage: $0 {status|initial|restart|repair|promote}" ;;
esac

mkdir -p "$scratch"
exec 9>"$scratch/route.lock"
flock -n 9 || die "another T10 PE checkpoint stage owns $scratch/route.lock"

if [[ $mode == promote ]]; then
  [[ -s $state ]] || die "no completed checkpoint state"
  drvs=$(state_value drvs)
  [[ $drvs == 0 ]] || die "refusing to promote checkpoint with drvs=$drvs"
  input=$(state_value output_odb)
  expected_sha=$(state_value output_sha256)
  [[ -s $input ]] || die "checkpoint ODB missing: $input"
  actual_sha=$(sha256sum "$input" | awk '{print $1}')
  [[ $actual_sha == "$expected_sha" ]] || die "checkpoint ODB hash mismatch"
  install -m 0644 "$input" "$result_dir/5_2_route.odb"
  printf '%s\n' "$expected_sha  $input" >"$result_dir/5_2_route.t10_source.sha256"
  echo "PROMOTED: $input -> $result_dir/5_2_route.odb"
  exit 0
fi

source "$backend_root/physical/t10_acquire_openroad_slot.sh"
[[ -s $driver ]] || die "missing Tcl driver: $driver"

if [[ $mode == initial ]]; then
  [[ ! -e $state ]] || die "checkpoint state already exists; use repair"
  input=$result_dir/5_1_grt.odb
  stage=0
  iterations=${T10_DRT_ITERATIONS:-1}
  route_mode=initial
elif [[ $mode == restart ]]; then
  [[ -s $state ]] || die "no completed checkpoint state; run initial first"
  input=$result_dir/5_1_grt.odb
  stage=$(( $(state_value stage) + 1 ))
  iterations=${T10_DRT_ITERATIONS:-1}
  route_mode=initial
else
  [[ -s $state ]] || die "no initial checkpoint; run initial first"
  input=$(state_value output_odb)
  stage=$(( $(state_value stage) + 1 ))
  iterations=${T10_DRT_ITERATIONS:-1}
  route_mode=repair
fi

[[ $iterations =~ ^[1-9][0-9]*$ ]] || die "T10_DRT_ITERATIONS must be a positive integer"
(( iterations <= 64 )) || die "T10_DRT_ITERATIONS must be <= 64"
[[ -s $input ]] || die "input ODB missing: $input"

tag=$(printf 'stage%03d_%s_i%d_seed%d' "$stage" "$mode" "$iterations" "$seed")
output=$scratch/$tag.odb
drc=$scratch/$tag.drc
maze=$scratch/$tag.maze
status_tmp=$scratch/$tag.status.tmp
log=$scratch/$tag.log
state_tmp=$scratch/state.json.tmp
[[ ! -e $output ]] || die "refusing to overwrite $output"
rm -f "$status_tmp" "$state_tmp"

export T10_INPUT_ODB=$input
export T10_OUTPUT_ODB=$output
export T10_DRC_REPORT=$drc
export T10_MAZE_REPORT=$maze
export T10_ROUTE_STATUS=$status_tmp
export T10_ROUTE_MODE=$route_mode
export T10_DRT_ITERATIONS=$iterations
export T10_ROUTE_SEED=${T10_ROUTE_SEED:-$seed}
export T10_THREADS=${T10_THREADS:-4}

printf 'T10_CHECKPOINT_START stage=%d mode=%s input=%s output=%s log=%s\n' \
  "$stage" "$mode" "$input" "$output" "$log"
ulimit -v $((vm_limit_gib * 1024 * 1024))
set +e
nice -n 10 /usr/bin/time -v "${T10_OPENROAD_EXE}" \
  -no_init -exit -threads "$T10_THREADS" -no_splash "$driver" >"$log" 2>&1
rc=$?
set -e
if (( rc != 0 )); then
  printf '%s\n' "$rc" >"$log.exit"
  die "OpenROAD checkpoint stage failed rc=$rc; see $log"
fi
printf '0\n' >"$log.exit"
[[ -e $maze ]] || : >"$maze"
# A clean detailed route produces an intentionally empty DRC report.
[[ -s $output && -s $status_tmp && -e $drc && -e $maze ]] || \
  die "stage did not produce complete evidence"
drvs=$(awk -F= '$1=="drvs" {print $2}' "$status_tmp")
[[ $drvs =~ ^[0-9]+$ ]] || die "invalid DRC count in $status_tmp"

python3 "$backend_root/physical/t10_record_route_checkpoint.py" \
  --output "$state_tmp" --stage "$stage" --mode "$mode" \
  --iterations "$iterations" --seed "$seed" --drvs "$drvs" \
  --input-odb "$input" --output-odb "$output" --drc-report "$drc" \
  --maze-log "$maze" --openroad-log "$log"
install -m 0644 "$state_tmp" "$scratch/$tag.state.json"
mv -f "$state_tmp" "$state"
mv -f "$status_tmp" "$scratch/$tag.status"
printf 'T10_CHECKPOINT_DONE stage=%d drvs=%s state=%s\n' "$stage" "$drvs" "$state"
