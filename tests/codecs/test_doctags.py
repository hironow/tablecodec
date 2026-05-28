"""Tests for tablecodec.codecs.doctags — DocTags table subset codec.

DocTags (IBM Granite-Docling) wraps OTSL cell tokens in ``<otsl>``...
``</otsl>`` and annotates each anchor with four ``<loc_n>`` tokens
(a 0–500 grid bbox) followed by content tokens. Read is full; write is
the OTSL-equivalent subset only (role is lost — SPEC §7 marks write △).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from tablecodec.codecs.doctags import DocTagsTablesCodec
from tablecodec.ir import GridCell

FIXTURES = Path(__file__).parent.parent / "fixtures" / "doctags"


@pytest.fixture
def codec() -> DocTagsTablesCodec:
    return DocTagsTablesCodec()


class TestIdentity:
    def test_name_and_versions(self, codec: DocTagsTablesCodec) -> None:
        assert codec.name == "doctags-tables"
        assert codec.media_type == "application/jsonl"
        assert codec.writable is True


class TestRead:
    def test_parses_loc_into_bbox_and_content_into_tokens(self, codec: DocTagsTablesCodec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            sample = next(iter(codec.read(f)))
        assert sample.nrows == 2
        assert sample.ncols == 2
        assert sample.cells[0] == GridCell(
            row=0, col=0, tokens=("Year",), bbox=(0, 0, 250, 50), role="body"
        )
        assert sample.cells[3] == GridCell(
            row=1, col=1, tokens=("42",), bbox=(250, 50, 500, 100), role="body"
        )

    def test_span_and_empty_anchor(self, codec: DocTagsTablesCodec) -> None:
        with (FIXTURES / "with_span_and_empty.jsonl").open() as f:
            sample = next(iter(codec.read(f)))
        big = next(c for c in sample.cells if c.tokens == ("Big",))
        assert big.colspan == 2
        assert big.bbox == (0, 0, 100, 100)
        empty = next(c for c in sample.cells if c.row == 1 and c.col == 0)
        assert empty.tokens == ()
        assert empty.bbox == (0, 100, 50, 150)


class TestWriteRoundTrip:
    @pytest.mark.parametrize("fixture_name", ["simple_2x2.jsonl", "with_span_and_empty.jsonl"])
    def test_round_trip_identity(self, codec: DocTagsTablesCodec, fixture_name: str) -> None:
        with (FIXTURES / fixture_name).open() as f:
            original = list(codec.read(f))

        sink = io.StringIO()
        codec.write(original, sink)
        sink.seek(0)
        round_tripped = list(codec.read(sink))

        assert round_tripped == original

    def test_write_wraps_in_otsl_tags(self, codec: DocTagsTablesCodec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            samples = list(codec.read(f))
        sink = io.StringIO()
        codec.write(samples, sink)
        payload = json.loads(sink.getvalue().splitlines()[0])
        tokens = payload["doctags"]
        assert tokens[0] == "<otsl>"
        assert tokens[-1] == "</otsl>"
        assert "<loc_0>" in tokens


class TestLossy:
    def test_lossy_read_drops_role(self, codec: DocTagsTablesCodec) -> None:
        # The OTSL core has no header marker, so role is lost on read.
        assert "role" in codec.lossy_read()

    def test_lossy_write_lists_role_and_extras(self, codec: DocTagsTablesCodec) -> None:
        lossy = codec.lossy_write()
        assert "role" in lossy
        assert "extras" in lossy


class TestSniff:
    def test_accepts_doctags_record(self, codec: DocTagsTablesCodec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            assert codec.sniff(f) is True

    def test_rejects_otsl_record(self, codec: DocTagsTablesCodec) -> None:
        # The plain OTSL fixture has an "otsl" key, not "doctags".
        otsl = Path(__file__).parent.parent / "fixtures" / "otsl" / "simple_2x2.jsonl"
        with otsl.open() as f:
            assert codec.sniff(f) is False
