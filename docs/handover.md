# Handover

**Last updated:** 2026-05-28 13:40 (JST)
**Updated by:** Claude (Opus 4.7, 1M context)

## Current State

M0 → M8 implemented end-to-end on `main`, with M8 (release) prepared up
to — but deliberately stopping short of — the actual PyPI publish. The
library is feature-complete against `docs/spec.md` for the v0.1.0
surface: IR + invariants + profiles + codec registry + three codecs
(pubtabnet-1.0.0, pubtabnet-2.0.0, otsl-1.0.0) + streaming I/O + static
loss analysis + click-based CLI + an in-repo conformance suite. Every
milestone is its own logical commit chain following Kent Beck TDD
(Red → Green → Refactor) and Conventional Commits; one commit ≈ one TDD
step.

- 163 tests pass locally (`just ci` green); +2 benchmark tests deselected.
- pyright strict, ruff, ruff-format, semgrep all clean.
- coverage 100% on `ir.py`, `_invariants.py`, `validate.py`; codec /
  cli modules in the 80–100% range.
- `docs/format_support.md` and `docs/loss_matrix.md` are
  auto-regenerated and CI-gated via `just docs-check`.
- GitHub Actions CI matrix: Python 3.11/3.12/3.13 × Ubuntu/macOS,
  plus a separate semgrep job and a pip-install-check job that proves
  the core still installs with zero third-party dependencies.
- Version is `0.1.0`; CHANGELOG has a `[0.1.0] - 2026-05-28` section.
- `uv build` verified locally: sdist + wheel build, wheel installs into
  a clean venv with an empty `Requires`, `[cli]` extra wires the
  `tablecodec` console script.

## In Progress

Nothing in active development. The PyPI publish is intentionally **on
hold** (maintainer decision): the human-side Trusted Publishing setup is
deferred. The release workflow is committed and will fire on a `v*` tag,
but its publish job cannot authenticate until PyPI is configured.

## Next Actions

The only remaining work is the deferred PyPI publish, which needs
out-of-band setup. The full procedure is written up in
**`private/PYPI_RELEASE_STEPS.md`** (gitignored, local-only).

1. When ready, follow `private/PYPI_RELEASE_STEPS.md`:
   register Trusted Publishing on PyPI (owner `hironow`, repo
   `tablecodec`, workflow `release.yaml`, environment `pypi`),
   optionally test on TestPyPI, then `git tag v0.1.0 && git push origin
   v0.1.0` to trigger `.github/workflows/release.yaml`.
2. Post-release: verify `pip install tablecodec` / `[cli]`, confirm the
   PyPI page renders the README, set the GitHub "About" blurb + SPEC
   link.
3. (Optional) Set up GitHub Discussions / issue templates per intent.md
   M8 acceptance criteria.

## Known Risks / Blockers

- **Conformance is in-repo, not vendor-neutral yet**: M7 was bootstrapped
  inside `conformance/` under ADR 0001 as a temporary deviation from
  SPEC §11. Before v1.0 it must be extracted to a separate MIT repo;
  a superseding ADR should record that move and flip ADR 0001 to
  "Superseded".
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
- `conformance/` — in-repo conformance corpus (INDEX.json + schema +
  samples + hand-authored expectations); see `docs/adr/0001-*.md`.
- `tests/test_conformance.py` — runs the conformance suite.
- `.github/workflows/release.yaml` — tag-triggered build + PyPI publish
  (OIDC) + GitHub Release. Inert until PyPI Trusted Publishing is set up.
- `private/PYPI_RELEASE_STEPS.md` — gitignored, local-only; the deferred
  human-side PyPI release procedure.
- `tests/strategies.py` — hypothesis strategies (intent.md M1 names).
- `scripts/gen_format_support.py`, `scripts/gen_loss_matrix.py` — doc
  regenerators wired into `just docs` / `just docs-check`.
- `just ci` — full pre-commit gate (lint + type + test + semgrep + docs).
- `just bench` — pytest-benchmark micro-benchmarks (deselected from
  default test run).
- `gh run list --workflow=ci.yaml --limit 1` — quickest way to check
  the matrix status from the CLI.
