import csv
from pathlib import Path

import duckdb
import pytest
from pipeline.stages.research.experiments.kazinnik_banks.networks import (
    report_kazinnik_banks,
)


@pytest.mark.component
def test_repeated_bank_yields_one_weight_per_unordered_pair(tmp_path: Path) -> None:
    # Arrange
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "roster.csv").write_text(
        "bank_order,bank,bank_group,bank_name\n"
        "1,A,Big 6,A Bank\n2,B,Regionals,B Bank\n3,C,Regionals,C Bank\n"
        "4,D,Trusts,D Bank\n5,E,IHC,E Bank\n"
    )
    (inputs / "crosswalk.csv").write_text(
        "bank,scope\nA,domestic_holding\nB,domestic_holding\n"
        "C,domestic_holding\nD,domestic_holding\n"
    )
    (inputs / "windows.csv").write_text(
        "study_window,period,starts_on,ends_on\n"
        "jan_week,week,2020-01-13,2020-01-19\n"
        "apr_week,week,2020-04-13,2020-04-19\n"
        "jan_month,month,2020-01-01,2020-01-31\n"
        "apr_month,month,2020-04-01,2020-04-30\n"
    )
    with duckdb.connect() as con:
        con.execute(
            """COPY (
                SELECT * FROM (VALUES
                    ('triple', 'A'), ('triple', 'A'), ('triple', 'B'), ('triple', 'C'),
                    ('solo', 'C')
                ) a(id, bank)
                CROSS JOIN (SELECT DATE '2020-01-19' AS published,
                    true AS directly_mapped, 'test.com' AS publisher,
                    '2020-02' AS capture_month, 'reporting' AS article_form,
                    NULL::VARCHAR AS headline, NULL::VARCHAR AS normalized_headline,
                    NULL::VARCHAR AS url, NULL::VARCHAR AS author,
                    NULL::VARCHAR AS minhash_cluster_id, NULL::VARCHAR AS text_hash)
            ) TO $path (FORMAT PARQUET)""",
            {"path": str(tmp_path / "article_banks.parquet")},
        )
    output = tmp_path / "report"

    # Act
    report_kazinnik_banks(tmp_path, inputs, output)

    # Assert
    with (output / "edges.csv").open(newline="") as file:
        edges = {
            (row["bank_a"], row["bank_b"]): int(row["weight"])
            for row in csv.DictReader(file)
            if row["study_window"] == "jan_week" and row["variant"] == "baseline"
        }
    assert edges == {("A", "B"): 1, ("A", "C"): 1, ("B", "C"): 1}
    assert sum(edges.values()) == 3 * 2 // 2
    with (output / "jan_week-matrix.csv").open(newline="") as file:
        _, *rows = csv.reader(file)
    assert rows == [
        ["A", "0", "1", "1", "0", ""],
        ["B", "1", "0", "1", "0", ""],
        ["C", "1", "1", "0", "0", ""],
        ["D", "0", "0", "0", "0", ""],
        ["E", "", "", "", "", ""],
    ]
    with (output / "bank-activity.csv").open(newline="") as file:
        nodes = {
            row["bank"]: (row["activity"], row["article_count"])
            for row in csv.DictReader(file)
            if row["study_window"] == "jan_week" and row["variant"] == "baseline"
        }
    assert nodes["C"] == ("mapped_active", "2")
    assert nodes["D"] == ("mapped_no_articles", "0")
    assert nodes["E"] == ("unresolved", "")
