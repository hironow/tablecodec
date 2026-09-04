# Handover

**Last updated:** 2026-09-04 15:04 (JST)
**Updated by:** Claude Code session 01LXPmm8VuMHBjo4Q6k7tRtq (delegated by hironow)

## Current State

`tablecodec` is feature-complete against `docs/spec.md` and **live on PyPI at
0.0.19**; the in-repo `tablecodec-docling` bridge carries its own `0.0.2`.
Shipped: the IR and invariants I-01..I-07, validation profiles, all nine core
codecs behind the registry, streaming I/O, static loss analysis, the `[teds]`
metric, the `[cli]` app, and the in-repo conformance corpus. The core keeps zero
third-party runtime dependencies. Since the release the only movement has been
tooling and Dependabot bumps. CI, Benchmark and CodeQL are green on the tip of
`main`.

**CodeQL default setup was enabled 2026-09-04**: languages `actions` and
`python`, default query suite, weekly schedule, first scan green with zero
alerts. It runs from GitHub's default setup, so there is deliberately no CodeQL
workflow file in the repo — do not add one.

## In Progress

No code work is active. The security board is clean. The `exclude-newer` cutoff
is a relative window now, which should let the **Dependabot `uv` updater**
resolve again — unproven until its next weekly run.

## Next Actions

1. **Watch the re-issued Dependabot `uv` pull requests.** The updater recovered
   on 2026-09-04 and opened five (#39-#43), but every one failed CI: Dependabot
   resolved against pypi.org and rewrote each registry line in `uv.lock`.
   Declaring the screened index in `.github/dependabot.yaml` is the fix. Once
   that lands Dependabot re-issues them; check the lock still carries
   `https://pypi.flatt.tech/simple/`.
2. **Decide whether `packages/tablecodec-docling` deserves its own Dependabot
   entry**, so the bridge gets routine bumps and not only security ones. Record
   the call in `docs/decision-queue.md`.
3. Beyond that, take work from `docs/intent.md` §8, which holds the roadmap.

## Known Risks / Blockers

- **Locking from scratch is no longer time-independent.** The relative window
  is recomputed on every fresh resolution, so `uv lock --upgrade` on two
  different days can pick different versions. The lock is the reproducibility
  artifact, and CI installs from it with `uv sync --locked`.
- **Dependabot resolves where it is told, and nowhere else.** Until the
  registry declaration lands its uv pull requests rewrite `uv.lock` to pypi.org
  and fail `uv sync --locked`; the same trap waits for any new ecosystem.
- **`packages/tablecodec-docling` gets no routine Dependabot bumps.**
  `.github/dependabot.yaml` configures only `/` for the `uv` ecosystem. The
  bumps that did land there were security updates, which need no config entry.
- **Conformance corpus and the docling bridge are still in-repo** (ADR 0001 and
  0013). Both must be extracted before v1.0.

## Context the Next Actor Needs

Project rules, the add-a-codec recipe and the hard-won gotchas live in
`CLAUDE.md`; the release flow and the repository settings behind it live in
`docs/release.md`. Read those first. What neither of them says:

- **`main` is protected by the `protect` ruleset.** Pull requests are required,
  squash-only, linear history, resolved review threads, **no bypass actors**.
  Eleven checks are required, one per pull-request job in `ci.yaml` and
  `benchmark.yaml`; rename a job and nothing merges until the ruleset matches.
- **Issues are disabled on this repo.** Anything needing a human decision goes
  into `docs/decision-queue.md`.
- **`sha_pinning_required` is on for Actions.** A workflow naming an action by
  tag is rejected at startup as a ~2s `startup_failure` with zero steps, which
  reads like a billing problem and is not one.
- **An agent security hook on hironow's machine blocks any edit containing the
  substring `eval`**, which trips the `ast.literal_eval` in
  `scripts/e2e_hf_check.py`. Surface it and ask rather than obfuscating.

## Relevant Files and Commands

- `docs/spec.md` — the contract. `docs/intent.md` §8 — the roadmap.
  `docs/release.md` — how a release reaches PyPI. `docs/adr/` — the reasoning.
- `pyproject.toml` `[tool.uv] exclude-newer` — the window; `just deps-upgrade` moves it.
- `just ci` — the full core gate (alias `just check`); `just docling-ci` the
  bridge, `just ci-all` both. `just docs` — regenerate the tables after any
  codec name or `lossy_*` change.
