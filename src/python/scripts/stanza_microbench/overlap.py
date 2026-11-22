"""Sensitivity of company extraction to boundaries on the frozen paired leads."""

import random
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment
from score import read_rows, spans


def main() -> None:
    """Score overlapping spans under one-to-one matching and paired resampling."""
    root = Path("data/inputs/stanza-microbench")
    manifest = read_rows(root / "manifest.jsonl")
    gold = read_rows(root / "gold.jsonl")
    strata = defaultdict(list)
    systems = [
        (read_rows(root / f"{name}-predictions.jsonl"), label)
        for name, label in (("stanza", "ORG"), ("gliner", "company"))
    ]
    for key, article in manifest.items():
        reference = sorted(spans(gold[key], article["end"]))
        counts = []
        for predictions, label in systems:
            candidates = spans(predictions[key], article["end"], label)
            overlap = np.array(
                [[a < d and c < b for c, d in reference] for a, b in candidates],
                dtype=int,
            )
            hits = 0
            if overlap.size:
                matches = linear_sum_assignment(overlap, maximize=True)
                hits = int(overlap[matches].sum())
            counts.append([2 * hits, len(reference) + len(candidates)])
        strata[article["year"]].append(counts)

    def scores(rows: list) -> np.ndarray:
        totals = np.sum(rows, axis=0)
        return 100 * totals[:, 0] / totals[:, 1]

    rng = random.Random(43)  # noqa: S311 - reproducible survey bootstrap.
    result = scores([row for group in strata.values() for row in group])
    differences = []
    for _ in range(2000):
        sample = [
            row for group in strata.values() for row in rng.choices(group, k=len(group))
        ]
        stanza, gliner = scores(sample)
        differences.append(gliner - stanza)
    print(result, np.percentile(differences, [2.5, 97.5]))


if __name__ == "__main__":
    main()
