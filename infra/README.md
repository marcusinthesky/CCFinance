---
description: Reproducible tools and repository document contracts.
---

# Infrastructure

Nix provisions the development environment under [nix/](nix/README.md).
Optional workflow document contracts live under schemas/documents/.
The pinned GPU extraction image is described in [inference/](inference/README.md).
The root Devenv files and justfile provide the normal entrypoints.
Cloud infrastructure is added only when a project needs it.
