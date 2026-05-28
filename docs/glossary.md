# Glossary

Precise shared vocabulary for tablecodec. `docs/spec.md` §4 (Terminology)
is authoritative; this file **expands** it and, deliberately, separates:

- **Group A — tablecodec-defined terms.** Concepts this library owns.
- **Group B — borrowed terms.** External/upstream words, included only as
  far as they are needed to understand Group A (necessary and sufficient,
  not a survey of the field).
- **Group C — data-property terms & confusion guards.** Words that
  describe the *input data*, not this library — kept here because they are
  the ones most often misread (e.g. "degenerate" vs "loss").

Each entry says what the word **does** mean and, where it bites, what it
does **NOT** mean.

---

## A. tablecodec-defined terms

| Term | Means | Defined in | Do NOT read it as |
|---|---|---|---|
| **IR** / Internal Representation | The neutral 2D-grid model every codec maps to/from: `TableSample` of `GridCell`s. | `src/tablecodec/ir.py`, spec §5 | Not HTML / OTSL / DocTags — those are *formats*, the IR is format-neutral. |
| **TableSample** | One annotated table image: `filename`, `nrows`, `ncols`, ordered `cells`, optional `split`/`imgid`/`extras`. | `ir.py`, spec §5.1 | Not a statistical "sample"; one TableSample = one table. |
| **GridCell** | One logical grid cell: `row`, `col`, `rowspan`, `colspan`, `tokens`, `bbox`, `role`. | `ir.py` | Not always one HTML `<td>` (a spanning cell is one GridCell over several grid squares). |
| **BBox** | `(x0, y0, x1, y1)`, absolute **integer** pixels. | `ir.py` | Not normalized/relative coords; not float. |
| **Codec** | A reader+writer for one external format, implementing the `Codec` Protocol (`name`, `spec_version`, `media_type`, `writable`, `read`, `write`, `lossy_read`, `lossy_write`, `sniff`). | `codecs/_base.py`, spec §6 | Not a video/audio codec; not an encoder of bytes. |
| **read / write** | `read`: external format → IR (streaming, lazy). `write`: IR → external format. | spec §6.1 | `read` never slurps the whole file (see *streaming*). |
| **lossy_read** | The set of fields a codec **drops when reading** a record into the IR (e.g. `pubtabnet-1.0.0` drops `bbox`). | codec classes; spec §9 | Not a runtime error; a declared, honest contract. |
| **lossy_write** | The set of IR fields a codec **cannot represent when writing** out (e.g. most codecs drop `extras`). | codec classes; spec §9 | — |
| **analyze_loss** / **LossReport** | A **static, data-free** computation of what a `source → IR → target` round-trip would drop, from the two codecs' `lossy_*` declarations. | `loss.py`, spec §9 | Does not read any data; it reasons over declarations only. |
| **round-trip classification** | `lossless` (nothing dropped) / `structure-preserving` (only *auxiliary fields* lost) / `lossy` (something else lost) / `unwritable` (target is read-only). | `loss.py` (`Classification`) | "structure-preserving" is **not** "lossless" — geometry/role/extras may still be lost. |
| **auxiliary field** | Exactly `{bbox, role, extras}`. Losing only these on a round-trip is "structure-preserving"; losing anything else is "lossy". | `loss.py` | Not "unimportant" — just the fields whose loss preserves the *structure*. |
| **Invariant** (I-01 … I-07) | The seven structural rules a valid `TableSample` must satisfy (positive dims, in-bounds cells/spans, exact cover, well-formed bbox, contiguous header, tuple tokens). | `_invariants.py`, spec §5.2 | Validation rules, not runtime assertions on every call. |
| **exact cover** (I-04) | The cell footprints (using rowspan/colspan) tile the `nrows × ncols` grid with **no overlaps and no gaps**. | I-04, spec §5.2 | A *grid* property; unrelated to set-cover optimization. |
| **Validation profile** | A named bundle of invariant checks: `LENIENT`, `DEFAULT`, `PUBTABNET_2_0`, `TABLEFORMER`, `STRICT`. The caller opts into strictness. | `validate.py`, spec §8 | Not a performance profile; not a config file. |
| **Registry** | The process-wide map of registered codecs (`register`, `get`, `detect`). `detect` uses each codec's `sniff`. | `codecs/__init__.py`, spec §6.2 | Not a package/Docker registry. |
| **sniff** | A codec's cheap "is this my format?" peek at a source (stream position restored). Drives `detect`. | `Codec.sniff` | Not full parsing/validation. |

