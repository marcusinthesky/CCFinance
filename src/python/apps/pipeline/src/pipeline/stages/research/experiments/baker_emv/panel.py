"""Build and calibrate the monthly EMV tracker panel."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import typer

INPUTS = Path("data/inputs/baker-emv")
PROCESSED = Path("data/processed/experiments/baker-emv")
ROOT = Path("data/research/experiments/baker-emv")


def build_baker_emv_panel(
    news: Path = PROCESSED / "news" / "publisher_month.parquet",
    market: Path = PROCESSED / "market" / "monthly_market.parquet",
    window: Path = INPUTS / "window.json",
    output: Path = ROOT / "panel",
) -> None:
    """Build the calibrated baseline and minimum-day monthly analysis panels."""
    bounds = json.loads(window.read_text())
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as work, duckdb.connect() as con:
        con.execute(
            """
            CREATE TEMP TABLE coverage AS
            WITH ledger AS (
                SELECT *, month BETWEEN ?::DATE AND ?::DATE AS calibration
                FROM read_parquet(?)
            ), variants AS (
                SELECT 'baseline' AS variant, *, hit_share AS eligible_share FROM ledger
                UNION ALL
                SELECT 'minimum_days', *,
                       CASE WHEN publication_days >= ? THEN hit_share END
                FROM ledger
            ), dispersion AS (
                SELECT variant, host,
                       count(eligible_share) FILTER (WHERE calibration)
                           AS calibration_months,
                       stddev_samp(eligible_share ORDER BY month)
                           FILTER (WHERE calibration) AS publisher_sd
                FROM variants GROUP BY variant, host
            )
            SELECT v.*, d.calibration_months, d.publisher_sd,
                   eligible_share / CASE WHEN publisher_sd > 0 THEN publisher_sd END
                       AS standardized_share
            FROM variants v JOIN dispersion d USING (variant, host)
            ORDER BY variant, month, host
            """,
            [
                bounds["start"],
                bounds["calibration_end"],
                str(news),
                bounds["min_publication_days"],
            ],
        )
        con.execute(
            """
            CREATE TEMP TABLE calibrated AS
            WITH months AS (
                SELECT month::DATE AS month
                FROM generate_series(?::DATE, ?::DATE, INTERVAL 1 MONTH) AS t(month)
            ), index_by_month AS (
                SELECT v.variant, m.month, any_value(c.calibration) AS calibration,
                       count(c.standardized_share) AS contributing_publishers,
                       avg(c.standardized_share ORDER BY c.host) AS unscaled_emv
                FROM (SELECT DISTINCT variant FROM coverage) v CROSS JOIN months m
                LEFT JOIN coverage c USING (variant, month)
                GROUP BY v.variant, m.month
            ), joined AS (
                SELECT i.*, vix, realized_volatility, vix_days, return_days
                FROM index_by_month i LEFT JOIN read_parquet(?) USING (month)
            ), calibration AS (
                SELECT variant, count(*) AS calibration_months,
                       avg(vix ORDER BY month) /
                           nullif(avg(unscaled_emv ORDER BY month), 0) AS scale
                FROM joined WHERE calibration AND vix > 0 AND unscaled_emv IS NOT NULL
                GROUP BY variant
            )
            SELECT j.*, c.calibration_months, c.scale, unscaled_emv * c.scale AS emv
            FROM joined j LEFT JOIN calibration c USING (variant)
            ORDER BY variant, month
            """,
            [bounds["start"], bounds["end"], str(market)],
        )
        invalid = con.execute(
            "SELECT DISTINCT variant FROM calibrated WHERE scale IS NULL"
        ).fetchall()
        if invalid:
            raise ValueError(f"No usable calibration for {invalid}")
        con.execute(
            """
            CREATE TEMP TABLE monthly_panel AS
            SELECT *, row_number() OVER calendar - 1 AS month_number,
                   lag(emv) OVER calendar AS emv_lag1,
                   lag(emv, 2) OVER calendar AS emv_lag2,
                   lag(vix) OVER calendar AS vix_lag1,
                   lag(realized_volatility) OVER calendar AS realized_volatility_lag1,
                   CASE WHEN emv > 0 THEN ln(emv) END AS log_emv,
                   CASE WHEN vix > 0 THEN ln(vix) END AS log_vix
            FROM calibrated
            WINDOW calendar AS (PARTITION BY variant ORDER BY month)
            ORDER BY variant, month
            """
        )
        con.execute(
            "COPY coverage TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(Path(work) / "coverage.parquet")],
        )
        con.execute(
            "COPY monthly_panel TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(Path(work) / "monthly_panel.parquet")],
        )
        for filename in ("coverage.parquet", "monthly_panel.parquet"):
            os.replace(Path(work) / filename, output / filename)
    typer.echo(f"Wrote: {output}")
