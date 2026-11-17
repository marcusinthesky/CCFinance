"""Compare GLiNER pilot suggestions with previously saved Kev decisions."""

import argparse
import gzip
import json
import unicodedata
from collections import Counter
from pathlib import Path

import duckdb


def normalize(value: str) -> str:
    """Normalize case and compatibility characters for exact alias comparison."""
    return unicodedata.normalize("NFKC", value).casefold().strip()


def main() -> None:
    """Count descriptive agreement, keeping unresolved Kev records separate."""
    parser = argparse.ArgumentParser()
    parser.add_argument("sample", type=Path)
    parser.add_argument("gliner", type=Path)
    parser.add_argument("kev", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.sample.open(encoding="utf-8") as stream:
        articles = {
            row["article_id"]: row for line in stream if (row := json.loads(line))
        }
    with gzip.open(args.gliner, "rt", encoding="utf-8") as stream:
        predictions = {
            row["article_id"]: row for line in stream if (row := json.loads(line))
        }
    kev = duckdb.sql(
        "SELECT article_id, count(*) AS candidates, "
        "count(*) FILTER (WHERE identity_score IS NULL) AS unresolved, "
        "count(*) FILTER (WHERE identity_score >= 0.5) AS mentioned, "
        "count(*) FILTER (WHERE primary_score >= 0.5) AS primary_count "
        "FROM read_parquet(?) GROUP BY article_id",
        params=[str(args.kev)],
    ).fetchall()
    counts: Counter[str] = Counter()
    for article_id, _, unresolved, mentioned, primary_count in kev:
        if article_id not in articles or article_id not in predictions:
            counts["missing_gliner"] += 1
            continue
        prediction = predictions[article_id]
        if prediction.get("status", "ok") != "ok":
            counts["invalid_gliner_spans"] += 1
            continue
        if unresolved:
            counts["unresolved_kev"] += 1
            continue
        article = articles[article_id]
        entities = prediction["prediction"].get("entities", {}).get("company", [])
        extracted = {normalize(entity["text"]) for entity in entities}
        aliases = {
            normalize(alias)
            for candidate in article["candidates"]
            for alias in candidate.get("supported_aliases", [])
            if alias
        }
        kev_yes = mentioned > 0
        exact_alias = bool(extracted & aliases)
        exact_primary = any(
            normalize(entity["text"]) in aliases
            and entity.get("article_role", {}).get("label") == "primary"
            for entity in entities
        )
        counts["eligible_articles"] += 1
        counts["gliner_any_company_span"] += bool(extracted)
        kev_label = "yes" if kev_yes else "no"
        alias_label = "yes" if exact_alias else "no"
        primary_label = "yes" if primary_count else "no"
        span_primary_label = "yes" if exact_primary else "no"
        counts[f"kev_{kev_label}_exact_alias_{alias_label}"] += 1
        counts[f"kev_primary_{primary_label}_exact_primary_{span_primary_label}"] += 1
    report = {
        "counts": dict(counts),
        "kev_threshold": 0.5,
        "alias_match": (
            "NFKC casefold exact match to a retrieved candidate's supported alias"
        ),
        "interpretation": (
            "Descriptive agreement only: Kev is not ground truth; exact alias matches "
            "can be ambiguous and miss valid variants, while GLiNER extracts companies "
            "outside the candidate universe. Per-span role labels and whole-article "
            "decisions differ. No issuer identity has been established."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
