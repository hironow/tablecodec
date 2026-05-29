# 0013. Develop `tablecodec-docling` in-repo as a temporary monorepo

**Date:** 2026-05-29
**Status:** Accepted

## Context

SPEC §15 plans a bridge codec, `tablecodec-docling`, as a **separate package**
that exports `DoclingDocument.tables` as `TableSample` instances. It must be a
distinct package because docling-core is heavy (Pydantic, numpy, pandas) and
tablecodec's core is stdlib-only (SPEC §13) — the dependency cannot live in the
core.

Two ways to start it: (a) a brand-new standalone repository, or (b) develop it
in-repo first and extract later. Standing up a separate repo (scaffold, CI,
PyPI Trusted Publishing) before the DoclingDocument→TableSample mapping is even
validated is front-loaded ceremony. The mapping — span offsets, header
semantics, bbox coordinate-origin conversion — is the actual risk.

This mirrors ADR 0001 (the conformance suite kept in-repo temporarily before
extraction to a vendor-neutral repo).

In-repo development conflicts with two global guidelines:

- "There MUST be exactly one justfile at the repository root. Do NOT create
  subdirectory justfiles."
- "Standard directories (src/, tests/) must exist only once at the repository
  root level; MUST NOT be duplicated in subdirectories" (exempting external
  submodules/clones).

## Decision

Develop `tablecodec-docling` under `packages/tablecodec-docling/` as a
**temporary monorepo member**, with its own `pyproject.toml`, `src/`, `tests/`,
and `LICENSE`, until it is extracted to its own repository before the first
PyPI publish.

Honor the guidelines as follows:

- **One justfile.** The sub-package has NO justfile. The root `justfile`
  orchestrates it via `docling-lint` / `docling-type` / `docling-test` /
  `docling-ci`, plus `ci-all = ci + docling-ci`. Core `just ci` stays
  core-only so the zero-dependency-core gate is unaffected.
- **Isolated environment.** The sub-package declares
  `[tool.uv.sources] tablecodec = { path = "../../", editable = true }` and is
  run with `uv run --project packages/tablecodec-docling`, so docling-core (and
  its numpy/pandas) install into the SUB-package's own `.venv`, never the core
  env. The core's `pip install -e .` zero-dep guard job is untouched.
- **Core invariant intact.** `semgrep.yaml`'s core import rule does not include
  `packages/`; the bridge's docling-core imports are legal where they live and
  impossible in the core.

The `src/`+`tests/` duplication in the sub-package is accepted as the
distributable-package exemption in spirit (a monorepo member is a distinct
publishable unit, like the submodule exemption), recorded here.

## Consequences

### Positive
- The mapping is validated now, with real docling-core, before any packaging
  ceremony. Extraction later is a `git filter-repo` move, not a rewrite.
- Core repo's zero-dep gate, env, and CI are unaffected (separate uv project).
- The bridge is usable today via `tablecodec.codecs.load_plugins()` once the
  sub-package is installed.

### Negative
- Two `pyproject.toml`s and a `src/`+`tests/` duplication in-repo — a temporary
  deviation from the one-tree guideline, to be removed on extraction.
- `just ci` does NOT run the bridge; contributors must run `just docling-ci`
  (or `just ci-all`). Documented in the handover.

### Neutral
- The bridge versions independently (starts at its own `0.0.1`); the core
  package version is unchanged by its addition.

## Extraction trigger

Extract `packages/tablecodec-docling/` to its own repository
(`tablecodec-docling`) before publishing it to PyPI — the same gate ADR 0001
sets for the conformance suite.
