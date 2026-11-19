"""Estimate design-weighted confusion matrices against blinded metadata judges."""

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Annotated, Any

import duckdb
import numpy as np
import typer


def _estimates(rows: list[tuple[str, str, str, float, str]]) -> dict[str, Any]:
    """Poststratified article-cluster multiplier intervals for classwise ratios."""
    rng = np.random.default_rng(46)
    ids = {key: i for i, key in enumerate(sorted({r[0] for r in rows}))}
    cluster = [ids[r[0]] for r in rows]
    weights = np.array([r[3] for r in rows])
    replicas = rng.exponential(size=(1000, len(ids)))[:, cluster] * weights
    for stratum in sorted({r[4] for r in rows}):
        ix = np.array([r[4] == stratum for r in rows])
        replicas[:, ix] *= weights[ix].sum() / replicas[:, ix].sum(axis=1)[:, None]
    weights = np.vstack((weights, replicas))
    result = {}
    for label in sorted({v for r in rows for v in r[1:3]}):
        pred = np.array([r[1] == label for r in rows])
        ref = np.array([r[2] == label for r in rows])
        hits = weights[:, pred & ref].sum(axis=1)
        metrics = {}
        for name, mask in (("precision", pred), ("recall", ref)):
            if mask.any():
                ratios = hits / weights[:, mask].sum(axis=1)
                metrics[name] = [
                    float(ratios[0]),
                    *np.quantile(ratios[1:], [0.025, 0.975]).tolist(),
                ]
            else:
                metrics[name] = None
        result[label] = {"judge_count": int(ref.sum()), **metrics}
    return result


def _press_shares(
    rows: list[tuple[str, int, int, int, bool, bool]],
) -> dict[str, object]:
    """Design-weighted paired prevalence and linearized stratified intervals."""
    result = {}
    w = np.array([n / k for _, n, k, _, _, _ in rows])
    factor = np.array([f for _, _, _, f, _, _ in rows])
    pred = np.array([int(p) for _, _, _, _, p, _ in rows])
    ref = np.array([int(r) for _, _, _, _, _, r in rows])
    denominator = (w * factor).sum()
    for key, response in (
        ("predicted", pred),
        ("judged", ref),
        ("paired_difference_judged_minus_predicted", ref - pred),
    ):
        estimate = (w * factor * response).sum() / denominator
        residual = factor * (response - estimate)
        variance = 0.0
        for grp, n, k in sorted({r[:3] for r in rows}):
            if k > 1 and k < n:
                values = residual[[r[0] == grp for r in rows]]
                variance += n * n * (1 - k / n) * values.var(ddof=1) / k
        half = 1.96 * np.sqrt(variance) / denominator
        result[key] = {
            "estimate": estimate,
            "ci95_low": max(-1.0 if key.startswith("paired") else 0.0, estimate - half),
            "ci95_high": min(1.0, estimate + half),
        }
    return result


