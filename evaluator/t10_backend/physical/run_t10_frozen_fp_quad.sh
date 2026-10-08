#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch

if [[ $# -lt 1 || $# -gt 2 || ! $1 =~ ^[012]$ ]]; then
  echo "usage: $0 CLASS(0|1|2) [make-target]" >&2
  exit 2
fi

class=$1
target=${2:-baseline}
if [[ $target == baseline ]]; then
  make_targets=(route do-finish)
else
  make_targets=("$target")
fi
backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
rtl=${T10_REFERENCE_RTL}
config=$backend_root/physical/t10_frozen_fp_quad/config.mk
expected_rtl_sha=248faca64fba735b879cad919f1f57a3cd638a7c784c6c35c8a223cd81538f91
seed=${T10_LAYOUT_SEED:-11}
design=t10_reference_fp_quad_class${class}_exact
constraint=$backend_root/physical/t10_frozen_fp_quad/constraint_class${class}.sdc
io_constraints=
hold_slack_margin=
variant_suffix=
if [[ $class == 1 || $class == 2 ]]; then
  io_constraints=$backend_root/physical/t10_class2_corner_io.tcl
  hold_slack_margin=${T10_FP_HOLD_SLACK_MARGIN:-50}
  variant_suffix=_cornerio_h${hold_slack_margin}
fi
variant=ic_t10_frozen_fp_class${class}${variant_suffix}_m7_wc_p1000_seed${seed}
log_root=${T10_LOG_ROOT:-${T10_SCRATCH_ROOT}/t10_frozen_fp_quad}
log=$log_root/${variant}_${target}.log

test "$(sha256sum "$rtl" | awk '{print $1}')" = "$expected_rtl_sha"
t10_require_file "$config"
t10_require_file "$constraint"
if [[ -n $io_constraints ]]; then
  t10_require_file "$io_constraints"
fi
source "$backend_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$log_root"
printf 'variant=%s\ndesign=%s\ntarget=%s\nlog=%s\nrtl_sha256=%s\nlayout_seed=%s\n' \
  "$variant" "$design" "$target" "$log" "$expected_rtl_sha" "$seed" | tee "$log_root/ACTIVE_RUN"
cd "$orfs_root/flow"
export T10_LAYOUT_SEED=$seed
export T10_FP_DESIGN_NAME=$design
export T10_FP_CONSTRAINT=$constraint
export T10_FP_IO_CONSTRAINTS=$io_constraints
export T10_FP_HOLD_SLACK_MARGIN=$hold_slack_margin
nice -n 10 make \
  DESIGN_CONFIG="$config" \
  FLOW_VARIANT="$variant" \
  OPENROAD_EXE="${T10_OPENROAD_EXE}" \
  YOSYS_EXE="${T10_YOSYS_EXE}" \
  NUM_CORES=${T10_NUM_CORES:-4} \
  "${make_targets[@]}" >"$log" 2>&1
