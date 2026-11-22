"""Compare bank networks across earnings weeks on common publisher support."""

import csv
from collections import defaultdict
from pathlib import Path
from typing import Annotated

import duckdb
import numpy as np
import typer

_DRAWS = 1_000
_SEED = 42


def _representatives(
    rows: list[tuple[str, str, str | None, str | None, str | None, list[str]]],
) -> list[tuple[str, list[str]]]:
    """Keep the earliest version in each connected story component of a week."""
    parents = list(range(len(rows)))

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    story_keys: dict[tuple[int, str], int] = {}
    for index, (_, _, headline, cluster, text_hash, _) in enumerate(rows):
        for key_type, key in enumerate((headline, cluster, text_hash)):
            if key:
                first = story_keys.setdefault((key_type, key), index)
                a, b = sorted((root(first), root(index)))
                parents[b] = a
    return [
        (publisher, banks)
        for index, (_, publisher, _, _, _, banks) in enumerate(rows)
        if root(index) == index
    ]


def _network(
    stories: list[list[str]], edge_bits: dict[tuple[str, str], int]
) -> tuple[int, int]:
    """Compute the pair union and pair weight on the given bank-mention lists."""
    union = weight = 0
    for banks in stories:
        for index, a in enumerate(banks):
            for b in banks[index + 1 :]:
                bit = edge_bits.setdefault((a, b), len(edge_bits))
                union |= 1 << bit
                weight += 1
    return union.bit_count(), weight


def _write_csv(
    path: Path, columns: tuple[str, ...], rows: list[tuple[object, ...]]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def report_kazinnik_matched_weeks(
    source: Annotated[Path, typer.Option(help="Prepared matched-week bridge.")],
    inputs: Annotated[Path, typer.Option(help="Matched weeks and comparisons.")],
    output: Annotated[Path, typer.Option(help="Matched-week report directory.")],
) -> None:
    """Write matched week estimates and their comparison to placebo changes."""
    output.mkdir(parents=True, exist_ok=True)
    with (inputs / "matched-weeks.csv").open(encoding="utf-8", newline="") as stream:
        windows = list(csv.DictReader(stream))

    weeks = [row["study_window"] for row in windows]
    with duckdb.connect(config={"threads": 4}) as con:
        records = con.execute(
            """SELECT w.study_window, a.id, a.publisher, a.normalized_headline,
                      a.minhash_cluster_id::VARCHAR, a.text_hash::VARCHAR,
                      list(DISTINCT a.bank ORDER BY a.bank)
               FROM read_parquet($bridge) a JOIN read_csv($windows, all_varchar=true) w
                   ON a.published BETWEEN w.starts_on::DATE AND w.ends_on::DATE
               GROUP BY w.study_window, a.id, a.published, a.publisher,
                        a.normalized_headline, a.minhash_cluster_id, a.text_hash
               ORDER BY w.study_window, a.published, a.id""",
            {
                "bridge": str(source / "article_banks.parquet"),
                "windows": str(inputs / "matched-weeks.csv"),
            },
        ).fetchall()
    raw: dict[
        str, list[tuple[str, str, str | None, str | None, str | None, list[str]]]
    ] = {week: [] for week in weeks}
    for week, article, publisher, headline, cluster, text_hash, banks in records:
        raw[week].append((article, publisher, headline, cluster, text_hash, banks))

    stories: dict[str, dict[str, list[list[str]]]] = {}
    for week, articles in raw.items():
        by_publisher: dict[str, list[list[str]]] = defaultdict(list)
        for publisher, banks in _representatives(articles):
            by_publisher[publisher].append(banks)
        stories[week] = by_publisher

    publishers = sorted(
        {publisher for period in stories.values() for publisher in period}
    )
    quotas = {
        publisher: min(
            len(by_publisher.get(publisher, [])) for by_publisher in stories.values()
        )
        for publisher in publishers
    }
    matched_count = sum(quotas.values())
    if not matched_count:
        message = "The specified earnings weeks have no publisher in common"
        raise ValueError(message)

    coverage = [
        (week, publisher, len(by_publisher.get(publisher, [])), quotas[publisher])
        for week, by_publisher in stories.items()
        for publisher in publishers
    ]
    _write_csv(
        output / "publisher-coverage.csv",
        ("week", "publisher", "stories", "matched"),
        coverage,
    )

    rng = np.random.default_rng(_SEED)
    edge_bits: dict[tuple[str, str], int] = {}
    week_rows: list[tuple[object, ...]] = []
    estimates: dict[str, np.ndarray[tuple[int, int], np.dtype[np.int64]]] = {}
    for week, by_publisher in stories.items():
        draws = np.empty((_DRAWS, 2), dtype=np.int64)
        bank_counts: list[int] = []
        for draw in range(_DRAWS):
            sample = []
            for publisher, quota in quotas.items():
                if quota:
                    candidates = by_publisher[publisher]
                    indices = rng.choice(len(candidates), quota, replace=False)
                    sample.extend(candidates[i] for i in indices)
            draws[draw] = _network(sample, edge_bits)
            bank_counts.append(len({bank for article in sample for bank in article}))
        estimates[week] = draws
        all_stories = [banks for group in by_publisher.values() for banks in group]
        week_rows.append(
            (
                week,
                len(raw[week]),
                len(all_stories),
                matched_count,
                *_network([banks for *_, banks in raw[week]], edge_bits),
                *_network(all_stories, edge_bits),
                *draws.mean(axis=0),
                min(bank_counts),
                max(bank_counts),
            )
        )
    _write_csv(
        output / "weeks.csv",
        (
            "week",
            "articles",
            "stories",
            "matched_stories",
            "raw_edges",
            "raw_weight",
            "story_edges",
            "story_weight",
            "matched_edges_mean",
            "matched_weight_mean",
            "matched_banks_min",
            "matched_banks_max",
        ),
        week_rows,
    )

    comparisons: dict[str, dict[str, str]] = defaultdict(dict)
    for row in windows:
        comparisons[row["comparison"]][row["position"]] = row["study_window"]
    changes: list[tuple[object, ...]] = []
    ranks: list[tuple[object, ...]] = []
    for index, metric in enumerate(("connected_pairs", "pair_weight")):
        means = {}
        for period, pair in comparisons.items():
            before, after = pair["before"], pair["after"]
            delta = estimates[after][:, index] - estimates[before][:, index]
            lower, upper = np.quantile(delta, [0.025, 0.975])
            means[period] = float(delta.mean())
            changes.append((period, before, after, metric, means[period], lower, upper))
        observed = means.pop("observed")
        ranks.append(
            (
                metric,
                observed,
                len(means),
                sum(value >= observed for value in means.values()),
                sum(abs(value) >= abs(observed) for value in means.values()),
            )
        )
    _write_csv(
        output / "changes.csv",
        (
            "comparison",
            "before",
            "after",
            "metric",
            "mean_change",
            "subsample_p025",
            "subsample_p975",
        ),
        changes,
    )
    _write_csv(
        output / "placebo-ranks.csv",
        (
            "metric",
            "observed_mean_change",
            "comparison_periods",
            "placebos_at_least_observed",
            "placebos_at_least_absolute_observed",
        ),
        ranks,
    )
