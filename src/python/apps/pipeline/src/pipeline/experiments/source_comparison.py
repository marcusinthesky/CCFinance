"""Parameters and artifacts shared by source sampling and research reports."""

import math
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatasetInput(BaseModel):
    """A native Parquet glob at an immutable Hub commit."""

    model_config = ConfigDict(extra="forbid")
    source: str


class ComparisonConfig(BaseModel):
    """Shared comparison parameters without environment-variable overrides."""

    model_config = ConfigDict(extra="forbid")
    seed: int
    draws: int = Field(gt=0)
    domains: Path
    datasets: dict[str, DatasetInput] = Field(min_length=1)


class FileRecord(BaseModel):
    """A member of the complete eligible file inventory."""

    file: str
    size: int = Field(gt=0)
    identity: str


class Draw(BaseModel):
    """One replacement draw, with half-open source row bounds."""

    draw: int = Field(ge=0)
    file: str
    row_group: int = Field(ge=0)
    row_start: int = Field(ge=0)
    row_stop: int = Field(gt=0)
    probability: float = Field(gt=0, le=1, allow_inf_nan=False)
    file_size_bytes: int = Field(gt=0)
    file_row_groups: int = Field(gt=0)
    projected_bytes: int = Field(ge=0)


class Manifest(BaseModel):
    """The source frame and every planned draw, including repeated groups."""

    dataset: str
    source: str
    revision: str
    seed: int
    file_count: int = Field(gt=0)
    listed_bytes: int = Field(gt=0)
    english_definition: str
    footer_bytes: int = Field(ge=0)
    draws: list[Draw] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_draws(self) -> Self:
        """Check the probability design before acquiring any article payload."""
        if len({draw.draw for draw in self.draws}) != len(self.draws):
            raise ValueError("Draw identifiers must be unique")
        groups: dict[tuple[str, int], Draw] = {}
        for draw in self.draws:
            if (
                draw.row_stop <= draw.row_start
                or draw.row_group >= draw.file_row_groups
                or not math.isclose(
                    draw.probability, 1 / (self.file_count * draw.file_row_groups)
                )
            ):
                raise ValueError("Draw bounds or probability differ from the design")
            key = (draw.file, draw.row_group)
            if key in groups and draw.model_dump(exclude={"draw"}) != groups[
                key
            ].model_dump(exclude={"draw"}):
                raise ValueError("Repeated groups have inconsistent metadata")
            groups[key] = draw
        return self


class DrawCounts(BaseModel):
    """Nested record counts from one selected group before and after filtering."""

    draw: int = Field(ge=0)
    input_rows: int = Field(ge=0)
    english_rows: int = Field(ge=0)
    matched_rows: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        """Require retained publisher records to be a subset of English records."""
        if not self.matched_rows <= self.english_rows <= self.input_rows:
            raise ValueError("Counts must satisfy matched <= English <= input rows")
        return self


class SampleCounts(BaseModel):
    """Acquisition counts with physical sizes measured once per unique group."""

    dataset: str
    draws: list[DrawCounts] = Field(min_length=1)
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    output_bytes: int = Field(ge=0)
    network_bytes: int | None = Field(default=None, ge=0)

    def ordered_counts(self, manifest: Manifest) -> list[DrawCounts]:
        """Reconcile the acquisition with every planned draw, preserving order."""
        if manifest.dataset != self.dataset:
            raise ValueError("Manifest and acquisition dataset identifiers differ")
        counts = {count.draw: count for count in self.draws}
        if len(counts) != len(self.draws) or set(counts) != {
            draw.draw for draw in manifest.draws
        }:
            raise ValueError(
                "Manifest and acquisition need matching, unique draw identifiers"
            )
        groups: dict[tuple[str, int], DrawCounts] = {}
        ordered = []
        for draw in manifest.draws:
            count = counts[draw.draw]
            if count.input_rows != draw.row_stop - draw.row_start:
                raise ValueError(
                    "Acquired row count differs from the selected row bounds"
                )
            key = (draw.file, draw.row_group)
            if key in groups and count.model_dump(exclude={"draw"}) != groups[
                key
            ].model_dump(exclude={"draw"}):
                raise ValueError(
                    "Repeated group selections contain inconsistent counts"
                )
            groups[key] = count
            ordered.append(count)
        return ordered


def load_config(params: Path) -> ComparisonConfig:
    """Read the source-comparison experiment's versioned parameters."""
    document = yaml.safe_load(params.read_text(encoding="utf-8"))
    return ComparisonConfig.model_validate(document["experiments"]["source_comparison"])
