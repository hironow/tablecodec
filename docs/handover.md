# Handover

**Last updated:** 2026-05-28 14:30 (JST)
**Updated by:** Claude (Opus 4.7, 1M context)

## Current State

M0 → M6 implemented end-to-end on `main`. The library is feature-complete
against `docs/spec.md` for the v0.1.0 surface: IR + invariants +
profiles + codec registry + three codecs (pubtabnet-1.0.0,
pubtabnet-2.0.0, otsl-1.0.0) + streaming I/O + static loss analysis +
click-based CLI. Every milestone is its own logical commit chain
following Kent Beck TDD (Red → Green → Refactor) and Conventional
Commits; one commit ≈ one TDD step.

- 145 tests pass locally (`just ci` green).
- pyright strict, ruff, ruff-format, semgrep all clean.
- coverage 100% on `ir.py`, `_invariants.py`, `validate.py`; codec /
  cli modules in the 80–100% range.
- `docs/format_support.md` and `docs/loss_matrix.md` are
  auto-regenerated and CI-gated via `just docs-check`.
- GitHub Actions CI matrix: Python 3.11/3.12/3.13 × Ubuntu/macOS,
  plus a separate semgrep job and a pip-install-check job that proves
  the core still installs with zero third-party dependencies.

## In Progress

Nothing in active development. Last commit on `main`:

- `0c93a46 ci: install [cli] extra so pyright can resolve click in cli.py`
- CI for that commit was running at handover-time (see Next Actions).

## Next Actions

The remaining milestones each require a decision or out-of-band setup
from the human; nothing further can be done autonomously without it.

1. **Verify the M6 CI fix is green** on GitHub Actions
   (`gh run list --workflow=ci.yaml --limit 1`).
2. **Decide M7 scope (Conformance Suite, SPEC §11)**:
   - Where to host: personal `github.com/hironow/tablecodec-conformance`
     (intent.md default) vs. a future `tablecodec` org.
   - Whether to seed fixtures from PMC samples (license-clean per
     PubTabNet README) or only hand-crafted synthetic.
3. **Prep M8 (v0.1.0 PyPI release)**:
   - Register `tablecodec` on PyPI (or claim the existing name) and
     set up Trusted Publishing for the GitHub repo so CI can publish
     on tag push without a stored API token.
   - Bump version to `0.1.0` in `pyproject.toml` and
     `src/tablecodec/__init__.py`, promote the Unreleased CHANGELOG
     section to `[0.1.0]`, tag `v0.1.0`, push.
4. (Optional) Set up GitHub Discussions / issue templates per intent.md
   M8 acceptance criteria.

## Known Risks / Blockers

- **Pyright + click**: until M6 CI fix lands green, the CLI module
  effectively blocks the matrix. The fix in `0c93a46` adds `[cli]` to
  the CI install; if it still fails, the next thing to check is whether
  pyright on Python 3.13 needs a click stub.
- **OTSL canonical jsonl shape is bespoke**: M4 defined
  `{filename, otsl: [...], cells: [...]}` because the SPEC does not
  pin a canonical envelope. If a published OTSL corpus (e.g.
  FinTabNet_OTSL on HF) lands and uses a different envelope, the
  fixture / sniff logic will need a minor PR.
- **Semgrep deprecation warnings** were silenced via anchored paths;
  the warnings will return if Semgrepignore v2 stops accepting `/`-
  anchored entries. Re-check on every semgrep major upgrade.

## Context the Next Actor Needs

- **TDD strictness**: 1 commit = 1 step. Mixing structural and
  behavioural changes in one commit is a review-reject (intent.md §2.2).
- **Codec contract pitfalls**: codec dataclasses must be frozen with
  `slots=True`. The `Codec` Protocol declares `name`/`spec_version`/
  `media_type` as `@property` getters precisely so frozen dataclasses
  satisfy them (pyright otherwise complains about writability mismatch).
- **Registry isolation in tests**: any test that registers codecs must
  bookend with `codecs._snapshot()` / `codecs._restore(saved)`,
  otherwise it pollutes sibling tests. See `tests/codecs/test_registry.py`
  for the canonical fixture.
- **`docs-check`** lives inside `just ci`. After ANY change to a
  codec's `name` / `spec_version` / `media_type` / `lossy_*`, regenerate
  with `just docs` before committing or CI will reject.
- **`__hash__` on TableSample** intentionally excludes `extras`
  because `Mapping` is not generally hashable; `__eq__` still considers
  it. This is the only spot in the codebase where the hash/eq contract
  is loosened deliberately — do not "fix" it.
- **Serialization round-trip is verified via `copy.deepcopy`** in
  tests (exercises the same `__reduce_ex__` protocol that the stdlib
  serializer uses) rather than importing the serializer module directly
  into the test tree.

## Relevant Files and Commands

- `docs/spec.md` — source of truth (CC BY 4.0).
- `docs/intent.md` — implementation brief / milestones / Definition of Done.
- `docs/format_support.md`, `docs/loss_matrix.md` — auto-generated; do
  not hand-edit.
- `src/tablecodec/{ir,_invariants,validate,io,loss}.py` — stdlib-only core.
- `src/tablecodec/codecs/{_base,__init__,pubtabnet,otsl}.py` — codec
  layer; protocol + registry + concrete codecs.
- `src/tablecodec/cli.py` — click app, only loaded when `[cli]` extra
  is installed.
- `tests/strategies.py` — hypothesis strategies (intent.md M1 names).
- `scripts/gen_format_support.py`, `scripts/gen_loss_matrix.py` — doc
  regenerators wired into `just docs` / `just docs-check`.
- `just ci` — full pre-commit gate (lint + type + test + semgrep + docs).
- `just bench` — pytest-benchmark micro-benchmarks (deselected from
  default test run).
- `gh run list --workflow=ci.yaml --limit 1` — quickest way to check
  the matrix status from the CLI.
