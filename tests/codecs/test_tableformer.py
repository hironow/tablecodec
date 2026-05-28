"""Tests for tablecodec.codecs.tableformer — TableFormer Format codec.

TableFormer (IBM internal) uses the same HTML-token structure as
PubTabNet 2.0, but with the additional invariant that EVERY cell —
including empty ones — carries a bbox. The codec enforces this on read.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from tablecodec import profiles, validate
from tablecodec.codecs.tableformer import TableFormerCodec
from tablecodec.ir import GridCell

FIXTURES = Path(__file__).parent.parent / "fixtures" / "tableformer"


@pytest.fixture
def codec() -> TableFormerCodec:
    return TableFormerCodec()


class TestIdentity:
    def test_name_and_versions(self, codec: TableFormerCodec) -> None:
        assert codec.name == "tableformer"
        assert codec.media_type == "application/jsonl"


class TestRead:
    def test_reads_simple_table(self, codec: TableFormerCodec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            sample = next(iter(codec.read(f)))
        assert sample.nrows == 2
        assert sample.ncols == 2
        assert sample.cells[0] == GridCell(
            row=0, col=0, tokens=("A",), bbox=(0, 0, 10, 5), role="header"
        )

    def test_empty_cell_keeps_its_bbox(self, codec: TableFormerCodec) -> None:
        # given — TableFormer's distinguishing feature: empty cells have bbox.
        with (FIXTURES / "empty_with_bbox.jsonl").open() as f:
            sample = next(iter(codec.read(f)))

        # then
        empty = sample.cells[1]
        assert empty.tokens == ()
        assert empty.bbox == (10, 0, 20, 5)


class TestReadEnforcesBBox:
    def test_rejects_cell_without_bbox(self, codec: TableFormerCodec) -> None:
        # given — a record where one cell lacks bbox (valid PubTabNet, but
        # NOT valid TableFormer).
        payload: dict[str, Any] = {
            "filename": "bad.png",
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
                "cells": [{"tokens": ["x"], "bbox": [0, 0, 10, 5]}, {"tokens": []}],
            },
        }
        source = io.StringIO(json.dumps(payload) + "\n")

        # when / then
        with pytest.raises(ValueError, match="bbox"):
            list(codec.read(source))


class TestWriteRoundTrip:
    @pytest.mark.parametrize("fixture_name", ["simple_2x2.jsonl", "empty_with_bbox.jsonl"])
    def test_round_trip_identity(self, codec: TableFormerCodec, fixture_name: str) -> None:
        with (FIXTURES / fixture_name).open() as f:
            original = list(codec.read(f))

        sink = io.StringIO()
        codec.write(original, sink)
        sink.seek(0)
        round_tripped = list(codec.read(sink))

        assert round_tripped == original


class TestLossy:
    def test_lossy_read_empty(self, codec: TableFormerCodec) -> None:
        assert codec.lossy_read() == frozenset()

    def test_lossy_write_lists_extras(self, codec: TableFormerCodec) -> None:
        assert "extras" in codec.lossy_write()


class TestTableFormerProfileAlignment:
    def test_read_output_passes_tableformer_profile(self, codec: TableFormerCodec) -> None:
        # The codec enforces "every cell has bbox" on read, so its output
        # must satisfy profiles.TABLEFORMER (which validates the same).
        with (FIXTURES / "empty_with_bbox.jsonl").open() as f:
            sample = next(iter(codec.read(f)))
        assert validate(sample, profile=profiles.TABLEFORMER) == []


class TestSniff:
    def test_accepts_tableformer_record(self, codec: TableFormerCodec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            assert codec.sniff(f) is True

    def test_rejects_record_with_bbox_less_cell(self, codec: TableFormerCodec) -> None:
        # The pubtabnet "with_empty" fixture has an empty cell WITHOUT bbox.
        pubtabnet_empty = (
            Path(__file__).parent.parent / "fixtures" / "pubtabnet" / "with_empty.jsonl"
        )
        with pubtabnet_empty.open() as f:
            assert codec.sniff(f) is False
