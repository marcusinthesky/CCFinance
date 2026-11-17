"""Versioned operating parameters for provisional article-company labels."""

from pathlib import Path

import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ArticleLabelsConfig(BaseModel):
    """Keep decision policy, inference limits and the deadline explicit."""

    model_config = ConfigDict(extra="forbid")

    seed: int = 42
    deadline_utc: AwareDatetime
    reserve_seconds: int = Field(default=1800, ge=0)
    server_url: str = "http://127.0.0.1:8008"
    api_model: str = "kev-latest"
    model: str = "jaredpalmer/kev-0.8b"
    model_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    base_model: str = "Qwen/Qwen3.5-0.8B-Base"
    base_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    runtime_manifest: Path = Path("data/inputs/article-labels/runtime.json")
    max_context_tokens: int = Field(default=8192, gt=0)
    max_candidates_per_request: int = Field(default=32, gt=0)
    concurrency: int = Field(default=1, gt=0)
    benchmark_size: int = Field(default=1000, gt=0)
    request_timeout_seconds: float = Field(default=60, gt=0, allow_inf_nan=False)
    min_probability: float = Field(default=0.95, ge=0, le=1, allow_inf_nan=False)
    precision_target: float = Field(default=0.95, gt=0, le=1, allow_inf_nan=False)


def load_config(params: Path) -> ArticleLabelsConfig:
    """Read the article-labeling experiment without environment overrides."""
    document = yaml.safe_load(params.read_text(encoding="utf-8"))
    return ArticleLabelsConfig.model_validate(document["experiments"]["article_labels"])
