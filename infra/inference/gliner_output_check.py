"""Validate saved extraction structure and finite confidence scores."""

import argparse
import gzip
import json
import math
from collections import Counter
from pathlib import Path


def main() -> None:
    """Check saved outputs without treating structural validity as accuracy."""
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    counts: Counter[str] = Counter()
    seen: set[str] = set()
    with gzip.open(args.predictions, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            article_id = row["article_id"]
            if article_id in seen:
                raise ValueError(f"Duplicate article: {article_id}")
            seen.add(article_id)
            prediction = row["prediction"]
            article_type = prediction.get("article_type", {})
            entities = prediction.get("entities", {}).get("company", [])
            values = [
                article_type,
                *entities,
                *[entity.get("article_role", {}) for entity in entities],
            ]
            invalid = not all(
                isinstance(value.get("confidence"), (int, float))
                and math.isfinite(value["confidence"])
                and 0 <= value["confidence"] <= 1
                for value in values
            )
            invalid_labels = article_type.get("label") not in {
                "reporting",
                "opinion",
                "press release",
                "promotional",
                "other",
            } or any(
                entity.get("article_role", {}).get("label")
                not in {"primary", "secondary", "incidental", "uncertain"}
                for entity in entities
            )
            counts["articles"] += 1
            counts["invalid_confidence_articles"] += invalid
            counts["invalid_label_articles"] += invalid_labels
            counts["invalid_span_articles"] += row.get("status", "ok") != "ok"
            counts["articles_with_company_spans"] += bool(entities)
            counts["company_spans"] += len(entities)
    report = {
        "counts": dict(counts),
        "interpretation": "Structural checks only; no semantic accuracy claim.",
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
