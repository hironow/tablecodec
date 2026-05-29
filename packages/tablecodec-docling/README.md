# tablecodec-docling

A bridge [codec](https://github.com/hironow/tablecodec) that exports the tables
of a [docling](https://github.com/docling-project/docling-core)
`DoclingDocument` as `tablecodec` `TableSample` instances.

`tablecodec`'s core is stdlib-only; docling-core is heavy (Pydantic, numpy,
pandas). This bridge therefore lives in its **own package** so the dependency
stays out of the core. It registers through the `tablecodec.codecs`
entry-point group, so once installed it is discovered by
`tablecodec.codecs.load_plugins()` and usable as the codec named
`docling-tables`.

```python
from tablecodec import codecs

codecs.load_plugins()                     # discovers docling-tables
codec = codecs.get("docling-tables")
with open("docs.jsonl", encoding="utf-8") as f:   # one DoclingDocument per line
    for sample in codec.read(f):                  # one TableSample per table
        ...
```

## Status

Read and write. `read`: JSONL of `DoclingDocument`s (one per line) ->
one `TableSample` per table, in document order. `write` (`writable = True`):
each `TableSample` -> one `DoclingDocument` (one table) on its own JSONL line —
the exact inverse of `read`, so `read(write([s]))` recovers `s` modulo the
declared write-losses.

Write losses (`lossy_write = {"tokens", "extras"}`): docling stores one text
string per cell, so a multi-token cell's segmentation collapses
(`("a","b")` -> `"ab"`); and `DoclingDocument` has no home for arbitrary IR
`extras`. Structure, spans, role, bbox, and image dimensions round-trip.

## Mapping notes

- Cell grid footprint comes from docling's `start/end_*_offset_idx`
  (authoritative), not `row_span`/`col_span`.
- `column_header` cells become `role="header"`. `row_header` (left-column
  headers) become `role="body"` because the tablecodec IR + invariant I-06
  model only contiguous top-region headers; that distinction is declared lost
  in `lossy_read`.
- Bounding boxes are normalized to a top-left origin (using the page height
  from `DoclingDocument.pages`) and truncated to integer pixels.
- `image_width`/`image_height` are populated from the table's page size when
  available, so docling-read samples can be validated under the `strict`
  profile.

Developed in-repo under `packages/` as a temporary monorepo arrangement
(ADR 0013); to be extracted to its own repository before publishing.
