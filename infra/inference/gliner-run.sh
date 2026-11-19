#!/usr/bin/env bash
# Run one GLiNER benchmark with isolated libraries and pinned CUDA dependencies.
set -euo pipefail
repo_root=$(git rev-parse --show-toplevel)
checkpoint=$1
shift
image=lmsysorg/sglang@sha256:f7876bef696ccf9cf75a2bf7ccb82970f5fac577f082fb8ca95c9a59d2160eb5
docker run --rm --device nvidia.com/gpu=all --network=none --shm-size=1g \
    --user "$(id -u):$(id -g)" \
    --mount "type=bind,source=$repo_root/.runtime/gliner-site,target=/site,readonly" \
    --mount "type=bind,source=$repo_root/.runtime/models/$checkpoint,target=/model,readonly" \
    --mount "type=bind,source=$repo_root,target=/workspace" \
    --env PYTHONPATH=/site --env HF_HUB_OFFLINE=1 \
    --env TOKENIZERS_PARALLELISM=false \
    --env HF_HOME=/workspace/.runtime/hf-cache \
    --env TRITON_CACHE_DIR=/workspace/.runtime/triton-gliner \
    --env TORCHINDUCTOR_CACHE_DIR=/workspace/.runtime/inductor-gliner \
    --workdir /workspace --entrypoint python "$image" \
    infra/inference/gliner_extract.py "$@"
