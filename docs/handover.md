# Handover

**Last updated:** 2026-09-04 14:24 (JST)
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

No code work is active. The security board is clean — the aiohttp alerts have
closed. The **Dependabot `uv` updater is still broken** for routine bumps,
described below.

## Next Actions

1. **Advance the global `exclude-newer` cutoff, as its own pull request.**
   `just deps-refresh` rewrites the cutoff to today, relocks through the
   screened index, and verifies the result. The timing is a human call, since it
   moves every dependency at once. Drop the aiohttp `exclude-newer-package`
   override in the same change: once the global cutoff passes 2026-07-24 the
   override stops protecting and starts holding aiohttp back.
2. **Decide whether `packages/tablecodec-docling` deserves its own Dependabot
   entry**, so the bridge gets routine bumps and not only security ones. Record
   the call in `docs/decision-queue.md`.
3. Beyond that, take work from `docs/intent.md` §8, which holds the roadmap.

## Known Risks / Blockers

- **The aiohttp fix rides on a per-package override.** `exclude-newer-package`
  lifts the cutoff for aiohttp alone to 2026-07-24, which is how 3.14.3 got in
  ahead of the global cutoff. It turns into a brake the moment that cutoff
  moves past the same date.
- **The cutoff still breaks every `uv` Dependabot run.** The updater last
  succeeded on 2026-07-22 and has failed on every run since, reporting "No
  solution found" for hypothesis, ruff, lxml, datasets, coverage and
  pytest-benchmark. No routine Python bump lands until the cutoff moves.
- **`packages/tablecodec-docling` gets no routine Dependabot bumps.**
  `.github/dependabot.yaml` configures only `/` for the `uv` ecosystem. The
  bumps that did land there were security updates, which need no config entry.
- **Conformance corpus and the docling bridge are still in-repo** (ADR 0001 and
  0013). Both must be extracted before v1.0.

## Context the Next Actor Needs

Project rules, the add-a-codec recipe and the hard-won gotchas live in
`CLAUDE.md`; the release flow and the repository settings behind it live in
`docs/release.md`. Read those first. What neither of them says:

- **`main` has no ruleset.** Only `v*` tags are protected, so nothing
  mechanically requires a pull request or a green check. Use one anyway.
- **Issues are disabled on this repo.** Anything needing a human decision goes
  into `docs/decision-queue.md`.
- **`sha_pinning_required` is on for Actions.** A workflow naming an action by
  tag is rejected at startup and shows as a ~2s `startup_failure` with zero
  steps, which reads like a billing problem and is not one.
- **`exclude-newer` couples the lockfile to Dependabot.** Every merged `uv` bump
  must carry a cutoff bump and a re-lock in the same change.
- **An agent security hook on hironow's machine blocks any edit containing the
  substring `eval`**, which trips the `ast.literal_eval` in
  `scripts/e2e_hf_check.py`. Surface it and ask rather than obfuscating.

## Relevant Files and Commands

- `docs/spec.md` — the contract. `docs/intent.md` §8 — the roadmap.
  `docs/release.md` — how a release reaches PyPI. `docs/adr/` — the reasoning.
- `pyproject.toml` `[tool.uv] exclude-newer` — the cutoff behind both risks above.
- `just ci` — the full core gate (alias `just check`); `just docling-ci` the
  bridge, `just ci-all` both. `just docs` — regenerate the tables after any
  codec name or `lossy_*` change.
