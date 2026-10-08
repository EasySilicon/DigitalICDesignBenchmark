#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch

backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
rtl=${T10_REFERENCE_RTL}
config=$backend_root/physical/t10_frozen_pe/config.mk
expected_rtl_sha=248faca64fba735b879cad919f1f57a3cd638a7c784c6c35c8a223cd81538f91
seed=${T10_LAYOUT_SEED:-11}
target=${1:-finish}
variant=ic_t10_frozen_pe_pin6b_softplus_m7_wc_p1000_seed${seed}
log_root=${T10_LOG_ROOT:-${T10_SCRATCH_ROOT}/t10_frozen_pe}
log=$log_root/${variant}_${target}.log

test "$(sha256sum "$rtl" | awk '{print $1}')" = "$expected_rtl_sha"
t10_require_file "$config"
mapfile -t macro_inputs < <(
  sed -n '/^export ADDITIONAL_LEFS =/,/^export ADDITIONAL_LIBS =/p; /^export ADDITIONAL_LIBS =/,/^export PDN_TCL =/p' "$config" |
    grep -o '/[^ \\]*\(\.lef\|\.lib\)'
)
for path in "${macro_inputs[@]}"; do
  t10_require_file "$path" || { echo "missing macro input: $path" >&2; exit 2; }
done
source "$backend_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$log_root"
{
  printf 'variant=%s\ntarget=%s\nlog=%s\nrtl_sha256=%s\n' \
    "$variant" "$target" "$log" "$expected_rtl_sha"
  for path in "${macro_inputs[@]}"; do sha256sum "$path"; done
} | tee "$log_root/ACTIVE_RUN"
cd "$orfs_root/flow"
export T10_LAYOUT_SEED=$seed
nice -n 10 make \
  DESIGN_CONFIG="$config" \
  FLOW_VARIANT="$variant" \
  OPENROAD_EXE="${T10_OPENROAD_EXE}" \
  YOSYS_EXE="${T10_YOSYS_EXE}" \
  NUM_CORES=${T10_NUM_CORES:-4} \
  "$target" >"$log" 2>&1
