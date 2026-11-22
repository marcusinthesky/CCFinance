"""Aggregate market closes and realized volatility by month."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import typer

INPUTS = Path("data/inputs/baker-emv")
ROOT = Path("data/processed/experiments/baker-emv")


def prepare_baker_emv_market(
    source: Path = Path("data/raw/experiments/baker-emv/market.csv"),
    window: Path = INPUTS / "window.json",
    output: Path = ROOT / "market",
) -> None:
    """Write daily closes and annualized monthly realized volatility."""
    bounds = json.loads(window.read_text())
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as work, duckdb.connect() as con:
        con.execute(
            """
            CREATE TEMP TABLE closes AS
            SELECT observation_date::DATE AS day,
                   nullif(nullif(VIXCLS, ''), '.')::DOUBLE AS vix_close,
                   nullif(nullif(SP500, ''), '.')::DOUBLE AS sp500_close
            FROM read_csv(?, all_varchar = true, header = true)
            WHERE observation_date::DATE < ?::DATE + INTERVAL 1 MONTH
            """,
            [str(source), bounds["end"]],
        )
        [(invalid, days, unique_days, prior)] = con.execute(
            """
            SELECT count(*) FILTER (
                       WHERE day IS NULL OR vix_close <= 0 OR sp500_close <= 0
                          OR NOT isfinite(vix_close) OR NOT isfinite(sp500_close)
                   ), count(*), count(DISTINCT day),
                   max(day) FILTER (WHERE day < ?::DATE AND sp500_close IS NOT NULL)
            FROM closes
            """,
            [bounds["start"]],
        ).fetchall()
        if invalid or days != unique_days or prior is None:
            raise ValueError(
                "Market data needs unique dates, positive closes, and a prior close"
            )
        con.execute(
            """
            CREATE TEMP TABLE daily_market AS
            WITH returns AS (
                SELECT day,
                       ln(sp500_close / lag(sp500_close) OVER (ORDER BY day))
                           AS log_return
                FROM closes WHERE sp500_close IS NOT NULL AND day >= ?
            )
            SELECT *, day >= ?::DATE AS study_day
            FROM closes LEFT JOIN returns USING (day)
            WHERE day >= ? AND (vix_close IS NOT NULL OR sp500_close IS NOT NULL)
            ORDER BY day
            """,
            [prior, bounds["start"], prior],
        )
        con.execute(
            """
            CREATE TEMP TABLE monthly_market AS
            SELECT date_trunc('month', day)::DATE AS month,
                   count(vix_close) FILTER (WHERE sp500_close IS NOT NULL) AS vix_days,
                   count(vix_close) FILTER (WHERE sp500_close IS NULL) AS vix_only_days,
                   count(log_return) AS return_days,
                   avg(vix_close) FILTER (WHERE sp500_close IS NOT NULL) AS vix,
                   100 * sqrt(252 * avg(log_return ^ 2)) AS realized_volatility
            FROM daily_market
            WHERE study_day
            GROUP BY month ORDER BY month
            """
        )
        con.execute(
            "COPY daily_market TO ? (FORMAT PARQUET)",
            [str(Path(work) / "daily_market.parquet")],
        )
        con.execute(
            "COPY monthly_market TO ? (FORMAT PARQUET)",
            [str(Path(work) / "monthly_market.parquet")],
        )
        for filename in ("daily_market.parquet", "monthly_market.parquet"):
            os.replace(Path(work) / filename, output / filename)
    typer.echo(f"Wrote: {output}")
