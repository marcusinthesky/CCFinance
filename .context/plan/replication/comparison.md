---
title: Replication estimates and inference
description: Published benchmarks, common-period comparisons and uncertainty in the three CCFinance studies.
---

# Replication estimates and inference

## Baker, Bloom, Davis and Kost

The original eleven-newspaper EMV tracker explains more contemporaneous
variation in both volatility measures. Both CCFinance slopes are positive.
The 49-month CCFinance sample is short enough that uncertainty about tracking
performance is substantial. We separately ran the estimators on the archived
data and reproduced the six published monthly columns to their displayed precision.
[Table 1, July 2025 paper][baker] · [CCFinance protocol and tables][emv]

| Monthly Table 1 column | Original EMV slope | CCFinance EMV slope | Original R² | CCFinance R² |
| --- | ---: | ---: | ---: | ---: |
| 1. VIX | 0.745 | 1.069 | 0.603 | 0.515 |
| 2. VIX, two EMV lags | 0.554 | 1.110 | 0.670 | 0.517 |
| 3. VIX, two EMV lags and lagged VIX | 0.496 | 1.102 | 0.824 | 0.680 |
| 6. Log VIX on log EMV | 0.765 | 0.921 | 0.575 | 0.421 |
| 7. Realized volatility | 0.971 | 1.460 | 0.627 | 0.336 |
| 8. Realized volatility with its own lag | 0.820 | 1.180 | 0.661 | 0.387 |

