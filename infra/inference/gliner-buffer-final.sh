#!/usr/bin/env bash
# Repeat the selected buffered hybrid configuration on the full article sample.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
batch_size=${1:-128}
precision=${2:-fp16}
chunk_size=${3:-384}
buffer_size=${4:-8192}
results=.runtime/gliner-benchmark/buffer-final-results
logs=.runtime/gliner-benchmark/buffer-final-logs
mkdir -p "$results" "$logs"
for repeat in 1 2 3; do
    name="$precision-b$batch_size-c$chunk_size-attrs-$repeat"
    if timeout 900 bash infra/inference/gliner-run.sh gliner2.5-small-v1 \
        --sample .runtime/gliner-benchmark/sample/articles.jsonl \
        --output "$results/$name" --limit 10000 --batch-size "$batch_size" \
        --buffer-size "$buffer_size" --workers 4 --precision "$precision" \
        --chunk-size "$chunk_size" \
        --batched-attributes \
        --backend disentangled_flash_heads > "$logs/$name.log" 2>&1; then
        cp infra/inference/gliner_benchmark.py "$results/$name/runner.py"
        printf '%s\t%s\n' "$name" 0 | tee -a "$logs/status.tsv"
    else
        status=$?
        printf '%s\t%s\n' "$name" "$status" | tee -a "$logs/status.tsv"
        exit "$status"
    fi
done
