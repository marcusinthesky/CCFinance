"""Estimate company-link precision and recall from adjudicated samples.

The sample and its labels are fixed; link decisions come from the linker
output under evaluation, joined by mention. A link is correct when it names
the judged issuer or the same listed security on the article date. Mention
estimates weight each stratum by its population over its labelled size and
use linearized ratio variances. Subgroups such as years or link methods are
domains of the full sample, never re-weighted subsets. Article estimates treat
the uniform article sample as one stratum. Article recall counts issuers the
judge verified in the issuer reference (those without a CIK are reported as a
coverage share); it is gated on issuers the article is about and also reported
for every issuer it mentions. Judge reliability compares linking labels. Headline
figures count links scored at or above the operating threshold; the
reliability table covers every score. "Unsure" judgements are excluded.

Every estimate is reported for the development split, the test split and both
pooled. Rules are tuned on development labels, so the error table uses
development labels and the gates use the pre-registered test labels. A
confirmation sample drawn after the rules were fixed leaves both splits
untouched, so the paper table shows all three. Agreement with explicit tickers
also carries its count and an exact binomial interval.
"""

import json
import math
from collections import defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Annotated, Any

import duckdb
import typer
from statsmodels.stats.proportion import proportion_confint

type Row = dict[str, Any]
type Indicator = Callable[[Row], float]
DIAGNOSTIC_KEYS = (
    "apple", "amazon", "target", "shell", "delta", "facebook", "meta", "google",
    "twitter", "reuters", "nasdaq", "business wire",
)  # fmt: skip
GATES = {
    "link_precision": 0.95,
    "ambiguous_precision": 0.90,
    "article_recall": 0.85,
    "anchor_agreement": 0.98,
    "audit_kappa": 0.80,
}
SUMMARY = {
    "link_precision": "Mention precision",
    "recall": "Mention recall",
    "nil_precision": "Unlinked precision",
    "ambiguous_precision": "Precision, several candidates",
    "article_precision": "Article precision",
    "article_recall": "Article recall, company-focused",
    "article_recall_mentioned": "Article recall, all mentioned issuers",
}
SPLITS = {"test": "Test", "dev": "Development", "pooled": "Pooled"}


def ratio(rows: Sequence[Row], numerator: Indicator, denominator: Indicator) -> Row:
    """Stratified ratio estimate with a linearized 95% normal interval."""
    strata: dict[object, list[Row]] = defaultdict(list)
    for row in rows:
        strata[row["stratum"]].append(row)
    totals = [0.0, 0.0]
    for members in strata.values():
        weight = float(members[0]["population"]) / len(members)
        totals[0] += weight * sum(map(numerator, members))
        totals[1] += weight * sum(map(denominator, members))
    if totals[1] == 0:
        return {"estimate": None, "standard_error": None, "n": 0}
    estimate = totals[0] / totals[1]
    variance = 0.0
    for members in strata.values():
        size, population = len(members), float(members[0]["population"])
        if size < 2:
            continue
        z = [numerator(row) - estimate * denominator(row) for row in members]
        mean = sum(z) / size
        spread = sum((value - mean) ** 2 for value in z) / (size - 1)
        variance += population**2 * max(0.0, 1 - size / population) * spread / size
    error = math.sqrt(variance) / totals[1]
    return {
        "estimate": estimate,
        "standard_error": error,
        "ci95_low": max(0.0, estimate - 1.96 * error),
        "ci95_high": min(1.0, estimate + 1.96 * error),
        "n": int(sum(map(denominator, rows))),
    }


def domain(
    rows: Sequence[Row], member: Indicator, numerator: Indicator, denominator: Indicator
) -> Row:
    """Estimate a ratio within a subgroup, keeping the full sample's weights."""
    return ratio(
        rows,
        lambda row: member(row) * numerator(row),
        lambda row: member(row) * denominator(row),
    )


