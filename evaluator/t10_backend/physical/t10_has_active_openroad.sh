#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch

# A paused benchmark suite may retain an OpenROAD checkpoint process in state
# T.  It consumes no CPU and must not prevent the single active T10 job.
while read -r state; do
  [[ -n "$state" ]] || continue
  if [[ ! $state =~ ^[TZ] ]]; then
    exit 0
  fi
done < <(ps -C openroad -o stat=)
exit 1
