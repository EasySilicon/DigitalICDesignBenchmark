#!/usr/bin/env bash
set -euo pipefail
private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
candidate_root=${T10_DISTRIBUTED_CANDIDATE_ROOT:-/mnt/ubu_3T/ic_bcmk_scratch/t10_qualification/v103_distributed_output}
options=()
if [[ ${T10_DISTRIBUTED_LOCAL_READY:-0} == 1 ]]; then options+=(--local-ready); fi
options+=(--queue-depth "${T10_DISTRIBUTED_QUEUE_DEPTH:-2}")
if [[ ${T10_DISTRIBUTED_CAPTURE_CREDIT:-0} == 1 ]]; then options+=(--capture-credit); fi
if [[ ${T10_DISTRIBUTED_ONE_CREDIT_STAGE:-0} == 1 ]]; then options+=(--one-credit-stage); fi
if [[ ${T10_DISTRIBUTED_LOCAL_ACCEPT:-0} == 1 ]]; then options+=(--local-accept); fi
if [[ ${T10_DISTRIBUTED_INDEPENDENT_MASK_CAPTURE:-0} == 1 ]]; then options+=(--independent-mask-capture); fi
python3 "$private_root/physical/t10_make_distributed_output_candidate.py" \
  "$private_root/refs/T10/rtl/npu_systolic_matmul_16x16.sv" "$candidate_root" "${options[@]}"
mkdir -p "$candidate_root/tmp"
export TMPDIR=$candidate_root/tmp
export T10_TRANSPORT_CANDIDATE_ROOT=$candidate_root
ulimit -v 25165824
/usr/bin/time -v nice -n 10 python3 "$private_root/physical/t10_qualify_transport_candidate.py" \
  > "$candidate_root/run.log" 2>&1
printf 'T10_DISTRIBUTED_OUTPUT_FULL_DUT_QUALIFICATION_FINISHED\n'
