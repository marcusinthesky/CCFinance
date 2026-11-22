---
description: One CCFinance manuscript with arXiv and anonymous AAAI-27 layouts.
---

# Manuscript build

The project under `projects/ccfinance` owns its section sources, metadata and
authored bibliography. Its `body.tex` and `appendix.tex` define the reading
order. The two target files own the document class, title block, abstract
environment and bibliography style. Shared packages live under `templates/`.

The arXiv target uses the pinned Tectonic bundle. The FinFM target uses the
vendored AAAI-27 author kit with pdfLaTeX and BibTeX from the pinned Nix shell.
Each build writes to its own ignored output directory. Generated research
reports continue to use the separate cached Tectonic render command.
