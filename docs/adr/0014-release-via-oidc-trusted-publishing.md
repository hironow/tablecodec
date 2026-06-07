# 0014. Release via OIDC Trusted Publishing; no long-lived publish tokens

**Date:** 2026-06-07
**Status:** Accepted

## Context

tablecodec is ready for its first PyPI release. The release workflow
(`.github/workflows/release.yaml`) already published via PyPI Trusted Publishing
(OIDC), but the surrounding supply-chain posture lagged the 2026 baseline:

- GitHub Actions were pinned to **mutable tags** (`@v4`, `@release/v1`, ...). The
  tj-actions/changed-files compromise (CVE-2025-30066, 2025-03) showed how an
  attacker who repoints a tag at a malicious commit reaches every workflow that
  references the tag — 23,000+ repositories leaked CI secrets. Only a full
  commit SHA is immutable.
- No build provenance, no dependency-update cooldown, no install-time package
  screening, no security policy, and no record of the release decision itself.

The sibling repo `hironow/firepact` already runs the 2026-state-of-the-art
release hardening (full-SHA pins, SLSA build provenance, Dependabot cooldown,
Takumi Guard screened installs, an absolute `exclude-newer` lock cutoff,
tokenless publishing). This ADR adopts that posture for tablecodec, adapted to a
pure-Python, PyPI-only package (no Rust/crates.io, no maturin).

A long-lived publish token stored in a developer keychain or a CI secret is the
single highest supply-chain risk for a published package (token theft →
unauthorized publish). PyPI has **Trusted Publishing** (OIDC, GA) and
**PEP 740 digital attestations**; `pypa/gh-action-pypi-publish` v1.11.0+
auto-produces and uploads attestations when publishing via Trusted Publishing,
and PyPI has **pending publishers** so even the first release is tokenless.

This does not touch the **zero-dependency runtime core** invariant (SPEC §13):
every control here lives in CI / repository metadata, never in the published
package's runtime dependencies, which stay empty.

## Decision

Publishing is done **from GitHub Actions via OIDC Trusted Publishing, with no
long-lived publish token in the repo, CI secrets, or the maintainer runbook.**

- A `v*` tag push drives `.github/workflows/release.yaml`. Publish is gated
  **both** by a protected GitHub Environment (`release`) **and** by a Ruleset that
  restricts who may create `v*` tags — the Environment alone only pauses for a
  reviewer; it does not stop a write-holder from pushing a `v*` tag, so
  tag-creation must be restricted at the ref level too.
- The pipeline is linearized **build → provenance → publish → github-release**,
  so a publish is only attempted on fully-built, attested artifacts. The four
  jobs share a single `dist` artifact (upload in `build`, download in each
  consumer).
- **PyPI**: `pypa/gh-action-pypi-publish` (pinned to the v1.14.0 SHA) uploads
  the sdist + wheel via Trusted Publishing, which emits **PEP 740 publish
  attestations on PyPI automatically**. `skip-existing: true` makes a
  partial-failure re-run idempotent (PyPI never allows overwriting a file).
- Separately and additively, `actions/attest-build-provenance` produces a
  **GitHub artifact attestation (SLSA build provenance)** for the
  distributions. This is a distinct artifact verified with
  `gh attestation verify`; it is **not** the PyPI PEP 740 attestation and is not
  uploaded to PyPI. The two are kept separate so runbook verification does not
  conflate them.
- Each job requests the **minimum permissions** (`id-token: write` for the OIDC
  exchange at job level; `attestations: write` only on the provenance job;
  `contents: read` otherwise; `contents: write` only on the github-release job).
  The default `GITHUB_TOKEN` is read-only.
- Every action is pinned to a **full commit SHA**, with **Dependabot** bumping
  the pins (and the uv extras) behind a **7-day cooldown**.
- CI installs route through **Takumi Guard** (`flatt-security/setup-takumi-guard-pypi`,
  blocking-only mode — no account, no `id-token`), which points
  `UV_INDEX_URL`/`PIP_INDEX_URL` at a screening proxy that blocks
  known-malicious packages before they execute. The release `build` job is
  screened too, so even the build-backend (hatchling) is resolved through the
  screened registry. `uv.lock` is resolved through the same screened registry.
