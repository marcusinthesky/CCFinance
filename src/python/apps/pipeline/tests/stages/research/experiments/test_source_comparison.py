"""Check probability weighting, uncertainty and complete comparison reports."""

import json
import math
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn
from pipeline.stages.research.experiments.source_comparison import (
    compare_sources,
    estimate_population,
)


@st.composite
def group_counts(draw: DrawFn) -> tuple[int, int]:
    rows = draw(st.integers(min_value=1, max_value=100))
    matches = draw(st.integers(min_value=0, max_value=rows))
    return rows, matches


@pytest.mark.unit
@given(
    st.lists(st.lists(group_counts(), min_size=1, max_size=3), min_size=1, max_size=3)
)
def test_probability_weighting_recovers_frame_totals(
    files: list[list[tuple[int, int]]],
) -> None:
    # Arrange: a finite population whose files have unequal numbers of groups.
    expected_english = sum(rows for groups in files for rows, _ in groups)
    expected_matches = sum(matches for groups in files for _, matches in groups)
    expected_estimates = {"english_records": 0.0, "publisher_records": 0.0}

    # Act: enumerate every possible one-draw outcome and its known probability.
    for groups in files:
        probability = 1 / (len(files) * len(groups))
        for rows, matches in groups:
            estimates = estimate_population([probability], [rows], [matches])
            for name in expected_estimates:
                value = estimates[f"estimated_{name}_estimate"]
                assert value is not None
                expected_estimates[name] += probability * value

    # Assert: expected estimated totals equal the independently counted population.
    assert expected_estimates["english_records"] == pytest.approx(expected_english)
    assert expected_estimates["publisher_records"] == pytest.approx(expected_matches)


@pytest.mark.unit
def test_unequal_weights_use_draw_variation_for_uncertainty() -> None:
    # Arrange: four draws with weighted English counts 100, 100, 300 and 200.
    probabilities = [0.1, 0.2, 0.1, 0.2]
    english = [10, 20, 30, 40]
    matched = [1, 4, 3, 8]

    # Act: estimate totals, the ratio and uncertainty across the four draws.
    estimates = estimate_population(probabilities, english, matched)

    # Assert: independently calculated totals and linearized errors are recovered.
    assert estimates["estimated_english_records_estimate"] == 175
    assert estimates["estimated_publisher_records_estimate"] == 25
    assert estimates["estimated_publisher_records_standard_error"] == pytest.approx(
        math.sqrt(125 / 3)
    )
    assert estimates["estimated_publisher_yield"] == pytest.approx(1 / 7)
    assert estimates["estimated_publisher_yield_standard_error"] == pytest.approx(
        math.sqrt(17000 / (49 * 12 * 175**2))
    )
    standard_error = math.sqrt(125 / 3)
    assert estimates["estimated_publisher_records_ci95_high"] == pytest.approx(
        25 + 3.182446305284263 * standard_error
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("probabilities", "english", "matched", "expected_yield"),
    [
        ([0.25] * 4, [10] * 4, [0] * 4, 0.0),
        ([0.25] * 4, [10] * 4, [2] * 4, 0.2),
        ([1.0], [0], [0], None),
        ([0.5], [10], [2], 0.2),
        ([1 / 3, 1 / 6, 1 / 9, 1 / 12], [10, 20, 50, 110], [7, 14, 35, 77], 0.7),
    ],
)
def test_insufficient_variation_does_not_claim_precision(
    probabilities: list[float],
    english: list[int],
    matched: list[int],
    expected_yield: float | None,
) -> None:
    # Arrange: no matches, identical groups, an empty denominator or a single draw.

    # Act: retain point estimates while estimating available uncertainty.
    estimates = estimate_population(probabilities, english, matched)

    # Assert: missing evidence produces null intervals, never zero-width intervals.
    assert estimates["estimated_publisher_yield"] == expected_yield
    if not any(matched):
        assert estimates["estimated_publisher_records_standard_error"] is None
    assert estimates["estimated_publisher_yield_standard_error"] is None
    assert estimates["estimated_publisher_yield_ci95_low"] is None
    assert estimates["estimated_publisher_yield_ci95_high"] is None


def _write_comparison_inputs(root: Path, datasets: tuple[str, ...]) -> tuple[Path, ...]:
    manifests, samples, params = root / "manifests", root / "samples", root / "p.yaml"
    source = "hf://datasets/example/source@revision/data/*.parquet"
    config: dict[str, object] = {"seed": 42, "draws": 4, "domains": "domains.csv"}
    config["datasets"] = {dataset: {"source": source} for dataset in datasets}
    params.write_text(json.dumps({"experiments": {"source_comparison": config}}))
    # Each source draws group A once and group B three times.
    groups = [("a.parquet", 10, 1)] + [("b.parquet", 20, 6)] * 3
    for dataset in datasets:
        draws = [
            {
                "draw": draw,
                "file": file,
                "row_group": 0,
                "row_start": 0,
                "row_stop": rows,
                "probability": 0.5,
                "file_row_groups": 1,
                "file_size_bytes": 200,
                "projected_bytes": 100,
            }
            for draw, (file, rows, _) in enumerate(groups)
        ]
        counts = [
            {"draw": d, "input_rows": n, "english_rows": n, "matched_rows": m}
            for d, (_, n, m) in enumerate(groups)
        ]
        manifest = {"dataset": dataset, "source": source, "revision": "revision"}
        manifest |= {"seed": 42, "file_count": 2, "listed_bytes": 400}
        manifest |= {"footer_bytes": 16, "english_definition": "English release"}
        (manifests / dataset).mkdir(parents=True)
        (manifests / dataset / "manifest.json").write_text(
            json.dumps(manifest | {"draws": draws})
        )
        sample = {"dataset": dataset, "draws": counts, "elapsed_seconds": 0.1}
        (samples / dataset).mkdir(parents=True)
        (samples / dataset / "counts.json").write_text(
            json.dumps(sample | {"output_bytes": 50, "network_bytes": None})
        )
    return manifests, samples, params


@pytest.mark.integration
def test_report_keeps_repeated_draws_but_counts_acquisition_once(
    tmp_path: Path,
) -> None:
    # Arrange: two configured sources, each with one repeated row group.
    manifests, samples, params = _write_comparison_inputs(
        tmp_path, ("fine_news", "refinedweb")
    )
    output = tmp_path / "report"

    # Act: publish all source estimates and their methods together.
    compare_sources(manifests, samples, output, params)

    # Assert: physical counts use two groups; weighted estimates keep all four draws.
    metrics = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
    assert set(metrics) == {"fine_news", "refinedweb"}
    for source in metrics.values():
        assert source["draws"] == 4
        assert source["selected_groups"] == 2
        assert source["sampled_matched_rows"] == 7
        assert source["projected_column_bytes"] == 200
        assert source["estimated_english_records_estimate"] == 35
        assert source["estimated_publisher_records_estimate"] == 9.5
        assert source["estimated_publisher_yield"] == pytest.approx(9.5 / 35)
        assert source["network_bytes"] is None
    yield_table = (output / "summary.tex").read_text(encoding="utf-8")
    assert r"fine\_news" in yield_table
    assert "27.1429" in yield_table
    assert r"95\% Student t" in (output / "summary.tex").read_text(encoding="utf-8")
