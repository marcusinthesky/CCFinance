# Monthly equity-market volatility replication

This study applies the six monthly Table 1 specifications from Baker, Bloom,
Davis and Kost to the frozen Fine News capture. The population is consistently
dated, canonical captured articles from [Benzinga, Forbes, MarketWatch and The
Wall Street Journal](hosts.csv) from September 2019 through September 2023.
The Wall Street Journal also appears in the authors' eleven-newspaper panel,
which uses full newspaper archives from 1985 through 2023. Each eligible
CCFinance article has unit weight. [July 2025 paper, §2.1 and Table 1][paper]

## News measurement

[The dictionary](dictionary.json) implements the selected economy, equity-market
and volatility sets in §2.1. The market set accepts the five specified
Standard and Poor variants, with straight or curly apostrophes in possessives.
The matcher lowercases Fine News `metadata.title` and `text` and searches each
field separately using RE2 word boundaries. Spaces in phrases admit one or
more whitespace characters. Punctuation can delimit a word. A phrase must be
wholly within one field, and the three term groups can occur in different
fields. Repetition yields one Boolean article hit. Null fields are empty.
The prepared publication date assigns the month, including when an article was
captured in the following month. [July 2025 paper, §2.1][paper]

The publisher-month denominator counts all eligible captures, including both
hits and non-hits. The ledger has one row for every publisher and month.
A covered month with zero hits has a share of zero. An absent cell has a null
share. The matching stage verifies each eligible ID has exactly one raw record.

## Calibration and coverage

[The window](window.json) fixes the analysis and calibration dates and coverage
rule. The estimated publisher dispersion is the sample standard deviation of
its monthly hit shares over September 2019 through December 2022. Divide each
share by that dispersion without centering, then take the equal-weight average
across available publishers. A publisher with fewer than two calibration
observations or zero calibration dispersion contributes no standardized
shares. A month with no contributing publishers has missing EMV. Multiply the
average by the ratio of mean VIX to mean unscaled EMV over calibration months
where both are observed. The authors used 1985 through 2015 to match the VIX
mean. [July 2025 paper, §2.1][paper]

The basket and coverage sensitivity were fixed from the capture counts before
estimating the regressions. All four publishers contribute to all 49 months in
the baseline. The sensitivity drops cells with fewer than 15 distinct
publication dates and recalculates calibration and the monthly index.
Benzinga in August and September 2023 had 9 and 5 dates, respectively.
MarketWatch in September 2023 had 12 dates. No cells in the calibration period
were dropped.

| Publisher | Eligible | Hits | Minimum dates in a month |
| --- | ---: | ---: | ---: |
| Benzinga | 119,189 | 5,172 | 5 |
| Forbes | 385,230 | 10,655 | 28 |
| MarketWatch | 120,723 | 4,687 | 12 |
| The Wall Street Journal | 50,092 | 566 | 20 |
| Total | 675,234 | 21,080 | |

Each of the 196 publisher-month cells recorded at least one hit. The final
pass counted two fewer hits than the feasibility pass, which accepted an
extra ampersand spelling and searched concatenated title and body text.

## Market data and models

The raw snapshot keeps the checksum-verified Mendeley archive and the FRED
daily closes, with retrieval URLs, timestamps and hashes in its provenance.
The processed daily observations retain the preceding S&P 500 close on
2019-08-30. Use the mean of VIX closes on dates with an S&P 500 close. This
session convention matches the archive within 0.005 VIX points across 49
months. Including the 11 VIX-only closes increases the maximum difference to
0.137 points. Monthly realized volatility is 100 times the square root of
252 times the mean squared daily S&P 500 log return, assigned to the month of
the ending close. Monthly realized volatility differs by at most 0.028 points
from the archived series. [VIX closes][vix] · [S&P 500 closes][sp500] ·
[July 2025 paper, Appendix D][paper]

| Table 1 column | Dependent variable | Regressors besides the intercept |
| --- | --- | --- |
| 1 | Monthly VIX | EMV |
| 2 | Monthly VIX | EMV, EMV lags 1 and 2 |
| 3 | Monthly VIX | EMV, EMV lags 1 and 2, VIX lag 1 |
| 6 | Log monthly VIX | Log EMV |
| 7 | Monthly realized volatility | EMV |
| 8 | Monthly realized volatility | EMV, realized volatility lag 1 |

Each statsmodels OLS fit uses its own complete cases. Lags refer to calendar
months, and logs require strictly positive values. The archived
`1. Baseline EMV and VIX Results.do` exports the results from the Stata
`newey` calls with lag 2. The replication uses Bartlett weights at calendar
lags 1 and 2, residual degrees-of-freedom correction, and Student's t
inference. If a month is unavailable for a model, it contributes no residual
score while remaining in the time calendar. [Authors' replication archive][archive]

## Verification and results

Running the six specifications on the authors' archive data reproduced
the published slope estimates, standard errors, sample counts and fit at
displayed precision. The small-panel test compares the implemented
coefficients, standard errors and fit with a direct matrix calculation
using the same observations and verifies absolute agreement within
`1e-12`. A direct NumPy OLS and HAC calculation on the 49 real baseline
rows verifies column 1's coefficients, standard errors and R² to an
absolute tolerance of `1e-10`, with the same observation count.

The baseline EMV slope is 1.069 (SE 0.305) for VIX and 1.460 (SE 0.806) for
realized volatility. The single-regressor models have R² of 0.515 and 0.336.
The coverage sensitivity yields R² of 0.506 and 0.336. Adding lagged VIX to
the model with two EMV lags raises in-sample VIX R² from 0.517 to 0.680.
The contemporaneous associations describe how the news index tracks the
same month's volatility.

Reproduce with `just dvc repro report_baker_emv` after restoring the frozen
inputs. Find the publisher-month ledger and the market observations in the
Baker processed directory, and find `monthly_panel.parquet`, `table.md`,
`regressions.csv`, `coverage.csv`, `model_inclusion.csv` and both tracking
figures under `data/research/experiments/baker-emv/`. The report stage renders both PDFs from the saved
PGFPlots sources and `tracking.csv` using the pinned TeX bundle.

[paper]: https://static1.squarespace.com/static/5e2ea3a8097ed30c779bd707/t/688847f536b2b31218aeefab/1753761782006/Policy%2BNews%2Band%2BStock%2BMarket%2BVolatility%2BJuly%2B2025.pdf
[archive]: https://data.mendeley.com/datasets/rmhtcwnvrk/1
[vix]: https://fred.stlouisfed.org/series/VIXCLS
[sp500]: https://fred.stlouisfed.org/series/SP500