def kappa(pairs: Sequence[tuple[str, str]]) -> float | None:
    """Cohen's kappa for two judgements of the same items."""
    if not pairs:
        return None
    observed = sum(a == b for a, b in pairs) / len(pairs)
    categories = {value for pair in pairs for value in pair}
    expected = (
        sum(
            sum(a == c for a, _ in pairs) * sum(b == c for _, b in pairs)
            for c in categories
        )
        / len(pairs) ** 2
    )
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def _rows(con: duckdb.DuckDBPyConnection, query: str) -> list[Row]:
    result = con.sql(query)
    return [
        dict(zip(result.columns, values, strict=True)) for values in result.fetchall()
    ]


# The linking label a judgement implies: an issuer, an issuer missing from the
# reference, or no issuer ("not_listed" and "not_company" are equivalent here).
IDENTITY = """CASE {j}.decision WHEN 'listed' THEN 'cik:' || {j}.cik
    WHEN 'listed_missing' THEN 'listed_missing' ELSE 'none' END"""


def _pairs(
    con: duckdb.DuckDBPyConnection, judge: str, *, full: bool = False
) -> list[tuple[str, str]]:
    """Primary and second judgements of the same mentions.

    By default the pair compares linking labels; with full=True it compares
    the complete decision and CIK.
    """
    first, second = (
        (
            "a.decision || ':' || coalesce(a.cik, 0)",
            "b.decision || ':' || coalesce(b.cik, 0)",
        )
        if full
        else (IDENTITY.format(j="a"), IDENTITY.format(j="b"))
    )
    pairs = con.execute(
        f"SELECT {first}, {second} FROM judged AS a "  # noqa: S608 - authored expressions.
        "JOIN judged AS b USING (id, start) "
        "WHERE a.judge = 'primary' AND b.judge = ?",
        [judge],
    ).fetchall()
    return [(str(a), str(b)) for a, b in pairs]


def _agreement(pairs: Sequence[tuple[str, str]]) -> float | None:
    return sum(a == b for a, b in pairs) / len(pairs) if pairs else None


def _cell(value: Row) -> str:
    """An estimate with its interval, then its size, as two table cells."""
    if value["estimate"] is None:
        return "-- & 0"
    interval = f"[{value['ci95_low']:.3f}, {value['ci95_high']:.3f}]"
    return f"{value['estimate']:.3f} {interval} & {value['n']}"


def _summary(metrics: Row) -> str:
    """A booktabs table of headline estimates for each split, for papers."""
    groups = " & ".join(
        rf"\multicolumn{{2}}{{c}}{{{name}}}" for name in SPLITS.values()
    )
    rules = "".join(
        rf"\cmidrule(lr){{{2 * i + 2}-{2 * i + 3}}}" for i in range(len(SPLITS))
    )
    lines = [
        r"\begin{tabular}{l" + "rr" * len(SPLITS) + "}",
        r"\toprule",
        f" & {groups} \\\\",
        rules,
        "Measure" + r" & Estimate [95\% CI] & $n$" * len(SPLITS) + r" \\",
        r"\midrule",
    ]
    for key, label in SUMMARY.items():
        cells = " & ".join(_cell(metrics[split]["estimates"][key]) for split in SPLITS)
        lines.append(f"{label} & {cells} \\\\")
    lines.append(r"\midrule")
    judge = metrics["adjudicator"]
    blank = " & &" * (len(SPLITS) - 1)
    anchors = (
        _cell(
            {
                "estimate": judge["anchor_agreement"],
                "ci95_low": judge["anchor_ci95_low"],
                "ci95_high": judge["anchor_ci95_high"],
                "n": judge["anchors"],
            }
        )
        if judge["anchor_agreement"] is not None
        else "-- & 0"
    )
    lines.append(f"Judge agreement with explicit tickers & {anchors}{blank} \\\\")
    for key, size, label in (
        ("repeat_kappa", "repeated", r"Judge repeat $\kappa$"),
        ("audit_kappa", "audited", r"Judge and audit model $\kappa$"),
    ):
        shown = "--" if judge[key] is None else f"{judge[key]:.3f}"
        lines.append(f"{label} & {shown} & {judge[size]}{blank} \\\\")
    return "\n".join([*lines, r"\bottomrule", r"\end{tabular}"]) + "\n"


