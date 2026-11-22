"""Compare fixed title encoders and body vectors on paired sessions."""

import csv
from pathlib import Path
from typing import Annotated

import duckdb
import numpy as np
import typer

from .portfolios import build_portfolio_days, load_portfolio_inputs, portfolio_metrics
from .probes import SEED, fit_probes

TITLE_CONTRASTS = (
    ("gemma_title", "body"),
    ("minilm_title", "body"),
    ("minilm_title", "gemma_title"),
)


def _paired_drift_interval(
    con: duckdb.DuckDBPyConnection, variant: str, reference: str, block_size: int
) -> tuple[float, float]:
    # Keep missing sessions in the calendar so gaps retain their original spacing.
    pairs = con.execute(
        """SELECT portfolio_delta FROM paired_days
           WHERE target='drift' AND variant=? AND reference=? ORDER BY session""",
        [variant, reference],
    ).fetchall()
    values = np.asarray([row[0] for row in pairs], dtype=np.float64)
    evaluated = np.flatnonzero(np.isfinite(values))
    if not len(evaluated):
        msg = "No evaluated sessions for the paired drift interval"
        raise ValueError(msg)
    values = values[evaluated[0] : evaluated[-1] + 1]
    repetitions = 10_000
    rng = np.random.default_rng(SEED)
    n_sessions = len(values)
    n_blocks = (n_sessions + block_size - 1) // block_size
    starts = rng.integers(n_sessions, size=(repetitions, n_blocks))
    indices = (starts[:, :, None] + np.arange(block_size)) % n_sessions
    replicates = values[indices.reshape(repetitions, -1)[:, :n_sessions]]
    denominators = np.isfinite(replicates).sum(axis=1)
    valid = denominators > 0
    limits = np.quantile(
        np.nansum(replicates[valid], axis=1) / denominators[valid], [0.025, 0.975]
    )
    return float(limits[0]), float(limits[1])


