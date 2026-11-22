#!/usr/bin/env bash
set -euo pipefail
output=${1:-data/processed/embeddinggemma-embeddings}
mkdir -p "$output"
docker run --rm --network none --device nvidia.com/gpu=all --shm-size=1g \
    -v "$PWD/.runtime/embeddinggemma-300m:/model:ro" \
    -v "$PWD/${ARTICLE_SOURCE:-data/raw/fine-news}:/articles:ro" \
    -v "$(realpath "$output"):/output" \
    -v "$PWD/infra/inference:/workers:ro" \
    -e BENCHMARK -e SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1 -e "WORKER_UID=$(id -u)" -e "WORKER_GID=$(id -g)" -e HOME=/tmp \
    -e HF_HUB_OFFLINE=1 -e TOKENIZERS_PARALLELISM=false \
    --entrypoint bash sha256:f7876bef696ccf9cf75a2bf7ccb82970f5fac577f082fb8ca95c9a59d2160eb5 \
    -ec '
    pkg=/sgl-workspace/sglang/python/sglang/srt
    sed -i "s/torch.cumsum(hidden_states, dim=0)/torch.cumsum(hidden_states, dim=0, dtype=torch.float32)/" "$pkg/layers/pooler.py"
    sed -i "s/pooled = self.projector(pooled)$/pooled = self.projector(pooled.to(self.projector[0].weight.dtype))/" "$pkg/models/gemma3_causal.py"
    sed -i "s/F.normalize(pooled, p=2, dim=-1)/F.normalize(pooled.float(), p=2, dim=-1)/" "$pkg/models/gemma3_causal.py"
    exec setpriv --reuid "$WORKER_UID" --regid "$WORKER_GID" --clear-groups python /workers/gemma_embed.py'
