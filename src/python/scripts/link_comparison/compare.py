"""Compare issuer linkers on frozen seed-43 mentions. Run from repository root."""

import json
from pathlib import Path

import duckdb
import numpy as np
from pipeline.stages.processed.company_links import (
    LEARNED_ANCHORS,
    LEARNED_RATE,
    LEARNED_SHARE,
    link_unit,
)
from pipeline.stages.processed.issuers import normalize
from pipeline.stages.research.experiments.company_links import SECURITY

ROOT = Path("data/inputs/company-links/comparison")
WORK = Path(".runtime/link-comparison")
SYSTEMS = ("names", "wiki", "prior_years", "production")


def setup(con: duckdb.DuckDBPyConnection) -> None:
    """Build the held-out frame and retain the other mentions in its articles."""
    con.create_function("normalize_name", normalize, ["VARCHAR"], "VARCHAR")
    for table in ("aliases", "tickers"):
        con.read_parquet(f"data/processed/issuers/{table}.parquet").create(table)
    con.execute(SECURITY)
    con.execute("""
        CREATE TABLE frame AS SELECT s.*, j.decision, j.cik AS gold
        FROM 'data/processed/experiments/company-links/sample/mentions.parquet' s
        JOIN read_json_auto(
            'data/processed/experiments/company-links/labels/mentions.jsonl'
        ) j USING (id,start)
        WHERE s.split='test' AND j.judge='primary' AND j.decision <> 'unsure';
        CREATE VIEW corpus AS SELECT *
        FROM 'data/processed/company-links/mentions/*.parquet';
        CREATE VIEW dates AS SELECT id, captured, published
        FROM 'data/processed/articles/articles.parquet';
        CREATE TABLE context AS
        SELECT m.*, f.day, f.host, year(least(f.day,d.captured::date)) AS cutoff_year,
            CASE WHEN method='anchor' THEN cik END AS anchor_cik
        FROM corpus m JOIN (SELECT DISTINCT id,day,host FROM frame) f USING(id)
        JOIN dates d USING(id);
        CREATE TABLE names AS
        SELECT f.id,f.start,count(DISTINCT a.cik) AS options,
               CASE WHEN count(DISTINCT a.cik)=1 THEN min(a.cik) END AS cik
        FROM frame f JOIN aliases a ON a.key=f.key
        WHERE a.source IN ('sec_name','former_name','wikidata_label')
        AND (a.valid_from IS NULL OR a.valid_from<=f.day)
        AND (a.valid_to IS NULL OR a.valid_to>=f.day)
        AND security(a.cik,f.day) IS NOT NULL GROUP BY ALL;
        CREATE TABLE publishers(domain VARCHAR,key VARCHAR);
        CREATE TABLE historical(id VARCHAR,start BIGINT,cik BIGINT);
    """)


def replay(con: duckdb.DuckDBPyConnection) -> None:
    """Replay production resolution with priors fixed before each calendar year."""
    con.execute("""
        CREATE TABLE history AS SELECT m.key,
            year(greatest(d.captured::date,d.published::date)) AS yr,
            CASE WHEN m.method='anchor' THEN m.cik END AS cik, count(*) AS n
        FROM corpus m JOIN dates d USING(id)
        SEMI JOIN (SELECT DISTINCT key FROM context) k USING(key)
        WHERE d.captured IS NOT NULL GROUP BY ALL
    """)
    cohorts = con.sql("SELECT DISTINCT cutoff_year FROM context ORDER BY 1").fetchall()
    cohorts.append((None,))
    for (year,) in cohorts:
        con.execute(
            """
            CREATE OR REPLACE TABLE priors AS
            WITH h AS (SELECT key,cik,sum(n) AS n FROM history WHERE yr < ?
                       GROUP BY ALL)
            SELECT * FROM (SELECT *,sum(n) OVER (PARTITION BY key) AS mentions
                           FROM h) WHERE cik IS NOT NULL
        """,
            [year],
        )
        if year is None:
            con.execute("""CREATE OR REPLACE TABLE priors AS
                SELECT * FROM 'data/processed/company-links/priors.parquet'""")
        con.execute(
            """
            CREATE OR REPLACE TABLE known AS
            SELECT key,cik,source,valid_from,valid_to FROM aliases UNION ALL
            SELECT key,cik,'anchor_alias',NULL,NULL FROM (
                SELECT *,sum(n) OVER(PARTITION BY key) AS total FROM priors
            ) p WHERE n>=? AND n>=?*total AND (
                n>=?*mentions OR EXISTS (SELECT 1 FROM aliases a
                WHERE a.cik=p.cik AND starts_with(a.key,p.key)))
        """,
            [LEARNED_ANCHORS, LEARNED_SHARE, LEARNED_RATE],
        )
        staged = WORK / "staged.parquet"
        # Only mention identity is scored. Placeholder article-aggregation inputs
        # below do not participate in candidate generation, ranking or acceptance.
        con.sql(
            """
            SELECT id,start,stop,text,key,anchor_cik,day,host,1 AS length,
                   [0.0] AS local_relevance,[0.0] AS financial_sentiment
            FROM context WHERE $year IS NULL OR cutoff_year=$year
        """,
            params={"year": year},
        ).write_parquet(str(staged))
        targets = {
            t: WORK / f"{t}.parquet" for t in ("mentions", "articles", "unresolved")
        }
        link_unit(
            con,
            staged,
            1.0,
            {"local_relevance": ["substantive"], "financial_sentiment": ["neutral"]},
            targets,
            True,
        )
        if year is None:
            mismatches = con.sql("""
                SELECT count(*) FROM frame f JOIN context c USING(id,start)
                JOIN unit_links u USING(id,start)
                WHERE (CASE WHEN u.link_score>=0.5 THEN u.cik END) IS DISTINCT FROM
                      (CASE WHEN c.link_score>=0.5 THEN c.cik END)
            """).fetchone()[0]
            if mismatches:
                raise ValueError(f"Full-prior replay differs on {mismatches} mentions")
            continue
        con.execute("""
            INSERT INTO historical SELECT id,start,
                   CASE WHEN link_score>=0.5 THEN cik END
            FROM unit_links
        """)


