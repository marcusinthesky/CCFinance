---
title: Kazinnik bank network results
description: CCFinance earnings-week and monthly comparisons with publisher and syndication evidence.
---

# Kazinnik bank network results

The four baseline networks map 33 of the working paper’s 34 banks. All 33
have at least one linked article in every window. BNP Paribas is unresolved.
The Big 6, credit-card banks, regionals and trusts map all 6, 3, 10 and 3
nodes respectively. IHC coverage is 11 of 12 with global parent proxies and
one direct US IHC mapping, Santander, which has zero direct articles in all
four windows. The baseline pair denominator is 528 of the manuscript’s 561
possible pairs. The domestic and US IHC sensitivity has 253 possible pairs.

| Window | Multi-bank articles | Connected pairs | Pair weight |
| --- | ---: | ---: | ---: |
| January 13–19 | 598 | 177 | 2,362 |
| April 13–19 | 778 | 242 | 3,203 |
| January 1–31 | 1,889 | 302 | 7,661 |
| April 1–30 | 2,760 | 408 | 11,109 |

The largest six banks form a complete subgraph in both months and weeks.
Their within-group weights rose from 1,667 to 2,276 in the earnings weeks
and from 4,132 to 5,920 across the months. They account for 71% of weekly pair
weight in both weeks. Weekly links between the Big 6 and other banks rose
from 89 to 126 of 162 possible mapped pairs, and weights rose from 547 to
708. Within regionals, weekly links rose from 4 to 15 of 45 and weights from
8 to 24. Within IHCs, weekly links fell from 25 to 20 of 55 and weights from
74 to 61. Monthly IHC links stayed at 39 of 55 while weights rose from 387
to 672. The broad increase in connected pairs and weights persists over the
full months, with a different within-IHC result.

All four baseline centrality rankings put JPMorgan Chase first. The next
two places are also Big 6 members in every window, with Citigroup second
in the January week and Wells Fargo second in the April week.

The 2023 manuscript’s Table 2 reports a rise in weekly Big 6 and regional
within-group weights and a fall within IHCs. Those directions recur in
CCFinance. Its total weekly edge count fell from 210 to 172 and its Big 6
cross-group count fell from 103 to 97. Both counts rise in the CCFinance
baseline and fall in the Reuters-host subset. The journal preview also
reports a core of large banks and more links among regional banks during
the pandemic. Both patterns appear in CCFinance. The final numerical table
and appendix were unavailable. [2023 manuscript](https://congress-files.s3.amazonaws.com/2023-07/Scida_News_and_Networks_CEBRA2023.pdf),
[journal article](https://doi.org/10.1016/j.jbankfin.2026.107694).

| Variant | Week edges Jan → Apr | Week weight Jan → Apr | Month edges Jan → Apr | Month weight Jan → Apr |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 177 → 242 | 2,362 → 3,203 | 302 → 408 | 7,661 → 11,109 |
| Unique headline | 177 → 242 | 1,992 → 2,761 | 302 → 408 | 6,762 → 9,504 |
| Under six banks | 145 → 162 | 1,720 → 2,048 | 261 → 287 | 5,162 → 7,474 |
| Exclude labeled roundups | 177 → 241 | 2,344 → 3,116 | 302 → 402 | 7,571 → 10,681 |
| Reporting | 72 → 172 | 889 → 1,459 | 145 → 244 | 1,927 → 2,983 |
| Reuters hosts | 50 → 35 | 245 → 287 | 88 → 82 | 797 → 926 |
| Excluding Nasdaq hosts | 162 → 230 | 1,761 → 2,530 | 279 → 379 | 5,465 → 8,342 |
| Direct mapping only | 77 → 133 | 1,927 → 2,670 | 145 → 213 | 5,193 → 7,818 |

## Concentration and article evidence

- Nasdaq.com and Seeking Alpha account for 36.7% of January-week pair
  weight and 32.3% of April-week weight. For full months the shares are 54.3%
  and 43.6%. These are distribution hosts and can carry syndicated copy.
- January’s earnings week includes 37 articles with six or more study banks,
  which contribute 642 pair observations (27.2%). The April week includes
  65 such articles and 1,155 pair observations (36.1%). Excluding them
  reduces the earnings-week increase in within-regional edges from 11 to
  2. Headline deduplication removes 15.7% and 13.8% of week weight and 11.7%
  and 14.4% of month weight in January and April respectively.
- The leading January-week edge links Citi and JPMorgan Chase in 237
  articles, including CNBC’s January 13 earnings preview
  (`828f7607-139e-4454-b46b-4b4dcdb72051`). The leading April-week edge
  links JPMorgan Chase and Wells Fargo in 346 articles, including Reuters’
  April 17 coverage of bank expenses
  (`b2e364ed-41a5-4ec2-ac41-a66ecb7115a9`). [CNBC](https://www.cnbc.com/2020/01/13/jp-morgan-kicks-off-bank-earnings-but-all-eyes-on-guidance.html),
  [Reuters](https://www.reuters.com/article/us-usa-banks-results-expenses/us-banks-say-cost-cuts-mostly-out-of-sight-during-coronavirus-idUSKBN21Z2ZR).
- Business Insider’s US and Australian editions carry a mortgage-relief
  roundup with the same headline and byline, both of which contribute to
  April’s largest monthly edge (Bank of America and JPMorgan Chase, 647
  articles). IDs `a9c05a05-9f94-4251-b2c0-b44315927857` and
  `3f8d5e04-d0f2-41b9-8cb0-b1624426ea17` each link the same 17 study banks
  and contribute 136 pairs. The bodies have separate exact hashes and
  MinHash IDs. The token-sequence similarity is 0.970 using case-folded
  word tokens and Python’s SequenceMatcher with autojunk disabled. The
  longest unchanged token run is 579 words. The unique-headline rule
  keeps the US edition.
- Adjacent capture months supply 47 of 5,941 January bank articles and
  92 of 7,769 April bank articles, including 7 January articles captured
  in December and 16 April articles captured in March.

The processed bridge has 23,115 unique article-bank rows. Each window's
summed edge weights match the count of distinct article-pair ledger rows
and the sum of `k(k-1)/2` over articles. The four exported matrices are
symmetric with zero on the mapped diagonal.

The article and source sensitivities describe dependence on the corpus.
Foreign-parent proxy links broaden the IHC scope, and the direct-only
network has no observable within-IHC pairs. Eigenvector rankings are
conditional on the observed network and its weighting. Differences in
publisher mix, timing, relevance and roster coverage prevent interpreting
the contrast as a measured change in financial exposures.

[Input protocol](../../../../../data/inputs/kazinnik-banks/README.md).
