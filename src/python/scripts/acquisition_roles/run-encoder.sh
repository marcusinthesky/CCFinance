#!/usr/bin/env bash
set -euo pipefail
study=${2:-data/processed/experiments/entity-embeddings}
docker run --rm --network none --cpus 3 --user "$(id -u):$(id -g)" -e HOME=/tmp -e HF_HUB_OFFLINE=1 \
  -v "$PWD/.runtime/opensearch-v1:/models/opensearch-v1:ro" \
  -v "$PWD/.runtime/Qwen3-Embedding-0.6B:/models/Qwen3-Embedding-0.6B:ro" \
  -v "$PWD/.runtime/embeddinggemma-300m:/models/embeddinggemma-300m:ro" \
  -v "$PWD/.runtime/role-wheels:/models/role-wheels:ro" \
  -v "$PWD/src/python/scripts/acquisition_roles:/code:ro" \
  -v "$PWD/$study:/study" --entrypoint bash \
  sha256:f7876bef696ccf9cf75a2bf7ccb82970f5fac577f082fb8ca95c9a59d2160eb5 \
  -ec 'pip install --no-index --no-deps --target /tmp/lib /models/role-wheels/*.whl >/dev/null
  export PYTHONPATH=/tmp/lib
  exec python /code/encode.py /models /study/acquisition-screen.parquet /study/facts.json "/study/$1.parquet" "$1"' _ "$1"
