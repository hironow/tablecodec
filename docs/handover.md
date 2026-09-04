# Handover

**Last updated:** 2026-09-04 13:30 (JST)
**Updated by:** Claude Code session (delegated by hironow)

## Current State

`tablecodec` is feature-complete against `docs/spec.md` and **live on PyPI at
0.0.19**; the in-repo `tablecodec-docling` bridge carries its own `0.0.2`.
Shipped: the IR + invariants I-01..I-07, validation profiles, the codec
registry with all nine core codecs, streaming I/O, static loss analysis, the
`[teds]` metric, the `[cli]` click app, and the in-repo conformance corpus. The
core keeps **zero third-party runtime dependencies**, enforced by
`.semgrep/rules/core-deps/`. Since the release the only movement on `main` has
been tooling (prek builtin hooks, markdownlint, `docs/decision-queue.md`) and
Dependabot bumps; the last commit is `784611c` (2026-08-29). CI, Benchmark and
the first CodeQL scan are all green on that commit. Roadmap and open contract
questions live in `docs/intent.md` §8; decisions in `docs/adr/`.

## In Progress

No code work is active. Two operational items are open on the GitHub side:

- **CodeQL default setup was enabled today (2026-09-04)**: languages `actions`
  and `python`, default query suite, remote threat model, weekly schedule. The
  first scan finished green with **0 alerts**. It runs from GitHub's default
  setup, so there is deliberately **no CodeQL workflow file** in the repo.
- **The Dependabot `uv` updater is broken** and has been since late July (see
  Known Risks). It is the one thing standing between the repo and a clean
  security-alert board.

## Next Actions

1. **Move the `exclude-newer` cutoff and relock.** `[tool.uv] exclude-newer` in
   `pyproject.toml` is `2026-07-22T00:00:00Z`; bump it to a current date, run
   `uv lock`, and land one consolidated relock PR (the pattern hironow used in
   #26). This single change unblocks the updater *and* pulls in the aiohttp
   security fix. Verify with `just ci` and `just docling-ci` before pushing.
2. **Correct the stale claims in `CLAUDE.md`.** Its "Versioning & release"
   section still says there is no public PyPI release yet and that
   `release.yaml` is inert; its codec recipe still tells you to bump a version
   literal in `src/tablecodec/__init__.py`, which no longer exists
   (`__version__` is derived from installed metadata). Docs-only change.
3. **Consider a Dependabot entry for `packages/tablecodec-docling`** so the
   bridge gets routine bumps, not just security ones. Worth a line in
   `docs/decision-queue.md` if it is not an obvious yes.
4. Beyond that, pick work from `docs/intent.md` §8: extract the docling bridge
   and the conformance suite, populate image dims in the `pubtables-1m` codec,
   and settle OQ-1..OQ-4.

## Known Risks / Blockers

- **The `exclude-newer` cutoff is blocking a security fix.** Three open
  Dependabot alerts on `aiohttp` (one high, two medium) are fixed in **3.14.3**,
  which was published 2026-07-23 — one day after the cutoff. aiohttp is not in
  the published wheel: it reaches `uv.lock` through `fsspec` under `datasets`,
  so it only affects the opt-in `[hf]` extra used by the local e2e script.
- **The same cutoff breaks every `uv` Dependabot run.** The updater last
  succeeded on 2026-07-22 and has failed on every run since, including the six
  security-update attempts on 2026-08-05 that would have produced the aiohttp
  PR. The latest failure reports six "No solution found" resolution errors
  (hypothesis, ruff, lxml, datasets, coverage, pytest-benchmark), each with a
  hint naming `exclude-newer`. No routine Python bump can land until it moves.
- **`packages/tablecodec-docling` gets no routine Dependabot bumps.**
  `.github/dependabot.yaml` configures only `/` for the `uv` ecosystem. The
  bumps that landed there were *security* updates, which need no config entry.
- **Conformance corpus and the docling bridge are still in-repo** (ADR 0001 and
  0013). Both must be extracted before v1.0.

## Context the Next Actor Needs

- **`sha_pinning_required` is enabled for Actions.** A workflow that references
  an action by tag is rejected at startup and shows as a ~2s `startup_failure`
  with zero steps. Pin every action to a full commit SHA.
- **`main` has no branch ruleset.** The only ruleset protects `v*` tags
  (creation, update, deletion; admin bypass). Direct pushes to `main` are
  technically possible — use pull requests anyway.
- **Issues are disabled on this repo.** Anything needing a human decision goes
  into `docs/decision-queue.md`, not an issue tracker.
- **Releases are tag-driven**: push `main`, then push `vX.Y.Z`. The `release`
  Environment requires hironow's review before the publish job runs, and
  publishing is OIDC trusted publishing with PEP 740 attestations plus a
  separate SLSA build provenance (ADR 0014). The steady-state runbook is the
  gitignored `private/PYPI_RELEASE_STEPS.md` §C.
- **The zero-dep core is sacred.** Only `cli.py` and `teds.py` may import
  third-party packages, and neither is imported by `tablecodec/__init__`.
  Adding a core module means adding its path to the `paths.include` list of
  `.semgrep/rules/core-deps/tablecodec-no-third-party-imports-in-core.yaml`.
- **Monorepo layout (ADR 0013).** The bridge is its own uv project, so
  docling-core lands in the sub-package `.venv` only. There is exactly one
  justfile, at the repo root; it drives the bridge via `docling-*` recipes.
- **A local agent security hook hard-blocks any edit containing the substring
  `eval`**, which trips the `ast.literal_eval` in `scripts/e2e_hf_check.py`.
  Surface it and ask rather than obfuscating around it.
- **`scripts/` is ruff-linted but not type-checked**; `just type` covers `src/`
  and `tests/` only, because the e2e script imports `datasets`.
- The e2e harness is network-heavy and deliberately local-only, never in CI.
  README's "End-to-end check" section and ADRs 0003, 0004 and 0006 cover the
  data sources and caveats.
- `input/`, `output/` and `private/` are gitignored local-only trees.

## Relevant Files and Commands

- `docs/spec.md` — the contract and source of truth. `docs/intent.md` §8 — the
  single home for all roadmap work. `docs/adr/` — why things are the way they
  are. `CLAUDE.md` — project rules, the add-a-codec recipe, and the gotchas.
- `pyproject.toml` `[tool.uv] exclude-newer` — the cutoff behind both
  Dependabot risks above.
- `.github/workflows/{ci,release,benchmark}.yaml` and
  `.github/dependabot.yaml` — all CI/CD and dependency configuration.
- `just ci` — the full core gate: lint, pyright strict, pytest, semgrep,
  semgrep-test, docs-check. `just check` is an alias.
- `just docling-ci` — the bridge gate. `just ci-all` — both packages.
- `just docs` — regenerate the codec and loss tables; required after any codec
  name or `lossy_*` change, and enforced by `docs-check`.
- `just e2e-selftest` — offline smoke test of the e2e adapters.
