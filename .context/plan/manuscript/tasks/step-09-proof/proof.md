---
title: Manuscript proof and reproduction check
description: Rendered layout, submission requirements and reproduction results for the revised manuscript.
---

# Manuscript proof and reproduction check

Checked on 22 November 2026 against manuscript source revision `0d1e1f160d965fc6dad67e852c41ed44b2ac665a`. Both PDFs come from the shared manuscript in the pinned environment. This is a circulation proof.

## Submission and rendered pages

FinFM's Track 02 benchmark long-paper limit is seven technical pages in the anonymous AAAI-27 template. References and appendices are outside that limit, and reviewers may skip supplements. The public call gives 23 November 2026 at 23:59 Anywhere on Earth as the extended deadline. The linked OpenReview venue returned a loading shell without form fields or additional instructions, so the public call is the verified basis for the format check. [FinFM CFP](https://finfm.finhorizons.org/#cfp) · [OpenReview venue](https://openreview.net/group?id=AAAI.org/2027/Workshop/FinFM)

| PDF | Physical pages | Technical pages | Reference and appendix boundaries |
| --- | ---: | ---: | --- |
| `finfm.pdf` | 11 | 5 of 7 allowed | Page 5 includes Table 3, the conclusion and the start of references and counts as technical. References continue on page 6, which also begins Appendix A. |
| `arxiv.pdf` | 17 | 8 | Table 3 is on page 6. The conclusion starts on page 7 and ends on page 8, which also begins the references. Appendix A begins on page 10. |

Inspected rendered page sheets, text extraction, captions and bibliography in both targets. Tables 1–3 and A1–A10 are present, numbered in order and legible, and the six appendix sections and 32 bibliography entries are present in both PDFs. The technical pages give the frozen sample and its eligibility rules, model-adjudicated validation, the roster funnel, all three financial comparisons with their uncertainty or sensitivity, and restricted artifact access. No overfull boxes, unresolved references or duplicate destinations appeared. ArXiv has underfull bibliography lines around long source links. FinFM has underfull line and float spacing in the appendix and page flow. Rendered content remains legible.

The neutral FinFM filename, anonymous submission byline, extracted metadata and printable references reveal no project account, private artifact location or author affiliation. The PDF contains no external URL annotations. The Gawronsky–Huang preprint appears as a normal third-person reference. The arXiv byline reads “CCFinance contributors” and remains a placeholder pending the author list. The shared abstract is 1,099 characters in single-line ASCII metadata form, converting the date-range dash to a hyphen, against arXiv's 1,920-character limit. [arXiv metadata instructions](https://info.arxiv.org/help/prep.html)

## Access and executable checks

Both layouts distinguish public crawl inputs and third-party article rights from the private code and processed artifacts, and identify the conditions attached to upstream metadata and text. Exact staging access without authentication remains unverified. Reconstruction requires authorized access to the pinned project revision and matching frozen dependencies.

Both PDFs preserve the reproduction flags, ASCII hyphens, path and line continuations in the locked mention-scoring command. Running that command succeeded and reproduced the 40-lead score, including the +8.43 F1 point difference and interval spanning zero. All 15 DVC stage names in Table A10 had passed the pinned `just dvc repro --dry -s` check on revision `4cdec0d`. The update changed the introduction, related corpora, bibliography and editorial record. The reproduction instructions, graph, code and artifact definitions stayed the same. The dry run resolved the stage entry points without fetching or rerunning frozen workloads. It does not establish a fresh installation or an unauthenticated rebuild.

Pinned `just latex::check` exited 0 for the proof revision. The coordinator ran full pinned `just check` on the same clean revision before the proof record was edited. It exited 0 with 102 passing tests, 88 generated views from 69 sources, both PDF builds and current Semflow fingerprints.
