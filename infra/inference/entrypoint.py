"""Apply the recorded native serving profile before loading Kev."""

import hashlib
import json
import os
from pathlib import Path

profile = json.loads(Path(os.environ["CCFINANCE_RUNTIME_MANIFEST"]).read_text())
for filename, key in (
    ("adapter_model.safetensors", "model_adapter_sha256"),
    ("head.pt", "model_head_sha256"),
):
    if key in profile:
        with (Path("/checkpoint") / filename).open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != profile[key]:
            raise ValueError(f"Checkpoint checksum differs from profile: {filename}")
os.environ.update(
    {
        "KEV_BACKEND": "torch",
        "KEV_DTYPE": {"bfloat16": "bf16", "float32": "fp32"}[profile["dtype"]],
        "KEV_ATTN": profile["attention"],
        "KEV_FUSED": str(int(profile["fused_linear_attention"])),
        "KEV_CUDA_GRAPHS": str(int(profile["cuda_graphs"])),
        "KEV_MERGE": str(int(profile["merge_adapter"])),
        "KEV_PREFIX_CACHE": str(profile["prefix_cache_states"]),
        "KEV_PREFIX_MIN_TOKENS": str(profile["prefix_cache_min_tokens"]),
        "KEV_PREFIX_MAX_TOKENS": str(profile["prefix_cache_max_tokens"]),
        "KEV_TRUNCATE_STATES": str(int(profile["truncate_states"])),
    }
)

import kev.model  # noqa: E402

kev.model.SERVE_MAX_STATE = profile["max_context_tokens"]
kev.model.SERVE_MAX_BRANCH = profile["max_context_tokens"]

if limits := profile.get("cuda_graph_limits"):
    import kev.cuda_graphs

    allowed = {"GRAPH_STATES", "GRAPH_ROWS", "GRAPH_TOKENS"}
    if set(limits) != allowed:
        raise ValueError("Specify every supported CUDA graph buffer limit")
    for name, value in limits.items():
        if not isinstance(value, int) or value < 1:
            raise ValueError(f"CUDA graph buffer limit must be positive: {name}")
        setattr(kev.cuda_graphs, name, value)

from kev.serve import main  # noqa: E402

main()
