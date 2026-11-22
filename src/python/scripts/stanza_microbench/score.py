"""Score frozen company spans and resample paired observations within year."""

import argparse
import hashlib
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

Count = tuple[int, int, int]
Span = tuple[int, int]


def read_rows(path: Path) -> dict[str, dict]:
    """Read result rows and reject duplicate IDs."""
    rows = {}
    for line in path.read_text(encoding="utf-8").split("\n"):
        if not line:
            continue
        row = json.loads(line)
        article_id = row["id"]
        if article_id in rows:
            raise ValueError(f"Duplicate ID in {path}: {article_id}")
        rows[article_id] = row
    return rows


def spans(row: dict, passage_end: int, entity_type: str | None = None) -> set[Span]:
    """Validate and return unique span offsets for the requested class."""
    offsets = set()
    for span in row["spans"]:
        start, end = span["start"], span["end"]
        if not 0 <= start < end <= passage_end or len(span["text"]) != end - start:
            raise ValueError(f"Invalid span for {row['id']}: {span}")
        if entity_type is None or span["type"] == entity_type:
            offsets.add((start, end))
    return offsets


def verify_text(rows: list[dict], text: str) -> None:
    """Check the original Unicode slices when the frozen passages are available."""
    for row in rows:
        for span in row["spans"]:
            if text[span["start"] : span["end"]] != span["text"]:
                raise ValueError(f"Span text does not match {row['id']}: {span}")


def counts(gold: set[Span], candidate: set[Span]) -> Count:
    """Count unique exact matches, extra spans and missed spans."""
    return len(gold & candidate), len(candidate - gold), len(gold - candidate)


def pool(rows: list[Count]) -> Count:
    """Pool counts across the supplied passages or bootstrap draws."""
    return tuple(map(sum, zip(*rows, strict=True)))


def metrics(count: Count) -> dict:
    """Calculate micro rates, keeping zero denominators undefined."""
    tp, fp, fn = count
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if tp or fp or fn else None,
    }


def main() -> None:
    """Write paired company-span results and independent exact-span agreement."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path("data/inputs/stanza-microbench")
    )
    parser.add_argument("--passages", type=Path)
    args = parser.parse_args()
    root = args.input
    manifest = read_rows(root / "manifest.jsonl")
    gold = read_rows(root / "gold.jsonl")
    primary = read_rows(root / "primary-labels.jsonl")
    repeat = read_rows(root / "repeat-labels.jsonl")
    passages = read_rows(args.passages) if args.passages else None
    systems = {
        label: read_rows(root / f"{label}-predictions.jsonl")
        for label in ("stanza", "gliner")
    }
    if any(set(rows) != set(manifest) for rows in (gold, primary, *systems.values())):
        raise ValueError("Gold, primary and predictions must cover the manifest")
    if passages is not None and set(passages) != set(manifest):
        raise ValueError("Passages must cover the manifest")
    ranks = {year: set() for year in range(2019, 2024)}
    for row in manifest.values():
        ranks[row["year"]].add(row["year_rank"])
    if len(manifest) != 40 or any(
        values != set(range(1, 9)) for values in ranks.values()
    ):
        raise ValueError("Expected eight distinct ranks in each of the five years")
    if set(repeat) != {key for key, row in manifest.items() if row["year_rank"] <= 2}:
        raise ValueError("Repeat IDs must be the first two ranks in each year")

    strata = defaultdict(list)
    exact_agreement = 0
    agreement_counts = []
    ordered_ids = sorted(
        manifest, key=lambda key: (manifest[key]["year"], manifest[key]["year_rank"])
    )
    for key in ordered_ids:
        article = manifest[key]
        end = article["end"]
        expected = spans(gold[key], end)
        st, gl = (systems[label][key] for label in ("stanza", "gliner"))
        if any(row["text_sha256"] != article["text_sha256"] for row in (st, gl)):
            raise ValueError(f"Extractors saw different text for {key}")
        if passages is not None:
            text = passages[key]["text"]
            if (
                len(text) != end
                or hashlib.sha256(text.encode()).hexdigest() != (article["text_sha256"])
            ):
                raise ValueError(f"Passage does not match the frozen digest for {key}")
            verify_text([gold[key], primary[key], st, gl], text)
            if key in repeat:
                verify_text([repeat[key]], text)
        strata[article["year"]].append(
            (
                counts(expected, spans(st, end, "ORG")),
                counts(expected, spans(gl, end, "company")),
            )
        )
        if key in repeat:
            a, b = spans(primary[key], end), spans(repeat[key], end)
            agreement_counts.append(counts(a, b))
            exact_agreement += a == b
    paired = [pair for year in sorted(strata) for pair in strata[year]]
    stanza_counts = [pair[0] for pair in paired]
    gliner_counts = [pair[1] for pair in paired]
    stanza = metrics(pool(stanza_counts))
    gliner = metrics(pool(gliner_counts))
    bootstrap_seed, draws = 42, 2_000
    rng = random.Random(bootstrap_seed)  # noqa: S311 - reproducible bootstrap.
    differences = []
    for _ in range(draws):
        sampled = [
            pair
            for year in sorted(strata)
            for pair in rng.choices(strata[year], k=len(strata[year]))
        ]
        stanza_f1 = metrics(pool([pair[0] for pair in sampled]))["f1"]
        gliner_f1 = metrics(pool([pair[1] for pair in sampled]))["f1"]
        if stanza_f1 is not None and gliner_f1 is not None:
            differences.append(gliner_f1 - stanza_f1)
    if differences:
        percentiles = statistics.quantiles(differences, n=40, method="inclusive")
        interval = [percentiles[0], percentiles[-1]]
    else:
        interval = None
    overlap, repeat_only, primary_only = pool(agreement_counts)
    agreement = {
        "passages": len(repeat),
        "passages_with_identical_span_sets": exact_agreement,
        "primary_spans": overlap + primary_only,
        "repeat_spans": overlap + repeat_only,
        "overlapping_spans": overlap,
        "span_f1": metrics((overlap, repeat_only, primary_only))["f1"],
    }
    result = {
        "passages": len(gold),
        "gold_spans": stanza["tp"] + stanza["fn"],
        "zero_mention_passages": sum(not row["spans"] for row in gold.values()),
        "repeat_agreement": agreement,
        "models": {"stanza": stanza, "gliner": gliner},
        "gliner_minus_stanza_f1": {
            "observed": gliner["f1"] - stanza["f1"]
            if gliner["f1"] is not None and stanza["f1"] is not None
            else None,
            "percentile_95": interval,
            "seed": bootstrap_seed,
            "draws": draws,
            "undefined_draws": draws - len(differences),
        },
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
