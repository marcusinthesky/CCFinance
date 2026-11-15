---
title: Project context
description: Plans, nested tasks and local literature records.
---

# Project context

[Planning](plan/README.md) holds versioned plans and nested tasks. The root
[roadmap](../ROADMAP.md) lists their immediate children. Schematter validates
document contracts; Insitu generates child views and backlinks.

`.context/reference/` holds local bibliographic records and source material.
The entire directory is ignored by Git. Create a record with
`just reference-new KEY TITLE`; its README owns flat CSL metadata and source
notes. Local reference records are validated when present but are not required
for a fresh checkout. The manuscript's `src/latex/refs.bib` remains authored
and versioned independently.

Edit record frontmatter and prose outside generated regions. Run `just sync`
to refresh views and `just context-check` to validate them without repairs.
Reference backlinks stay local; versioned plans must remain understandable
without the local literature folder. Cite public sources directly in plan prose.
