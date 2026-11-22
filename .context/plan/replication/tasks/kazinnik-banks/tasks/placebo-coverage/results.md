---
title: Bank networks across fourteen earnings weeks
description: Historical ranks on a fixed thirty-two-bank mapping and identical publisher quotas.
---

# Bank networks across fourteen earnings weeks

January–April 2020 added 19.1 connected pairs and 56.2 pair observations on
average. Among seven non-overlapping changes, the observed increase ranks
first for connected pairs and second for pair weight. The runner-up edge
increase was 19.0, a difference of just 0.1 edge across the seeded draws.
Ranking by absolute magnitude puts the observed change second and third,
respectively. Four of the six placebos precede the pandemic. Three compare
January to April and three compare July to October.

| Calendar comparison | Connected pairs, mean [95% draw range] | Pair weight, mean [95% draw range] |
| --- | ---: | ---: |
| Jan–Apr 2018 | +11.3 [−13, 30] | +26.9 [−36, 89] |
| Jul–Oct 2018 | −5.2 [−24, 16] | −100.1 [−161, −42] |
| Jan–Apr 2019 | +4.6 [−18, 22] | +18.7 [−77, 120] |
| Jul–Oct 2019 | −2.5 [−41, 23] | +11.1 [−85, 99] |
| **Jan–Apr 2020** | **+19.1 [−25, 59]** | **+56.2 [−40, 155]** |
| Jul–Oct 2020 | +19.0 [−13, 52] | +89.8 [−14, 199] |
| Jan–Apr 2021 | −49.5 [−71, −29] | −13.8 [−99, 67] |

Every draw retains 158 stories per week from 14 of 82 representative hosts.
The largest quotas are CNBC (50), Forbes (20), Benzinga (16), Channel NewsAsia
and Reuters (15 each). The other quotas are Business Standard (12),
MarketWatch (10), Financial Express (6), Business Insider (5), Barron's,
Livemint, Oilprice and The Straits Times (2 each), and the Financial Times (1).
Weekly draws contain 15–30 distinct banks across the calendar, including
18–29 in the observed January week and 18–30 in April. All 32 mapped banks
are eligible each week. The report's weeks.csv gives per-week min/max bank
counts and publisher-coverage.csv records every host quota.

The [original six-week analysis](../matched-weeks/results.md) used 33 mapped
banks and 682 stories from 31 hosts per week. Its January–April changes were
+56.3 pairs and +307.6 weight, both above its two placebo changes. Dropping
Truist to keep the roster consistent with 2018–19 leaves the raw January
network at 177 edges and 2,362 weight, while April falls from 242 to 229 edges
and from 3,203 to 3,187 weight. Rerunning just the original six weeks on
the extended bridge gives +45.4 pairs and +297.1 weight, retaining 681
stories from 31 hosts per week. Thus both the roster change and the stricter
publisher support attenuate the increase. Matching across fourteen weeks removes
Nasdaq.com, which previously supplied 271 of the 682 stories per draw. The
extended result describes this smaller publisher mix and fixed roster.

The ranges quantify selection of stories within host and week over 1,000
draws. Six distinct historical placebo periods determine the rank. The
observed weight increase is smaller than July–October 2020, both observed
draw ranges cross zero, and the January–April 2021 fall in edges is larger
in absolute terms. These descriptive comparisons offer limited evidence that
the onset of pandemic stress produced an exceptional change.

Run `just dvc repro report_kazinnik_extended_weeks` to reproduce the outputs
under `data/research/experiments/kazinnik-extended-weeks`. See the [calendar
sources and roster rules](../../../../../../../data/inputs/kazinnik-banks/README.md#extended-earnings-calendar).
