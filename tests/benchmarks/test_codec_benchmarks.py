"""Codec read/write micro-benchmarks (pytest-benchmark).

Marked ``benchmark`` so they are deselected from the default test run
(see ``just bench`` and ``.github/workflows/benchmark.yaml``).
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from tablecodec.codecs.pubtabnet import PubTabNet20Codec
from tablecodec.ir import TableSample

FIXTURES = Path(__file__).parent.parent / "fixtures" / "pubtabnet"


def _make_corpus(n: int) -> str:
    record = {
        "filename": "synth.png",
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
    return line * n


@pytest.mark.benchmark(group="pubtabnet-2.0.0")
def test_read_1k_samples(benchmark: Callable[..., object]) -> None:
    corpus = _make_corpus(1_000)
    codec = PubTabNet20Codec()

    def _run() -> int:
        return sum(1 for _ in codec.read(io.StringIO(corpus)))

    count = benchmark(_run)
    assert count == 1_000


@pytest.mark.benchmark(group="pubtabnet-2.0.0")
def test_write_1k_samples(benchmark: Callable[..., object]) -> None:
    corpus = _make_corpus(1_000)
    codec = PubTabNet20Codec()
    samples: list[TableSample] = list(codec.read(io.StringIO(corpus)))

    def _run() -> None:
        sink = io.StringIO()
        codec.write(samples, sink)

    benchmark(_run)
