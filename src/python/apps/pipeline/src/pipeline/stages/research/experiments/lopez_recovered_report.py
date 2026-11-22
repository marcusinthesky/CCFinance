"""Reconcile original and recovered overnight panels and verify baseline refits."""

from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

from .lopez_lira_tang import (
    _load_portfolio_inputs,
    _portfolio_days,
    _portfolio_metrics,
    fit_lopez_probes,
)

PROCESSED = Path("data/processed/experiments")
RESEARCH = Path("data/research/experiments")
OUTPUT = RESEARCH / "lopez-recovered"


def report_lopez_recovered() -> None:
    """Write the article dispositions, panel transitions and paired rolling results."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    baseline = PROCESSED / "lopez-lira-tang-sample"
    expanded = PROCESSED / "lopez-recovered-sample"
    saved = RESEARCH / "lopez-lira-tang-probes"
    with TemporaryDirectory() as temporary:
        refit = Path(temporary)
        fit_lopez_probes(baseline, refit)
        for name in ("predictions.csv", "windows.csv"):
            if (refit / name).read_bytes() != (saved / name).read_bytes():
                msg = f"Baseline refit differs in {name}"
                raise ValueError(msg)
    fit_lopez_probes(expanded, OUTPUT)
    with duckdb.connect() as con:
        _load_portfolio_inputs(con, expanded, OUTPUT)
        _portfolio_days(con)
        _portfolio_metrics(con).write_csv(str(OUTPUT / "portfolios.csv"), header=True)
        con.read_parquet(str(baseline / "sample.parquet")).create_view("base")
        con.read_parquet(str(expanded / "sample.parquet")).create_view("expanded")
        con.read_parquet(str(expanded / "eligibility.parquet")).create_view(
            "eligibility"
        )
        clocks = PROCESSED / "lopez-recovered-events/recovered.parquet"
        con.read_parquet(str(clocks)).create_view("clocks")
        con.read_csv(str(saved / "windows.csv")).create_view("frozen_windows")
        con.sql("""
            SELECT c.*,e.cik,coalesce(e.sample_status, CASE WHEN clock_status='eligible'
                THEN 'outside_fixed_roster' ELSE clock_status END) AS disposition
            FROM clocks c LEFT JOIN eligibility e USING(id) ORDER BY c.id,e.cik
        """).write_csv(str(OUTPUT / "recovered_dispositions.csv"), header=True)
        con.sql("""
            SELECT b.id,b.cik,b.session,e.sample_status FROM base b
            ANTI JOIN expanded x USING(id,cik) LEFT JOIN eligibility e USING(id,cik)
            ORDER BY b.session,b.id,b.cik
        """).write_csv(str(OUTPUT / "displaced.csv"), header=True)
        con.sql("""
            SELECT w.month,w.training_start,w.training_end,
                b.training_rows AS baseline_rows,w.training_rows AS expanded_rows,
                b.training_articles AS baseline_articles,
                w.training_articles AS expanded_articles,
                b.training_security_sessions AS baseline_firm_sessions,
                w.training_security_sessions AS expanded_firm_sessions,
                b.disposition AS baseline_fit,w.disposition AS expanded_fit
            FROM windows w JOIN frozen_windows b USING(sample,target,month)
            WHERE sample='body' AND target='drift' ORDER BY month
        """).write_csv(str(OUTPUT / "training_support.csv"), header=True)
        con.sql("""
            WITH panels AS (
                SELECT 'baseline' AS panel,id,cik,session FROM base
                UNION ALL SELECT 'expanded',id,cik,session FROM expanded
            ), scoped AS (
                SELECT 'full' AS period,* FROM panels UNION ALL
                SELECT 'evaluation',* FROM panels WHERE session>='2021-10-01'
            ), breadth AS (
                SELECT period,panel,session,count(DISTINCT cik) AS firms
                FROM scoped GROUP BY ALL
            )
            SELECT period,panel,count(*) AS article_firm_rows,
                count(DISTINCT id) AS articles,
                count(DISTINCT (cik,session)) AS firm_sessions,
                count(DISTINCT session) AS sessions,
                count(DISTINCT session) FILTER (WHERE firms>=4) AS four_firm_sessions
            FROM scoped JOIN breadth USING(period,panel,session)
            GROUP BY ALL ORDER BY ALL
        """).write_csv(str(OUTPUT / "panel_support.csv"), header=True)