def _compare_title_predictions(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE paired_positions AS
        SELECT t.sample AS variant,b.sample AS reference,t.target,t.session,t.cik,
               t.ticker,t.id,t.month,
               b.predicted_sign AS reference_sign,t.predicted_sign AS variant_sign,
               t.realized_sign,
               b.positive_probability AS reference_probability,
               t.positive_probability AS variant_probability,t.source_rank
        FROM positions t
        JOIN positions b USING(target,session,cik,ticker,id,month,source_rank,
                               training_rows,realized_return,realized_sign)
        WHERE (t.sample,b.sample) IN (
            ('gemma_title','body'),('minilm_title','body'),('minilm_title','gemma_title')
        );

        CREATE TABLE paired_days AS
        SELECT t.sample AS variant,b.sample AS reference,t.target,t.session,
               t.month,t.evaluated,
               b.positions,
               b.long_exposure AS reference_long_leg,
               t.long_exposure AS variant_long_leg,
               b.short_exposure AS reference_short_leg,
               t.short_exposure AS variant_short_leg,
               b.long_return AS reference_long_return,
               t.long_return AS variant_long_return,
               b.short_security_return AS reference_short_return,
               t.short_security_return AS variant_short_return,
               b.portfolio_return AS reference_return,
               t.portfolio_return AS variant_return,
               t.portfolio_return-b.portfolio_return AS portfolio_delta
        FROM daily t JOIN daily b
            USING(target,session,month,evaluated,positions,disposition)
        WHERE (t.sample,b.sample) IN (
            ('gemma_title','body'),('minilm_title','body'),('minilm_title','gemma_title')
        );
        """
    )
    for table, matched in (("positions", "paired_positions"), ("daily", "paired_days")):
        counts = dict(
            con.table(table)
            .filter("sample IN ('body','gemma_title','minilm_title')")
            .aggregate("sample, count(*)")
            .fetchall()
        )
        matching = con.table(matched).aggregate("variant, reference, count(*)")
        expected = {
            (variant, reference, counts.get(variant))
            for variant, reference in TITLE_CONTRASTS
        }
        if (
            len(counts) != 3
            or len(set(counts.values())) != 1
            or set(matching.fetchall()) != expected
        ):
            msg = f"Title {table} do not match the fixed body prediction support"
            raise ValueError(msg)


def report_lopez_title_probes(
    sample: Annotated[Path, typer.Option()],
    gemma: Annotated[Path, typer.Option()],
    minilm: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
) -> None:
    """Compare title and body vectors on the same rolling probe and sessions."""
    variants = {"gemma_title": (gemma, 768), "minilm_title": (minilm, 384)}
    fit_probes(sample, output, title_vectors=variants)
    with duckdb.connect(config={"threads": "1"}) as con:
        load_portfolio_inputs(con, sample, output)
        build_portfolio_days(con)
        _compare_title_predictions(con)
        for table in ("paired_positions", "paired_days"):
            con.sql(f"FROM {table} ORDER BY ALL").write_csv(
                str(output / f"{table}.csv"), header=True
            )
        portfolio_metrics(con).write_csv(str(output / "portfolios.csv"), header=True)
        con.sql(
            """SELECT sample,target,count_if(disposition='fit') AS fits,
                      count_if(convergence_warning IS NOT NULL) AS convergence_warnings
               FROM windows GROUP BY sample,target ORDER BY sample,target"""
        ).write_csv(str(output / "fits.csv"), header=True)
        con.sql(
            """SELECT variant,reference,target,count(*) AS predictions,
                      count_if(reference_sign<>variant_sign) AS changed_sign,
                      count_if(reference_sign=-variant_sign AND variant_sign<>0)
                          AS reversed_sign,
                      count_if(source_rank=1) AS chosen_predictions,
                      count_if(source_rank=1 AND reference_sign<>variant_sign)
                          AS changed_chosen_sign,
                      count_if(source_rank=1 AND reference_sign=-variant_sign
                               AND variant_sign<>0)
                          AS reversed_chosen_sign,
                      avg((reference_sign=realized_sign)::DOUBLE) AS reference_accuracy,
                      avg((variant_sign=realized_sign)::DOUBLE) AS variant_accuracy
               FROM paired_positions GROUP BY ALL ORDER BY variant,reference,target"""
        ).write_csv(str(output / "prediction_changes.csv"), header=True)
        con.sql(
            """SELECT variant,reference,target,count(*) AS scheduled_sessions,
                      count_if(evaluated) AS evaluated_sessions,
                      count_if(reference_long_leg<>variant_long_leg)
                          AS changed_long_leg,
                      count_if(reference_short_leg<>variant_short_leg)
                          AS changed_short_leg,
                      count_if(sign(reference_return)<>sign(variant_return))
                          AS changed_return_sign,
                      count_if(reference_return*variant_return<0)
                          AS reversed_return_sign,
                      avg(variant_long_return-reference_long_return) AS mean_long_delta,
                      avg(variant_short_return-reference_short_return)
                          AS mean_short_security_delta,
                      avg(portfolio_delta) AS mean_portfolio_delta
               FROM paired_days GROUP BY ALL ORDER BY variant,reference,target"""
        ).write_csv(str(output / "portfolio_changes.csv"), header=True)
        with (output / "paired_drift_intervals.csv").open("w", newline="") as intervals:
            writer = csv.writer(intervals)
            writer.writerow(
                (
                    "variant",
                    "reference",
                    "block_sessions",
                    "replicates",
                    "seed",
                    "lower",
                    "upper",
                )
            )
            for variant, reference in TITLE_CONTRASTS:
                for block_size in (21, 5):
                    interval = _paired_drift_interval(
                        con, variant, reference, block_size
                    )
                    writer.writerow(
                        (variant, reference, block_size, 10_000, SEED, *interval)
                    )
