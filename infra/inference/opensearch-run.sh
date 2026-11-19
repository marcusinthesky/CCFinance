#!/usr/bin/env bash
# Run from the repository root with the pinned model snapshot in .runtime/opensearch-v1.
set -euo pipefail
output=${1:-data/processed/opensearch-embeddings}
mkdir -p "$output"
docker run --rm --network none --device nvidia.com/gpu=all --shm-size=1g \
    -v "$PWD/.runtime/opensearch-v1:/model:ro" \
    -v "$PWD/data/raw/fine-news:/articles:ro" \
    -v "$(realpath "$output"):/output" \
    -v "$PWD/infra/inference/opensearch_embed.py:/worker.py:ro" \
    -e "WORKER_UID=$(id -u)" -e "WORKER_GID=$(id -g)" -e HOME=/tmp \
    -e HF_HUB_OFFLINE=1 -e TOKENIZERS_PARALLELISM=false \
    --entrypoint bash sha256:f7876bef696ccf9cf75a2bf7ccb82970f5fac577f082fb8ca95c9a59d2160eb5 \
    -ec '
    module=/sgl-workspace/sglang/python/sglang/srt/models/qwen3_embedding.py
    grep -q "PoolingType.LAST, normalize=True" "$module"
    sed -i "s/PoolingType.LAST, normalize=True/PoolingType.MEAN, normalize=False/" "$module"
    pkg=/sgl-workspace/sglang/python/sglang/srt
    sed -i "s/torch.cumsum(hidden_states, dim=0)/torch.cumsum(hidden_states, dim=0, dtype=torch.float32)/" "$pkg/layers/pooler.py"
    exec setpriv --reuid "$WORKER_UID" --regid "$WORKER_GID" --clear-groups python /worker.py'
