---
description: Static Schematter contracts for plans, references and the repository changelog.
---

# Document schemas

`just context-check` selects schemas by record path. Plans and tasks share the
work-item contract; `type` asserts their physical role. References use flat CSL
metadata and derive citation keys from directory names. Local references are
validated when present.

Entry points and records have a 1,500-token budget. Schematter checks document
shape; the workflow helper checks containment, declared links and completion.

`just changelog-check` validates the root `CHANGELOG.md` using the
Pricing Perspective changelog contract, with `Unreleased` allowed for changes
awaiting a pull request. Published entries use `PR #NUMBER: Title` headings.
Categories are `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed` and `Security`,
each containing a bullet list. Frontmatter permits only `type` and `description`.
Both checks run in CI and through pre-commit hooks.
