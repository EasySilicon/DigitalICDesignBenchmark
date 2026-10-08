#!/usr/bin/env bash
set -euo pipefail
private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
export T10_TRANSPORT_QUALIFICATION_ROOT=${T10_DISTRIBUTED_CANDIDATE_ROOT:?Set the accepted full-DUT candidate}
export T10_FLOW_VARIANT=${T10_DISTRIBUTED_SYNTH_VARIANT:?Set a unique synthesis variant}
bash "$private_root/physical/run_t10_top_transport_synth_probe.sh"
bash "$private_root/physical/run_t10_transport_floorplan_probe.sh"
export T10_SPATIAL_SOURCE_VARIANT=$T10_FLOW_VARIANT
export T10_FLOW_VARIANT=${T10_DISTRIBUTED_PLACE_VARIANT:?Set a unique placement variant}
export T10_DISTRIBUTED_EGRESS=1
bash "$private_root/physical/run_t10_transport_spatial_probe.sh"
export T10_CHECK_VARIANT=$T10_FLOW_VARIANT
bash "$private_root/physical/run_t10_transport_spatial_checks.sh"
