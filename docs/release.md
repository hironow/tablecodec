# Releasing

How `tablecodec` reaches PyPI. Rationale and the full threat model:
[ADR 0014](adr/0014-release-via-oidc-trusted-publishing.md).

## Two facts that shape everything

- **No PyPI token exists for this project, and none ever did.** PyPI's *pending
  publisher* covers even the first upload, so there is no bootstrap token to
  create and no publish secret to leak. The only credential is a GitHub OIDC
  id-token minted per job. `git grep -nE '_TOKEN' .github/` finds exactly one
  hit, the ephemeral `github.token` used to create the GitHub Release.
- **The PyPI trusted-publisher binding is matched by string, not by identity.**
  It names the repository `hironow/tablecodec`, the workflow *filename*
  `release.yaml`, and the environment `release`. Renaming the workflow file or
  the environment breaks publishing with an OIDC failure and nothing else.

## Repository rules (GitHub)

- `v*` tags cannot be created, moved, or deleted except by admins (ruleset
  "Protect release tags (v*)", rules `creation` / `update` / `deletion`, bypass
  for the admin repository role). This is what actually restricts who can start
  a release; the environment gate below cannot, since it only pauses a run that
  a tag push has already triggered.
- **`main` has no ruleset.** Unlike the sibling repos, nothing mechanically
  requires a pull request or a green check before a commit lands on `main`. Use
  pull requests anyway.
- Publishing waits for a reviewer in the `release` environment (required
  reviewer `hironow`, self-review permitted). Its deployment branch policy
  admits exactly one ref pattern: the tag `v*`.
- Actions are restricted to selected actions with **`sha_pinning_required`
  enabled**: a workflow that names an action by tag is rejected at startup and
  the run shows as a ~2s `startup_failure` with zero steps. Pin full SHAs.
- The default `GITHUB_TOKEN` is read-only and cannot approve pull requests.
  Each release job elevates only what it needs.
- Secret scanning, push protection, Dependabot security updates, private
  vulnerability reporting, and CodeQL default setup (languages `actions` and
  `python`, weekly) are all on. None of them gate the release path.

## Versioning

- The project stays in **0.0.x**; one codec is roughly one patch bump. The
  public surface freezes at 1.0 (SPEC §14).
- `pyproject.toml` is the **single human-edited version source**.
  `src/tablecodec/__init__.py` derives `__version__` from the installed package
  metadata (`importlib.metadata.version`), falling back to `0.0.0+unknown` in a
  source checkout with nothing installed. Do not add a version literal back.
- The in-repo `tablecodec-docling` bridge (`packages/`, ADR 0013) carries its
  own version and is not published from this workflow.
- `CHANGELOG.md` follows Keep a Changelog. Promote `[Unreleased]` to `[X.Y.Z]`
  and update the compare links at the bottom of the file in the same change.
- Bump `[tool.uv] exclude-newer` and re-run `uv lock` alongside the version
  bump — see the cutoff section below.

## Every release (CI)

Pushing a `v*` tag drives `.github/workflows/release.yaml`. Four jobs run in a
line — **build → provenance → publish → github-release** — so an upload is only
ever attempted on fully built, attested artifacts. Every job is guarded by
`github.repository == 'hironow/tablecodec'` so a fork cannot publish, and the
concurrency group never cancels a run mid-publish.

1. **build** — checkout, `astral-sh/setup-uv` pinned to uv 0.11.17, then
   `flatt-security/setup-takumi-guard-pypi` *before* any resolution, so even
   hatchling comes from the screened registry. `uv python install 3.11`, then
   `uv build`. The next step strips `refs/tags/v` from `github.ref`, reads the
   version back out of the built wheel filename, and fails unless the two are
   equal. The `dist/` directory is uploaded as one artifact that the three
   downstream jobs each download.
2. **provenance** — `actions/attest-build-provenance` over `dist/*`, with
   `id-token: write` and `attestations: write`. This produces a GitHub SLSA
   build provenance, a **separate** artifact from the PyPI attestation, checked
   with `gh attestation verify` and never uploaded to PyPI.
3. **publish** — runs in the `release` environment, so it waits for the
   reviewer's click; nothing is uploaded before that. It holds `id-token: write`
   and nothing else. `pypa/gh-action-pypi-publish` uploads the sdist and wheel
   over trusted publishing and emits PEP 740 attestations by itself.
   `skip-existing: true` makes a partial-failure re-run safe, since PyPI never
   permits overwriting a file that already exists.
4. **github-release** — `gh release create "$tag" --title "$tag"
   --notes "See CHANGELOG.md for details."` with the built distributions
   attached. This is the only job with `contents: write`.

