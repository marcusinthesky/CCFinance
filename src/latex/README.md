---
description: A small LaTeX manuscript built with a versioned Tectonic asset bundle.
---

# LaTeX

`main.tex` is the manuscript. Tectonic produces `build/main.pdf`; its output and
intermediate files are ignored. Edit the source, and use:

```bash
just latex::setup
just latex::build
just latex::check
```

Setup is an explicit network step that primes the Tectonic cache using the
versioned `tlextras-2022.0r0` bundle. Ordinary builds use only cached assets. After
adding an uncached TeX package, run setup again. Formatting uses tex-fmt and lint
uses ChkTeX. The build gate rejects unresolved citations and references.

`refs.bib` is authored content. The sample article demonstrates a real citation;
add your own records and cite them with `\citep{key}`.

See [ARCHITECTURE.md](ARCHITECTURE.md) for source and artifact ownership.
