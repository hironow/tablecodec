# tablecodec

> Neutral Internal Representation + Codec registry for image-based table-recognition datasets.

`tablecodec` is a Python library that provides a single, lossless Internal
Representation (IR) for tables and a registry-based codec layer that translates
between this IR and the fragmented landscape of public table-recognition
datasets — PubTabNet, FinTabNet, OTSL, TableFormer, DocTags-tables,
PubTables-1M, TableBank.

- Stdlib-only core. Heavier features (TEDS, CLI, `orjson`, `pydantic`) are
  opt-in extras.
- Streams large JSONL datasets at constant memory.
- Self-declared loss analysis between any two codecs.

## Status

**0.0.2 (pre-alpha).** Not yet published to PyPI; codecs are being added
incrementally within the 0.0.x series. The 0.x line makes no
API-stability promises; the public surface freezes at 1.0 (see
[docs/spec.md](docs/spec.md) §14). The specification is the source of
truth. Auto-generated codec / loss tables live at
[docs/format_support.md](docs/format_support.md) and
[docs/loss_matrix.md](docs/loss_matrix.md).

## Installation

```bash
pip install tablecodec            # stdlib-only core
pip install "tablecodec[cli]"     # + command-line interface (click)
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

## Documents

- [`docs/spec.md`](docs/spec.md) — Specification (the single source of truth).
- [`docs/intent.md`](docs/intent.md) — Implementation brief (milestones, order,
  quality bar).
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — TDD-first workflow, Conventional
  Commits, PR template.
- [`CHANGELOG.md`](CHANGELOG.md) — Keep a Changelog format.

## License

MIT. See [LICENSE](LICENSE).
