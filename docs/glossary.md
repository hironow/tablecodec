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

Groups B and C carry an explicit **Origin** column — **Paper** (which
paper), **Dataset** (which dataset), **Standard**, **General**, or
**tablecodec** (a word we coined for an external concept). The point is
that a borrowed term is never silently confused with a tablecodec (IR /
Group A) concept just because it shows up next to one here.

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
| **round-trip** | Passing data through the IR and back out: `read → write` (one codec) or `source → IR → target` (two codecs). The unit `analyze_loss` reasons about. | `loss.py`, spec §9 | Not a network round-trip. |
| **round-trip classification** | `lossless` (nothing dropped) / `structure-preserving` (only *auxiliary fields* lost) / `lossy` (something else lost) / `unwritable` (target is read-only). | `loss.py` (`Classification`) | "structure-preserving" is **not** "lossless" — bbox/role/extras may still be lost. |
| **auxiliary field** | Exactly `{bbox, role, extras}`. Losing only these on a round-trip is "structure-preserving"; losing anything else is "lossy". | `loss.py` | Not "unimportant" — just the fields whose loss preserves the *structure*. |
| **structure-only** (codec/format) | A codec/format that carries the table **structure** (the grid skeleton: rows, columns, spans) but **no cell content** (`tokens`) and no `bbox` — e.g. `tablebank`. | `codecs/tablebank.py`, `_htmltable.py` | A property of the *format*. NOT the same as **structure-preserving** (a loss *classification*). A structure-only write is *lossy* (it drops tokens), not structure-preserving. |
| **Conformance** | Verifiable behavioural compliance with the spec, established by passing the published test corpus (the `conformance/` suite). | spec §4, §11 | Not type-checking or linting. |
| **Invariant** (I-01 … I-07) | The seven structural rules a valid `TableSample` must satisfy (positive dims, in-bounds cells/spans, exact cover, well-formed bbox, contiguous header, tuple tokens). | `_invariants.py`, spec §5.2 | Validation rules, not runtime assertions on every call. |
| **exact cover** (I-04) | The cell footprints (using rowspan/colspan) tile the `nrows × ncols` grid with **no overlaps and no gaps**. | I-04, spec §5.2 | A *grid* property; unrelated to set-cover optimization. |
| **Validation profile** | A named bundle of invariant checks: `LENIENT`, `DEFAULT`, `PUBTABNET_2_0`, `TABLEFORMER`, `STRICT`. The caller opts into strictness. | `validate.py`, spec §8 | Not a performance profile; not a config file. |
| **Registry** | The process-wide map of registered codecs (`register`, `get`, `detect`). `detect` uses each codec's `sniff`. | `codecs/__init__.py`, spec §6.2 | Not a package/Docker registry. |
| **sniff** | A codec's cheap "is this my format?" peek at a source (stream position restored). Drives `detect`. | `Codec.sniff` | Not full parsing/validation. |

---

## B. Borrowed terms (only what Group A needs)

The **Origin** column says where each term comes from — a **Paper**, a
specific **Dataset**, an external **Standard**, **General** usage, or a
**tablecodec** word coined for an external concept — so a borrowed term is
never mistaken for a Group A (tablecodec-defined) concept when you land on
it next to the IR.

