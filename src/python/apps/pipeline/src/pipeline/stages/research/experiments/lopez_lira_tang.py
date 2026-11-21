"""Fit the monthly body-vector probes and report their daily portfolio diagnostics."""

import csv
import json
import shutil
import warnings
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated

import duckdb
import numpy as np
import typer
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

TARGETS = ("reaction", "drift")
SAMPLES = ("body", "title_named_body")
MIN_ROWS = 100
MAX_ITER = 10
SEED = 42
FEATURES = 768


def _shift_month(day: date, months: int) -> date:
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    return date(year, month + 1, min(day.day, monthrange(year, month + 1)[1]))


def training_start(month: date) -> date:
    """Apply the archive's six-month offset to the inclusive last training day."""
    return _shift_month(month - timedelta(days=1), -6) + timedelta(days=1)


def fit_disposition(training_rows: int, test_rows: int, classes: set[int]) -> str:
    """Identify the archive's fitting requirements without stopping later months."""
    if test_rows == 0:
        return "empty_test_month"
    if training_rows < MIN_ROWS:
        return "insufficient_training"
    if len(classes) < 2:
        return "single_class"
    if 1 not in classes:
        return "no_positive_class"
    return "fit"


def fit_lopez_probes(
    sample: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
    prediction_start: str = "2021-10-01",
    prediction_end: str = "2024-05-31",
) -> None:
    """Fit both sign classifiers and write predictions and a monthly audit."""
    first = date.fromisoformat(prediction_start)
    last = date.fromisoformat(prediction_end)
    if first.day != 1 or last < first:
        msg = (
            "Prediction start must be the first of a month, on or before prediction end"
        )
        raise ValueError(msg)
    output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(config={"threads": "2"}) as con:
        rows = con.execute(
            """
            SELECT
                id,cik,ticker,session,published_at,captured_at,label_observed_at,title_named,
                   reaction,drift,embedding
            FROM read_parquet(?)
            ORDER BY session,cik,ticker,published_at,captured_at,id
            """,
            [str(sample / "sample.parquet")],
        ).fetchall()
    x = np.asarray([row[10] for row in rows], dtype=np.float64).reshape(-1, FEATURES)
    y = np.sign(
        np.asarray([[row[8], row[9]] for row in rows], dtype=np.float64).reshape(-1, 2)
    ).astype(np.int8)
    sessions = np.asarray([row[3] for row in rows], dtype="datetime64[D]")
    observable = np.asarray([row[6] for row in rows], dtype="datetime64[s]")
    named = np.asarray([row[7] for row in rows], dtype=np.bool_)
    if not np.all(np.isfinite(x)):
        msg = "Nonfinite body embedding coordinates"
        raise ValueError(msg)

    with (
        (output / "predictions.csv").open("w", newline="") as predictions,
        (output / "windows.csv").open("w", newline="") as windows,
    ):
        prediction_writer = csv.writer(predictions)
        prediction_writer.writerow(
            (
                "sample",
                "target",
                "month",
                "id",
                "cik",
                "ticker",
                "session",
                "published_at",
                "captured_at",
                "label_observed_at",
                "realized_return",
                "realized_sign",
                "predicted_sign",
                "positive_probability",
                "training_rows",
            )
        )
        window_writer = csv.writer(windows)
        window_writer.writerow(
            (
                "sample",
                "target",
                "month",
                "training_start",
                "training_end",
                "test_end",
                "last_label_observed_at",
                "training_rows",
                "training_articles",
                "training_securities",
                "training_security_sessions",
                "negative",
                "zero",
                "positive",
                "test_rows",
                "features",
                "solver",
                "max_iter",
                "random_state",
                "disposition",
                "iterations",
                "convergence_warning",
            )
        )
        for cohort in SAMPLES:
            selected = (
                named
                if cohort == "title_named_body"
                else np.ones(len(rows), dtype=np.bool_)
            )
            month = first
            while month <= last:
                start = max(date(2021, 1, 1), training_start(month))
                next_month = _shift_month(month, 1)
                # Both returns are known by the training session's close.
                bound = datetime.combine(month, time.min)
                train = np.flatnonzero(
                    selected
                    & (sessions >= np.datetime64(start))
                    & (sessions < np.datetime64(month))
                    & (observable < np.datetime64(bound))
                )
                test = np.flatnonzero(
                    selected
                    & (sessions >= np.datetime64(month))
                    & (sessions < np.datetime64(next_month))
                    & (sessions <= np.datetime64(last))
                )
                for target_index, target in enumerate(TARGETS):
                    labels = y[train, target_index]
                    disposition = fit_disposition(
                        len(train), len(test), set(map(int, labels))
                    )
                    convergence = None
                    iterations = None
                    if disposition == "fit":
                        with warnings.catch_warnings(record=True) as messages:
                            warnings.simplefilter("always", ConvergenceWarning)
                            model = LogisticRegression(
                                max_iter=MAX_ITER,
                                random_state=SEED,
                                solver="lbfgs",
                                n_jobs=1,
                            ).fit(x[train], labels)
                        iterations = int(max(model.n_iter_))
                        convergence = next(
                            (
                                str(item.message)
                                for item in messages
                                if issubclass(item.category, ConvergenceWarning)
                            ),
                            "",
                        )
                        signs = model.predict(x[test])
                        positive_column = int(np.flatnonzero(model.classes_ == 1)[0])
                        probabilities = model.predict_proba(x[test])[:, positive_column]
                        for index, sign, probability in zip(
                            test, signs, probabilities, strict=True
                        ):
                            row = rows[index]
                            prediction_writer.writerow(
                                (
                                    cohort,
                                    target,
                                    month,
                                    *row[:7],
                                    row[8 + target_index],
                                    int(y[index, target_index]),
                                    int(sign),
                                    float(probability),
                                    len(train),
                                )
                            )
                    window_writer.writerow(
                        (
                            cohort,
                            target,
                            month,
                            start,
                            month - timedelta(days=1),
                            min(last, next_month - timedelta(days=1)),
                            max((rows[i][6] for i in train), default=None),
                            len(train),
                            len({rows[i][0] for i in train}),
                            len({rows[i][1:3] for i in train}),
                            len({rows[i][1:4] for i in train}),
                            int(np.sum(labels == -1)),
                            int(np.sum(labels == 0)),
                            int(np.sum(labels == 1)),
                            len(test),
                            FEATURES,
                            "lbfgs",
                            MAX_ITER,
                            SEED,
                            disposition,
                            iterations,
                            convergence,
                        )
                    )
                month = next_month


