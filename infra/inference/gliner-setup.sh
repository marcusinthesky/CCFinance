#!/usr/bin/env bash
# Prepare isolated GLiNER libraries and immutable public checkpoint snapshots.
set -euo pipefail
repo_root=$(git rev-parse --show-toplevel)
runtime="$repo_root/.runtime"
image=lmsysorg/sglang@sha256:f7876bef696ccf9cf75a2bf7ccb82970f5fac577f082fb8ca95c9a59d2160eb5
mkdir -p "$runtime/gliner-site"
docker run --rm --user "$(id -u):$(id -g)" \
    --mount "type=bind,source=$runtime/gliner-site,target=/site" \
    --mount "type=bind,source=$repo_root/infra/inference/gliner-requirements.txt,target=/requirements.txt,readonly" \
    --entrypoint python "$image" -m pip install --upgrade --no-cache-dir --no-deps \
    --target /site -r /requirements.txt
patch -d "$runtime/gliner-site" -p1 < "$repo_root/infra/inference/gliner2-2.1.0-cuda-attributes.patch"
patch -d "$runtime/gliner-site" -p1 < "$repo_root/infra/inference/gliner2-2.1.0-window-offsets.patch"
patch -d "$runtime/gliner-site" -p1 < "$repo_root/infra/inference/gliner2-2.1.0-batched-attributes.patch"
env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --project "$repo_root/src/python" --offline --frozen \
    hf download fastino/gliner2.5-small-v1 --revision b5d42bf7dc7d01c40304ae4ed43c2f13c325a75b \
    --local-dir "$runtime/models/gliner2.5-small-v1"
env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --project "$repo_root/src/python" --offline --frozen \
    hf download fastino/gliner2.5-base-v1 --revision 07d99c0ba5d15cb3b24e0a236fa99bdd4ef87a5c \
    --local-dir "$runtime/models/gliner2.5-base-v1"
