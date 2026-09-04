# Releasing

How `tablecodec` reaches PyPI. Rationale and the full threat model:
[ADR 0014](adr/0014-release-via-oidc-trusted-publishing.md).

## Two facts that shape everything

- **No PyPI token exists for this project, and none ever did.** PyPI's *pending
  publisher* covers even the first upload, so there is nothing to create and
  nothing to leak. The only credential is a per-job GitHub OIDC id-token.
- **The trusted-publisher binding is matched by string, not by identity.** It
  names the repository `hironow/tablecodec`, the workflow *filename*
  `release.yaml`, and the environment `release`. Renaming the workflow file or
  the environment breaks publishing with an OIDC failure and nothing else.

## Repository rules (GitHub)

- `v*` tags cannot be created, moved, or deleted except by admins (ruleset
  "Protect release tags (v*)"). This is what restricts who can start a release.
  The environment gate below cannot: it only pauses a run that a tag push has
  already triggered.
- `main` is protected by the `protect` ruleset: pull requests required,
  squash-only merges, linear history, resolved review threads, and **no bypass
  actors** — admins included. Approvals themselves are not required.
- **Eleven status checks are required**, strictly, so a branch must also be up
  to date before it merges: `pytest-benchmark`, `pip install -e .`,
  `semgrep (rules + core scan)`, `test (py3.11 / ubuntu-latest)`,
  `test (py3.12 / ubuntu-latest)`, `test (py3.13 / ubuntu-latest)`,
  `test (py3.14 / ubuntu-latest)`, `test (py3.11 / macos-latest)`,
  `test (py3.12 / macos-latest)`, `test (py3.13 / macos-latest)` and
  `test (py3.14 / macos-latest)`. That is every job `ci.yaml` and
  `benchmark.yaml` run on a pull request. CodeQL's `Analyze` jobs are not among
  them: they come from GitHub's default setup, not from a workflow here.
- **Renaming a job blocks every merge.** Checks are matched by name, so a
  renamed job or a dropped matrix leg reports under a name the ruleset never
  sees, and the configured name waits forever as "Expected — Waiting for status
  to be reported". No bypass actor exists. Update the ruleset in the same change
  that touches a job name or the matrix.
- Publishing waits for a reviewer in the `release` environment (required
  reviewer `hironow`, self-review permitted). Its deployment branch policy
  admits exactly one ref pattern: the tag `v*`.
- Actions are restricted to selected actions with **`sha_pinning_required`**. A
  workflow naming an action by tag is rejected at startup and shows as a ~2s
  `startup_failure` with zero steps. Pin full SHAs.
- The default `GITHUB_TOKEN` is read-only and cannot approve pull requests.
- Secret scanning, push protection, Dependabot security updates, private
  vulnerability reporting, and CodeQL default setup are on; none gate this path.

## Versioning

- The project stays in **0.0.x**; one codec is roughly one patch bump. The
  public surface freezes at 1.0 (SPEC §14).
- `pyproject.toml` is the **single human-edited version source**; `__version__`
  is derived from the installed metadata, falling back to `0.0.0+unknown` in a
  source checkout. Do not add a literal back.
- The in-repo `tablecodec-docling` bridge carries its own version and is not
  published from this workflow.
- `CHANGELOG.md` follows Keep a Changelog: promote `[Unreleased]` to `[X.Y.Z]`
  and update the compare links at the bottom of the file in the same change.

## Every release (CI)

Pushing a `v*` tag drives `.github/workflows/release.yaml`. Four jobs run in a
line — **build → provenance → publish → github-release** — so an upload is only
ever attempted on fully built, attested artifacts. Every job is guarded by
`github.repository == 'hironow/tablecodec'`, and the concurrency group never
cancels a run mid-publish.

1. **build** — checkout, `astral-sh/setup-uv` pinned to uv 0.11.17, then Takumi
   Guard before any resolution. `uv python install 3.11`, then `uv build`. The
   next step compares the tag against the version in the built wheel filename
   and fails unless they match. `dist/` is uploaded as one artifact that the
   three downstream jobs each download.
2. **provenance** — `actions/attest-build-provenance` over `dist/*`. This is a
   GitHub SLSA build provenance, a **separate** artifact from the PyPI
   attestation, checked with `gh attestation verify` and never sent to PyPI.
3. **publish** — runs in the `release` environment, so it waits for the
   reviewer's click; nothing is uploaded before that. It holds `id-token: write`
   and nothing else. `pypa/gh-action-pypi-publish` uploads the sdist and wheel
   over trusted publishing and emits PEP 740 attestations by itself.
   `skip-existing` makes a partial-failure re-run safe, since PyPI never permits
   overwriting a file that already exists.
