#!/usr/bin/env bash
# Check patched source offsets and CPU/CUDA attribute decoding.
set -euo pipefail
repo_root=$(git rev-parse --show-toplevel)
image=lmsysorg/sglang@sha256:f7876bef696ccf9cf75a2bf7ccb82970f5fac577f082fb8ca95c9a59d2160eb5
docker run --rm --device nvidia.com/gpu=all --network=none \
    --user "$(id -u):$(id -g)" \
    --mount "type=bind,source=$repo_root/.runtime/gliner-site,target=/site,readonly" \
    --mount "type=bind,source=$repo_root/.runtime/models/gliner2.5-small-v1,target=/model,readonly" \
    --mount "type=bind,source=$repo_root/infra/inference,target=/checks,readonly" \
    --env PYTHONPATH=/site --env HF_HUB_OFFLINE=1 --entrypoint bash "$image" \
    -c 'python /checks/gliner_offset_check.py && python /checks/gliner_device_check.py'
