---
title: Recovered overnight events and Gemma body probe
description: Full eligibility, sample reconciliation and refits on the frozen 171-issuer roster.
---

# Recovered overnight events and Gemma body probe

The historical first-publication format added 943 eligible articles and 667
firm-sessions. The Gemma body drift probe gained 68 days with both portfolio
legs. Mean gross daily drift moved from −10.15 to −7.73 bp across each panel’s
evaluated days. The expanded sample still produced a negative mean.

| Main Gemma body drift result | Frozen | Expanded |
| --- | ---: | ---: |
| Fitted months out of 32 | 20 | 20 |
| Evaluated days out of 670 | 277 | 340 |
| Both-leg days | 42 | 110 |
| Evaluated zero-leg days | 123 | 74 |
| Positive days (%) | 26.71 | 37.65 |
| Mean daily drift (bp) | −10.15 | −7.73 |

The original refit reproduced the saved prediction and rolling-window CSVs
byte for byte for both targets and both cohorts. We applied the same refit and
portfolio functions to a separate expanded panel. The new clocks changed both
training inputs and the days on which a prediction could be evaluated.

| Panel coverage | Frozen full panel | Expanded full panel | Frozen evaluation | Expanded evaluation |
| --- | ---: | ---: | ---: | ---: |
| Article–firm rows | 1,104 | 2,092 | 1,100 | 2,088 |
| Unique articles | 996 | 1,939 | 992 | 1,935 |
| Distinct firm-sessions | 984 | 1,651 | 980 | 1,647 |
| Sessions with any firm | 405 | 482 | 402 | 479 |
| Sessions with at least four firms | 98 | 215 | 98 | 215 |

The historical format recovered 11,196 first-publication clocks. Across
the full calendar, 2,738 fell outside an overnight interval and 274 were
captured after cutoff. Of the remaining 8,184 articles, 5,392 had no link
to the fixed roster. The original event rules rejected 2,510 on-roster links
for focus. The 995 remaining article–firm links matched the prior audit.
Five failed the joint within-session similarity screen, one had an exact
title in the previous 90 days, and one failed the price-movement headline
screen. All 988 remaining links passed the dated listing, vector and price
screens. No original article–firm row was displaced. The recovered ledger
retains each article ID, the matched marker, its UTC time, and each on-roster
issuer’s disposition.

Each of the 32 six-month windows is reconciled in `training_support.csv`,
including article rows, unique articles, distinct firm-sessions and fit
decisions. The first September 2022 fit grew from 100 to 140 training rows.
In April 2023, support grew from 103 to 961 rows. The first fit and all
subsequent fit or skip decisions for the main sample stayed the same.

Run `just dvc repro report_lopez_recovered` to recreate the ledgers and fits
under `data/research/experiments/lopez-recovered/`.
