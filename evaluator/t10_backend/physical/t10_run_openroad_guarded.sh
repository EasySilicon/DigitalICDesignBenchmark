#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 OPENROAD [ARG ...]" >&2
  exit 2
fi
repo=/home/reefshark/research/agent_os/ic_bcmk_eval_private
openroad=$1
shift
[[ -x $openroad ]] || { echo "missing OpenROAD executable: $openroad" >&2; exit 2; }
source "$repo/physical/t10_acquire_openroad_slot.sh"
exec nice -n 10 "$openroad" "$@"