`benchmark.yaml` is **not part of this path**. It runs pytest-benchmark on
pushes and pull requests to `main` and uploads `benchmark-results.json` for 30
days. It gates nothing, and a release never waits on it.

## The `exclude-newer` cutoff, and its trap

`[tool.uv] exclude-newer` pins resolution to distributions uploaded before an
absolute date (currently `2026-07-22T00:00:00Z`). It must stay an absolute date;
a relative span makes `uv sync --locked` non-deterministic (astral-sh/uv#18775),
and CI's `uv sync --locked` is what guarantees the lock matches `pyproject.toml`
before a tag is ever pushed.

The trap: **a fix published after the cutoff cannot be resolved at all.** When
that fix is what Dependabot is trying to apply, the updater fails outright
rather than opening a smaller pull request, and it stays failing for every
subsequent run — including security updates. Merging any Dependabot `uv` pull
request therefore means bumping the cutoff to that day's date and re-running
`uv lock` in the same change. `docs/handover.md` records whether the cutoff is
currently blocking anything.

## Installs route through Takumi Guard

`flatt-security/setup-takumi-guard-pypi` runs in blocking-only mode (no account,
no `id-token`) in the CI test job, the benchmark job, and the release build job.
It points `UV_INDEX_URL` and `PIP_INDEX_URL` at a screening proxy that blocks
known-malicious packages before they execute, and `uv.lock` records that
registry as its source. Consumers are unaffected: `pip install tablecodec` goes
to PyPI directly, and the sdist does not ship `uv.lock`.

## First release / bootstrap

Already done, and recorded here in case the repository is ever recreated. All
of it is one-time, outward-facing setup in the GitHub and PyPI web interfaces,
not automatable from CI:

1. On PyPI, register a **pending publisher** for the project name, bound to
   `hironow/tablecodec`, workflow filename `release.yaml`, environment
   `release`. No token is created at any point.
2. On GitHub, create the `release` environment with a required reviewer and a
   deployment branch policy limited to the `v*` tag pattern.
3. On GitHub, create the ruleset restricting creation, update, and deletion of
   `v*` tags.
4. Push the first `vX.Y.Z` tag. An admin bypass is needed for that push, since
   the ruleset restricts tag creation.

The maintainer's own runbook lives in the gitignored
`private/PYPI_RELEASE_STEPS.md`; its steady-state section is the day-to-day
sequence. **Unverified:** that file was not read while writing this document,
so everything above is drawn from the workflow and the live repository settings
instead. If the two disagree, the workflow is the truth.

## Verified on 0.0.19 (released 2026-06-07, re-checked 2026-09-04)

- PyPI carries 0.0.18 and 0.0.19, each as sdist plus a `py3-none-any` wheel,
  with `License-Expression: MIT` and `requires-python >=3.11`.
- **PEP 740 attestations** are present on PyPI for both versions
  (`https://pypi.org/integrity/tablecodec/<version>/<file>/provenance` returns
  200). Each names publisher kind GitHub, repository `hironow/tablecodec`,
  workflow `release.yaml`, environment `release`.
- **SLSA build provenance** verifies: `gh attestation verify
  tablecodec-0.0.19-py3-none-any.whl --repo hironow/tablecodec` succeeds,
  reporting predicate type `https://slsa.dev/provenance/v1` over both the wheel
  and the sdist, built by `.github/workflows/release.yaml` at
  `refs/tags/v0.0.19`.
- Both GitHub Releases exist with the distributions attached.
- **Unverified:** ADR 0014 lists a zizmor-style workflow lint among its coverage
  claims, asserting that each publish job declares minimal permissions and runs
  under the `release` environment. No such check exists in the repository today;
  that assertion is currently manual.

## Local checks before any release

- `just ci` green (alias: `just check`) — ruff lint and format, markdownlint,
  pyright strict, pytest, semgrep scan, semgrep rule tests, and `docs-check`.
  The prek pre-push hook runs it.
- `just ci-all` if anything under `packages/` changed; `just docling-ci` covers
  the bridge alone.
- `just docs` after any codec name or `lossy_*` change, so the generated tables
  match. `docs-check` fails the build otherwise.
- `uv lock` clean and committed, so CI's `uv sync --locked` cannot fail after
  the tag is already pushed. Bump `exclude-newer` in the same commit.
- `CHANGELOG.md` promoted and its compare links updated.
- Benchmarks are excluded from `just ci` by a pytest marker; run `just bench`
  by hand when a change could plausibly affect throughput.
