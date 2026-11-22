---
title: Publisher influence on EMV tracking
description: Leave-one-publisher-out R² gaps during and outside the early pandemic shock.
---

# Publisher influence on EMV tracking

Omitting Forbes produced the largest tracking shortfalls against the archived EMV tracker for both outcomes on both calendars. The shock mattered most for realized volatility when Forbes was omitted. Removing March and April 2020 narrowed that gap by 0.311, compared with 0.182 for all publishers. For VIX the largest narrowing was 0.185 when The Wall Street Journal was omitted, compared with 0.091 for all publishers.

| Publisher omitted | VIX gap, 49 months | VIX gap, 47 months | Realized volatility gap, 49 months | Realized volatility gap, 47 months |
| --- | ---: | ---: | ---: | ---: |
| None | −0.132 | −0.041 | −0.233 | −0.051 |
| Benzinga | −0.098 | −0.067 | −0.115 | −0.010 |
| Forbes | −0.360 | −0.233 | −0.382 | −0.072 |
| MarketWatch | −0.149 | +0.004 | −0.284 | −0.050 |
| The Wall Street Journal | −0.202 | −0.017 | −0.320 | −0.036 |

Each gap subtracts the authors’ contemporaneous R² from the CCFinance R² on the same outcome and calendar. The full calendar runs from September 2019 through September 2023. For every rebuild, publisher shares are divided by their sample standard deviations over the original 40 calibration months through December 2022. The monthly average of the retained standardized shares is rescaled to the calibration-period mean VIX. The 47-month regressions then exclude the two shock months, keeping this calibration fixed.

All 196 publisher-month shares were available. Each three-publisher rebuild used all 147 retained cells over the full period and all 141 retained cells in the restricted period. These exploratory comparisons describe how changing the publisher mix affects historical fit. They provide no causal attribution or out-of-sample test.

Run `just dvc repro compare_baker_tracking`. The stage writes full-precision estimates, slopes and missing-cell counts to `data/research/experiments/baker-emv/paired-tracking/publisher_influence.csv`. An independent pandas reconstruction from the publisher shares reproduced all 20 gaps within `1e-12`. The all-publisher rebuild also reproduced all 49 frozen tracker levels and the four [paired-tracking benchmark gaps](../paired-tracking/results.md) within that tolerance.
