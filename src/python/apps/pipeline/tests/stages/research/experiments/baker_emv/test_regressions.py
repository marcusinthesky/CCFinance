import numpy as np
import pytest
from pipeline.stages.research.experiments.baker_emv.regressions import fit_monthly


@pytest.mark.unit
def test_ols_and_calendar_hac_agree_with_direct_sandwich_calculation() -> None:
    # Arrange
    rows = [
        [11.0, 1.0],
        [14.0, 2.0],
        [None, 3.0],
        [16.0, 4.0],
        [21.0, 5.0],
        [19.0, 6.0],
    ]
    x = np.array([[1, 1], [1, 2], [1, 4], [1, 5], [1, 6]])
    y = np.array([11, 14, 16, 21, 19])
    periods = [0, 1, 3, 4, 5]
    inverse = np.linalg.inv(x.T @ x)
    beta = inverse @ x.T @ y
    residuals = y - x @ beta
    # The Bartlett window gives weights 2/3 and 1/3 at calendar lags 1 and 2.
    meat = np.zeros((2, 2))
    for i, month in enumerate(periods):
        for j, other_month in enumerate(periods):
            weight = max(0, 1 - abs(month - other_month) / 3)
            meat += weight * np.outer(x[i], x[j]) * residuals[i] * residuals[j]
    expected_se = np.sqrt(np.diag((5 / 3) * inverse @ meat @ inverse))
    expected_r_squared = 1 - sum(residuals**2) / sum((y - y.mean()) ** 2)

    # Act
    fit = fit_monthly(rows)

    # Assert
    assert fit.included.tolist() == [True, True, False, True, True, True]
    assert fit.nobs == 5
    assert fit.coefficients == pytest.approx(beta, abs=1e-12)
    assert fit.standard_errors == pytest.approx(expected_se, abs=1e-12)
    assert fit.r_squared == pytest.approx(expected_r_squared, abs=1e-12)
