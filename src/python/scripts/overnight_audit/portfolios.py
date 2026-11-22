"""Compare overnight drift fits and portfolio support on the exchange calendar."""

import csv
import warnings
from pathlib import Path

import duckdb
import numpy as np
from pipeline.stages.research.experiments.lopez_lira_tang.portfolios import (
    build_portfolio_days,
    load_portfolio_inputs,
)
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

DATA = Path("data/processed/experiments")
REPORT = Path("data/research/experiments")
OUT = Path("data/inputs/lopez-lira-tang/sensitivity")
BASE = DATA / "lopez-lira-tang-sample"


def save(name: str, rows: list[dict]) -> None:
    """Write a named summary table."""
    with (OUT / name).open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def refit(con: duckdb.DuckDBPyConnection) -> None:
    """Verify the reference fit before varying solver settings."""
    rows = con.execute("""
        SELECT id,cik,ticker,session,published_at,captured_at,label_observed_at,
               drift,embedding FROM baseline
               ORDER BY session,cik,ticker,published_at,captured_at,id
    """).fetchall()
    x = np.asarray([r[8] for r in rows], dtype=np.float64)
    y = np.sign([r[7] for r in rows]).astype(int)
    sessions = np.array([r[3] for r in rows], dtype="datetime64[D]")
    observable = np.array([r[6] for r in rows], dtype="datetime64[s]")
    windows = con.sql("""SELECT month,training_start,test_end,training_rows
        FROM windows WHERE sample='body' AND target='drift' AND disposition='fit'
        ORDER BY month""").fetchall()
    con.execute("""CREATE TABLE refits(id VARCHAR,cik BIGINT,session DATE,
        iterations INTEGER,c DOUBLE,sign INTEGER)""")
    summary = []
    for iterations, c in ((10, 1.0), (1000, 1.0), (1000, 0.1)):
        warned = 0
        predictions = []
        for month, start, end, n in windows:
            train = (sessions >= np.datetime64(start)) & (
                sessions < np.datetime64(month)
            )
            train &= observable < np.datetime64(month)
            test = np.flatnonzero(
                (sessions >= np.datetime64(month)) & (sessions <= np.datetime64(end))
            )
            if train.sum() != n:
                raise ValueError("Training window differs from saved baseline")
            with warnings.catch_warnings(record=True) as messages:
                warnings.simplefilter("always", ConvergenceWarning)
                model = LogisticRegression(
                    C=c, max_iter=iterations, random_state=42, solver="lbfgs", n_jobs=1
                ).fit(x[train], y[train])
            warned += any(issubclass(m.category, ConvergenceWarning) for m in messages)
            for i, sign in zip(test, model.predict(x[test]), strict=True):
                predictions.append(
                    (rows[i][0], rows[i][1], rows[i][3], iterations, c, int(sign))
                )
        con.executemany("INSERT INTO refits VALUES (?,?,?,?,?,?)", predictions)
        metrics = con.execute(
            """
            WITH signals AS (
                SELECT p.*,r.sign,sign<>predicted_sign AS changed FROM positions p
                JOIN refits r USING(id,cik,session) WHERE sample='body'
                  AND target='drift'
                  AND r.iterations=? AND r.c=? AND source_rank=1
            ), days AS (
                SELECT session,count(*) AS signals,count_if(changed) AS changed,
                    count_if(sign=1)>1 AS long_leg,count_if(sign=-1)>1 AS short_leg,
                    CASE WHEN long_leg THEN avg(realized_return) FILTER (WHERE sign=1)
                         ELSE 0 END
                    - CASE WHEN short_leg THEN avg(realized_return)
                          FILTER (WHERE sign=-1)
                        ELSE 0 END AS drift
                FROM signals GROUP BY session
            )
            SELECT sum(signals),sum(changed),count(*),count_if(long_leg AND short_leg),
                avg(drift)*10000 FROM days
        """,
            [iterations, c],
        ).fetchone()
        if iterations == 10 and (
            metrics[1] != 0 or abs(metrics[4] + 10.1501002893) > 1e-8
        ):
            raise ValueError(
                "Reference refit fails to reproduce chosen signals or mean"
            )
        summary.append(
            {
                "max_iter": iterations,
                "C": c,
                "fits": len(windows),
                "warnings": warned,
                "signals": metrics[0],
                "changed": metrics[1],
                "evaluated": metrics[2],
                "both": metrics[3],
                "mean_bp": metrics[4],
            }
        )
    save("solver.csv", summary)


