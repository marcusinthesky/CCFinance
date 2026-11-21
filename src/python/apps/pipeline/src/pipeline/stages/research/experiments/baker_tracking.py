"""Compare the two monthly EMV trackers on a shared calendar."""

import csv
import os
import subprocess
from collections.abc import Sequence
from datetime import date
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NamedTuple

import duckdb
import numpy as np
import pandas as pd
import typer
from numpy.typing import NDArray

ROOT = Path("data/research/experiments/baker-emv")
ARCHIVE = Path("data/raw/experiments/baker-emv/replication.rar")
MEMBER = "2025 EMV Replication/norm_results_allpapers_constrained_clean_1986.dta"
OUTCOMES = ("vix", "realized_volatility")
VARIANTS = ("baseline", "minimum_days", "unscaled", "calibrated_through_2021")
BLOCK_LENGTHS = (1, 3, 6, 12)
BOOTSTRAP_DRAWS = 10_000
BOOTSTRAP_SEED = 42


class TrackerFit(NamedTuple):
    """Comparative in-sample fit on the same rows."""

    author_r2: float
    ccfinance_r2: float
    difference: float
    author_slope: float
    ccfinance_slope: float


def _author_index(archive: Path) -> dict[date, float]:
    # Extract only the selected member to stdout, keeping archive paths off disk.
    result = subprocess.run(  # noqa: S603
        ["bsdtar", "-xOf", str(archive), MEMBER],  # noqa: S607
        check=True,
        stdout=subprocess.PIPE,
    )
    source = pd.read_stata(
        BytesIO(result.stdout), columns=["year", "month", "reg_final"]
    )
    months: dict[date, float] = {}
    for year, month, value in source.itertuples(index=False, name=None):
        key = date(int(year), int(month), 1)
        if key in months:
            raise ValueError(f"Duplicate author month {key}")
        months[key] = float(value)
    return months


def _paired_panel(panel: Path, archive: Path) -> tuple[list[date], NDArray[np.float64]]:
    authors = _author_index(archive)
    with duckdb.connect() as connection:
        rows = connection.execute(
            """
            WITH cells AS (
                SELECT month, host, eligible_share,
                       stddev_samp(eligible_share ORDER BY month) FILTER (
                           WHERE month <= DATE '2021-12-01'
                       ) OVER (PARTITION BY host) AS publisher_sd
                FROM read_parquet(?) WHERE variant = 'baseline'
            ), alternative AS (
                SELECT month,
                       avg(eligible_share / nullif(publisher_sd, 0) ORDER BY host)
                           AS alternative_unscaled
                FROM cells GROUP BY month
            ), baseline AS (
                FROM read_parquet(?) WHERE variant = 'baseline'
            ), minimum_days AS (
                FROM read_parquet(?) WHERE variant = 'minimum_days'
            ), paired AS (
                SELECT month, b.vix, b.realized_volatility, b.emv AS baseline,
                       m.emv AS minimum_days, b.unscaled_emv AS unscaled,
                       alternative_unscaled
                FROM baseline b JOIN minimum_days m USING (month)
                JOIN alternative a USING (month)
            ), alternative_scale AS (
                SELECT avg(vix ORDER BY month)
                       / avg(alternative_unscaled ORDER BY month) AS scale
                FROM paired WHERE month <= DATE '2021-12-01'
            )
            SELECT month, vix, realized_volatility, baseline, minimum_days, unscaled,
                   alternative_unscaled * scale
            FROM paired CROSS JOIN alternative_scale ORDER BY month
            """,
            [
                str(panel / "coverage.parquet"),
                str(panel / "monthly_panel.parquet"),
                str(panel / "monthly_panel.parquet"),
            ],
        ).fetchall()
    months = [row[0] for row in rows]
    expected = pd.date_range("2019-09-01", "2023-09-01", freq="MS").date.tolist()
    if months != expected:
        raise ValueError("Expected one paired observation for each of the 49 months")
    values = np.asarray(
        [(authors.get(month, np.nan), *values) for month, *values in rows],
        dtype=np.float64,
    )
    if not np.isfinite(values).all():
        raise ValueError("The shared calendar requires finite trackers and outcomes")
    return months, values


