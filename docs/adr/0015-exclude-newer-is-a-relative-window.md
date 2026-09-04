# 0015. `exclude-newer` is a relative window, not an absolute date

**Date:** 2026-09-04
**Status:** Accepted

## Context

ADR 0014 pinned `[tool.uv] exclude-newer` to an absolute date so a
compromised-then-yanked release could not be pulled into `uv.lock` on day zero.
The cutoff had to be advanced by hand, and until someone did it, uv could
resolve nothing published after it.

That cost came due. The cutoff sat at `2026-07-22T00:00:00Z`, and from that day
onward **every** Dependabot `uv` run failed, including the six security-update
attempts on 2026-08-05. uv does not degrade gracefully here: when the version it
wants is past the cutoff it reports `No solution found` and opens no pull
request at all, rather than proposing a smaller bump. Three aiohttp advisories
(GHSA-cq5v-8q36-5273 high, GHSA-mfx4-hv73-q22v, GHSA-mq44-7p77-q5h7) therefore
stayed open for a month: their fix, 3.14.3, was uploaded 2026-07-23, one day
past the cutoff. Taking it required a hand-written `exclude-newer-package`
override.

ADR 0014 rejected a relative span on the grounds that it "makes `uv sync
--locked` non-deterministic (astral-sh/uv#18775)". Re-reading that issue, it
describes a different failure: an `exclude-newer` set in a host's global
`uv.toml` is baked into the lockfile, and `uv lock --check` then fails inside a
container that does not carry the same configuration. It is a
configuration-mismatch problem between environments. A window declared in
`pyproject.toml`, which every environment reads from the repository, is not that
case. The citation was a misreading.

Measured with uv 0.11.17 (the version CI pins) and uv 0.12.9, a relative window
is recorded in `uv.lock` as the span itself, not as a materialized timestamp:

```toml
[options]
exclude-newer = "0001-01-01T00:00:00Z" # This has no effect and is included for backwards compatibility when using relative exclude-newer values.
exclude-newer-span = "P7D"
```

`uv sync --locked` and `uv lock --check` still pass as time moves, because
`exclude-newer` is an upper bound that only travels forward: a version already
in the lock cannot fall outside a later window. Both uv versions write a
byte-identical block, and 0.11.17 accepts a lock written by 0.12.9.

## Decision

`[tool.uv] exclude-newer` is the relative window `"7 days"`. It matches the
7-day `cooldown` already configured for Dependabot in
`.github/dependabot.yaml`, so both halves of the supply-chain delay agree on one
number.

- The aiohttp `exclude-newer-package` override is removed. 3.14.3 sits far
  outside a seven-day window and resolves unaided.
- `just deps-upgrade` — `uv lock --upgrade` through the screened index, then
  `uv sync --locked` — is the only way dependencies move forward. A plain
  `uv lock` keeps existing pins, so changing the window alone moves nothing.
- An urgent fix newer than the window is taken one package at a time with
  `exclude-newer-package = { some-package = false }`, never by widening the
  window for everything.

This supersedes **only** the `exclude-newer` clause of ADR 0014. Every other
decision recorded there stands unchanged: OIDC trusted publishing with no
long-lived token, full-SHA action pinning, the `release` environment gate, the
`v*` tag ruleset, Takumi Guard screened installs, and the Dependabot cooldown.

## Consequences

### Positive

- Dependabot resolves on its own again. No routine bump waits on a human
  editing a date, and a security update can no longer be blocked outright by a
  stale one.
- The supply-chain delay is stated once, as a duration, and agrees with the
  Dependabot cooldown instead of drifting out of step with it.
- The per-package override returns to being an exception for an urgent fix,
  rather than the standing workaround for a cutoff nobody advanced.

### Negative

- **Re-deriving the lock from scratch is no longer time-independent.** Two
  `uv lock --upgrade` runs on different days can pick different versions. The
  lock, not the setting, remains the reproducibility artifact and CI installs
  from it with `uv sync --locked`, but a from-scratch resolution can no longer
  be reproduced from the date alone.
- Because uv stores the window as a span, reading `uv.lock` no longer tells you
  the exact cutoff instant that was in force when the lock was written.

### Neutral

- Switching the setting changed no dependency version; aiohttp stayed at
  3.14.3. Moving versions is `just deps-upgrade`, a separate deliberate act.
- The `tablecodec-docling` sub-package declares no `exclude-newer`, so it is
  unaffected.
