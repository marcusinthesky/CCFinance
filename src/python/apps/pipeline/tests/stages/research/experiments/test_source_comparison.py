"""Check probability weighting, uncertainty and complete comparison reports."""

import json
import math
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn
from pipeline.stages.research.experiments.source_comparison import (
    REPORT_FILES,
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


def _write_comparison_inputs(
    root: Path,
    datasets: tuple[str, ...] = (
        "fine_news",
        "infini_news",
        "refinedweb",
        "fineweb_hq",
    ),
    *,
    zero_matches: bool = False,
) -> tuple[Path, Path, Path]:
    manifests = root / "manifests"
    samples = root / "samples"
    source = "hf://datasets/example/source@revision/data/*.parquet"
    params = root / "params.yaml"
    params.write_text(
        json.dumps(
            {
                "experiments": {
                    "source_comparison": {
                        "seed": 42,
                        "draws": 4,
                        "domains": "domains.csv",
                        "datasets": {
                            dataset: {"source": source} for dataset in datasets
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    for dataset in datasets:
        draws = []
        counts = []
        for draw, (file, rows, matches) in enumerate(
            [
                ("a.parquet", 10, 1),
                ("b.parquet", 20, 6),
                ("b.parquet", 20, 6),
                ("b.parquet", 20, 6),
            ]
        ):
            draws.append(
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
            )
            counts.append(
                {
                    "draw": draw,
                    "input_rows": rows,
                    "english_rows": rows,
                    "matched_rows": 0 if zero_matches else matches,
                }
            )
        manifest_dir = manifests / dataset
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "dataset": dataset,
                    "source": source,
                    "revision": "revision",
                    "seed": 42,
                    "file_count": 2,
                    "listed_bytes": 400,
                    "footer_bytes": 16,
                    "english_definition": "English release",
                    "draws": draws,
                }
            ),
            encoding="utf-8",
        )
        sample_dir = samples / dataset
        sample_dir.mkdir(parents=True)
        (sample_dir / "counts.json").write_text(
            json.dumps(
                {
                    "dataset": dataset,
                    "draws": counts,
                    "elapsed_seconds": 0.1,
                    "output_bytes": 50,
                    "network_bytes": None,
                }
            ),
            encoding="utf-8",
        )
    return manifests, samples, params


@pytest.mark.integration
def test_report_keeps_repeated_draws_but_counts_acquisition_once(
    tmp_path: Path,
) -> None:
    # Arrange: each source draws group A once and group B three times.
    manifests, samples, params = _write_comparison_inputs(tmp_path)
    output = tmp_path / "report"

    # Act: publish all source estimates and their methods together.
    compare_sources(manifests, samples, output, params)

    # Assert: physical counts use two groups; weighted estimates keep all four draws.
    metrics = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
    assert set(metrics) == {"fine_news", "infini_news", "refinedweb", "fineweb_hq"}
    for source in metrics.values():
        assert source["draws"] == 4
        assert source["selected_groups"] == 2
        assert source["sampled_input_rows"] == 30
        assert source["sampled_matched_rows"] == 7
        assert source["projected_column_bytes"] == 200
        assert source["observed_publisher_yield"] == pytest.approx(7 / 30)
        assert source["estimated_english_records_estimate"] == 35
        assert source["estimated_publisher_records_estimate"] == 9.5
        assert source["estimated_publisher_yield"] == pytest.approx(9.5 / 35)
        assert source["network_bytes"] is None
    methods = json.loads((output / "methods.json").read_text(encoding="utf-8"))
    assert methods["sources"]["fine_news"]["degrees_of_freedom"] == 3
    assert (
        len((output / "comparison.csv").read_text(encoding="utf-8").splitlines()) == 5
    )
    yield_table = (output / "yield.tex").read_text(encoding="utf-8")
    summary = (output / "summary.tex").read_text(encoding="utf-8")
    assert r"fine\_news" in yield_table
    assert r"Yield (\%)" in yield_table
    assert "27.1429" in yield_table
    assert "16.7512" in yield_table
    assert "37.5345" in yield_table
    assert "27.1429" in summary
    assert r"95\% Student t" in summary
    assert "insufficient evidence" in summary
    assert r"\begin{tabular}" in yield_table
    assert r"\begin{center}" not in yield_table


@pytest.mark.integration
def test_report_accepts_configured_subset_and_renders_missing_intervals(
    tmp_path: Path,
) -> None:
    # Arrange: a deliberate one-source experiment with no publisher matches.
    manifests, samples, params = _write_comparison_inputs(
        tmp_path, ("fine_news",), zero_matches=True
    )
    output = tmp_path / "report"

    # Act: report only the configured population without inventing precision.
    compare_sources(manifests, samples, output, params)

    # Assert: CSV, JSON and LaTeX agree on the zero estimate and unavailable CI.
    metrics = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
    assert set(metrics) == {"fine_news"}
    assert metrics["fine_news"]["estimated_publisher_yield"] == 0.0
    assert metrics["fine_news"]["estimated_publisher_yield_ci95_low"] is None
    assert len((output / "comparison.csv").read_text().splitlines()) == 2
    for name in ("yield.tex", "population.tex"):
        table = (output / name).read_text(encoding="utf-8")
        assert r"fine\_news" in table
        assert "--" in table
        assert "nan" not in table.lower()
    assert "0.0000" in (output / "yield.tex").read_text(encoding="utf-8")


@pytest.mark.integration
def test_missing_source_cannot_publish_partial_comparison(tmp_path: Path) -> None:
    # Arrange: omit one required source's acquisition results.
    manifests, samples, params = _write_comparison_inputs(tmp_path)
    (samples / "fineweb_hq" / "counts.json").unlink()
    output = tmp_path / "report"

    # Act: attempt to publish a comparison with incomplete evidence.
    with pytest.raises(FileNotFoundError):
        compare_sources(manifests, samples, output, params)

    # Assert: no report directory or partial metrics were published.
    assert not output.exists()


@pytest.mark.integration
def test_report_reproduces_after_dvc_removes_output_files(tmp_path: Path) -> None:
    # Arrange: DVC removes declared files before reproduction, leaving their parent.
    manifests, samples, params = _write_comparison_inputs(tmp_path)
    output = tmp_path / "report"
    compare_sources(manifests, samples, output, params)
    original_metrics = (output / "metrics.json").read_bytes()
    for file in output.iterdir():
        file.unlink()

    # Act: reproduce the report into the existing empty directory.
    compare_sources(manifests, samples, output, params)

    # Assert: all declared files are republished with identical metrics.
    assert {file.name for file in output.iterdir()} == set(REPORT_FILES)
    assert (output / "metrics.json").read_bytes() == original_metrics
