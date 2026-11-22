#!/usr/bin/env bash
set -euo pipefail
source=$(realpath "${1:?Title projection required}")
output=${2:?Output directory required}
(cd "$PWD/.runtime/all-MiniLM-L6-v2" && sha256sum --check --strict "$OLDPWD/infra/inference/minilm-model.sha256")
mkdir -p "$output"
docker run --rm --network none --device nvidia.com/gpu=all \
    --user "$(id -u):$(id -g)" \
    -v "$PWD/.runtime/all-MiniLM-L6-v2:/model:ro" \
    -v "$source:/articles:ro" \
    -v "$(realpath "$output"):/output" \
    -v "$PWD/infra/inference:/workers:ro" \
    -e HOME=/tmp -e HF_HUB_OFFLINE=1 -e TOKENIZERS_PARALLELISM=false \
    --entrypoint python sha256:f7876bef696ccf9cf75a2bf7ccb82970f5fac577f082fb8ca95c9a59d2160eb5 \
    /workers/minilm_embed.py