def _portfolio_days(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE positions AS
        SELECT *, row_number() OVER (
            PARTITION BY sample,target,session,cik,ticker ORDER BY
                published_at,captured_at,id
        ) AS source_rank
        FROM predictions;
        CREATE TABLE daily AS
        WITH actual_days AS (
            SELECT sample,target,session,count(*) AS positions,
                   count_if(predicted_sign=1) AS longs,
                   count_if(predicted_sign=-1) AS shorts,
                   count_if(predicted_sign=0) AS neutrals,
                   CASE WHEN count_if(predicted_sign=1)>1
                        THEN avg(realized_return) FILTER (WHERE predicted_sign=1) ELSE 0
                            END AS long_return,
                   CASE WHEN count_if(predicted_sign=-1)>1
                        THEN avg(realized_return) FILTER (WHERE predicted_sign=-1) ELSE
                            0 END AS short_security_return
            FROM positions WHERE source_rank=1 GROUP BY sample,target,session
        ), all_days AS (
            SELECT w.sample,w.target,w.month,s.session,w.disposition,
                   d.positions IS NOT NULL AS evaluated,
                   coalesce(d.positions,0) AS positions,
                   coalesce(d.longs,0) AS longs,
                   coalesce(d.shorts,0) AS shorts,
                   coalesce(d.neutrals,0) AS neutrals,
                   (coalesce(d.longs,0)>1)::INTEGER AS long_exposure,
                   (coalesce(d.shorts,0)>1)::INTEGER AS short_exposure,
                   d.long_return, d.short_security_return,
                   d.long_return-d.short_security_return AS portfolio_return
            FROM sessions s JOIN windows w ON s.session BETWEEN w.month AND w.test_end
            LEFT JOIN actual_days d USING(sample,target,session)
        )
        SELECT *, long_exposure+short_exposure AS gross_exposure,
                  long_exposure-short_exposure AS net_exposure
        FROM all_days
        """
    )


def _portfolio_metrics(con: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyRelation:
    return con.sql(
        """
        SELECT sample,target,count(*) AS scheduled_days,count_if(evaluated) AS
            evaluated_days,
               count_if(evaluated AND gross_exposure=0) AS evaluated_zero_leg_days,
               count_if(gross_exposure=1) AS one_leg_days,
               count_if(gross_exposure=2) AS both_leg_days,
               count_if(long_exposure>0) AS long_leg_days,count_if(short_exposure>0) AS
                   short_leg_days,
               sum(positions)::BIGINT AS positions,max(positions) AS max_positions,
               CASE WHEN count_if(evaluated)>=2 THEN avg((portfolio_return>0)::DOUBLE)
                   END AS hit_rate,
               CASE WHEN count_if(evaluated)>=2 THEN avg(portfolio_return) END AS
                   mean_return,
               avg(portfolio_return) FILTER (WHERE gross_exposure>0) AS active_day_mean,
               avg(portfolio_return) FILTER (WHERE gross_exposure=2) AS both_leg_mean,
               CASE WHEN target='drift' AND stddev_samp(portfolio_return)>0
                    THEN sqrt(252)*avg(portfolio_return)/stddev_samp(portfolio_return)
                        END AS annualized_sharpe
        FROM daily GROUP BY sample,target ORDER BY sample,target
        """
    )


def _write_portfolio_figure(con: duckdb.DuckDBPyConnection, output: Path) -> None:
    dates = con.sql("SELECT DISTINCT session FROM daily ORDER BY session").fetchall()
    ticks = range(0, len(dates), 100)
    tick_positions = ",".join(str(tick + 1) for tick in ticks)
    tick_labels = ",".join(dates[tick][0].strftime("%Y-%m") for tick in ticks)
    con.sql(
        """
        WITH lines AS (
            SELECT session,target, 100 * sum(coalesce(portfolio_return,0))
                OVER (PARTITION BY target ORDER BY session) AS cumulative_return_pct
            FROM daily WHERE sample='body'
        )
        SELECT row_number() OVER (ORDER BY session) AS session_number,
               session, max(cumulative_return_pct) FILTER
                   (WHERE target='reaction') AS reaction_pct,
               max(cumulative_return_pct) FILTER (WHERE target='drift') AS drift_pct
        FROM lines GROUP BY session ORDER BY session
        """
    ).write_csv(str(output / "portfolio_figure_data.csv"), header=True)
    (output / "portfolio_figure.tex").write_text(
        r"""\documentclass{article}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\pagestyle{empty}
\begin{document}
\noindent
\begin{tikzpicture}
\begin{axis}[
  width=11cm,height=7cm,
"""
        + f"  xtick={{{tick_positions}}}, xticklabels={{{tick_labels}}},\n"
        + r"""  xticklabel style={rotate=30,anchor=east},
  ylabel={Cumulative sum of daily returns (percent)},
  ymajorgrids,legend pos=south west,
]
\addplot[blue,thick] table[x=session_number,y=reaction_pct,col sep=comma]
  {portfolio_figure_data.csv};
\addlegendentry{Reaction}
\addplot[orange,thick,dashed] table[x=session_number,y=drift_pct,col sep=comma]
  {portfolio_figure_data.csv};
\addlegendentry{Drift}
\end{axis}
\end{tikzpicture}
\end{document}
""",
        encoding="utf-8",
    )


def report_lopez_portfolios(
    sample: Annotated[Path, typer.Option()],
    probes: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
) -> None:
    """Write reaction and drift metrics, daily legs, stories and support."""
    output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(config={"threads": "1"}) as con:
        con.read_parquet(str(sample / "sessions.parquet")).create("sessions")
        # Preserve the output schema when every fit is skipped.
        con.execute(
            """
            CREATE TABLE predictions AS SELECT * FROM read_csv(?, types={
                'sample':'VARCHAR','target':'VARCHAR','month':'DATE','id':'VARCHAR','cik':'BIGINT',
                'ticker':'VARCHAR','session':'DATE','published_at':'TIMESTAMP','captured_at':'TIMESTAMP',
                'label_observed_at':'TIMESTAMP','realized_return':'DOUBLE','realized_sign':'INTEGER',
                'predicted_sign':'INTEGER','positive_probability':'DOUBLE','training_rows':'INTEGER'
            });
            """,
            [str(probes / "predictions.csv")],
        )
        con.read_csv(str(probes / "windows.csv"), header=True).create("windows")
        _portfolio_days(con)
        con.sql("FROM daily ORDER BY target,sample,session").write_csv(
            str(output / "daily_portfolios.csv"), header=True
        )
        con.sql(
            "FROM positions ORDER BY target,sample,session,cik,ticker,source_rank"
        ).write_parquet(str(output / "story_positions.parquet"), compression="zstd")
        con.sql(
            """SELECT w.*, count_if(d.evaluated) AS evaluated_days,
                      count_if(d.gross_exposure>0) AS active_days,
                      count_if(d.gross_exposure=2) AS paired_leg_days
               FROM windows w LEFT JOIN daily d USING(sample,target,month)
               GROUP BY ALL ORDER BY sample,target,month"""
        ).write_csv(str(output / "monthly_support.csv"), header=True)
        _write_portfolio_figure(con, output)
        metrics = _portfolio_metrics(con)
        summaries = [
            dict(zip(metrics.columns, row, strict=True)) for row in metrics.fetchall()
        ]
        for target in TARGETS:
            metrics.filter(f"target='{target}'").write_csv(
                str(output / f"{target}.csv"), header=True
            )
        fit_rows = con.sql(
            """SELECT sample,target,count_if(disposition='fit') AS fits,
                      count_if(disposition='fit' AND convergence_warning IS NOT NULL) AS
                          warnings,
                      max(training_rows) AS max_training_rows,
                      min(training_rows) FILTER (WHERE disposition='fit') AS
                          smallest_fit
               FROM windows GROUP BY sample,target ORDER BY sample,target"""
        )
        model_support = [
            dict(zip(fit_rows.columns, row, strict=True)) for row in fit_rows.fetchall()
        ]
        con.read_parquet(str(sample / "sample.parquet")).create("eligible")
        vector_use = con.sql(
            """SELECT count(*) AS eligible_article_security_rows,
                      count(DISTINCT id) AS distinct_body_vectors,
                      count(DISTINCT id) FILTER (WHERE linked_issuers>1) AS
                          vectors_from_multi_issuer_bodies,
                      count(*)-count(DISTINCT id) AS vector_reuses
               FROM eligible"""
        )
        vector_support = dict(
            zip(vector_use.columns, vector_use.fetchall()[0], strict=True)
        )
    for filename in ("attrition.csv", "daily_support.csv"):
        shutil.copyfile(sample / filename, output / filename)
    (output / "metrics.json").write_text(
        json.dumps(
            {
                "portfolios": summaries,
                "models": model_support,
                "vectors": vector_support,
            },
            indent=2,
        )
        + "\n"
    )
