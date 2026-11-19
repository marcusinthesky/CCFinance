"""Exercise weighted class scores on known reference labels."""

import pytest
from pipeline.stages.research.experiments.metadata_validation import (
    _estimates,
    _press_shares,
)


@pytest.mark.unit
def test_weighted_precision_and_unsupported_recall() -> None:
    # Arrange unequal inclusion weights and a class missing from the reference.
    rows = [
        ("a", "positive", "positive", 9.0, "head"),
        ("b", "positive", "negative", 1.0, "tail"),
        ("c", "mixed", "negative", 1.0, "tail"),
    ]

    # Act with article-cluster intervals enabled.
    metrics = _estimates(rows)

    # Assert the primary estimate and explicitly undefined denominator.
    assert metrics["positive"]["precision"][0] == pytest.approx(0.9)
    assert metrics["mixed"]["recall"] is None


@pytest.mark.unit
def test_paired_press_release_difference_uses_link_multiplicity() -> None:
    # Arrange one missed press release with three links and one correct non-release.
    rows = [
        ("reporting", 2, 2, 3, False, True),
        ("reporting", 2, 2, 1, False, False),
    ]

    # Act on the article-issuer denominator.
    result = _press_shares(rows)

    # Assert exact ratios for a census stratum.
    assert result["paired_difference_judged_minus_predicted"] == {
        "estimate": 0.75,
        "ci95_low": 0.75,
        "ci95_high": 0.75,
    }
