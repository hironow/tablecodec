# 0011. TEDS metric: IR-native API, ported from IBM's Apache-2.0 reference

**Date:** 2026-05-29
**Status:** Accepted

## Context

The `[teds]` extra (`apted`, `lxml`) has been declared since M0 but never
implemented — it was the one remaining "declared but unwired" extra after
the 0.0.14 reconciliation (ADR 0009 kept it precisely because, unlike
`fast`/`validate`, TEDS is a separate, core-external feature that CAN import
its dependencies). intent.md's roadmap lists "TEDS extra 実装" as 0.0.x work.

TEDS (Tree-Edit-Distance based Similarity; Zhong et al., "Image-based table
recognition: data, model, and evaluation") scores two tables in `[0, 1]` as
`1 - editdistance(tree_pred, tree_true) / max(#nodes)`, where each table is an
HTML-DOM tree and the per-cell relabel cost is a normalized Levenshtein over
the cell's content tokens. `structure_only` drops cell content (TEDS-Struct).

The canonical implementation is IBM's PubTabNet `src/metric.py`
(**Apache-2.0**, Copyright 2020 IBM). Two design questions had to be settled
before writing code, and both were confirmed with the maintainer.

## Decision

### 1. Port with attribution (not clean-room)

The metric's tree construction, the rename-cost rule, and the
`1 - dist/max_nodes` formula are adapted from IBM's Apache-2.0 reference.
Apache-2.0 code may be included in this MIT project provided the notice is
preserved and changes are stated, so:

- `src/tablecodec/teds.py` carries an attribution header (Apache-2.0, IBM,
  2020) and states the changes: an IR-native entry point, a pure-Python
  normalized Levenshtein replacing the `distance` package, and removal of the
  batching/parallelism (`tqdm`, `parallel_process`).
- `THIRD_PARTY_NOTICES.md` records the upstream and its license.

This mirrors ADR 0005 (the docling OTSL port). A clean-room reimplementation
was considered and rejected: the algorithm is short, the reference is
permissively licensed, and an attributed port keeps the metric faithful to
published TEDS numbers with less risk than re-deriving the node-counting and
span handling from the paper.

### 2. IR-native primary API; HTML secondary

```python
from tablecodec.teds import teds, teds_html
teds(pred: TableSample, true: TableSample, *, structure_only=False) -> float
teds_html(pred_html: str, true_html: str, *, structure_only=False) -> float
```

`teds` is the primary entry point (the library is IR-centric). It renders
each `TableSample` to an HTML `<table>` with a single internal renderer
(`_sample_to_html`: cells grouped by anchor row, header rows in `<thead>`,
all cells as `<td>` per PubTabNet convention), then delegates to `teds_html`,
which runs the canonical lxml-parse + apted edit-distance. Because both sides
use the same renderer, the score is a well-defined similarity in `[0, 1]`
regardless of the samples' source codecs. `teds_html` is exposed for callers
who already hold HTML and want parity with externally-produced numbers.

Consequence accepted by the maintainer: a `teds(pred, true)` score is defined
by tablecodec's own HTML rendering and may differ slightly from IBM
leaderboard numbers that score the dataset's own HTML. Internal consistency
(the property that matters for comparing two IR samples) is preserved.

### 3. Zero-dependency-core safety

`teds.py` lives OUTSIDE the core: it is NOT in `semgrep.yaml`'s core include
list (so `apted`/`lxml` imports are allowed there, like `cli.py`), and it is
NEVER imported by `tablecodec/__init__`. The public surface is
`from tablecodec.teds import teds` — `import tablecodec` on a bare interpreter
does not pull `apted`/`lxml` (verified; the `pip install -e .` CI job guards
this). `lxml`'s `.//*` node count provides the canonical denominator
(including inline-markup elements inside cells), so `lxml` is genuinely
needed rather than rebuilding that count from the IR by hand.

## Consequences

### Positive

- Closes the last declared-but-unimplemented extra honestly.
- Reuses a faithful, permissively-licensed algorithm; `structure_only`
  gives TEDS-Struct for free.
- Core stays zero-dependency; the metric is fully optional.

### Negative

- Two untyped third-party deps under pyright strict: the boundary is confined
  to three thin wrappers (`_parse_first_table`, `_count_descendant_elements`,
  `_tree_edit_distance`) with narrow `# pyright: ignore`s; the rest of the
  module is fully type-checked. `just type`/`test` now run with `--extra teds`.
- Scores are renderer-defined (see §2) — not bit-identical to IBM's published
  numbers when the source HTML differs from our rendering.

### Neutral

- No batching/parallel API in v1 (callers loop). Can be added later without
  changing the per-pair contract.
