# 0006. Cover download-only native datasets via a local `input/` tree

**Date:** 2026-05-28
**Status:** Accepted

## Context

ADR 0004 noted that three codecs' first-published native datasets are
**not exposed through the HF Datasets streaming viewer** — they ship as
tar.gz / split-zip archives — so the e2e harness could only cover them via
the Docling OTSL conversion, not their real on-disk envelope:

- `pubtables-1m`: `bsmock/pubtables-1m` — PASCAL VOC XML object detection.
- `fintabnet`: `bsmock/FinTabNet.c` — a single 3.2 GB structure tar.
- `tablebank`: `liminghao1630/TableBank` — a ~24 GB 5-part split zip.

The maintainer authorized downloading these locally to add native-format
coverage.

## Decision

Add a **local download area** at `input/` (gitignored, never committed)
and a **local-tar source** to `scripts/e2e_hf_check.py` (a `Check` may set
`local_tar=`; rows are read from tar members instead of streamed from the
hub). The harness stays occasional / local-only.

Cover `pubtables-1m` natively **now**: download only the small annotation
archive (`PubTables-1M-Structure_Annotations_Val.tar.gz`, ~30 MB — images
are multi-GB and unnecessary since the harness reads structure only) and
reconstruct the logical grid from the VOC geometry:

- `table row` × `table column` objects → the base grid (row band × column
  band intersection);
- `table spanning cell` objects → merge the base cells whose centres fall
  inside them into one spanning cell;
- `table projected row header` → a full-width cell for that row;
- `table column header` → `role="header"` for the rows it covers;
- cell `tokens` are empty (VOC carries no text content).

XML is parsed with `defusedxml` (added to the `[hf]` extra) to harden
against entity/DTD/external-reference attacks. A live run reads 200/200
real VOC tables into valid IR (DEFAULT-clean).

`fintabnet` (FinTabNet.c, 3.2 GB) is **deferred** — feasible but heavy,
and a separate native parser; revisit on demand. `tablebank` (~24 GB
split zip) is **out of scope** for local sampling.

## Consequences

### Positive

- `pubtables-1m` is now exercised against its genuine native envelope
  (object-detection geometry + grid reconstruction), not only the Docling
  OTSL conversion — closing the largest part of ADR 0004's gap.
- The local-tar source generalises: adding FinTabNet.c later is a new
  adapter + `Check`, no harness change.

### Negative

- The VOC grid reconstruction is bespoke logic (geometry → grid); its
  correctness rests on the live pass rate + DEFAULT validation, not a
  separate oracle.
- Requires a manual ~30 MB download into `input/` before the native check
  runs; absent the archive, the check records a single "missing archive"
  note rather than failing hard.

### Neutral

- `input/` joins `output/` and `private/` as gitignored local-only trees.
- No core library change and no new runtime dependency in core; defusedxml
  lives in the optional `[hf]` extra used by the script.
