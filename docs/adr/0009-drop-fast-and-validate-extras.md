# 0009. Drop the `fast` (orjson) and `validate` (pydantic) extras

**Date:** 2026-05-29
**Status:** Accepted

## Context

SPEC §13 declared four optional extras: `teds` (apted/lxml), `cli` (click),
`fast` (orjson — "faster JSONL parsing") and `validate` (pydantic —
"optional stricter type validation"). A conformance audit (2026-05-29)
found `fast` and `validate` were **declared in `pyproject.toml` but wired
nowhere** in `src/`.

Trying to wire them surfaces a hard architectural conflict:

- The work each would accelerate/strengthen happens in the **core**:
  JSONL parsing and `TableSample` construction live in the codecs
  (`codecs/*.py`), and validation in `_invariants.py` / `validate.py`.
- The **zero-dependency core** invariant (SPEC §13) — enforced by
  `semgrep.yaml`'s `tablecodec-no-third-party-imports-in-core`, whose
  forbidden list explicitly includes `orjson` and `pydantic` — bans any
  third-party import in those modules.

So `import orjson` / `import pydantic` cannot appear where they would be
used. The only core-external modules are `cli.py` (and the local-only
`scripts/`), and JSON parsing does not happen there. Shipping an extra
that installs a package nothing can import is misleading.

`teds` does not have this problem: TEDS is a *separate, optional feature*
(table-similarity scoring) that lives in its own core-external module, so
`apted`/`lxml` are importable there. It remains (implementation is
roadmap, intent.md §8).

## Decision

Remove the `fast` and `validate` extras from `pyproject.toml` (and from
`[all]`), and from the SPEC §13 dependency table. Keep `teds`, `cli`,
`hf`, `dev`. A `pip install "tablecodec[fast]"` / `[validate]` now errors
(intended) rather than installing a no-op dependency.

If a future need arises:

- Faster parsing would require an architecture where parsing is delegated
  to a swappable, core-external component — a larger design change, not a
  drop-in extra.
- Stricter input validation already has a home: the layered validation
  profiles (SPEC §8), which are stdlib-only.

## Consequences

### Positive

- The advertised install surface is honest: every remaining extra wires a
  real, importable feature.
- Removes a latent contradiction between SPEC §13's extras list and SPEC
  §13's zero-dependency-core rule.

### Negative

- A (hypothetical) user of `tablecodec[fast]` / `[validate]` breaks. In
  0.x this is allowed (SPEC §14); no real feature is lost because neither
  was implemented.

### Neutral

- Recorded as a `Removed` entry in the CHANGELOG and a patch bump, since
  it changes the public install surface.
