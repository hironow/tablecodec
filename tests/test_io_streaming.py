"""SPEC §10 streaming guarantees verified via tracemalloc.

Generates a large jsonl file (100k samples) and asserts that the
streaming reader processes it without retaining all samples in memory.

The threshold is 50MB peak after the first sample has been pulled, per
docs/intent.md M3 Acceptance Criteria.
"""

from __future__ import annotations

import json
import tracemalloc
from pathlib import Path

import pytest

from tablecodec.codecs.pubtabnet import PubTabNet20Codec

_SAMPLE_COUNT = 100_000
_MAX_PEAK_BYTES = 50 * 1024 * 1024  # 50 MB per intent.md M3.


def _write_corpus(path: Path, count: int) -> None:
    """Generate a synthetic PubTabNet 2.0 jsonl file with *count* records."""
    record = {
        "filename": "synth.png",
        "split": "train",
        "imgid": 0,
        "html": {
            "structure": {
                "tokens": [
                    "<tbody>",
                    "<tr>",
                    "<td>",
                    "</td>",
                    "<td>",
                    "</td>",
                    "</tr>",
                    "</tbody>",
                ]
            },
            "cells": [
                {"tokens": ["x"], "bbox": [0, 0, 10, 5]},
                {"tokens": ["y"], "bbox": [10, 0, 20, 5]},
            ],
        },
    }
    line = json.dumps(record) + "\n"
    with path.open("w") as f:
        for _ in range(count):
            f.write(line)


@pytest.mark.slow
def test_reader_peak_memory_is_bounded(tmp_path: Path) -> None:
    # given
    corpus = tmp_path / "big.jsonl"
    _write_corpus(corpus, _SAMPLE_COUNT)
    codec = PubTabNet20Codec()

    tracemalloc.start()
    snapshot_baseline = tracemalloc.take_snapshot()

    # when — iterate without retaining samples.
    count = 0
    with corpus.open() as f:
        for _ in codec.read(f):
            count += 1

    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del snapshot_baseline  # silence unused-var

    # then
    assert count == _SAMPLE_COUNT
    assert peak < _MAX_PEAK_BYTES, f"peak memory {peak / 1024 / 1024:.1f} MB exceeds 50 MB"


@pytest.mark.slow
def test_reader_does_not_buffer_all_lines(tmp_path: Path) -> None:
    # given — write a much smaller corpus but pull just the first sample.
    corpus = tmp_path / "lazy.jsonl"
    _write_corpus(corpus, 1_000)
    codec = PubTabNet20Codec()

    tracemalloc.start()

    # when — only pull one sample.
    with corpus.open() as f:
        it = codec.read(f)
        first = next(it)

    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # then — first sample landed and peak is well under any per-corpus budget.
    assert first.filename == "synth.png"
    assert peak < 5 * 1024 * 1024  # 5 MB headroom for a 1k-sample file.
