#!/usr/bin/env bash
set -euo pipefail
study=data/processed/experiments/entity-focus
out=data/research/experiments/entity-pooling
mkdir -p "$out"
for model in gemma open qwen; do
docker run --rm --network none --cpus 3 --user "$(id -u):$(id -g)" -e HOME=/tmp -e HF_HUB_OFFLINE=1 \
  -v "$PWD/.runtime/opensearch-v1:/models/opensearch-v1:ro" \
  -v "$PWD/.runtime/Qwen3-Embedding-0.6B:/models/Qwen3-Embedding-0.6B:ro" \
  -v "$PWD/.runtime/embeddinggemma-300m:/models/embeddinggemma-300m:ro" \
  -v "$PWD/.runtime/role-wheels:/models/role-wheels:ro" \
  -v "$PWD/src/python/scripts/acquisition_roles:/shared:ro" -v "$PWD/src/python/scripts/entity_focus:/code:ro" \
  -v "$PWD/$study:/study:ro" -v "$PWD/data/research/experiments/entity-focus/test-coverage.csv:/test-coverage.csv:ro" -v "$PWD/$out:/out" --entrypoint bash \
  sha256:f7876bef696ccf9cf75a2bf7ccb82970f5fac577f082fb8ca95c9a59d2160eb5 \
  -ec 'pip install --no-index --no-deps --target /tmp/lib /models/role-wheels/*.whl >/dev/null
  export PYTHONPATH=/tmp/lib:/shared
  exec python /code/pooling.py "$1"' _ "$model"
done
duckdb -bail < src/python/scripts/entity_focus/pooling.sql