| Term | Origin | Means + why it appears |
|---|---|---|
| **HTML table structure tokens** | Standard — HTML (as serialized by the PubTabNet/FinTabNet annotations) | `<thead>/<tbody>/<tr>/<td>` + optional `rowspan`/`colspan`, plus cell content tokens. The envelope of the PubTabNet / FinTabNet / TableFormer codecs. |
| **rowspan / colspan** | Standard — HTML | How many grid rows/columns a cell occupies (≥ 1). A `GridCell` field; the unit of I-03 / I-04. |
| **OTSL** | Paper — Lysak et al., arXiv 2305.03393 | "Optimized Table Structure Language": a 5-token grid language. Used by the `otsl-1.0.0` / `fintabnet-otsl` / `doctags-tables` codecs; reconstructed in `_otslgrid.py`. |
| **fcel / ecel / lcel / ucel / xcel / nl** | Paper concept (OTSL); these exact spellings from the **docling** datasets | OTSL cell tokens: filled / empty **anchor**; left- / up- / cross-merged **continuation**; newline. The vocabulary `build_anchors` reconstructs from. |
| **anchor / continuation** | tablecodec's words for the OTSL roles (not literal paper terms) | *Anchor* = the cell that owns a span (`fcel`/`ecel`, or the `<td>` opening); *continuation* = an `lcel`/`ucel`/`xcel` that only extends it. Modeled as `AnchorPlacement`; a continuation is skipped on read. Not an HTML `<a>` anchor. |
| **square-table assumption** | Paper — OTSL | Every row produced by `nl` has the **same number of cells** — the token grid is **rectangular**. `ensure_square` enforces it. NOTE: "square" = **uniform row width**, **NOT** `nrows == ncols`; a 3x7 grid is "square" here. |
| **spanning cell** | General (HTML/tables); also an explicit object in PubTables-1M | A merged cell (`rowspan > 1` or `colspan > 1`). A `GridCell` with span > 1; what I-03 / I-04 reason about. |
| **PASCAL VOC** | Standard — PASCAL VOC object-detection annotation | XML of `<object><name><bndbox>`. PubTables-1M's native structure format; the grid is *reconstructed* from its regions. |
| **table row / table column / table spanning cell / table projected row header / table column header** | Dataset — PubTables-1M (Smock et al., Microsoft) object labels | The VOC `<object><name>` values the native PubTables-1M adapter reads. They are dataset annotation labels, **not** IR fields. |
| **DocTags** | Tooling — IBM Granite-Docling (model output) | A document-token output format; its table subset reuses the OTSL grid. The `doctags-tables` codec; an OUTPUT format with no ground-truth dataset. |
| **PubTabNet / FinTabNet / PubTables-1M / TableBank / SynthTabNet** | Datasets — IBM (PubTabNet, FinTabNet, SynthTabNet), Microsoft (PubTables-1M, TableBank) | Public table-recognition datasets, each with its own annotation format. Each codec targets one; the e2e harness reads them. |
| **streaming** | General (CS) | Iterating records lazily at constant memory (never `f.read()` the whole file). Required of every `read` (spec §10). |

---

## C. Data-property terms & confusion guards

These describe the **input data**, not tablecodec. They exist because real
datasets carry imperfect annotations that validation correctly surfaces.
The **Origin** column distinguishes general/geometry terms from labels
tablecodec coined to describe a finding.

| Term | Origin | Means + confusion guard (what it is NOT) |
|---|---|---|
| **degenerate bbox** | General (geometry) | A bounding box with non-positive area: `x0 >= x1` or `y0 >= y1`. Rejected by **I-05**. **NOT a conversion "loss"** — verified across 16k rows, every degenerate box was already degenerate in the SOURCE floats; our float→int cast introduced zero. A *data-quality* property. |
| **inverted bbox** | General (geometry) | The `x0 > x1` (or `y0 > y1`) sub-case — coordinates in the wrong order in the source. A genuine upstream annotation error, not a "loss". |
| **ragged table** | General (descriptive) | A table whose rows do not all span the same number of columns (some under-cover the grid). Surfaced by **I-04**; passes `LENIENT`. NOT a parse failure or library bug — the tokens faithfully describe a non-rectangular grid. |
| **OTSL span ambiguity** | tablecodec (our shorthand) | An OTSL token stream whose merge region is not a clean rectangle (e.g. L-shaped), so it cannot reconstruct to an exact-cover grid. NOT a reconstruction bug — the same ambiguity shows in the HTML path; an inherent limit of the compressed encoding. (Not a term from the OTSL paper — our label for the observed case.) |

### Words most likely to mislead

- **"loss" / "lossy" / "structure-preserving"** — in tablecodec these are
  about **which IR fields a codec drops on a round-trip** (`{bbox, role,
  extras}` and friends; see Group A). They are **not** about image/pixel
  compression, numeric precision, or geometry quality. A *degenerate bbox*
  is **not** "lossy" — the bbox was read and kept faithfully; its geometry
  was already bad in the source.
- **"degenerate"** — a **geometry** term (zero-area / inverted box), and a
  property of the **data**, not of any tablecodec transform. Do not read it
  as "decayed by conversion" or "field lost".
- **"structure-only" vs "structure-preserving"** — easy to swap. *Structure-
  only* describes a **format** (TableBank carries structure but no cell
  content). *Structure-preserving* describes a **loss classification** (a
  round-trip dropped only `{bbox, role, extras}`). A structure-only write
  is in fact *lossy* (it also drops `tokens`), so the two are nearly
  opposite, not synonyms.
- **"square" (square-table assumption)** — means the OTSL token grid is
  **rectangular** (every row the same width), **NOT** a literally square
  `nrows == ncols` table. The word is the paper's, kept for fidelity; read
  it as "uniform-width rows".
- **"sample" vs "sampling"** — `TableSample` is **one table** (the IR unit).
  The e2e harness's "sample N rows" / "random sampling" is the unrelated
  statistical sense (drawing dataset rows). Same root word, different idea.