**Same-month comparison.** We joined the authors' archived `reg_final` in
`norm_results_allpapers_constrained_clean_1986.dta` to the baseline
`monthly_panel.parquet` by year and month. Each regression uses the same
49 monthly FRED outcomes, September 2019 through September 2023, with an
intercept. For VIX, the authors' tracker has R² 0.647 versus 0.515 for
CCFinance, a difference of −0.132 for CCFinance. For realized volatility the
comparison is 0.569 versus 0.336, a difference of −0.233. Recalibration changes
the units of a slope. A constant rescaling leaves the single-regressor R²
unchanged. [Authors' replication archive][baker-data]

**Uncertainty.** A paired six-month block bootstrap gives a 95% interval of
[−0.215, 0.110] for the VIX R² difference and [−0.311, 0.041] for realized
volatility. Three-month blocks give [−0.219, 0.095] and [−0.315, 0.025].
Both trackers see the same volatility shocks in every draw. The negative
point estimates leave zero within the plausible range for both outcomes.
Within CCFinance, the univariate lag-two Newey–West slope intervals are
[0.456, 1.682] for VIX and [−0.162, 3.081] for realized volatility.

## Kazinnik, Killen, Scidá and Wu

| Earnings-week measure | July 2023 manuscript, Jan → Apr | CCFinance, Jan → Apr |
| --- | ---: | ---: |
| Distinct connected pairs | 210 → 172 (−38) | 177 → 242 (+65) |
| Total pair weight | 1,057 → 1,075 (+1.7%) | 2,362 → 3,203 (+35.6%) |
| Big 6 to other banks, distinct pairs | 103 → 97 | 89 → 126 |
| Within regionals, distinct pairs | 9 → 12 | 4 → 15 |
| Within intermediate holding companies, distinct pairs | 30 → 12 | 25 → 20 |

The CCFinance results recover a complete Big 6 core and the directions of
the regional and foreign holding-company changes. The sign of the change in
total connections reverses. Restricting CCFinance to Reuters hosts gives a
decline from 50 to 35. This makes publisher coverage a material explanation to
investigate. A comparison of count levels also depends on article volume and
coverage of 33 of the 34 roster members, including foreign-parent proxies.
The detailed numerical benchmark is the authors' 2023 Table 2. The accessible
final journal preview confirms the qualitative claims. Its final tables and
appendix remain unverified. [Manuscript, Table 2][banks] · [Journal article][journal]
· [CCFinance network and source sensitivities][networks]

**Inference.** January and April supply one earnings week each. A single
multi-bank article generates many related edges, and the same syndicated
story can appear on several hosts. An independent-pairs test would understate
uncertainty. Keep the two-week result descriptive. To test a broader stress
effect, predefine other earnings weeks, match article volume and publisher
composition, and rebuild networks under a week-level placebo or resampling
design. Group syndications when resampling stories. This would estimate how
unusual the change was relative to comparable weeks.

## López-Lira and Tang

| Overnight portfolio measure | Paper MiniLM headlines | Paper OpenAI headlines | CCFinance Gemma bodies |
| --- | ---: | ---: | ---: |
| Reaction positive days | 80.15% | 84.63% | 23.10% |
| Reaction mean daily return | +1.12% | +1.37% | −0.261% |
| Drift positive days | 56.57% | 59.85% | 26.71% |
| Drift mean daily return | +0.11% | +0.23% | −0.102% |
| Drift annualized Sharpe | 1.42 | 2.53 | −1.35 |

Against MiniLM, the mean differences are −1.381 percentage points for reaction
and −0.212 for drift. CCFinance has 277 evaluated sessions, with both legs on
29 reaction days and 42 drift days. On 127 reaction days and 123 drift days,
neither leg met the two-security minimum and the evaluated return was zero.
A hit means a positive portfolio day. These zeros affect the hit rate directly.
Two publishers, 996 distinct bodies, 171 firms, public prices, and a different
encoder and relevance screen all change this comparison. A single May 2024
session contributed about 57% of the summed reaction loss. The overnight
reaction also starts before the news arrives. Drift is the forward-looking
test. [Paper, Table 8][lopez] · [CCFinance protocol and results][probes]

**Uncertainty.** Conditional on the saved predictions, the 21-session block
bootstrap gives 95% intervals for mean daily returns of [−0.636%, −0.038%]
for reaction and [−0.252%, +0.042%] for drift. With five-session blocks the
intervals are [−0.617%, −0.038%] and [−0.243%, +0.036%]. Drift is compatible
with zero. These intervals measure uncertainty in this portfolio series.
Attributing a gap to the text or encoder requires a paired experiment on
identical stories, issuers, sessions, returns and exposure rules. Run the
same encoder on titles and bodies first. Compare encoders on the same text
separately. Predefine mean drift as the primary endpoint, report trading
costs and paired-leg support, and block-resample daily return differences.
Treat reaction, hit rate, Sharpe and additional subgroup tests as secondary.

## Resampling details

The intervals above are exploratory percentile intervals, conditional on the
frozen trackers and fitted probes. In each calculation, sort the series by
date, draw 10,000 circular block samples with replacement and use the 2.5th
and 97.5th percentiles. For Baker, compute each simple-regression R² as the
squared Pearson correlation of the resampled tracker and outcome and then
subtract the authors' R² from CCFinance's. For the probes, use the 438
exchange sessions between the first and last evaluated dates, including
unevaluated dates as missing and zero-leg evaluated dates as zeros. Take the
mean over observed returns in each draw. This conditions on the estimated
trading rules and preserves local calendar gaps. A future assessment of the
training procedure would refit it over fresh out-of-sample periods.

The following NumPy expression reproduces the draw indices. Initialize the
generator separately for each block length. Use the same rows for every
series in a paired comparison.

```python
rng = np.random.default_rng(42)
starts = rng.integers(0, n, size=(10_000, (n + length - 1) // length))
draws = ((starts[:, :, None] + np.arange(length)) % n).reshape(10_000, -1)[:, :n]
```

[baker]: https://static1.squarespace.com/static/5e2ea3a8097ed30c779bd707/t/688847f536b2b31218aeefab/1753761782006/Policy%2BNews%2Band%2BStock%2BMarket%2BVolatility%2BJuly%2B2025.pdf
[baker-data]: https://data.mendeley.com/datasets/rmhtcwnvrk/1
[emv]: ../../../data/inputs/baker-emv/README.md
[banks]: https://congress-files.s3.amazonaws.com/2023-07/Scida_News_and_Networks_CEBRA2023.pdf
[journal]: https://doi.org/10.1016/j.jbankfin.2026.107694
[networks]: tasks/kazinnik-banks/results.md
[lopez]: https://arxiv.org/html/2304.07619v6#Sx7.T8
[probes]: ../../../data/inputs/lopez-lira-tang/README.md
