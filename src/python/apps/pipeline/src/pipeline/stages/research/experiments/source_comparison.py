"""Estimate publisher-filter yield from independently drawn source row groups."""

import csv
import json
import math
import os
from collections.abc import Sequence
from pathlib import Path
from statistics import fmean
from tempfile import TemporaryDirectory
from typing import Annotated

import typer
from statsmodels.iolib.summary import Summary
from statsmodels.iolib.table import SimpleTable
from statsmodels.stats.weightstats import DescrStatsW

from pipeline.experiments.source_comparison import Manifest, SampleCounts, load_config

REPORT_FILES = (
    "metrics.json",
    "methods.json",
    "comparison.csv",
    "summary.tex",
)
type Metric = int | float | None


def _estimate(
    values: Sequence[float],
    *,
    center: float | None = None,
    maximum: float | None = None,
) -> dict[str, float | None]:
    mean = fmean(values) if center is None else center
    if len(values) < 2 or all(value == values[0] for value in values):
        return dict.fromkeys(("standard_error", "ci95_low", "ci95_high")) | {
            "estimate": mean
        }
    # Probability expansion occurs before this call: each IID draw has unit weight.
    statistics = DescrStatsW(values, ddof=1)
    _, high = statistics.tconfint_mean(alpha=0.05)
    margin = float(high - statistics.mean)
    return {
        "estimate": mean,
        "standard_error": float(statistics.std_mean),
        "ci95_low": max(0.0, mean - margin),
        "ci95_high": min(maximum, mean + margin)
        if maximum is not None
        else mean + margin,
    }


def estimate_population(
    probabilities: Sequence[float],
    english_counts: Sequence[int],
    matched_counts: Sequence[int],
) -> dict[str, float | None]:
    """Estimate totals and a yield ratio using all with-replacement draws.

    Each group contributes its count divided by its draw probability. Totals
    use Hansen-Hurwitz means; the ratio uses a linearized standard error.
    Missing or zero between-draw variation cannot establish precision.
    """
    if not probabilities or not (
        len(probabilities) == len(english_counts) == len(matched_counts)
    ):
        raise ValueError("Probabilities and counts must have equal nonzero lengths")
    if any(not math.isfinite(q) or not 0 < q <= 1 for q in probabilities):
        raise ValueError("Draw probabilities must be finite and in (0, 1]")
    if any(
        not 0 <= y <= n for n, y in zip(english_counts, matched_counts, strict=True)
    ):
        raise ValueError("Counts must satisfy 0 <= matched <= English")
    english = [n / q for n, q in zip(english_counts, probabilities, strict=True)]
    matched = [y / q for y, q in zip(matched_counts, probabilities, strict=True)]
    estimates: dict[str, float | None] = {}
    for prefix, values in (
        ("english_records", english),
        ("publisher_records", matched),
    ):
        estimates.update(
            {
                f"estimated_{prefix}_{key}": value
                for key, value in _estimate(values).items()
            }
        )
    denominator = fmean(english)
    ratio = fmean(matched) / denominator if denominator else None
    estimates["estimated_publisher_yield"] = ratio
    reference_english, reference_matched = next(
        ((n, y) for n, y in zip(english_counts, matched_counts, strict=True) if n),
        (0, 0),
    )
    # Exact count products avoid fictitious variation from floating-point ratios.
    varying_yield = any(
        y * reference_english != n * reference_matched
        for n, y in zip(english_counts, matched_counts, strict=True)
        if n
    )
    if ratio is not None and varying_yield:
        residuals = [
            (y - ratio * n) / denominator for n, y in zip(english, matched, strict=True)
        ]
        uncertainty = _estimate(residuals, center=ratio, maximum=1.0)
    else:
        uncertainty = dict.fromkeys(("standard_error", "ci95_low", "ci95_high"))
    estimates.update(
        {
            f"estimated_publisher_yield_{key}": value
            for key, value in uncertainty.items()
            if key != "estimate"
        }
    )
    return estimates


def _summarize(
    manifest: Manifest, sample: SampleCounts
) -> tuple[dict[str, Metric], dict[str, str | int]]:
    ordered_counts = sample.ordered_counts(manifest)
    unique = {
        (draw.file, draw.row_group): (draw, count)
        for draw, count in zip(manifest.draws, ordered_counts, strict=True)
    }
    english_rows = sum(count.english_rows for _, count in unique.values())
    matched_rows = sum(count.matched_rows for _, count in unique.values())
    metrics: dict[str, Metric] = {
        "population_files": manifest.file_count,
        "population_listed_bytes": manifest.listed_bytes,
        "draws": len(manifest.draws),
        "selected_files": len({draw.file for draw in manifest.draws}),
        "selected_groups": len(unique),
        "sampled_input_rows": sum(count.input_rows for _, count in unique.values()),
        "sampled_english_rows": english_rows,
        "sampled_matched_rows": matched_rows,
        "observed_publisher_yield": matched_rows / english_rows
        if english_rows
        else None,
        "projected_column_bytes": sum(
            draw.projected_bytes for draw, _ in unique.values()
        ),
        "elapsed_seconds": sample.elapsed_seconds,
        "output_bytes": sample.output_bytes,
        "network_bytes": sample.network_bytes,
    }
    metrics.update(
        estimate_population(
            [draw.probability for draw in manifest.draws],
            [count.english_rows for count in ordered_counts],
            [count.matched_rows for count in ordered_counts],
        )
    )
    details = {
        "source": manifest.source,
        "revision": manifest.revision,
        "english_definition": manifest.english_definition,
        "seed": manifest.seed,
        "degrees_of_freedom": len(manifest.draws) - 1,
        "uncertainty_status": "exploratory"
        if metrics["estimated_publisher_yield_standard_error"] is not None
        else "insufficient_evidence",
    }
    return metrics, details


