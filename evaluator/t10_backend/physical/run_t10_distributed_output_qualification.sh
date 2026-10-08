#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
candidate_root=${T10_DISTRIBUTED_CANDIDATE_ROOT:-${T10_SCRATCH_ROOT}/t10_qualification/v103_distributed_output}
options=()
if [[ ${T10_DISTRIBUTED_LOCAL_READY:-0} == 1 ]]; then options+=(--local-ready); fi
options+=(--queue-depth "${T10_DISTRIBUTED_QUEUE_DEPTH:-2}")
if [[ ${T10_DISTRIBUTED_CAPTURE_CREDIT:-0} == 1 ]]; then options+=(--capture-credit); fi
if [[ ${T10_DISTRIBUTED_ONE_CREDIT_STAGE:-0} == 1 ]]; then options+=(--one-credit-stage); fi
if [[ ${T10_DISTRIBUTED_LOCAL_ACCEPT:-0} == 1 ]]; then options+=(--local-accept); fi
if [[ ${T10_DISTRIBUTED_INDEPENDENT_MASK_CAPTURE:-0} == 1 ]]; then options+=(--independent-mask-capture); fi
python3 "$backend_root/physical/t10_make_distributed_output_candidate.py" \
  "${T10_REFERENCE_RTL}" "$candidate_root" "${options[@]}"
mkdir -p "$candidate_root/tmp"
export TMPDIR=$candidate_root/tmp
export T10_TRANSPORT_CANDIDATE_ROOT=$candidate_root
ulimit -v 25165824
/usr/bin/time -v nice -n 10 python3 "$backend_root/physical/t10_qualify_transport_candidate.py" \
  > "$candidate_root/run.log" 2>&1
printf 'T10_DISTRIBUTED_OUTPUT_FULL_DUT_QUALIFICATION_FINISHED\n'