def predictions(con: duckdb.DuckDBPyConnection) -> None:
    """Freeze one row per mention with shared gold and dated-equivalence calls."""
    con.read_csv(str(ROOT / "wiki-pages.csv"), all_varchar=True).create("pages")
    con.execute("""
        CREATE TABLE wiki AS
        WITH mapped AS (SELECT f.id,f.start,p.page,p.qid,
            CASE WHEN security(w.cik,f.day) IS NOT NULL THEN w.cik END AS eligible
        FROM frame f LEFT JOIN pages p ON p.surface=f.text
        LEFT JOIN (SELECT DISTINCT split_part(item,'/',5) AS qid,
                          try_cast(cik AS BIGINT) AS cik
                   FROM 'data/raw/issuers/wikidata/names.csv') w
          ON w.qid=p.qid)
        SELECT id,start,page,qid,CASE WHEN count(DISTINCT eligible)=1 THEN min(eligible)
            END AS cik FROM mapped GROUP BY ALL;
        CREATE TABLE paired AS SELECT f.id,f.start,f.stratum,f.population,
            f.decision,f.gold,coalesce(n.options,0) AS options,w.page,w.qid,
            n.cik AS names,w.cik AS wiki,h.cik AS prior_years,
            CASE WHEN c.link_score>=0.5 THEN c.cik END AS production,
            f.day
        FROM frame f LEFT JOIN names n USING(id,start)
        JOIN wiki w USING(id,start) JOIN context c USING(id,start)
        JOIN historical h USING(id,start)
    """)
    terms = [
        f"coalesce({s}=gold OR security({s},day)=security(gold,day),false) AS {s}_ok"
        for s in SYSTEMS
    ]
    query = "SELECT *, " + ", ".join(terms) + " FROM paired ORDER BY id,start"  # noqa: S608
    result = con.sql(query)
    if len(result) != con.sql("SELECT count(*) FROM frame").fetchone()[0]:
        raise ValueError("Prediction counts differ from the held-out frame")
    result.write_csv(str(ROOT / "predictions.csv"), header=True)


def summarize() -> None:
    """Reweight within strata and share article multipliers across systems."""
    import csv

    with (ROOT / "predictions.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    groups = np.unique([r["stratum"] for r in rows], return_inverse=True)[1]
    ids = np.unique([r["id"] for r in rows], return_inverse=True)[1]
    pop = np.array([int(r["population"]) for r in rows])
    listed = np.array([r["decision"] in ("listed", "listed_missing") for r in rows])
    options = np.array([int(r["options"]) for r in rows])
    domains = {
        "all": np.ones(len(rows), bool),
        "one_name": options == 1,
        "multiple_names": options > 1,
        "no_name": options == 0,
        "no_eligible_issuer": ~listed,
    }
    linked = np.array([[bool(r[s]) for r in rows] for s in SYSTEMS])
    correct = np.array(
        [[r[s + "_ok"].lower() == "true" for r in rows] for s in SYSTEMS]
    )

    def measures(weight: np.ndarray, domain: np.ndarray) -> np.ndarray:
        w = weight * domain
        accepted, hits, gold = linked @ w, correct @ w, listed @ w
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.array(
                [
                    hits / accepted,
                    hits / gold,
                    2 * hits / (gold + accepted),
                    accepted / w.sum(),
                ]
            ).T

    weight = pop / np.bincount(groups)[groups]
    out = {
        "systems": SYSTEMS,
        "metrics": ["precision", "recall", "f1", "assigned_share"],
        "n": len(rows),
        "articles": int(ids.max() + 1),
        "listed": int(listed.sum()),
        "wiki_pages": sum(bool(r["page"]) for r in rows),
        "wiki_qids": sum(bool(r["qid"]) for r in rows),
        "assigned": linked.sum(axis=1).tolist(),
        "correct": correct.sum(axis=1).tolist(),
    }
    for name, domain in domains.items():
        values = measures(weight, domain)
        out[name] = {
            "n": int(domain.sum()),
            "values": [
                [float(v) if np.isfinite(v) else None for v in row] for row in values
            ],
        }
    rng = np.random.default_rng(43)
    draws = []
    for _ in range(2000):
        factors = rng.exponential(size=ids.max() + 1)[ids]
        w = pop * factors / np.bincount(groups, weights=factors)[groups]
        vals = measures(w, domains["all"])[:, 2]
        draws.append(vals[-1] - vals[:-1])
    out["production_minus_other_f1_ci"] = np.quantile(
        draws, [0.025, 0.975], axis=0
    ).T.tolist()
    (ROOT / "metrics.json").write_text(
        json.dumps(out, indent=2, allow_nan=False) + "\n"
    )


if __name__ == "__main__":
    WORK.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(config={"threads": "4", "memory_limit": "6GB"}) as connection:
        setup(connection)
        replay(connection)
        predictions(connection)
    summarize()
