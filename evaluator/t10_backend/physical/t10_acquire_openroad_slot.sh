#!/usr/bin/env bash
# Source this file immediately before launching a T10 OpenROAD process.
# Other benchmark runs on this shared host have priority.  Admit T10 only when
# no OpenROAD process is already active, memory is available, and the T10
# family lock is free.

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  echo "ERROR: source t10_acquire_openroad_slot.sh from a T10 runner" >&2
  exit 2
fi

min_available_gib=${T10_MIN_AVAILABLE_GIB:-50}
[[ $min_available_gib =~ ^[1-9][0-9]*$ ]] || {
  echo "ERROR: T10_MIN_AVAILABLE_GIB must be a positive integer" >&2
  exit 2
}
available_kib=$(awk '/^MemAvailable:/ {print $2; exit}' /proc/meminfo)
required_kib=$((min_available_gib * 1024 * 1024))
if (( available_kib < required_kib )); then
  available_gib=$(awk -v kib="$available_kib" \
    'BEGIN {printf "%.2f", kib/1024/1024}')
  printf 'WAIT: MemAvailable=%s GiB is below T10 threshold=%d GiB\n' \
    "$available_gib" "$min_available_gib" >&2
  exit 75
fi

if pgrep -x 'openroad.*' >/dev/null; then
  printf 'WAIT: an OpenROAD process is already active; T10 yields the host\n' >&2
  pgrep -a -x 'openroad.*' >&2 || true
  exit 74
fi

t10_lock=${T10_OPENROAD_LOCK:-/mnt/ubu_3T/ic_bcmk_scratch/t10_openroad.lock}
mkdir -p "$(dirname "$t10_lock")"
exec {T10_OPENROAD_LOCK_FD}>"$t10_lock"
if ! flock -n "$T10_OPENROAD_LOCK_FD"; then
  echo "WAIT: another T10 OpenROAD stage owns $t10_lock" >&2
  exit 73
fi
printf 'T10_OPENROAD_SLOT pass available_kib=%s threshold_gib=%s lock=%s\n' \
  "$available_kib" "$min_available_gib" "$t10_lock"
