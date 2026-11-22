---
title: Paired EMV tracking on 49 months
description: Common-period fits, paired block bootstrap, calibration and month influence.
---

# Paired EMV tracking on 49 months

The authors’ EMV tracker explains more variation in both measures over
September 2019 through September 2023. The baseline CCFinance-minus-authors
R² gaps are −0.132 for monthly VIX and −0.233 for realized volatility.
Both six-month block intervals include zero. Removing March and April
2020 reduces the gaps to −0.041 and −0.051.

## Shared observations and estimand

The stage reads `reg_final` by calendar month from the Stata file
`2025 EMV Replication/norm_results_allpapers_constrained_clean_1986.dta`
inside the frozen `replication.rar`. The archive SHA-256 is
`05032793137ed46f73a86fd7d7b3896fa1b02c1422b27d15a33e3965dce1e9a9`.
The extracted member SHA-256 is
`3431a39f58ae66289ddaf3ad99d484183fdd551246ad52b0c3a50964d0cdd7eb`.
The comparisons use FRED-based VIX and realized volatility from the
CCFinance monthly panel as common outcomes. The saved ledger has one finite
row per calendar month, with both trackers and both outcomes. Each fit uses
an intercept and one contemporaneous tracker. The difference is CCFinance
R² minus the authors’ R². [Authors’ replication archive][archive]

| Outcome | Authors’ R² | CCFinance R² | Difference | Six-month 95% interval |
| --- | ---: | ---: | ---: | ---: |
| VIX | 0.647 | 0.515 | −0.132 | [−0.215, +0.110] |
| Realized volatility | 0.569 | 0.336 | −0.233 | [−0.311, +0.041] |

For each block length, draw 10,000 samples with NumPy seed 42. Draw block
starts uniformly with replacement on the ordered calendar, wrap at the end
and truncate each resampled series to 49 rows. Use the same draw for both
trackers and both outcomes. Recompute the two squared Pearson correlations
and take the 2.5th and 97.5th percentiles of their difference. All draws
have variation in both trackers and the outcome. Six-month blocks are the
main specification. The other lengths show sensitivity to preservation of
serial dependence over a panel of about four years.

| Block length | VIX 95% interval | Realized volatility 95% interval |
| ---: | ---: | ---: |
| 1 month | [−0.246, +0.069] | [−0.334, +0.009] |
| 3 months | [−0.219, +0.095] | [−0.315, +0.025] |
| 6 months | [−0.215, +0.110] | [−0.311, +0.041] |
| 12 months | [−0.203, +0.096] | [−0.293, +0.032] |

These exploratory intervals condition on the constructed tracker values.
They address contemporaneous tracking over this period and leave
uncertainty about the size and sign of the differences.

## Calibration and publication coverage

The baseline scales each publisher by its own share dispersion through
December 2022 and rescales the resulting average to the mean VIX over that
period. Removing the final scalar changes the VIX slope from 1.069 to
8.410 and the realized-volatility slope from 1.460 to 11.485. The R² values
and interval endpoints agree to numerical precision. Re-estimating the
publisher dispersions through December 2021 changes the relative weights
and lowers both R² values. The minimum-days rule drops three sparse
publisher-month cells and preserves all 49 shared calendar months.

| CCFinance variant | VIX R² | VIX gap | VIX six-month 95% interval | Realized vol. R² | Realized vol. gap | Realized vol. six-month 95% interval |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Minimum 15 publication dates | 0.506 | −0.142 | [−0.218, +0.087] | 0.336 | −0.233 | [−0.310, +0.040] |
| Calibration through December 2021 | 0.481 | −0.167 | [−0.257, +0.106] | 0.300 | −0.268 | [−0.345, +0.042] |

For realized volatility with the earlier calibration, the one-month
independent-draw interval ends just below zero at −0.001. The three-, six-
and twelve-month intervals all include zero.

## Calendar influence

Holding tracker values fixed, repeat both fits after omitting each month
in turn, then after omitting March and April 2020 or all of calendar 2020.
These are descriptive refits. The largest narrowing from any one omission
comes from March 2020 for both outcomes. The leave-one-month-out range is
[−0.150, −0.073] for VIX and [−0.248, −0.093] for realized volatility.

| Omitted | Months kept | VIX authors’ R² | VIX CCFinance R² | VIX gap | Realized vol. authors’ R² | Realized vol. CCFinance R² | Realized vol. gap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| March 2020 | 48 | 0.398 | 0.325 | −0.073 | 0.171 | 0.078 | −0.093 |
| March and April 2020 | 47 | 0.292 | 0.251 | −0.041 | 0.075 | 0.024 | −0.051 |
| Calendar 2020 | 37 | 0.095 | 0.073 | −0.022 | 0.024 | 0.012 | −0.012 |

The gap stays negative after these omissions, while the explained
variation falls substantially for both trackers. Much of the full-period
fit and of the difference depends on the early pandemic shock.

## Reproduction

Run `just dvc repro compare_baker_tracking` in the pinned environment
with the frozen archive and panel restored. The stage writes
`shared_months.csv`, `fits.csv`, `intervals.csv` and `influence.csv`
under `data/research/experiments/baker-emv/paired-tracking/`. The saved fits
and slopes matched an independent NumPy least-squares calculation
within `1e-12`. Recomputing each baseline three- and six-month draw with
`numpy.corrcoef` reproduced all four interval bounds within `1e-12`.

[archive]: https://data.mendeley.com/datasets/rmhtcwnvrk/1
