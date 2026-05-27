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

**Pre-alpha (M6 in progress).** The specification is the source of truth;
see [docs/spec.md](docs/spec.md). Auto-generated codec / loss tables live
at [docs/format_support.md](docs/format_support.md) and
[docs/loss_matrix.md](docs/loss_matrix.md).

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