# The listed security an issuer traded as on a date: dated listings first, then
# plain common-stock symbols. Links to sibling filers of one security (a parent
# and the subsidiary carrying its ticker) therefore count as the same answer.
SECURITY = """
CREATE MACRO security(issuer, day) AS (
    SELECT first(ticker ORDER BY valid_from IS NULL, valid_from DESC,
                 regexp_matches(ticker, '[-.]'), length(ticker), ticker)
    FROM tickers
    WHERE cik = issuer AND (valid_from IS NULL OR valid_from <= day)
      AND (valid_to IS NULL OR day <= valid_to)
)"""


def _linked(row: Row) -> float:
    return float(row["cik"] is not None)


def _correct(row: Row) -> float:
    return float(row["cik"] is not None and row["match"])


def _listed(row: Row) -> float:
    """US-listed on the date, whether or not the issuer tables contain it."""
    return float(row["decision"] in ("listed", "listed_missing"))


def _unlinked(row: Row) -> float:
    return float(row["cik"] is None)


def _nil(row: Row) -> float:
    return _unlinked(row) * (1 - _listed(row))


def _several(row: Row) -> float:
    return float(str(row["stratum"]).startswith("several"))


def _estimates(mentions: list[Row], articles: list[Row]) -> Row:
    """Headline, per-method, per-year and score-reliability estimates."""

    def within(name: str, value: object) -> Indicator:
        return lambda row: float(row[name] == value)

    reliability = []
    for low in range(10):
        upper = (low + 1) / 10 + (low == 9)

        def scored(row: Row, low: int = low, upper: float = upper) -> float:
            score = row["link_score"]
            return float(score is not None and low / 10 <= score < upper)

        estimate = domain(
            mentions,
            scored,
            lambda r: float(r["link_cik"] is not None and r["match"]),
            lambda r: float(r["link_cik"] is not None),
        )
        reliability.append(
            {"score": f"{low / 10:.1f}", "precision": estimate["estimate"]}
            | {"n": estimate["n"]}
        )
    return {
        "estimates": {
            "link_precision": ratio(mentions, _correct, _linked),
            "recall": ratio(mentions, _correct, _listed),
            "nil_precision": ratio(mentions, _nil, _unlinked),
            "ambiguous_precision": domain(mentions, _several, _correct, _linked),
            "article_precision": ratio(
                articles, lambda r: r["hits"], lambda r: r["links"]
            ),
            "article_recall": ratio(
                articles, lambda r: r["subject_hits"], lambda r: r["subjects"]
            ),
            "article_recall_mentioned": ratio(
                articles, lambda r: r["issuer_hits"], lambda r: r["issuers"]
            ),
        },
        "by_method": {
            method: domain(mentions, within("method", method), _correct, _linked)
            for method in ("anchor", "propagated", "alias")
        },
        "by_year": {
            str(year): {
                "precision": domain(mentions, within("year", year), _correct, _linked),
                "recall": domain(mentions, within("year", year), _correct, _listed),
            }
            for year in sorted({row["year"] for row in mentions})
        },
        "source_or_venue_share": ratio(
            mentions,
            lambda r: _linked(r) * float(r["role"] == "source_or_venue"),
            _linked,
        ),
        "reliability": reliability,
    }