---

## B. Borrowed terms (only what Group A needs)

| Term | Means (brief) | Why it appears here |
|---|---|---|
| **HTML table structure tokens** | `<thead>/<tbody>/<tr>/<td>` with optional `rowspan`/`colspan` attributes, plus cell content tokens. | The envelope of the PubTabNet / FinTabNet / TableFormer codecs. |
| **rowspan / colspan** | How many grid rows/columns a cell occupies (HTML attribute; ≥ 1). | A `GridCell` field; the unit of I-03 / I-04. |
| **OTSL** | "Optimized Table Structure Language" (Lysak et al., arXiv 2305.03393): a 5-token grid language. | The `otsl-1.0.0` / `fintabnet-otsl` / `doctags-tables` codecs; grid reconstruction in `_otslgrid.py`. |
| **fcel / ecel / lcel / ucel / xcel / nl** | OTSL cell tokens: filled / empty **anchor**; left- / up- / cross-merged **continuation**; newline. | The token vocabulary `build_anchors` reconstructs from. |
| **anchor** (OTSL) | The `fcel`/`ecel` that *owns* a span; continuations extend it. tablecodec models it as `AnchorPlacement`. | Output of OTSL reconstruction → becomes one `GridCell`. |
| **continuation** (OTSL) | An `lcel`/`ucel`/`xcel` that carries no content; it only extends an anchor's span. | Skipped on read — it is not a separate cell. |
| **PASCAL VOC** | An object-detection XML annotation (`<object><name><bndbox>`). PubTables-1M's native structure format. | The native `pubtables-1m` source; the grid is *reconstructed* from VOC row/column/cell regions. |
| **DocTags** | IBM Granite-Docling's document-token output format (a table subset reuses the OTSL grid). | The `doctags-tables` codec; it is a model **output** format with no ground-truth dataset. |
| **PubTabNet / FinTabNet / PubTables-1M / TableBank / SynthTabNet** | Public table-recognition datasets, each with its own annotation format. | Each codec targets one of these; the e2e harness reads them. |
| **streaming** | Iterating records lazily at constant memory (never `f.read()` the whole file). | The required behavior of every `read` (spec §10). |

---

## C. Data-property terms & confusion guards

These describe the **input data**, not tablecodec. They exist because real
datasets carry imperfect annotations that validation correctly surfaces.

| Term | Means | Confusion guard (what it is NOT) |
|---|---|---|
| **degenerate bbox** | A bounding box with non-positive area: `x0 >= x1` (zero-width / inverted) or `y0 >= y1`. Rejected by **I-05**. | **NOT a conversion "loss".** Verified across 16k real rows: every degenerate bbox was already degenerate in the *source* floats; tablecodec's float→int cast introduced **zero**. It is a *data-quality* property, not something the library does to your data. |
| **inverted bbox** | The `x0 > x1` (or `y0 > y1`) sub-case of degenerate — coordinates in the wrong order in the source. | A genuine upstream annotation error, not a rendering of "loss". |
| **ragged table** | A table whose rows do not all span the same number of columns (some rows under-cover the grid). Surfaced by **I-04** (exact cover); passes `LENIENT`. | NOT a parse failure and NOT a library bug — the tokens faithfully describe a non-rectangular grid. |
| **OTSL span ambiguity** | An OTSL token stream whose merge region is not a clean rectangle (e.g. L-shaped), so it cannot reconstruct to an exact-cover grid. | NOT a reconstruction bug — the same ambiguity shows in the HTML path; it is an inherent limit of the compressed encoding for that table. |

### The two words most likely to mislead

- **"loss" / "lossy" / "structure-preserving"** — in tablecodec these are
  about **which IR fields a codec drops on a round-trip** (`{bbox, role,
  extras}` and friends; see Group A). They are **not** about image/pixel
  compression, numeric precision, or geometry quality. A *degenerate bbox*
  is **not** "lossy" — the bbox was read and kept faithfully; its geometry
  was already bad in the source.
- **"degenerate"** — a **geometry** term (zero-area / inverted box), and a
  property of the **data**, not of any tablecodec transform. Do not read it
  as "decayed by conversion" or "field lost".
