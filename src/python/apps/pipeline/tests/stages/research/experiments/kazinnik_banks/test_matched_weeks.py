import csv
from pathlib import Path

import duckdb
import pytest
from pipeline.stages.research.experiments.kazinnik_banks.matched_weeks import (
    report_kazinnik_matched_weeks,
)


@pytest.mark.component
def test_matched_network_counts_one_story_and_uses_common_publishers(
    tmp_path: Path,
) -> None:
    # Arrange
    (tmp_path / "matched-weeks.csv").write_text(
        "study_window,starts_on,ends_on,comparison,position\n"
        "jan,2020-01-13,2020-01-19,observed,before\n"
        "apr,2020-04-13,2020-04-19,observed,after\n"
        "jul,2020-07-13,2020-07-19,placebo,before\n"
        "oct,2020-10-12,2020-10-18,placebo,after\n",
        encoding="utf-8",
    )
    with duckdb.connect() as con:
        con.execute(
            """COPY (
                SELECT id, publisher, published::DATE AS published,
                       headline AS normalized_headline, cluster AS minhash_cluster_id,
                       NULL::VARCHAR AS text_hash, unnest(banks) AS bank
                FROM (VALUES
                    ('jan1', 'common', '2020-01-13', 'title', NULL, ['A']),
                    ('jan2', 'copy', '2020-01-14', 'title', '123', ['A', 'B']),
                    ('jan3', 'common', '2020-01-15', 'rewrite', '123', ['A', 'C']),
                    ('jan4', 'local', '2020-01-13', NULL, NULL, ['A', 'C']),
                    ('apr1', 'common', '2020-04-13', NULL, NULL, ['A', 'B']),
                    ('jul1', 'common', '2020-07-13', NULL, NULL, ['A', 'B']),
                    ('oct1', 'common', '2020-10-12', NULL, NULL, ['A', 'B'])
                ) a(id, publisher, published, headline, cluster, banks)
            ) TO $path (FORMAT PARQUET)""",
            {"path": str(tmp_path / "article_banks.parquet")},
        )
    output = tmp_path / "report"

    # Act
    report_kazinnik_matched_weeks(tmp_path, tmp_path, output)

    # Assert
    with (output / "weeks.csv").open(encoding="utf-8", newline="") as stream:
        january = next(csv.DictReader(stream))
    assert january["articles"] == "4"
    assert january["stories"] == "2"
    assert january["raw_weight"] == "3"
    assert january["story_weight"] == "1"
    assert january["matched_stories"] == "1"
    assert float(january["matched_weight_mean"]) == pytest.approx(0)
    with (output / "placebo-ranks.csv").open(encoding="utf-8", newline="") as stream:
        connected = next(csv.DictReader(stream))
    assert float(connected["observed_mean_change"]) == pytest.approx(1)
    assert connected["comparison_periods"] == "1"
    assert connected["placebos_at_least_observed"] == "0"
