# 0005. Adapt docling's OTSL grid reconstruction (with attribution)

**Date:** 2026-05-28
**Status:** Accepted

## Context

`_otslgrid.py::build_anchors` reconstructs a table grid from an OTSL token
stream. It was originally written clean-room from the OTSL paper (intent.md
§6: "derive from the paper, never copy upstream reference code verbatim").

A live e2e sweep (scripts/e2e_hf_check.py) against the docling OTSL family
revealed that the clean-room reconstruction is **incorrect on complex span
topologies**: SynthTabNet_OTSL through `otsl-1.0.0` scored 48/300 (vs
300/300 for PubTabNet/FinTabNet/PubTables-1M through the same codec). An
authoritative cross-check — parsing the SAME rows via the HTML structure
path, which yields clean valid grids — proved the OTSL token streams are
well-formed and the bug is in our reconstruction:

- a diagonal `xcel` resolution + independent `max` colspan/rowspan inflated
  vertical-only spans into 2D boxes → 138 spurious I-04 overlaps;
- `xcel` in column 0 was hard-rejected → 89 false "no anchor" parse errors;
- a first attempt to repair this with a conservative anchor-centric scan
  still wrongly rejected 44/300 rows the HTML path accepts (it only counted
  `lcel`/`ucel` runs, missing spans whose edges use `xcel`).

The correct, proven algorithm is docling's `otsl_to_html`
(`docling_ibm_models/tableformer/otsl.py`): an anchor-centric scan where
`check_right` counts `lcel`/`xcel`, `check_down` counts `ucel`/`xcel`, a
`registry_2d_span` prevents double-claiming, and continuation tokens are
skipped rather than erroring.

docling-ibm-models is **MIT-licensed** (Copyright (c) 2024 International
Business Machines) — the same license as tablecodec. So we may reuse its
logic provided we retain the copyright notice and license text.

## Decision

Reimplement `build_anchors`'s span/registry logic as a faithful adaptation
of docling's `otsl_to_html` algorithm, targeting tablecodec's neutral IR
(emitting `GridCell` spans, not HTML strings) and keeping the
zero-third-party-import core invariant intact.

Attribution is recorded in three places: a header block in
`_otslgrid.py`, `THIRD_PARTY_NOTICES.md` (full MIT text + copyright), and
this ADR.

We do **not** change tablecodec's license: MIT → MIT requires only
attribution, so the Apache-2.0 switch that was initially considered (under
the mistaken belief docling was Apache-licensed) is unnecessary and was
rejected as needless, high-blast-radius churn.

This **supersedes intent.md §6's blanket "never copy upstream" rule** for
the specific, narrow case of adapting a permissively-licensed (MIT/BSD/
Apache) upstream algorithm *with* attribution. Clean-room remains the
default; an attributed adaptation is permitted when (a) the upstream
license allows it, (b) attribution is recorded, and (c) the core invariants
(zero third-party imports, neutral IR) still hold.

## Consequences

### Positive

- The OTSL reconstruction now matches the reference behaviour: SynthTabNet
  agrees with the HTML path (the "OTSL fails / HTML ok" divergence is
  eliminated; remaining failures are shared I-05 degenerate-bbox DATA
  quirks). Fixes `otsl-1.0.0`, `fintabnet-otsl`, `doctags-tables`,
  `pubtables-1m` (all call `build_anchors`).
- Correctness comes from a proven, widely-used algorithm rather than a
  bespoke reinvention.

### Negative

- The reconstruction logic is now a derivative work and must keep its
  attribution if it is further modified.
- A small precedent crack in the clean-room policy; mitigated by the
  narrow, license-gated, attribution-required conditions above.

### Neutral

- No runtime dependency is added; the port is pure-stdlib and the semgrep
  zero-third-party rule still passes.
- The OTSL serializer (`cells_to_otsl` / `build_token_grid`) is unchanged
  and still round-trips with the new reader.
