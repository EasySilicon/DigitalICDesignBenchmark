#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -uo pipefail
t10_init_scratch

backend_root=${T10_BACKEND_ROOT}
priority_pid=${1:-}

if [[ -n $priority_pid ]]; then
  while kill -0 "$priority_pid" 2>/dev/null; do
    printf 'T10_TILE_V33_WAIT_PRIORITY pid=%s time=%s\n' "$priority_pid" "$(date -Is)"
    sleep 20
  done
fi

run_with_slot_retry() {
  local target=$1 rc
  while true; do
    "$backend_root/physical/run_t10_frozen_tile.sh" "$target"
    rc=$?
    case $rc in
      73|74|75)
        printf 'T10_TILE_V33_WAIT_SLOT target=%s rc=%s time=%s\n' \
          "$target" "$rc" "$(date -Is)"
        sleep 20
        ;;
      *) return "$rc" ;;
    esac
  done
}

for target in place cts_resume; do
  printf 'T10_TILE_V33_STAGE_START target=%s time=%s\n' "$target" "$(date -Is)"
  run_with_slot_retry "$target"
  rc=$?
  printf 'T10_TILE_V33_STAGE_DONE target=%s rc=%s time=%s\n' \
    "$target" "$rc" "$(date -Is)"
  (( rc == 0 )) || exit "$rc"
done
