#!/usr/bin/env bash
set -euo pipefail
repo_root=$(git rev-parse --show-toplevel)
runtime="$repo_root/.runtime"
source_commit=2074cc44256200bb37540103fa4572901faa10f3
image=lmsysorg/sglang@sha256:f7876bef696ccf9cf75a2bf7ccb82970f5fac577f082fb8ca95c9a59d2160eb5
mkdir -p "$runtime/serving-site"
if [[ ! -d "$runtime/kev/.git" ]]; then
    git init "$runtime/kev"
    git -C "$runtime/kev" remote add origin https://github.com/jaredpalmer/kev.git
    git -C "$runtime/kev" fetch --depth 1 origin "$source_commit"
    git -C "$runtime/kev" checkout --detach FETCH_HEAD
fi
test "$(git -C "$runtime/kev" rev-parse HEAD)" = "$source_commit"
docker image inspect "$image" >/dev/null
docker run --rm --user "$(id -u):$(id -g)" \
    --mount "type=bind,source=$runtime/serving-site,target=/runtime-site" \
    --mount "type=bind,source=$repo_root/infra/inference/requirements.txt,target=/requirements.txt,readonly" \
    --entrypoint python "$image" -m pip install --disable-pip-version-check \
    --no-cache-dir --no-deps --target /runtime-site -r /requirements.txt
