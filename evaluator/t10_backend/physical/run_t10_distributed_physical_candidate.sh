#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
export T10_TRANSPORT_QUALIFICATION_ROOT=${T10_DISTRIBUTED_CANDIDATE_ROOT:?Set the accepted full-DUT candidate}
export T10_FLOW_VARIANT=${T10_DISTRIBUTED_SYNTH_VARIANT:?Set a unique synthesis variant}
bash "$backend_root/physical/run_t10_top_transport_synth_probe.sh"
bash "$backend_root/physical/run_t10_transport_floorplan_probe.sh"
export T10_SPATIAL_SOURCE_VARIANT=$T10_FLOW_VARIANT
export T10_FLOW_VARIANT=${T10_DISTRIBUTED_PLACE_VARIANT:?Set a unique placement variant}
export T10_DISTRIBUTED_EGRESS=1
bash "$backend_root/physical/run_t10_transport_spatial_probe.sh"
export T10_CHECK_VARIANT=$T10_FLOW_VARIANT
bash "$backend_root/physical/run_t10_transport_spatial_checks.sh"
