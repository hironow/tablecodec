# Handover

**Last updated:** 2026-10-11 (JST)
**Updated by:** Codex

## Current State

The core package is version 0.0.19 and retains zero third-party runtime
dependencies. The separate docling bridge is version 0.0.2.

The dependency rollup combines PRs #65, #66, #68, #69, and #70: coverage
7.16.2, hypothesis 6.168.3, fsspec 2026.6.0, multidict 6.9.1, urllib3 2.8.0,
mise-action 5.0.1, and setup-takumi-guard-pypi 1.3.0. #70 duplicates the urllib3
update in #69 and is included once. Locks retain the screened registry and
seven-day cooldown; no blanket re-resolution was performed.

CI and Benchmark skip draft PRs and resume on `ready_for_review`. Four regression
checks enforce this in the normal test suite. Core installation uses uv through
`just core-install-check`, while preserving the required status-check name.
Five redundant fixture type suppressions were removed; the existing strict type
gate now reports zero errors and warnings.

## In Progress

Branch `chore/dependency-rollup-20261011` is ready for rollup CI validation.
Local `just check` passes with 349 tests, zero lint/type findings, all three
Semgrep rule tests, zero source findings, and current generated docs.
`just cov` passes with 91% coverage. `just lock-check` and the isolated
`just core-install-check` pass.

The optional real HF streaming check validated 20 rows per PubTabNet format
(40 total) with no parse or validation failures, but timed out during process
shutdown. The identical shutdown timeout reproduces with main's original lock;
it is not introduced by the rollup. Stack sampling shows Arrow IO thread-pool
shutdown waiting for a Python read callback during interpreter finalization.
Command: `just e2e 20 --dataset apoidea/pubtabnet-html --no-shuffle --no-record`.
This optional check is not a CI gate and is not claimed as a passing E2E run.

## Next Actions

1. Verify all eleven CI/Benchmark jobs, both CodeQL language analyses, the
   CodeQL result, and AI security review on the final rollup head.
2. Squash merge that validated head and close the five superseded PRs.

## Known Risks / Blockers

- Optional HF partial-stream shutdown hangs locally on Python 3.14.5 with
  PyArrow 24.0.0, reproducing on main and the rollup. An isolated Arrow 25.0.1
  trial also timed out and was reverted. Track the baseline tool issue separately;
  the rollup preserves the original Arrow lock and harness.
  Upstream context: [Arrow #45214](https://github.com/apache/arrow/issues/45214).

- The previous bot heads had neutral CodeQL results due to missing analysis
  configurations. The fresh rollup must receive successful results.
- The docling bridge has its own lock and gate; this rollup does not modify it.
- A fresh lock resolution recomputes the relative cooldown; the committed lock
  remains the reproducibility artifact.

## Context the Next Actor Needs

- Preserve the eleven required job names in CI and Benchmark. Main requires
  PRs, squash merges, linear history, and resolved review threads.
- CodeQL uses GitHub default setup for Actions and Python; do not add a workflow.
- Issues are disabled; decisions belong in `docs/decision-queue.md`.
- mise-action 5 adds a 24-hour release age default and verifies cached binaries.
  The reviewed 5.0.1 configuration keeps the existing cache input.
- The core invariants and codec contract are in `CLAUDE.md` and `docs/spec.md`;
  future work stays in `docs/intent.md`.

## Relevant Files and Commands

- `.github/workflows/{ci,benchmark,release}.yaml` — gates and reviewed action pins.
- `tests/test_workflow_policy.py` — draft/ready regression checks.
- `just check` / `just cov` / `just lock-check` — core validation.
- `just core-install-check` — extras-free editable install and import.
- `just e2e LIMIT --dataset NAME` — targeted real HF streaming smoke check.
- `just docling-ci` / `just ci-all` — bridge / whole-monorepo gates.
