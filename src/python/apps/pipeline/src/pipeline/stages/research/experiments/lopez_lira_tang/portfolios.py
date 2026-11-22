"""Construct overnight portfolios and report their returns and support."""

import json
import shutil
from pathlib import Path
from typing import Annotated

import duckdb
import typer

from .probes import TARGETS


def build_portfolio_days(con: duckdb.DuckDBPyConnection) -> None:
    """Create first-story positions and daily portfolio returns."""
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


def portfolio_metrics(con: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyRelation:
    """Summarize the daily returns by prediction target and sample."""
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


def load_portfolio_inputs(
    con: duckdb.DuckDBPyConnection, sample: Path, probes: Path
) -> None:
    """Load session, prediction and fit-window tables for portfolio reports."""
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


def report_lopez_portfolios(
    sample: Annotated[Path, typer.Option()],
    probes: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
) -> None:
    """Write reaction and drift metrics, daily legs, stories and support."""
    output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(config={"threads": "1"}) as con:
        load_portfolio_inputs(con, sample, probes)
        build_portfolio_days(con)
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
        metrics = portfolio_metrics(con)
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
