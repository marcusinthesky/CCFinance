---
description: Shared agent instructions and Codex configuration managed by AgentSync.
---

# Agent configuration

Canonical instructions and skills live here. AgentSync projects them into
Codex configuration using the targets in `agentsync.toml`. The pinned Nix
environment supplies the AgentSync CLI.

```bash
just agents::preview
just agents::apply
just agents::check
```

`just setup` applies the configuration. AgentSync backs up existing regular
files to `.bak` and replaces them with managed links. It can also replace
existing symlinks. Preview changes and preserve any local instructions or
settings before applying; `.bak` files are ignored by Git. AgentSync's apply
is not an all-target atomic operation, so inspect its output if it fails.