def _latex_reports(metrics: dict[str, dict[str, Metric]]) -> dict[str, str]:
    summary = Summary()
    tables = (
        ("yield", "Publisher yield", "Yield (%)", 100.0, 4),
        ("population", "Publisher-matched population", "Matched records", 1.0, 0),
    )
    for name, title, column, scale, precision in tables:
        prefix = (
            "estimated_publisher_yield"
            if name == "yield"
            else ("estimated_publisher_records")
        )
        estimate = prefix if name == "yield" else f"{prefix}_estimate"
        rows = []
        for source in metrics.values():
            values = [
                source[estimate],
                source[f"{prefix}_ci95_low"],
                source[f"{prefix}_ci95_high"],
            ]
            rows.append(
                [str(source["draws"])]
                + [
                    f"{value * scale:,.{precision}f}" if value is not None else "--"
                    for value in values
                ]
            )
        summary.tables.append(
            SimpleTable(
                rows,
                headers=["Draws", column, "95% lower", "95% upper"],
                stubs=list(metrics),
                title=title,
            )
        )
    summary.add_extra_txt(
        [
            r"Exploratory 95\% Student t intervals from independent row-group draws.",
            "Hansen--Hurwitz population totals; linearized variance for yield.",
            "Few draws provide limited evidence about rare or uneven matches.",
            "-- indicates insufficient evidence for uncertainty, not zero.",
            "Records do not establish unique articles or research eligibility.",
        ]
    )
    return {"summary.tex": summary.as_latex()}


def compare_sources(
    manifests: Annotated[
        Path, typer.Option(help="Prepared manifests indexed by configured dataset.")
    ],
    samples: Annotated[
        Path, typer.Option(help="Acquisition counts indexed by configured dataset.")
    ],
    output: Annotated[
        Path, typer.Option(help="New directory for the comparison table and metrics.")
    ],
    params: Annotated[Path, typer.Option()] = Path("params.yaml"),
) -> None:
    """Compare observed retention and exploratory population estimates."""
    config = load_config(params)
    for name in REPORT_FILES:
        if (output / name).exists():
            raise FileExistsError(f"Output exists: {output / name}")
    metrics = {}
    details = {}
    for dataset, specification in config.datasets.items():
        manifest = Manifest.model_validate_json(
            (manifests / dataset / "manifest.json").read_text(encoding="utf-8")
        )
        sample = SampleCounts.model_validate_json(
            (samples / dataset / "counts.json").read_text(encoding="utf-8")
        )
        if manifest.dataset != dataset:
            raise ValueError(f"Manifest dataset differs from its directory: {dataset}")
        if (
            manifest.source != specification.source
            or manifest.seed != config.seed
            or len(manifest.draws) != config.draws
        ):
            raise ValueError(f"Manifest differs from configured comparison: {dataset}")
        metrics[dataset], details[dataset] = _summarize(manifest, sample)
    methods = {
        "estimand": "English source records retained by the publisher filter",
        "design": "Independent uniform file and row-group draws with replacement",
        "totals": "Hansen-Hurwitz mean of count / draw probability",
        "yield": "Estimated publisher-matched records / estimated English records",
        "uncertainty": "Exploratory Student t intervals; linearized yield variance",
        "inference": (
            "statsmodels DescrStatsW on probability-expanded IID draw values, "
            "using unit frequency weights and sample degrees of freedom"
        ),
        "interval_bounds": "Nonnegative totals; yield intervals bounded to [0, 1]",
        "missing_uncertainty": (
            "Fewer than two draws, zero matches, or zero between-draw variance"
        ),
        "physical_counts": "Observed counts count each unique selected group once",
        "repeated_draws": "Population estimates retain repeated selections",
        "size_scope": (
            "Eligible-file bytes include non-English rows in multilingual files"
        ),
        "transfer_scope": (
            "Projected compressed column bytes exclude HTTP overhead and footers; "
            "network bytes require measurement"
        ),
        "limitations": [
            "Few cluster draws poorly characterize rare or uneven publisher matches",
            "Records do not establish unique articles or incremental source coverage",
            "Publisher retention does not establish research eligibility or coverage",
            "Native English labels and release scopes differ between sources",
        ],
        "sources": details,
    }
    latex = _latex_reports(metrics)
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as temporary:
        staging = Path(temporary)
        for name, payload in (("metrics.json", metrics), ("methods.json", methods)):
            (staging / name).write_text(
                json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
            )
        rows = [
            {"dataset": dataset, **details[dataset], **metrics[dataset]}
            for dataset in config.datasets
        ]
        with (staging / "comparison.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        for name, content in latex.items():
            (staging / name).write_text(content + "\n", encoding="utf-8")
        linked = []
        try:
            for name in REPORT_FILES:
                target = output / name
                os.link(staging / name, target)
                linked.append(target)
        except OSError:
            for target in linked:
                target.unlink()
            raise
    typer.echo(f"Wrote comparison for {len(config.datasets)} sources: {output}")
