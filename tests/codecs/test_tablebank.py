"""Tests for tablecodec.codecs.tablebank — TableBank codec.

TableBank ships table *structure* only — no per-cell tokens or bbox.
On read every cell is empty (tokens=(), bbox=None). Writing therefore
loses any tokens/bbox the IR carried (SPEC §7 marks write as partial).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from tablecodec.codecs.pubtabnet import PubTabNet20Codec
from tablecodec.codecs.tablebank import TableBankCodec

FIXTURES = Path(__file__).parent.parent / "fixtures" / "tablebank"


@pytest.fixture
def codec() -> TableBankCodec:
    return TableBankCodec()


class TestIdentity:
    def test_name_and_media_type(self, codec: TableBankCodec) -> None:
        assert codec.name == "tablebank"
        assert codec.media_type == "application/jsonl"


class TestRead:
    def test_builds_grid_with_empty_cells(self, codec: TableBankCodec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            sample = next(iter(codec.read(f)))
        assert sample.nrows == 2
        assert sample.ncols == 2
        assert len(sample.cells) == 4
        assert all(c.tokens == () and c.bbox is None for c in sample.cells)
        assert sample.imgid == 51
        assert sample.split == "train"

    def test_reads_rowspan_structure(self, codec: TableBankCodec) -> None:
        with (FIXTURES / "with_rowspan.jsonl").open() as f:
            sample = next(iter(codec.read(f)))
        assert sample.cells[0].rowspan == 2
        assert sample.nrows == 2
        assert sample.ncols == 2
        assert all(c.tokens == () for c in sample.cells)


class TestWriteRoundTrip:
    @pytest.mark.parametrize("fixture_name", ["simple_2x2.jsonl", "with_rowspan.jsonl"])
    def test_round_trip_identity(self, codec: TableBankCodec, fixture_name: str) -> None:
        with (FIXTURES / fixture_name).open() as f:
            original = list(codec.read(f))

        sink = io.StringIO()
        codec.write(original, sink)
        sink.seek(0)
        round_tripped = list(codec.read(sink))

        assert round_tripped == original

    def test_write_emits_structure_without_cells(self, codec: TableBankCodec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            samples = list(codec.read(f))
        sink = io.StringIO()
        codec.write(samples, sink)
        payload = json.loads(sink.getvalue().splitlines()[0])
        assert "structure" in payload["html"]
        assert "cells" not in payload["html"]

    def test_write_drops_tokens_from_rich_sample(self, codec: TableBankCodec) -> None:
        # given — a PubTabNet sample WITH tokens + bbox.
        with (
            Path(__file__).parent.parent / "fixtures" / "pubtabnet" / "simple_2x2.jsonl"
        ).open() as f:
            rich = next(iter(PubTabNet20Codec().read(f)))
        assert any(c.tokens for c in rich.cells)

        # when — write via TableBank, re-read.
        sink = io.StringIO()
        codec.write([rich], sink)
        sink.seek(0)
        restored = next(iter(codec.read(sink)))

        # then — tokens and bbox are gone (matches lossy_write).
        assert all(c.tokens == () and c.bbox is None for c in restored.cells)
        # structure (grid shape) survives.
        assert restored.nrows == rich.nrows
        assert restored.ncols == rich.ncols


class TestLossy:
    def test_lossy_read_drops_tokens_and_bbox(self, codec: TableBankCodec) -> None:
        lossy = codec.lossy_read()
        assert "tokens" in lossy
        assert "bbox" in lossy

    def test_lossy_write_lists_tokens_bbox_extras(self, codec: TableBankCodec) -> None:
        lossy = codec.lossy_write()
        assert {"tokens", "bbox", "extras"} <= lossy


class TestSniff:
    def test_accepts_structure_only_record(self, codec: TableBankCodec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            assert codec.sniff(f) is True

    def test_rejects_record_with_cells(self, codec: TableBankCodec) -> None:
        # PubTabNet records carry html.cells — TableBank sniff must reject.
        pubtabnet = Path(__file__).parent.parent / "fixtures" / "pubtabnet" / "simple_2x2.jsonl"
        with pubtabnet.open() as f:
            assert codec.sniff(f) is False
