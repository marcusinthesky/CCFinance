---
description: Build the shared CCFinance manuscript for arXiv or anonymous AAAI submission.
---

# CCFinance manuscript

Edit the eight files in [projects/ccfinance/src/sections](projects/ccfinance/src/sections/).
Put abstract text directly in `00_abstract.tex`. Add section headings and text
to the other files when drafting. Both targets read the same abstract, body,
appendix and project-local bibliography. Edit the title and arXiv byline in
[metadata.tex](projects/ccfinance/src/metadata.tex).

Run from the repository root in the pinned devenv shell.

```sh
just latex::setup        # Prime the TeX cache and install the locked prose linter
just latex::build arxiv  # Tectonic, single-column preprint
just latex::bundle arxiv # Create and verify the arXiv source upload
just latex::build finfm  # pdfLaTeX and BibTeX, anonymous AAAI-27 layout
just latex::check        # Lint and build both targets
just latex::prose-lint   # Optional editorial suggestions for the sections
```

PDFs are written to `projects/ccfinance/build/<target>/<target>.pdf`
beneath this directory. The academic-manuscript skill also supports outlines
and editorial review. Its prose linter accepts individual section paths.

Upload `projects/ccfinance/build/arxiv/arxiv.tar.gz` to arXiv.
The bundle contains the named-author manuscript, its local style and its
compiled bibliography. The recipe unpacks the archive and compiles
`main.tex` with pdfLaTeX before publishing the file locally.

The coverage report uses `coverage.tex`. DVC stages render standalone figures
with `just latex::render <file>`. The source-comparison stage also produces a
table fragment. See the [source comparison guide](../../data/inputs/source-comparison/README.md)
for its inputs and interpretation.
