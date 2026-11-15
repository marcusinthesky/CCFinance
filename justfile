set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

mod python 'src/python/justfile'
mod latex 'src/latex/justfile'
workflow := "env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --offline --frozen --script src/python/scripts/workflow/script.py"

# Discover this project's commands.
default:
    @just --list

# Prepare locked dependencies and Git hooks (uses the network).
setup:
    env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --frozen --script src/python/scripts/workflow/script.py prepare
    just python::setup
    just latex::setup
    prek install

# Check source, views and selected languages without repairing files.
check:
    bash infra/nix/check.sh
    {{ workflow }} check
    just python::check
    just latex::check
    just data-check
    just changelog-check


# Run the selected language tests.
test:
    just python::test
    just latex::test

# Explicitly format sources.
fmt:
    nixfmt devenv.nix infra/nix/devenv.nix infra/nix/pkgs/schematter.nix
    rumdl fmt .
    just python::fmt
    just latex::fmt

# Check external links online.
links:
    git ls-files -z '*.md' | xargs -0 -r lychee --config lychee.toml --no-progress

# Run root-level DVC using the locked Python environment.
dvc *args:
    env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --project src/python --offline --frozen dvc "$@"

# Validate DVC metadata without fetching data.
data-check:
    just dvc status
    just dvc dag

# Refresh generated planning and reference views.
sync:
    {{ workflow }} sync

# Validate document schemas, links and generated views.
context-check:
    {{ workflow }} check

# Create a plan without overwriting existing content.
plan-new slug title:
    {{ workflow }} plan-new "$1" --title "$2"

# Create a task inside an existing plan or task.
task-new parent slug title:
    {{ workflow }} task-new "$1" "$2" --title "$3"

# Create a local reference record with its directory as citation key.
reference-new key title:
    {{ workflow }} reference-new "$1" --title "$2"

# Validate the repository changelog structure and change categories.
changelog-check:
    schematter validate --schema infra/schemas/documents/changelog.document-schema.yaml CHANGELOG.md
