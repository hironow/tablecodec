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
- **`main` has no ruleset.** Unlike the sibling repos, nothing mechanically
  requires a pull request or a green check before a commit lands. Use a pull
  request anyway.
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
4. **github-release** — `gh release create` with the built distributions
   attached. This is the only job with `contents: write`.

`benchmark.yaml` is **not on this path**. It runs pytest-benchmark on pushes and
pull requests to `main` and uploads a JSON artifact. It gates nothing.

### Installs route through Takumi Guard

`flatt-security/setup-takumi-guard-pypi` runs in blocking-only mode in the CI
test job, the benchmark job, and the release build job. It points
`UV_INDEX_URL` and `PIP_INDEX_URL` at a screening proxy that blocks
known-malicious packages before they execute, and `uv.lock` records that
registry (`https://pypi.flatt.tech/simple/`) as its source. Consumers are
unaffected: `pip install tablecodec` reaches PyPI directly, and the sdist ships
no lockfile.

## First release / bootstrap

Already done; recorded in case the repository is recreated. One-time setup in
the GitHub and PyPI web interfaces, not automatable from CI:

1. On PyPI, register a **pending publisher** carrying the binding named above.
   No token is created at any point.
2. On GitHub, create the `release` environment with a required reviewer and a
   deployment branch policy limited to the `v*` tag pattern.
3. On GitHub, create the ruleset restricting creation, update, and deletion of
   `v*` tags.
4. Push the first `vX.Y.Z` tag, which needs an admin bypass because of step 3.

**Unverified:** the maintainer's own runbook, `private/PYPI_RELEASE_STEPS.md`,
is gitignored and was not read. Everything here comes from the workflow and the
live settings; the workflow wins on any disagreement.

## Verified on 0.0.19 (released 2026-06-07, re-checked 2026-09-04)

- PyPI carries 0.0.18 and 0.0.19, each as an sdist plus a `py3-none-any` wheel.
- **PEP 740 attestations** are present on PyPI for both versions (the integrity
  endpoint returns 200), each naming publisher GitHub, repository
  `hironow/tablecodec`, workflow `release.yaml`, environment `release`.
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

`[tool.uv] exclude-newer` pins resolution to distributions uploaded before an
absolute date. It must stay absolute; a relative span makes `uv sync --locked`
non-deterministic (astral-sh/uv#18775).

The trap: **a fix published after the cutoff cannot be resolved at all.** When
that fix is what Dependabot is trying to apply, the updater fails outright
rather than opening a smaller pull request, and stays failing for every later
run — security updates included. Merging any Dependabot `uv` pull request
therefore means bumping the cutoff and re-running `uv lock` in the same change.
`just deps-refresh` does that bump, the relock and the `uv sync --locked` check
in one step, through the same screened index CI uses.
`docs/handover.md` records whether the cutoff is blocking anything right now.
