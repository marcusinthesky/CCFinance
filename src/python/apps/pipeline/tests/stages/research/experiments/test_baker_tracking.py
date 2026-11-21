"""Tests for paired block resampling in the EMV tracker comparison."""

import numpy as np
import pytest
from pipeline.stages.research.experiments.baker_tracking import paired_r2_interval


@pytest.mark.unit
def test_affine_trackers_have_equal_fit_in_every_paired_draw() -> None:
    """Both fits use the same sampled rows and an intercept."""
    # Arrange
    author = np.array([1.0, 5.0, 3.0, 21.0, 7.0, 0.0, 2.0])
    trackers = np.column_stack([author, 2.0 * author + 4.0])
    outcome = np.array([4.0, 5.0, 10.0, 30.0, 16.0, 1.0, 0.0])

    # Act
    lower, upper, valid = paired_r2_interval(trackers, outcome, 3, draws=200)

    # Assert
    assert valid == 200
    assert (lower, upper) == pytest.approx((0.0, 0.0), abs=1e-14)


@pytest.mark.unit
def test_single_circular_block_preserves_the_signed_difference() -> None:
    """A full-period draw rotates the rows without changing either fit."""
    # Arrange
    trackers = np.array([[0.0, 1.0], [1.0, 2.0], [2.0, 2.0], [3.0, 1.0]])
    outcome = trackers[:, 0]

    # Act
    lower, upper, valid = paired_r2_interval(trackers, outcome, 4, draws=100)

    # Assert
    assert valid == 100
    assert (lower, upper) == pytest.approx((-1.0, -1.0))
