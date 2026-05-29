# tablecodec Conformance Suite (in-repo, temporary)

> **Status:** hosted in-repo pending extraction to a separate
> vendor-neutral repository before v1.0. See
> [`docs/adr/0001-conformance-suite-in-repo-temporarily.md`](../docs/adr/0001-conformance-suite-in-repo-temporarily.md).
>
> **This is a data corpus, NOT a pip package.** It deliberately sits at the
> repository root (not under `packages/`, which is for installable Python
> sub-packages): its extraction target is a vendor-neutral *repository*, not
> a PyPI release. Roadmap tracking lives in `docs/intent.md` §8.

This directory holds the conformance corpus described in SPEC §11. Any
implementation claiming `tablecodec`-compatibility (in any language)
must read each `sample` with the declared `codec` and produce the IR in
the matching `expectation` file.

## Layout

```
conformance/
├── schema/index.schema.json   # JSON Schema (draft 2020-12) for INDEX.json
├── INDEX.json                 # manifest: list of test cases
├── samples/<codec>/*.jsonl    # input records
└── expectations/<codec>/*.ir.json  # expected IR after read
```

## IR expectation format

Each `*.ir.json` is the canonical JSON form of a `TableSample`:

```json
{
  "filename": "string",
  "nrows": 1,
  "ncols": 1,
  "split": "train | val | test | null",
  "imgid": 0,
  "cells": [
    {
      "row": 0, "col": 0, "rowspan": 1, "colspan": 1,
      "tokens": ["..."], "bbox": [x0, y0, x1, y1] | null,
      "role": "header | body"
    }
  ]
}
```

`extras` is intentionally omitted — it is opaque to conformance.

## Running

The reference Python implementation runs the suite as part of its test
suite: `tests/test_conformance.py` (executed by `just test` / `just ci`).
Expectations are authored independently of the codec implementation, so
the suite is a genuine regression net for the read path.
