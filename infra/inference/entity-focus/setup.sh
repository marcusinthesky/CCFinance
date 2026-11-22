#!/usr/bin/env bash
# Run in the pinned devenv shell, from the repository root.
set -euo pipefail
uv run --project src/python --offline --frozen python - <<'PY'
from huggingface_hub import snapshot_download

for repo, revision in (
    ("google/embeddinggemma-300m", "57c266a740f537b4dc058e1b0cda161fd15afa75"),
    ("Qwen/Qwen3-Embedding-0.6B", "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"),
):
    snapshot_download(repo, revision=revision, local_dir=".runtime/" + repo.split("/")[-1],
                      allow_patterns=["*.json", "*.safetensors", "*.model", "*.txt"],
                      ignore_patterns=["onnx/*", "openvino/*"])
PY
mkdir -p .runtime/role-wheels
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$PWD/.runtime/role-wheels:/w" --entrypoint pip \
    sha256:f7876bef696ccf9cf75a2bf7ccb82970f5fac577f082fb8ca95c9a59d2160eb5 \
    download --dest /w --no-deps sentence-transformers==5.5.1 scikit-learn==1.7.2 \
    joblib==1.5.2 threadpoolctl==3.6.0