def report_company_links(
    sample: Annotated[Path, typer.Option(help="Sample directory.")] = Path(
        "data/processed/experiments/company-links/sample"
    ),
    labels: Annotated[Path, typer.Option(help="Labels directory.")] = Path(
        "data/processed/experiments/company-links/labels"
    ),
    links: Annotated[Path, typer.Option(help="Linker output.")] = Path(
        "data/processed/company-links"
    ),
    issuers: Annotated[Path, typer.Option(help="Prepared issuer tables.")] = Path(
        "data/processed/issuers"
    ),
    threshold: Annotated[float, typer.Option(help="Operating link score.")] = 0.5,
    output: Annotated[Path, typer.Option(help="Report directory.")] = Path(
        "data/research/experiments/company-links"
    ),
) -> None:
    """Write precision, recall, reliability, error, diagnostic and LaTeX reports."""
    output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        con.read_parquet(str(sample / "mentions.parquet")).create_view("sample")
        con.read_json(str(labels / "mentions.jsonl")).create_view("judged")
        con.read_parquet(str(links / "mentions/*.parquet")).create_view("corpus")
        con.read_parquet(str(links / "articles/*.parquet")).create_view("linked")
        con.read_parquet(str(issuers / "issuers.parquet")).create_view("issuers")
        con.read_parquet(str(issuers / "tickers.parquet")).create_view("tickers")
        con.execute(SECURITY)
        con.execute(
            """CREATE TABLE labelled AS
            SELECT s.id, s.start, s.stratum, s.population, s.split, s.day, s.key,
                   l.cik AS link_cik, l.link_score, l.method,
                   CASE WHEN l.link_score >= $threshold THEN l.cik END AS cik,
                   j.decision, j.cik AS label_cik, j.role, j.rationale,
                   coalesce(l.cik = j.cik
                            OR security(l.cik, s.day) = security(j.cik, s.day),
                            false) AS match,
                   year(s.day) AS year,
                   s.population::DOUBLE
                       / count(*) OVER (PARTITION BY s.split, s.stratum) AS weight
            FROM sample AS s
            JOIN judged AS j USING (id, start)
            LEFT JOIN corpus AS l USING (id, start)
            WHERE j.judge = 'primary' AND j.decision <> 'unsure'""",
            {"threshold": threshold},
        )
        con.execute(
            "CREATE TABLE links AS SELECT id, cik FROM linked WHERE link_score >= ?",
            [threshold],
        )
        con.read_json(str(labels / "articles.jsonl")).filter(
            "judge = 'primary'"
        ).create_view("articles_judged")
        con.read_parquet(str(sample / "articles.parquet")).create_view("drawn")
        articles = _rows(
            con,
            """WITH gold AS (
                SELECT * FROM (
                    SELECT a.id, d.day, unnest(a.issuers, recursive := true)
                    FROM articles_judged AS a JOIN drawn AS d USING (id)
                ) WHERE cik IS NOT NULL
            ), hits AS (
                SELECT g.id, g.cik, g.role FROM gold AS g JOIN links AS l
                  ON g.id = l.id AND (g.cik = l.cik
                      OR security(g.cik, g.day) = security(l.cik, g.day))
                GROUP BY ALL
            )
            SELECT d.id, d.split, 'all' AS stratum,
                (SELECT count(DISTINCT id) FROM corpus) AS population,
                (SELECT count(*) FROM links AS l WHERE l.id = d.id) AS links,
                (SELECT count(*) FROM hits AS h WHERE h.id = d.id) AS hits,
                (SELECT count(*) FROM gold AS g WHERE g.id = d.id
                   AND g.role = 'subject') AS subjects,
                (SELECT count(*) FROM hits AS h WHERE h.id = d.id
                   AND h.role = 'subject') AS subject_hits,
                (SELECT count(*) FROM gold AS g WHERE g.id = d.id
                   AND g.role <> 'source_or_venue') AS issuers,
                (SELECT count(*) FROM hits AS h WHERE h.id = d.id
                   AND h.role <> 'source_or_venue') AS issuer_hits
            FROM drawn AS d""",
        )
        mentions = _rows(con, "SELECT * FROM labelled")
        anchors = [row for row in mentions if row["method"] == "anchor"]
        repeats, audits = _pairs(con, "repeat"), _pairs(con, "audit")
        metrics: Row = {"threshold": threshold} | {
            split: _estimates(
                [row for row in mentions if split in ("pooled", row["split"])],
                [row for row in articles if split in ("pooled", row["split"])],
            )
            for split in SPLITS
        }
        agreed = int(sum(map(_correct, anchors)))
        low, high = (
            proportion_confint(agreed, len(anchors), method="beta")
            if anchors
            else (None, None)
        )
        counts = con.sql(
            "SELECT count(*) FILTER (WHERE j.decision = 'unsure'), "
            "count(*) FILTER (WHERE j.id IS NULL) FROM sample AS s "
            "LEFT JOIN (SELECT * FROM judged WHERE judge = 'primary') AS j "
            "USING (id, start)"
        ).fetchall()[0]
        unverified = con.sql(
            "SELECT avg((cik IS NULL)::INT) FROM (SELECT unnest(issuers, "
            "recursive := true) FROM articles_judged) WHERE role <> 'source_or_venue'"
        ).fetchall()[0][0]
        metrics["adjudicator"] = {
            "labelled": len(mentions),
            "article_issuers_without_cik": unverified,
            "unsure": counts[0],
            "missing": counts[1],
            "anchor_agreement": agreed / len(anchors) if anchors else None,
            "anchors": len(anchors),
            "anchor_ci95_low": low,
            "anchor_ci95_high": high,
            "repeat_agreement": _agreement(repeats),
            "repeat_kappa": kappa(repeats),
            "audit_agreement": _agreement(audits),
            "audit_kappa": kappa(audits),
            "repeat_kappa_full_decision": kappa(_pairs(con, "repeat", full=True)),
            "audit_kappa_full_decision": kappa(_pairs(con, "audit", full=True)),
            "audited": len(audits),
            "repeated": len(repeats),
        }
        values = {
            name: metrics["test"]["estimates"][name]["estimate"]
            for name in ("link_precision", "ambiguous_precision", "article_recall")
        } | {
            name: metrics["adjudicator"][name]
            for name in ("anchor_agreement", "audit_kappa")
        }
        metrics["gates"] = {
            name: {"target": target, "value": values[name]}
            | {"passed": values[name] is not None and values[name] >= target}
            for name, target in GATES.items()
        }
        con.sql(
            """WITH errors AS (
                SELECT key,
                       CASE WHEN cik IS NOT NULL AND NOT match
                            THEN 'false_positive' ELSE 'false_negative' END AS kind,
                       weight, cik, label_cik, rationale
                FROM labelled
                WHERE split = 'dev' AND (
                    (cik IS NOT NULL AND NOT match)
                    OR (decision IN ('listed', 'listed_missing')
                        AND (cik IS NULL OR NOT match)))
            )
            SELECT kind, key, round(sum(weight)) AS weighted_mentions,
                   count(*) AS sampled, any_value(cik) AS linked_cik,
                   any_value(label_cik) AS label_cik, any_value(rationale) AS rationale
            FROM errors GROUP BY kind, key
            QUALIFY row_number() OVER (PARTITION BY kind
                                       ORDER BY sum(weight) DESC, key) <= 25
            ORDER BY kind, weighted_mentions DESC, key"""
        ).write_csv(str(output / "errors.csv"))
        diagnostics = {}
        for key in DIAGNOSTIC_KEYS:
            diagnostics[key] = {
                "corpus": _rows(
                    con,
                    f"""SELECT method, c.cik, any_value(i.name) AS name,
                           count(*) AS mentions, round(avg(link_score), 3) AS score
                    FROM corpus AS c LEFT JOIN issuers AS i USING (cik)
                    WHERE key = '{key}' GROUP BY ALL ORDER BY mentions DESC LIMIT 5""",  # noqa: S608 - authored keys.
                ),
                "labelled": _rows(
                    con,
                    f"""SELECT count(*) AS n,
                           round(avg(CASE WHEN cik IS NULL THEN label_cik IS NULL
                                          ELSE match END::INT), 3)
                               AS agreement
                    FROM labelled WHERE split = 'dev' AND key = '{key}'""",  # noqa: S608 - authored keys.
                )[0],
            }
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (output / "summary.tex").write_text(_summary(metrics))
    (output / "diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2, default=str) + "\n"
    )
    typer.echo(f"Wrote: {output}")
