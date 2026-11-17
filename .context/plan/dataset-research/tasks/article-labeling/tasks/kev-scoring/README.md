---
type: task
title: Score company coverage with native Kev
description: Score company coverage with native Kev
links: []
status: done
---

# Score company coverage with native Kev

## Goal

The runtime agent prepares the pinned native Kev-0.8B server with cached weights,
then verifies shared article computation and multi-company structured questions.
The coordinating agent compares measured throughput with the actual CPU survivors
before scheduling the full run against the 07:00 SAST deadline.
The immediate audit scores a fixed probability sample of 1,000 CPU-retained
articles and checks whether the lexical selection is sensible. Inspect no-hit
exclusions separately; model agreement does not establish CPU correctness.

## Acceptance

- [x] Verify native serving, structured answers, context admission and GPU memory.
- [x] Benchmark representative retained articles through durable output.
- [x] Record the full-run estimate using the actual retained population.
- [x] Preserve complete scores or explicit unresolved/error/checkpoint statuses.

## Results

The fixed 1,000-record sample produced 993 scored records and seven explicit
context exclusions, with no server errors. Scoring and article I/O took 155.04
seconds (6.40 successful records/second). Observed GPU use was 7,618 MiB of
16,311 MiB, with no OOM retries. The retained-source-record extrapolation is
approximately 22 days, so no full-corpus scoring run was launched.

All 3,137 candidate pairs remain provisional: 3,061 require review, 75 belong
to context-excluded records, one is rejected and none meets the 0.95 acceptance
policy. Synthetic canaries exhibit substantial wording and answer-order
sensitivity on both optimized and reference kernels. These results establish
runtime feasibility for sampling, not reliable automated company labeling.

<!-- insitu:begin sql
id = "planning-children"
model = "children"
template = "children.md.j2"
-->

_No open children._

`0 open; 0 terminal`

<!-- insitu:end -->

## Backlinks

<!-- insitu:begin sql
id = "reference-backlinks"
model = "backlinks"
template = "backlinks.md.j2"
-->

_No declared backlinks._

<!-- insitu:end -->
