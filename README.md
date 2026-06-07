# tablecodec

> Neutral Internal Representation + Codec registry for image-based table-recognition datasets.

`tablecodec` is a Python library that provides a single, lossless Internal
Representation (IR) for tables and a registry-based codec layer that translates
between this IR and the fragmented landscape of public table-recognition
datasets — PubTabNet, FinTabNet, OTSL, TableFormer, DocTags-tables,
PubTables-1M, TableBank.

- Stdlib-only core. Heavier features (TEDS, CLI) are opt-in extras.
- Streams large JSONL datasets at constant memory.
- Self-declared loss analysis between any two codecs.

## Status

**0.0.18 (pre-alpha).** Not yet published to PyPI. The nine codecs, the TEDS
metric (`[teds]`), and the STRICT validation profile were all added
incrementally within the 0.0.x series; a separate `tablecodec-docling` bridge
codec lives in `packages/` (its own version). The 0.x line makes no
API-stability promises; the public surface freezes at 1.0 (see
[docs/spec.md](docs/spec.md) §14). The specification is the source of
truth. Auto-generated codec / loss tables live at
[docs/format_support.md](docs/format_support.md) and
[docs/loss_matrix.md](docs/loss_matrix.md).

## Installation

```bash
pip install tablecodec            # stdlib-only core
pip install "tablecodec[cli]"     # + command-line interface (click)
pip install "tablecodec[teds]"    # + TEDS similarity metric (apted, lxml)
```

Requires Python 3.11+.

## Basic usage

```python
import tablecodec
from tablecodec import codecs, validate, profiles, analyze_loss
from tablecodec.codecs.pubtabnet import PubTabNet20Codec

# Register a codec (built-ins self-register through the CLI; in library
# use you register the ones you need).
codecs.register(PubTabNet20Codec())

# Stream-read a dataset into the neutral IR.
with open("pubtabnet_val.jsonl", encoding="utf-8") as f:
    for sample in codecs.get("pubtabnet-2.0.0").read(f):
        errors = validate(sample, profile=profiles.DEFAULT)
        if errors:
            print(sample.filename, errors)

# Static, data-free loss analysis between two formats.
report = analyze_loss(source="pubtabnet-2.0.0", target="otsl-1.0.0")
print(report.round_trip_classification)  # "structure-preserving"
```

The core has **zero third-party runtime dependencies** (SPEC §13);
`import tablecodec` works on a bare Python 3.11+.

## TEDS similarity (optional)

The `[teds]` extra adds a Tree-Edit-Distance based Similarity score between
two samples. It lives outside the core (it imports `apted`/`lxml`), so import
it from its submodule:

```python
from tablecodec.teds import teds

score = teds(pred_sample, true_sample)              # 0.0 .. 1.0
struct = teds(pred_sample, true_sample, structure_only=True)  # ignore cell text
```

## CLI

Install with the optional ``[cli]`` extra:

```bash
pip install "tablecodec[cli]"
```

```bash
tablecodec codecs list
tablecodec analyze-loss --from pubtabnet-2.0.0 --to otsl-1.0.0
tablecodec validate path/to/dataset.jsonl --codec pubtabnet-2.0.0 --profile DEFAULT
tablecodec stats path/to/dataset.jsonl --codec pubtabnet-2.0.0 --json
tablecodec convert in.jsonl out.jsonl --from pubtabnet-2.0.0 --to otsl-1.0.0
tablecodec convert in.jsonl /dev/null --from pubtabnet-2.0.0 --to otsl-1.0.0 --dry-run
tablecodec diff a.jsonl b.jsonl --codec pubtabnet-2.0.0
```

All commands stream their input; exit codes are non-zero on validation
failures or diffs (suitable for CI / data pipelines).

## End-to-end check against real datasets

`scripts/e2e_hf_check.py` streams real datasets through the codecs and
validates the resulting IR. Every shipped codec gets at least one
official-corpus check. Two data sources are used:

- the Docling OTSL family
  (`docling-project/{PubTabNet,FinTabNet,PubTables-1M,SynthTabNet}_OTSL`)
  — a uniform converted schema that feeds all nine codecs;
- the **native** first-published PubTabNet annotation
  (`apoidea/pubtabnet-html`) fed unmodified to the `pubtabnet` codecs;
- the **native** PubTables-1M PASCAL VOC structure annotation
  (`bsmock/pubtables-1m`, download-only) read from a local tar under
  `input/` with the logical grid reconstructed for the `pubtables-1m`
  codec (FinTabNet / TableBank natives stay download-only + Docling-covered).

It is **occasional / local-only** (network + multi-GB datasets), not part
of CI.

```bash
just e2e-selftest              # network-free adapter smoke test
just e2e 200                   # 200 randomly-sampled rows per check (needs [hf] extra)
uv run --extra hf python scripts/e2e_hf_check.py --dataset apoidea --limit 50
just e2e-fetch-pubtables1m     # download native PubTables-1M VOC (~30MB) into input/
uv run --extra hf python scripts/e2e_hf_check.py --dataset bsmock --limit 200
```

Rows are sampled randomly (streaming shuffle reshuffles shard order), so
repeated runs progressively cover the multi-hundred-thousand-row corpora.
Each run prints its `--seed` so a finding can be reproduced; pass
`--seed N` to fix it or `--no-shuffle` for a deterministic head read.
The harness reports parse errors and validation findings — e.g. it
surfaces real upstream rows with geometrically invalid bboxes (I-05) —
and appends each failed row to `output/e2e_findings/` (gitignored) with
its full provenance and replayable payload for later audit.

See [`docs/adr/0003-e2e-against-docling-otsl-family.md`](docs/adr/0003-e2e-against-docling-otsl-family.md)
and [`docs/adr/0004-e2e-native-first-published-datasets.md`](docs/adr/0004-e2e-native-first-published-datasets.md)
for the data-source decisions and the canonical-vs-real-shape caveats.

## Documents

- [`docs/spec.md`](docs/spec.md) — Specification (the single source of truth).
- [`docs/glossary.md`](docs/glossary.md) — Precise vocabulary: terms tablecodec
  defines vs. borrows, and the words most likely to be misread (e.g. "loss"
  vs a "degenerate" bbox).
- [`docs/intent.md`](docs/intent.md) — Implementation brief (milestones, order,
  quality bar).
- [`CHANGELOG.md`](CHANGELOG.md) — Keep a Changelog format.

## License

MIT. See [LICENSE](LICENSE). The OTSL grid-reconstruction logic is
adapted (with attribution) from the MIT-licensed docling-ibm-models — see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