def main() -> None:
    """Compute signed leg returns and paired contrasts with the same bootstrap draws."""
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for panel, sample, probes in (
        ("original", BASE, REPORT / "lopez-lira-tang-probes"),
        ("recovered", DATA / "lopez-recovered-sample", REPORT / "lopez-recovered"),
    ):
        with duckdb.connect() as con:
            load_portfolio_inputs(con, sample, probes)
            build_portfolio_days(con)
            if panel == "original":
                con.read_parquet(str(BASE / "sample.parquet")).create_view("baseline")
                con.sql("""SELECT exchange,dated_match=0 AS fallback,count(*) AS rows,
                    count(DISTINCT cik) AS issuers FROM baseline
                    GROUP BY ALL ORDER BY ALL
                    """).write_csv(str(OUT / "universe.csv"), header=True)
                refit(con)
            frames.append(
                con.sql("""SELECT session,evaluated,long_exposure,short_exposure,
                long_return,-short_security_return FROM daily WHERE sample='body'
                AND target='drift' ORDER BY session""").fetchall()
            )
    if [r[0] for r in frames[0]] != [r[0] for r in frames[1]]:
        raise ValueError("Panels do not share the exchange calendar")
    a, b = (np.asarray([r[1:] for r in f], dtype=float) for f in frames)
    observed = np.flatnonzero((a[:, 0] + b[:, 0]) > 0)
    a, b = a[observed[0] : observed[-1] + 1], b[observed[0] : observed[-1] + 1]
    size = len(a)
    starts = np.random.default_rng(42).integers(
        0, size, size=(10000, (size + 20) // 21)
    )
    draws = ((starts[:, :, None] + np.arange(21)) % size).reshape(10000, -1)[:, :size]
    summary = []
    for support in ("all", "active", "both", "long", "short"):
        samples = []
        for data in (a, b):
            evaluated, long, short, rlong, rshort = data.T
            legs = long + short
            selected = {
                "all": evaluated > 0,
                "active": legs > 0,
                "both": legs == 2,
                "long": long > 0,
                "short": short > 0,
            }[support]
            leg_return = {"long": rlong, "short": rshort}.get(support, rlong + rshort)
            exposures = np.ones(size) if support in ("long", "short") else legs
            samples.append((selected, leg_return * 10000, exposures))
        common = samples[0][0] & samples[1][0]
        for cost in (0, 5):
            totals = []
            for panel, (selected, returns, exposures) in zip(
                ("original", "recovered"), samples, strict=True
            ):
                values = returns - 2 * cost * exposures
                totals.append(values)
                for dates, mask in (("own", selected), ("common", common)):
                    summarize(summary, draws, panel, support, dates, cost, mask, values)
            summarize(
                summary,
                draws,
                "recovered-original",
                support,
                "common",
                cost,
                common,
                totals[1] - totals[0],
            )
    save("returns.csv", summary)


def summarize(
    summary: list[dict],
    draws: np.ndarray,
    panel: str,
    support: str,
    dates: str,
    cost: int,
    selected: np.ndarray,
    values: np.ndarray,
) -> None:
    """Use each block sample's observed numerator and denominator."""
    values = np.where(selected, values, np.nan)
    replicated = np.nanmean(values[draws], axis=1)
    low, high = np.nanquantile(replicated, [0.025, 0.975])
    summary.append(
        {
            "panel": panel,
            "support": support,
            "dates": dates,
            "one_way_bp": cost,
            "sessions": int(selected.sum()),
            "mean_bp": np.nanmean(values),
            "lo": low,
            "hi": high,
        }
    )


if __name__ == "__main__":
    main()
