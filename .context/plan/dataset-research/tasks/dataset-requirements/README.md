---
type: task
title: Define dataset requirements
description: Establish and validate the functional requirements for research use.
links: []
status: done
---

# Define dataset requirements

## Goal

Specify a public, reproducible financial news dataset for firm-level text,
co-mention networks and market research.

## Requirements

- **Coverage:** Report distinct usable articles per company-year, including zero
  counts for a declared universe, and firms meeting selectable annual thresholds
  over consecutive years. Compare with 47 raw articles per year over 2018–2022
  for the 100-firm Pricing Perspective frame; report raw and usable counts separately.
- **Articles:** Provide stable IDs, source and publisher, URL, title, article text,
  language, publication and capture times with precision, quality flags, and
  traceable capture provenance where available.
- **Companies:** Preserve all article–company links, dated issuer identifiers,
  supporting evidence, ambiguity and substantive relevance. Distinguish mentions
  from company-focused coverage and retain unresolved identities.
- **Sources:** Maintain versioned publisher selection criteria and distinguish
  original reporting, syndicated material and press releases where possible.
  Deduplicate stories without discarding source records or company links.
- **Research validity:** Evaluate extraction, deduplication, dates, company links
  and relevance against model-adjudicated samples with repeat and audit judges,
  labelled as such. Report precision, recall, judge reliability, uncertainty
  and coverage gaps across years, publishers and firms.
- **Reproducibility:** Publish a versioned schema, data dictionary, lineage,
  checksums, methods, coverage reports and examples for firm-year panels and
  co-mention networks. Document article-text access and redistribution conditions.
- **Extensions:** Treat company-specific sentiment and events, article topics and
  novelty as separately versioned, evaluated enrichments.

For the first release, screen firms on at least 47 usable articles in **each**
year from 2018 through 2022. Staging supports this cohort for 94 of the 100
Pricing Perspective firms (95 on raw links). For studies that require company
focus, apply the same threshold to focused articles: 57 roster firms qualify.
Publish both cohort lists with annual counts, retaining zero counts for the
broader evidenced universe. The focus classifier has about 66% test precision
and 57% recall against model labels; report those estimates with uncertainty.
The original seed-43 ticker-agreement check scored 19/20. The fresh seed-44
anchor audit scored 294/300 (98.0%, exact 95% interval 95.70%–99.26%), meeting
the point-estimate target. See the [methods and disagreements](../../../../../data/inputs/company-links/README.md#explicit-ticker-confirmation-audit).
See the [coverage audit](../coverage-audit/README.md).
Publication dates before CC-News began do not establish when text was observable.
See the [Pricing Perspective comparison](https://arxiv.org/html/2410.23447v3#Sx1)
for the baseline and its limitations.

## Acceptance

- [x] Review these requirements against staging evidence and intended studies.
- [x] Set evidence-based coverage and quality targets for a first release.

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
