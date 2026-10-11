# Handover

**Last updated:** 2026-10-11 (JST)
**Updated by:** Codex

## Current State

The core is version 0.0.19 with zero third-party runtime dependencies. The
Docling bridge is version 0.0.2. Both projects resolve dependencies from official
PyPI and retain their seven-day cooldown. Application and test dependency
versions and artifact hashes are preserved. The lint groups pin Ruff and ty.

Five proxy setup steps and the Dependabot proxy registry are removed. CI and
Benchmark retain draft gates and required check names. Tag, OIDC, environment
approval, and release publication gates are unchanged.

## Validation

Local core validation passed: 349 tests, zero lint/type findings, three Semgrep
rule tests, zero source findings, and unchanged generated tables. Bridge lint,
types, and 30 tests passed. Both sdist/wheel builds and the extras-free core
install passed. Non-lint dependency versions and artifact hash sets are unchanged.

`just check` covers core lint, types, tests, Semgrep rules, and generated docs.
`just docling-ci` covers the bridge. `just build-check` builds both packages
without publishing. `just lock-check bridge-lock-check` validates both locks.

## Known Risks

The optional HF partial-stream check can hang during Python 3.14/PyArrow 24
shutdown; this was reproduced on the previous main and remains outside CI.
[Arrow #45214](https://github.com/apache/arrow/issues/45214) has upstream context.

## Next Actions

Verify PR CI, squash merge, then verify main CI and the Actions allowlist.
Preserve accepted ADRs as historical records.