def report_metadata_validation(
    sample: Annotated[Path, typer.Option()],
    extraction: Annotated[Path, typer.Option()],
    links: Annotated[Path, typer.Option()],
    panel: Annotated[Path, typer.Option()],
    focus: Annotated[Path, typer.Option()],
    quality: Annotated[Path, typer.Option()],
    threshold: Annotated[float, typer.Option()],
    labels: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
) -> None:
    """Compare primary labels with the stored production decisions."""
    names = json.loads((extraction / "schema.json").read_text())["labels"]
    with duckdb.connect() as con:
        con.execute("SET threads=4")
        con.read_parquet(str(sample)).create("units")
        con.read_parquet(str(extraction / "mentions/*.parquet")).create_view("mentions")
        con.read_parquet(str(extraction / "articles/*.parquet")).create_view("articles")
        query = """
        SELECT id,start,stop,local_relevance,financial_sentiment FROM mentions
        JOIN units USING(id,start,stop) WHERE frame='mention' AND entity_type='company'
        """
        mentions = {(i, a, b): (r, s) for i, a, b, r, s in con.sql(query).fetchall()}
        company_counts = dict(
            con.sql(
                """SELECT id,count(DISTINCT text) FROM mentions JOIN
                (SELECT DISTINCT id FROM units WHERE frame='mention') USING(id)
                WHERE entity_type='company' GROUP BY id"""
            ).fetchall()
        )
        events = {
            (i, a, b): e
            for i, a, b, e in con.sql("""
                SELECT id,w.start,w.stop,w.event_family FROM articles JOIN units
                USING(id),unnest(windows) t(w) WHERE frame='window' AND
                w.start=units.start AND w.stop=units.stop""").fetchall()
        }
        con.read_parquet(str(quality)).create_view("quality")
        con.read_parquet(str(links / "articles/*.parquet")).create_view("links")
        con.read_parquet(str(panel / "pp_roster.parquet")).create_view("roster")
        multiplicities = dict(
            con.execute(
                """
            SELECT id,count(*) FROM links JOIN units USING(id)
            WHERE frame='article' AND link_score>=? GROUP BY id""",
                [threshold],
            ).fetchall()
        )
        curve = con.read_csv(str(focus / "curve.csv"), header=True)
        curve.create_view("curve")
        best = con.sql("""SELECT value FROM curve WHERE split='dev'
            AND rule='min_relevance' ORDER BY f1 DESC,value LIMIT 1""").fetchone()[0]
        operating = json.loads((focus / "metrics.json").read_text())["configured"]
        cohort = con.execute(
            """
            WITH annual AS (SELECT cik, year(day) AS y,
              count(*) FILTER(WHERE n_mentions>=3) AS count_only,
              count(*) FILTER(WHERE relevance_substantive>=?) AS relevance_only,
              count(*) FILTER(WHERE relevance_substantive>=? AND first_offset_share<=?
                                AND n_mentions>=?) AS combined
            FROM links JOIN quality USING(id) WHERE usable AND link_score>=?
            AND year(day) BETWEEN 2018 AND 2022
            AND cik IN (SELECT cik FROM roster) GROUP BY ALL),
            passing AS (SELECT cik,min(count_only) AS c,min(relevance_only) AS r,
                        min(combined) AS b FROM annual GROUP BY cik HAVING count(*)=5)
            SELECT count(*) FILTER(WHERE c>=47), count(*) FILTER(WHERE r>=47),
                   count(*) FILTER(WHERE b>=47) FROM passing""",
            [
                best,
                operating["min_relevance"],
                operating["max_offset"],
                operating["min_mentions"],
                threshold,
            ],
        ).fetchone()
        focus_rules = {}
        for idx, (name, rule, value) in enumerate(
            [
                ("count_only", "min_mentions", 3),
                ("relevance_only", "min_relevance", best),
            ]
        ):
            scores = con.execute(
                "SELECT precision,recall FROM curve WHERE split='test' "
                "AND rule=? AND value=?",
                [rule, value],
            ).fetchone()
            focus_rules[name] = {
                "cutoff": value,
                "precision": scores[0],
                "recall": scores[1],
                "roster_passing": cohort[idx],
            }
        held = json.loads((focus / "metrics.json").read_text())["test"]
        focus_rules["configured"] = {
            "rule": operating,
            "precision": held["precision"],
            "recall": held["recall"],
            "roster_passing": cohort[2],
        }
        inventory = dict(
            con.sql("""SELECT coalesce(extraction_status,'missing'), count(*)
                                   FROM quality WHERE usable GROUP BY 1""").fetchall()
        )
        units = con.table("units").fetchall()
        provenance = con.sql("""SELECT u.*,a.text_sha256,
                            u.draws/u.population AS probability
                            FROM units u JOIN articles a USING(id)
                            ORDER BY frame,id,start,stop""").fetchall()
        columns = (
            "frame",
            "id",
            "start",
            "stop",
            "stratum",
            "population",
            "draws",
            "audit",
            "text_sha256",
            "probability",
        )
    judged = {}
    for path in (labels / "primary").glob("*.json"):
        record = json.loads(path.read_text())
        key = (record["frame"], record["id"], record["start"], record["stop"])
        if key in judged or record["role"] != "primary":
            raise ValueError(f"Unexpected duplicate or role in {path}")
        judged[key] = record["label"]
    secondary = {}
    for role in ("repeat", "audit"):
        records = [json.loads(p.read_text()) for p in (labels / role).glob("*.json")]
        secondary[role] = {
            (r["frame"], r["id"], r["start"], r["stop"]): r["label"] for r in records
        }
    comparison_rows: dict[str, list[tuple[str, str, str, float, str]]] = defaultdict(
        list
    )
    reliability: dict[str, list[tuple[str, str, str, float, str]]] = defaultdict(list)
    matrices: dict[str, dict[str, dict[str, float]]] = {}
    counts: dict[str, int] = defaultdict(int)
    errors = defaultdict(list)
    event_empty = []
    empty_set_hits = []
    press = defaultdict(list)
    unclear_form_weight: dict[str, float] = defaultdict(float)
    curves = defaultdict(list)
    for frame, identifier, start, stop, stratum, population, draws, audit in units:
        label = judged[frame, identifier, start, stop]
        comparisons = []
        if frame == "article":
            for base, factor in (
                ("distinct_articles", 1),
                ("article_issuer_links", multiplicities.get(identifier, 0)),
            ):
                if label["label"] == "insufficient context":
                    unclear_form_weight[base] += population / draws * factor
                press[base].append(
                    (
                        stratum,
                        population,
                        draws,
                        factor,
                        stratum == "press release",
                        label["label"] == "press release",
                    )
                )
            comparisons.append(("article_form", stratum, label["label"]))
        elif frame == "mention":
            for task, reference, vector in zip(
                ("local_relevance", "financial_sentiment"),
                ("relevance", "sentiment"),
                mentions[identifier, start, stop],
                strict=True,
            ):
                pred = names[task][vector.index(max(vector))] if vector else "missing"
                comparisons.append((task, pred, label[reference]))
                if vector:
                    curves[task].append(
                        (max(vector), pred == label[reference], population / draws)
                    )
        else:
            empty_set_hits.append((len(label["families"]) == 0, population / draws))
            if stratum == "empty":
                event_empty.append((len(label["families"]) > 0, population / draws))
            for family, score in zip(
                names["event_family"], events[identifier, start, stop], strict=True
            ):
                curves[family].append(
                    (score, family in label["families"], population / draws)
                )
                comparisons.append(
                    (family, str(score >= 0.5), str(family in label["families"]))
                )
        for task, pred, reference_label in comparisons:
            comparison_rows[task].append(
                (identifier, pred, reference_label, population / draws, stratum)
            )
            if pred != reference_label and len(errors[task]) < 5:
                errors[task].append(
                    {
                        "id": identifier,
                        "start": start,
                        "stop": stop,
                        "predicted": pred,
                        "judge": reference_label,
                    }
                )
            if task == "financial_sentiment" and company_counts[identifier] > 1:
                comparison_rows["multi_company_surface_forms/sentiment"].append(
                    (identifier, pred, reference_label, population / draws, stratum)
                )
            if audit:
                for role, records in secondary.items():
                    other = records[frame, identifier, start, stop]
                    field = {
                        "article_form": "label",
                        "financial_sentiment": "sentiment",
                        "local_relevance": "relevance",
                    }.get(task)
                    alt = other[field] if field else str(task in other["families"])
                    reliability[f"{role}/{task}"].append(
                        (identifier, alt, reference_label, population / draws, stratum)
                    )
                    comparison_rows[f"{role}/{task}"].append(
                        (identifier, pred, alt, population / draws, stratum)
                    )
            if pred != reference_label and len(errors[task]) < 5:
                errors[task].append(
                    {
                        "id": identifier,
                        "start": start,
                        "stop": stop,
                        "predicted": pred,
                        "judge": reference_label,
                    }
                )
            if task == "financial_sentiment" and company_counts[identifier] > 1:
                comparison_rows["multi_company_surface_forms/sentiment"].append(
                    (identifier, pred, reference_label, population / draws, stratum)
                )
            if audit:
                comparison_rows.setdefault(f"primary_subset/{task}", []).append(
                    (identifier, pred, reference_label, population / draws, stratum)
                )
            cell = matrices.setdefault(task, {}).setdefault(pred, {})
            cell[reference_label] = cell.get(reference_label, 0.0) + population / draws
            counts[task] += 1
    sentiment_rows = comparison_rows["financial_sentiment"]
    reversals = sum(
        w
        for _, pred, ref, w, _ in sentiment_rows
        if (pred, ref) in (("positive", "negative"), ("negative", "positive"))
    ) / sum(row[3] for row in sentiment_rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.with_suffix(".csv").open("w", newline="") as manifest:
        writer = csv.writer(manifest)
        writer.writerow(columns)
        writer.writerows(provenance)
    output.write_text(
        json.dumps(
            {
                "extraction_status": inventory,
                "focus_rules": focus_rules,
                "insufficient_context_share": {
                    base: unclear_form_weight[base]
                    / sum(n / k * f for _, n, k, f, _, _ in rows)
                    for base, rows in press.items()
                },
                "press_release_shares": {k: _press_shares(v) for k, v in press.items()},
                "score_curves": {
                    k: [
                        {
                            "minimum": t,
                            "coverage": sum(w for s, c, w in v if s >= t)
                            / sum(w for s, c, w in v),
                            "precision": sum(w * c for s, c, w in v if s >= t)
                            / sum(w for s, c, w in v if s >= t)
                            if any(s >= t for s, c, w in v)
                            else None,
                        }
                        for t in (0, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
                    ]
                    for k, v in curves.items()
                },
                "example_disagreements": errors,
                "empty_set_baseline_exact_match": sum(v * w for v, w in empty_set_hits)
                / sum(w for _, w in empty_set_hits),
                "empty_window_judged_positive_share": sum(v * w for v, w in event_empty)
                / sum(w for _, w in event_empty),
                "baselines": {
                    task: max(
                        sum(w for _, _, r, w, _ in rows if r == label)
                        for label in {r for _, _, r, _, _ in rows}
                    )
                    / sum(w for _, _, _, w, _ in rows)
                    for task, rows in comparison_rows.items()
                    if "/" not in task
                },
                "weighted_counts": matrices,
                "sentiment_opposite_polarity_share": reversals,
                "n": counts,
                "metrics": {k: _estimates(v) for k, v in comparison_rows.items()},
                "judge_pair_counts": {
                    task: {
                        a: {
                            b: sum(1 for _, x, y, _, _ in rows if x == a and y == b)
                            for b in sorted({r[2] for r in rows})
                        }
                        for a in sorted({r[1] for r in rows})
                    }
                    for task, rows in reliability.items()
                },
                "judge_raw_agreement": {
                    task: sum(x == y for _, x, y, _, _ in rows) / len(rows)
                    for task, rows in reliability.items()
                },
                "judge_agreement": {
                    k: sum(r[3] for r in v if r[1] == r[2]) / sum(r[3] for r in v)
                    for k, v in reliability.items()
                },
            },
            indent=2,
        )
        + "\n"
    )
    metrics = json.loads(output.read_text())
    lines = [
        r"\begin{tabular}{llrrr}\toprule",
        r"Task & Class & Judge count & Precision [95\% CI] & Recall [95\% CI] \\",
        r"\midrule",
    ]
    for task in counts:
        for category, estimates in metrics["metrics"][task].items():
            if task in names["event_family"] and category == "False":
                continue
            cells = [task.replace("_", " "), category, str(estimates["judge_count"])]
            for key in ("precision", "recall"):
                interval = estimates[key]
                cells.append(
                    "--"
                    if interval is None
                    else f"{interval[0]:.2f} [{interval[1]:.2f}, {interval[2]:.2f}]"
                )
            lines.append(" & ".join(cells) + r" \\")
    lines.append(r"\bottomrule\end{tabular}")
    output.with_suffix(".tex").write_text("\n".join(lines) + "\n")
