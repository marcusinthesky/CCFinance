---
title: Overnight publisher coverage in the fixed issuer universe
description: Recoverable first-publication clocks and incremental security coverage on the original calendar.
---

# Overnight publisher coverage in the fixed issuer universe

Business Standard is the first place to expand. The original parser missed a
historical format such as `First Published: Sun, October 16 2022. 22:16 IST`.
We recovered **11,196 of the 84,225** missing first-publication clocks by
requiring the explicit marker, date, clock, IST suffix and consistent weekday.
The 512-article audit contains 71 recoveries. Update times are recorded as
separate evidence. Among the recovered articles, 8,125 were published after
the previous close and captured by the 09:00 New York cutoff in the original
October 2021–May 2024 evaluation period.

Requiring an original-sample issuer, a complete extracted body and the
original mention and focus thresholds leaves 995 links to 82 firms in 950
articles. Across 159 sessions these supply **667 distinct firm-sessions**
absent from the original sample. Before price, listing and novelty checks,
**117 sessions** could move from fewer than four firms to at least four firms,
including 70 starting with one to three. These are opportunities to build both
portfolio legs. Realized model support would also depend on predictions.

## Prospective publishers

For each of the 670 evaluation sessions we screened usable articles captured
after the previous close and by the morning cutoff, with a catalogue
publication date close to the interval, the same body focus criteria, and
an issuer from the same frozen 171-firm universe. We counted each extra firm
once per host and session. Each row adds one host independently to the
original daily sample. The rows overlap.

| Host | Extra firm-sessions screened | Sessions potentially crossing four |
| --- | ---: | ---: |
| Forbes | 7,782 | 561 |
| Nasdaq | 32,318 | 552 |
| Business Insider | 5,804 | 545 |
| Yahoo Finance | 10,060 | 541 |
| Seeking Alpha | 13,492 | 476 |

Capture timing alone cannot establish first publication. We inspected the
matched publication-marker snippets for 32 deterministically sampled articles
per host. Thirteen of the 160 articles matched the phrase screen, including
syndication credits on Yahoo and a reference to another publication on Forbes.
None of those snippets established the story's own first-publication date,
clock and timezone. Other formats or archived bylines could yield usable
clocks. The prospective host counts therefore describe a screening opportunity;
the recovered Business Standard clocks have stronger evidence.

Run `just dvc repro audit_lopez_publisher_support`. Its report under
`data/research/experiments/lopez-publisher-support/` includes per-host
daily counts, rankings, ID-level clock evidence, recovery totals and the
dated issuer links. The frozen training and evaluation panels remain the basis
for the title experiment.
