"""Summarize paired GLiNER benchmark outputs without treating them as truth."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path


def read_predictions(path: Path) -> dict[str, dict]:
    """Load one prediction per article, rejecting duplicate identifiers."""
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    result = {row["article_id"]: row for row in rows}
    if len(rows) != len(result):
        raise ValueError(f"Duplicate article IDs in {path}")
    return result


def spans(row: dict) -> dict[tuple[int, int], dict]:
    """Index company predictions by source offsets."""
    entities = row["prediction"].get("entities", {}).get("company", [])
    return {(entity["start"], entity["end"]): entity for entity in entities}


def main() -> None:
    """Compare a run with a reference configuration on shared valid records."""
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reference = read_predictions(args.reference)
    candidate = read_predictions(args.candidate)
    shared = sorted(reference.keys() & candidate.keys())
    counts: Counter[str] = Counter()
    maximum_role_confidence_difference = 0.0
    for key in shared:
        left, right = reference[key], candidate[key]
        if left.get("status", "ok") != "ok" or right.get("status", "ok") != "ok":
            counts["invalid_articles_excluded"] += 1
            continue
        counts["valid_paired_articles"] += 1
        ref_spans, test_spans = spans(left), spans(right)
        counts["reference_spans"] += len(ref_spans)
        counts["candidate_spans"] += len(test_spans)
        common = ref_spans.keys() & test_spans.keys()
        counts["matching_spans"] += len(common)
        for span in common:
            ref_role = ref_spans[span].get("article_role", {})
            test_role = test_spans[span].get("article_role", {})
            counts["matching_span_roles"] += ref_role.get("label") == test_role.get(
                "label"
            )
            maximum_role_confidence_difference = max(
                maximum_role_confidence_difference,
                abs(ref_role.get("confidence", 0) - test_role.get("confidence", 0)),
            )
        counts["same_span_set_articles"] += ref_spans.keys() == test_spans.keys()
        counts["same_article_type"] += left["prediction"].get("article_type", {}).get(
            "label"
        ) == right["prediction"].get("article_type", {}).get("label")
    report = {
        "reference": str(args.reference),
        "candidate": str(args.candidate),
        "shared_articles": len(shared),
        "counts": dict(counts),
        "maximum_top_role_confidence_difference": maximum_role_confidence_difference,
        "interpretation": "Paired agreement only; neither model is ground truth.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