4. **github-release** — `gh release create` with the distributions attached.
   The only job with `contents: write`.

`benchmark.yaml` is **not on this path**. It runs pytest-benchmark on pushes and
pull requests to `main` and uploads a JSON artifact. It gates nothing.

### Installs route through Takumi Guard

Everything that resolves a Python dependency uses one screened index,
`https://pypi.flatt.tech/simple/` — a proxy that blocks known-malicious packages
before they execute. It is declared in three places, and each must match
`registry = "..."` in `uv.lock` character for character:

- `pyproject.toml` — `[[tool.uv.index]]` with `default = true`. A local
  `uv lock` or `just deps-upgrade` therefore records the screened registry with
  no environment variable set; forgetting one is no longer a way to corrupt the
  lock.
- The workflows — `flatt-security/setup-takumi-guard-pypi`, blocking-only mode,
  sets `UV_INDEX_URL` and `PIP_INDEX_URL` for the CI test job, the benchmark
  job, and the release build job. Same URL, so it agrees with `pyproject.toml`
  rather than overriding it.
- `.github/dependabot.yaml` — a `python-index` registry with `replaces-base`.
  Dependabot reaches no registry it has not been given, so without this it
  resolves against pypi.org, rewrites every registry line in `uv.lock`, and
  `uv sync --locked` rejects the result.

Consumers are unaffected: `pip install tablecodec` reaches PyPI directly, and
the sdist ships no lockfile.

## First release / bootstrap

Already done; recorded in case the repository is recreated. One-time web-UI
setup, not automatable from CI:

1. On PyPI, register a **pending publisher** carrying the binding named above.
2. On GitHub, create the `release` environment with a required reviewer and a
   deployment branch policy limited to the `v*` tag pattern.
3. On GitHub, create the ruleset restricting creation, update, and deletion of
   `v*` tags.
4. Push the first `vX.Y.Z` tag, which needs an admin bypass (step 3).

**Unverified:** `private/PYPI_RELEASE_STEPS.md`, the maintainer's own runbook,
is gitignored and was not read. Everything here comes from the workflow and the
live settings; the workflow wins on any disagreement.

## Verified on 0.0.19 (released 2026-06-07, re-checked 2026-09-04)

- PyPI carries 0.0.18 and 0.0.19, each as an sdist plus a wheel.
- **PEP 740 attestations** are on PyPI for both versions (integrity endpoint
  200), each naming publisher GitHub, `hironow/tablecodec`, `release.yaml`,
  environment `release`.
- **SLSA build provenance** verifies: `gh attestation verify` on the 0.0.19
  wheel succeeds, reporting `https://slsa.dev/provenance/v1` over both wheel and
  sdist, built from `release.yaml` at `refs/tags/v0.0.19`.
- **Unverified:** ADR 0014 lists a zizmor-style workflow lint among its coverage
  claims. No such check exists in the repository today, so that assertion is
  currently manual.

## Local checks before any release

- `just ci` green (alias `just check`); the prek pre-push hook runs it, and
  `CLAUDE.md` lists what it covers.
- `just ci-all` if anything under `packages/` changed.
- `just docs` after any codec name or `lossy_*` change, so the generated tables
  match. `docs-check` fails the build otherwise.
- `uv lock` clean and committed, so CI's `uv sync --locked` cannot fail after the
  tag is already pushed.
- `CHANGELOG.md` promoted and its compare links updated.

### The `exclude-newer` cutoff

`[tool.uv] exclude-newer` is `"7 days"`: resolution only sees distributions
public for a week, so a compromised-then-yanked release is not pulled in on day
zero. uv records the span in `uv.lock` (`exclude-newer-span = "P7D"`), not a
date. The reasoning, and what it supersedes in ADR 0014, is
[ADR 0015](adr/0015-exclude-newer-is-a-relative-window.md).

The window moving does not disturb `uv sync --locked`: the cutoff is an upper
bound that only travels forward, so a version already in the lock cannot fall
outside a later window. What the relative form gives up is time-independent
re-derivation — locking from scratch on two different days can pick different
versions. The lock is the reproducibility artifact.

**`just deps-upgrade` moves dependencies forward**, through the screened index
and verified with `uv sync --locked`. `--upgrade` forces the fresh resolution
that recomputes the window; a plain `uv lock` keeps existing pins.

A fix newer than the window needs `exclude-newer-package = { some-package =
false }`, exempting one package rather than widening it for everything.
