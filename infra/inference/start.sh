#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo 'Usage: bash infra/inference/start.sh CHECKPOINT_DIRECTORY HF_HUB_CACHE [RUNTIME_PROFILE]' >&2
    exit 2
fi
repo_root=$(git rev-parse --show-toplevel)
runtime="$repo_root/.runtime"
model_dir=$(realpath "$1")
hub_cache=$(realpath "$2")
profile=$(realpath "${3:-$repo_root/data/inputs/article-labels/runtime.json}")
profile_fields=$(
    python3 - "$profile" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    profile = json.load(source)
for key in ("image", "source_revision"):
    value = profile[key]
    if not isinstance(value, str) or not value or "\n" in value:
        raise ValueError(f"Runtime profile field must be a single string: {key}")
    print(value)
PY
)
image=${profile_fields%$'\n'*}
source_revision=${profile_fields##*$'\n'}
test "$(git -C "$runtime/kev" rev-parse HEAD)" = "$source_revision"
docker run --detach --name ccfinance-kev-native --device nvidia.com/gpu=all \
    --user "$(id -u):$(id -g)" --shm-size 2g --publish 127.0.0.1:8008:8008 \
    --mount "type=bind,source=$runtime/kev,target=/native-kev,readonly" \
    --mount "type=bind,source=$runtime/serving-site,target=/runtime-site,readonly" \
    --mount "type=bind,source=$model_dir,target=/checkpoint,readonly" \
    --mount "type=bind,source=$hub_cache,target=/hf-cache,readonly" \
    --mount "type=bind,source=$runtime,target=/runtime" \
    --mount "type=bind,source=$repo_root/infra/inference/entrypoint.py,target=/entrypoint.py,readonly" \
    --mount "type=bind,source=$profile,target=/runtime-manifest.json,readonly" \
    --env PYTHONPATH=/runtime-site:/native-kev --env HF_HUB_CACHE=/hf-cache \
    --env HF_HUB_OFFLINE=1 --env HF_DATASETS_OFFLINE=1 \
    --env HOME=/runtime --env TRITON_CACHE_DIR=/runtime/triton \
    --env CUDA_CACHE_PATH=/runtime/cuda --env CCFINANCE_RUNTIME_MANIFEST=/runtime-manifest.json \
    --entrypoint python "$image" /entrypoint.py --run /checkpoint \
    --fallback /checkpoint --device cuda --host 0.0.0.0 --port 8008
