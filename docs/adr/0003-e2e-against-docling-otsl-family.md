# 0003. E2E validation against the Docling OTSL dataset family

**Date:** 2026-05-28
**Status:** Accepted

## Context

The codecs were built and unit-tested entirely against **synthetic
fixtures** (license-clean, no upstream data). The conformance suite
(ADR 0001) likewise uses hand-authored samples. Nothing has yet been
validated against **real upstream datasets**, so we do not know whether
the codecs' `read()` paths cope with the structural diversity of the
public corpora (token vocabularies, cell counts, span patterns,
degenerate bboxes, non-square OTSL, etc.).

A survey of Hugging Face (May 2026) found that the codecs' bespoke
canonical jsonl shapes differ from the real upstream envelopes — e.g.
`ajimeno/PubTabNet` ships images only (no structure annotation), and
the original `bsmock/pubtables-1m` is PASCAL VOC XML, not the
object-detection jsonl this library defines.

However, the **Docling project** publishes an OTSL-converted family with
a single uniform parquet schema:

- `docling-project/PubTabNet_OTSL`
- `docling-project/FinTabNet_OTSL`
- `docling-project/PubTables-1M_OTSL` (+ `-v1.1`)
- `docling-project/SynthTabNet_OTSL`

Shared columns: `filename`, `split`, `imgid`, `dataset`,
`cells: List[List[{tokens, bbox}]]` (grouped by row), `otsl: List[str]`,
`html: List[str]` (structure tokens), `cols`, `rows`. Crucially each row
carries **both** the OTSL and the HTML structure representation plus the
cell content, in one schema, streamable via `datasets`.

## Decision

Use the Docling OTSL dataset family as the e2e data source. A single
adapter converts a Docling row into the canonical input of a target
codec and runs the **actual `codec.read()`** (not a bypass), then
`validate(sample, profile)`:

- OTSL path: feed `row["otsl"]` + a row-major flattening of
  `row["cells"]` to `otsl-1.0.0`.
- HTML path: feed `{"structure": {"tokens": row["html"]}, "cells": …}`
  to `pubtabnet-2.0.0`.

The harness lives at `scripts/e2e_hf_check.py`, streams with
`--limit`, and tallies parse errors (codec `ValueError`) separately from
validation findings. It is **occasional / local-only** — not CI-gated
(network + multi-GB datasets). A network-free `--self-test` exercises
the adapters through the real codecs on a synthetic Docling-shaped row.

### Known adapter responsibilities (the canonical↔real gap)

- `cells` is nested by row in Docling but flat in the codecs → the
  adapter flattens row-major.
- Docling uses `imgid`; the library's `fintabnet` / `fintabnet-otsl`
  codecs were written expecting `table_id`. The e2e harness targets the
  generic `otsl-1.0.0` / `pubtabnet-2.0.0` codecs (which use `imgid`),
  so this mismatch is sidestepped for now; aligning those two codecs to
  accept `imgid` is tracked as follow-up.

## Consequences

### Positive

- One adapter validates 5+ codecs (OTSL + HTML families) against four
  real corpora totalling >1.5M tables.
- Exercises the genuinely risky logic — square-table assumption,
  anchor/cell-count alignment, HTML structure parsing — on real tables.

### Negative

- `pubtables-1m` (object-detection / VOC XML), `tablebank`, and
  `doctags-tables` have no public dataset in the codec's exact shape, so
  they are **not** covered by this harness; each needs its own adapter
  (or remains synthetic-only). Recorded as out of scope here.
- The harness depends on network access and the optional `[hf]` extra.

### Neutral

- Findings from running the harness may motivate broadening some
  codecs' `read()` (e.g. accept nested `cells`, accept `imgid` on the
  FinTabNet codecs) or revising the canonical shapes toward the Docling
  de-facto standard. Such changes will be their own commits/ADRs.
