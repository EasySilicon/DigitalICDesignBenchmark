#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch

if [[ $# -lt 1 ]]; then
  echo "usage: $0 OPENROAD [ARG ...]" >&2
  exit 2
fi
repo=${T10_BACKEND_ROOT}
openroad=$1
shift
[[ -x $openroad ]] || { echo "missing OpenROAD executable: $openroad" >&2; exit 2; }
source "$repo/physical/t10_acquire_openroad_slot.sh"
exec nice -n 10 "$openroad" "$@"
