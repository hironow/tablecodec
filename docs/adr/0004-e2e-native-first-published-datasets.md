# 0004. Extend the e2e harness to native first-published datasets

**Date:** 2026-05-28
**Status:** Accepted

## Context

ADR 0003 wired the e2e harness (`scripts/e2e_hf_check.py`) to the
**Docling OTSL family** — a uniform, converted schema covering PubTabNet
/ FinTabNet / PubTables-1M / SynthTabNet. That conversion is convenient
(one adapter feeds many codecs) but it is **not** the shape each codec
was originally designed for: the Docling rows carry OTSL tokens, nested
`cells`, and an `imgid` key, whereas the codecs' native envelopes are the
upstream formats (PubTabNet's `{cells, structure}` jsonl, PubTables-1M's
PASCAL VOC XML, etc.).

We want each codec to also be exercised against the dataset in which its
format was **first published**, in that dataset's native shape — so the
e2e proves the codec copes with the real on-disk envelope, not only the
Docling re-encoding.

A Hugging Face survey (May 2026) of the native originals:

| Codec | First-published dataset | HF availability | Streamable? |
|---|---|---|---|
| `pubtabnet-2.0.0` / `pubtabnet-1.0.0` | PubTabNet (IBM) | `apoidea/pubtabnet-html` — parquet, `html` column = the original `{cells, structure}` annotation | **Yes** |
| `otsl-1.0.0` | OTSL (introduced by the Docling paper) | `docling-project/*_OTSL` | Yes (already covered by ADR 0003 — Docling *is* the original) |
| `fintabnet` | FinTabNet (IBM) | `bsmock/FinTabNet.c` — parquet export failed / 0 rows (file-based) | No |
| `fintabnet-otsl` | FinTabNet_OTSL (Docling) | `docling-project/FinTabNet_OTSL` | Yes (already covered) |
| `pubtables-1m` | PubTables-1M (Microsoft) | `bsmock/pubtables-1m` — tar.gz of PASCAL VOC XML, no Datasets integration | No |
| `tablebank` | TableBank | `liminghao1630/TableBank` — Datasets viewer: "no supported data files" (file-based) | No |
| `tableformer` | (no own dataset; trained on PubTabNet/FinTabNet) | n/a | n/a |
| `doctags-tables` | (model OUTPUT format; no ground-truth dataset) | n/a | n/a |

## Decision

Add `apoidea/pubtabnet-html` to the e2e `CHECKS`, feeding the **native**
PubTabNet annotation to `pubtabnet-2.0.0` and `pubtabnet-1.0.0` via the
`apoidea_to_pubtabnet_payload` adapter. The adapter does no structural
reshaping: it parses the `html` string column (JSON, mirroring the
upstream jsonl) and wraps it back into a record of the exact shape the
codecs read. A non-JSON `html` string raises and is recorded as a
`parse_error` finding rather than being silently coerced.

The codecs whose native originals are **not streamable** through the HF
Datasets viewer (FinTabNet original, TableBank, PubTables-1M PASCAL VOC)
remain covered only by the Docling-derived checks from ADR 0003. We do
**not** download tar.gz archives or parse VOC XML in this harness; that
is explicitly out of scope.

`tableformer` is intentionally **not** fed the native PubTabNet data: the
codec requires every cell (including empty ones) to carry a bbox, and the
PubTabNet convention omits bbox on empty cells, so native rows would
raise on read by design.

## Consequences

### Positive

- The PubTabNet codecs are now validated against their genuine native
  envelope, not only the Docling OTSL re-encoding — closing the
  "canonical-vs-real" gap noted in ADR 0003 for the most-used format.
- `--self-test` exercises the native adapter on a shape-matched synthetic
  row, so the wiring is covered without network.

### Negative

- Three codecs (`fintabnet`, `pubtables-1m`, `tablebank`) still have no
  native-shape e2e coverage because their originals are file-based
  (tar.gz / images / VOC XML) and not exposed through the Datasets
  streaming viewer. Adding them would require a downloader + format
  parser, deferred until there is a reason to invest.
- One more network dataset dependency (apoidea/pubtabnet-html, ~12.7 GB;
  only the `validation` split, 230 MB, is used by default).

### Neutral

- If `apoidea/pubtabnet-html` ever stores `html` as a Python `repr`
  (single-quoted) rather than JSON, those rows will surface as
  `parse_error` findings, prompting a revisit of `_parse_struct`.
