"""Test the headline similarity rule."""

import pytest
from pipeline.stages.processed.experiments.lopez_lira_tang.events import (
    headline_similarity,
)


@pytest.mark.unit
def test_headline_similarity_counts_adjacent_transposition_once() -> None:
    """Match the normalized Optimal String Alignment rule."""
    # Arrange
    first, second = "abcd", "abdc"

    # Act
    distance = headline_similarity(first, second)

    # Assert
    assert distance == 0.75
