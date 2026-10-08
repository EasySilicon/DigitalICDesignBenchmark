#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 OPENROAD_BIN TCL_SCRIPT LOG" >&2
  exit 2
fi

openroad_bin=$1
tcl_script=$2
log=$3
repo=/home/reefshark/research/agent_os/ic_bcmk_eval_private
: "${T10_OPENROAD_VMEM_KIB:=31457280}"

for input in "$openroad_bin" "$tcl_script"; do
  if [[ ! -e "$input" ]]; then
    echo "missing input: $input" >&2
    exit 2
  fi
done

# The Tcl signoff flows intentionally receive paths as environment variables.
# Keeping the command line fixed makes the log and invocation reproducible.
required=(
  T10_WC_LIB_FILES T10_BC_LIB_FILES
  T10_WC_MACRO_LIB_FILES T10_BC_MACRO_LIB_FILES
  T10_INPUT_ODB T10_INPUT_SDC T10_RCX_RULES T10_SETRC_TCL
  T10_OUTPUT_PREFIX T10_SETUP_UNCERTAINTY_PS T10_HOLD_UNCERTAINTY_PS
)
for name in "${required[@]}"; do
  if [[ -z ${!name:-} ]]; then
    echo "missing required environment variable: $name" >&2
    exit 2
  fi
done

mkdir -p "$(dirname "$log")" "$(dirname "$T10_OUTPUT_PREFIX")"
source "$repo/physical/t10_acquire_openroad_slot.sh"
ulimit -v "$T10_OPENROAD_VMEM_KIB"
set +e
/usr/bin/time -v "$openroad_bin" -no_init -exit "$tcl_script" 2>&1 | tee "$log"
status=${PIPESTATUS[0]}
set -e
printf '%s\n' "$status" > "${log}.exit"
printf 'T10_OPENROAD_SIGNOFF_EXIT=%s\n' "$status"
exit "$status"