def _fit(trackers: NDArray[np.float64], outcome: NDArray[np.float64]) -> TrackerFit:
    centered = trackers - trackers.mean(axis=0)
    y = outcome - outcome.mean()
    tracker_sums = np.sum(centered**2, axis=0)
    outcome_sum = np.sum(y**2)
    if np.any(tracker_sums <= 0) or outcome_sum <= 0:
        raise ValueError("Tracking fits require varying trackers and outcome")
    covariation = y @ centered
    slopes = covariation / tracker_sums
    author_r2, ccfinance_r2 = (covariation**2 / tracker_sums / outcome_sum).tolist()
    author_slope, ccfinance_slope = slopes.tolist()
    return TrackerFit(
        author_r2, ccfinance_r2, ccfinance_r2 - author_r2, author_slope, ccfinance_slope
    )


def paired_r2_interval(
    trackers: NDArray[np.float64],
    outcome: NDArray[np.float64],
    block_length: int,
    *,
    draws: int = BOOTSTRAP_DRAWS,
) -> tuple[float, float, int]:
    """Return a paired circular-block percentile interval and valid draw count."""
    n = len(outcome)
    if not 1 <= block_length <= n or draws <= 0:
        raise ValueError("Use a positive draw count and a block length from one to n")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    starts = rng.integers(0, n, size=(draws, (n + block_length - 1) // block_length))
    indices = ((starts[:, :, None] + np.arange(block_length)) % n).reshape(draws, -1)
    indices = indices[:, :n]
    x = trackers[indices]
    y = outcome[indices]
    x = x - x.mean(axis=1, keepdims=True)
    y = y - y.mean(axis=1, keepdims=True)
    denominators = np.sum(x**2, axis=1) * np.sum(y**2, axis=1)[:, None]
    valid = (denominators > 0).all(axis=1)
    if not np.any(valid):
        raise ValueError("All bootstrap draws have a constant tracker or outcome")
    fits = np.sum(x[valid] * y[valid, :, None], axis=1) ** 2 / denominators[valid]
    lower, upper = np.quantile(fits[:, 1] - fits[:, 0], [0.025, 0.975])
    return float(lower), float(upper), int(valid.sum())


def _write_csv(
    path: Path, fields: Sequence[str], rows: Sequence[Sequence[object]]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        writer.writerows(rows)


def compare_baker_tracking(
    panel: Path = ROOT / "panel",
    archive: Path = ARCHIVE,
    output: Path = ROOT / "paired-tracking",
) -> None:
    """Write common-month tracking fits, paired intervals and influence checks."""
    months, values = _paired_panel(panel, archive)
    fits: list[Sequence[object]] = []
    intervals: list[Sequence[object]] = []
    influence: list[Sequence[object]] = []
    dates = np.asarray(months)
    exclusions = {month.isoformat(): dates == month for month in months}
    exclusions["march_april_2020"] = (dates >= date(2020, 3, 1)) & (
        dates <= date(2020, 4, 1)
    )
    exclusions["calendar_2020"] = (dates >= date(2020, 1, 1)) & (
        dates <= date(2020, 12, 1)
    )
    for outcome_index, outcome_name in enumerate(OUTCOMES, start=1):
        outcome = values[:, outcome_index]
        for tracker_index, variant in enumerate(VARIANTS, start=3):
            trackers = values[:, [0, tracker_index]]
            fits.append((outcome_name, variant, len(months), *_fit(trackers, outcome)))
            for block in BLOCK_LENGTHS:
                intervals.append(
                    (
                        outcome_name,
                        variant,
                        block,
                        BOOTSTRAP_SEED,
                        BOOTSTRAP_DRAWS,
                        *paired_r2_interval(trackers, outcome, block),
                    )
                )
        baseline = values[:, [0, 3]]
        for label, omitted in exclusions.items():
            included = ~omitted
            influence.append(
                (
                    outcome_name,
                    label,
                    int(included.sum()),
                    *_fit(baseline[included], outcome[included]),
                )
            )

    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as work:
        stage = Path(work)
        _write_csv(
            stage / "shared_months.csv",
            ("month", "author_emv", *OUTCOMES, *VARIANTS),
            [(month, *row) for month, row in zip(months, values.tolist(), strict=True)],
        )
        _write_csv(
            stage / "fits.csv",
            ("outcome", "variant", "months", *TrackerFit._fields),
            fits,
        )
        _write_csv(
            stage / "intervals.csv",
            (
                "outcome",
                "variant",
                "block_months",
                "seed",
                "draws",
                "lower",
                "upper",
                "valid_draws",
            ),
            intervals,
        )
        _write_csv(
            stage / "influence.csv",
            ("outcome", "omitted", "months", *TrackerFit._fields),
            influence,
        )
        for artifact in stage.iterdir():
            os.replace(artifact, output / artifact.name)
    typer.echo(f"Wrote: {output}")