- `pyproject.toml` pins `[tool.uv] exclude-newer` to an **absolute date** (a
  relative span makes `uv sync --locked` non-deterministic, astral-sh/uv#18775);
  CI's `uv sync --locked` then guarantees reproducible resolution.

Because PyPI has pending publishers, **no token is ever created** for tablecodec
— unlike registries without one, there is no bootstrap-token step.

## Enforcement inventory

The invariant: **no tablecodec release reaches PyPI except through an OIDC
Trusted Publishing flow that carries build provenance; no long-lived publish
token exists that could bypass it.**

### Entry points

- sdist/wheel upload → PyPI (`release.yaml` `publish` job via
  `gh-action-pypi-publish`).
- The maintainer runbook (`private/PYPI_RELEASE_STEPS.md`) — a human-run entry
  point describing the one-time bootstrap and steady-state release.

### Persistent / carried data needed at each enforcement point

- A GitHub OIDC id-token (`permissions: id-token: write`) on the `publish` job
  (and `provenance` for the attestation).
- The PyPI **pending/trusted-publisher binding**, which must match the workflow
  **exactly**: owner/repo `hironow/tablecodec`, the workflow **filename**
  `release.yaml`, and the environment `release`. A one-character mismatch fails the
  OIDC publish.
- The `release` GitHub Environment name, matched on both the workflow and the
  PyPI binding; plus a Ruleset restricting `v*` tag creation.
- Two distinct, separately-verified attestations: the **PyPI PEP 740 publish
  attestation** (on PyPI, auto-emitted) and the **GitHub SLSA build provenance**
  (artifact attestation, verified via `gh attestation verify`).

### Bypass candidates ("where can this go wrong?")

- A developer running `twine upload` / `uv publish` locally with a personal
  token. Closed by: **no PyPI token is ever issued**; the runbook documents no
  local publish path.
- A leaked `PYPI_TOKEN` / `UV_PUBLISH_TOKEN` repo or org secret. Closed by:
  **no such secret is ever created** (pending publisher needs none).
- A release workflow with over-broad permissions or run from an unprotected ref.
  Closed by: explicit minimal `permissions:`, read-only default `GITHUB_TOKEN`,
  the `release` Environment (reviewer gate), **and a Ruleset restricting `v*` tag
  creation** — the Environment only pauses for a reviewer, it does not stop the
  tag push that triggers the run.
- A swapped or compromised third-party action. Closed by: **full-SHA pinning**
  of every action + Dependabot SHA bumps behind a cooldown.
- The **release build resolving build dependencies from an unscreened index**.
  Closed by: the `build` job routes through Takumi Guard before `uv build`, so
  the build-backend is fetched from the screened registry.

### Tests proving coverage

A release workflow cannot be exercised by a unit test without actually
publishing, so enforcement is verified structurally rather than by a RED test:

- PyPI **trusted-publisher enforcement** is the fail-closed control: with no
  token issued, a bypass publish has no credential.
- A repo check (zizmor / a small workflow lint) asserts each publish job
  declares only the minimal permissions and runs under the `release` Environment.
- `git grep -nE '_TOKEN' .github/` asserts no `*_TOKEN` publish secret is
  referenced in any workflow.
- Provenance is verifiable post-publish: `pip download` + `gh attestation
  verify` (GitHub SLSA) and the PyPI attestation badge (PEP 740) confirm the
  carried data is present.

## Consequences

### Positive

- No long-lived publish credential to steal — the dominant package supply-chain
  risk is removed, and (unlike crates.io) PyPI's pending publisher means **no
  token is ever created**, not even a one-time bootstrap.
- Every PyPI artifact ships PEP 740 attestations and SLSA build provenance for
  free; consumers can verify where and how a distribution was built.
- Releases become reproducible CI events ("push a tag"), not a hand-run sequence
  that varies per maintainer machine.
- The zero-dependency runtime core is untouched: all hardening lives in CI /
  repo metadata.

### Negative

- A protected Environment + Ruleset + PyPI pending-publisher binding is per-repo
  setup the maintainer must do once in the GitHub / PyPI UIs (outward-facing;
  not automatable by CI or the assistant).
- **Screened-registry dependency.** Contributors, CI, and Dependabot resolve
  through `pypi.flatt.tech` (Takumi Guard). This is a development/CI dependency
  on that proxy's availability and policy; it does **not** affect consumers
  (`pip install tablecodec` hits PyPI directly, and the published sdist does not
  bundle `uv.lock`).
- **`exclude-newer` × Dependabot coupling.** The fixed absolute cutoff means a
  Dependabot uv PR cannot resolve distributions newer than the cutoff until the
  date is bumped; merging such a PR requires bumping `[tool.uv] exclude-newer`
  to that day and re-running `uv lock` in the same change.

### Neutral

- The wheel build is a single pure-Python `py3-none-any` artifact; no build
  matrix breadth is needed (orthogonal to this decision).
- The docling bridge (`packages/tablecodec-docling`, ADR 0013) and the
  conformance suite (ADR 0001) are extracted before their own publishes /
  before v1.0; the core `tablecodec` package publishes independently of both.
