"""Tests for tablecodec.codecs.fintabnet — FinTabNet (original) codec.

FinTabNet's original annotations use the same HTML-token structure as
PubTabNet 2.0, with `table_id` in place of `imgid`.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from tablecodec.codecs.fintabnet import FinTabNetCodec
from tablecodec.codecs.pubtabnet import PubTabNet20Codec
from tablecodec.ir import GridCell

FIXTURES = Path(__file__).parent.parent / "fixtures" / "fintabnet"


@pytest.fixture
def codec() -> FinTabNetCodec:
    return FinTabNetCodec()


class TestIdentity:
    def test_name_and_versions(self, codec: FinTabNetCodec) -> None:
        assert codec.name == "fintabnet"
        assert codec.spec_version == "1.0.0"
        assert codec.media_type == "application/jsonl"


class TestRead:
    def test_reads_table_id_into_imgid(self, codec: FinTabNetCodec) -> None:
        # given
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            sample = next(iter(codec.read(f)))

        # then — table_id maps onto the IR's imgid slot.
        assert sample.imgid == 7
        assert sample.filename == "fin_simple.png"
        assert sample.split == "train"
        assert sample.nrows == 2
        assert sample.ncols == 2
        assert sample.cells[0] == GridCell(
            row=0, col=0, tokens=("Q1",), bbox=(0, 0, 40, 10), role="header"
        )

    def test_reads_colspan(self, codec: FinTabNetCodec) -> None:
        with (FIXTURES / "with_colspan.jsonl").open() as f:
            sample = next(iter(codec.read(f)))
        assert sample.cells[0].colspan == 2
        assert sample.cells[0].tokens == ("Total",)


class TestWriteRoundTrip:
    @pytest.mark.parametrize("fixture_name", ["simple_2x2.jsonl", "with_colspan.jsonl"])
    def test_round_trip_identity(self, codec: FinTabNetCodec, fixture_name: str) -> None:
        with (FIXTURES / fixture_name).open() as f:
            original = list(codec.read(f))

        sink = io.StringIO()
        codec.write(original, sink)
        sink.seek(0)
        round_tripped = list(codec.read(sink))

        assert round_tripped == original

    def test_write_emits_table_id_not_imgid(self, codec: FinTabNetCodec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            samples = list(codec.read(f))

        sink = io.StringIO()
        codec.write(samples, sink)
        payload = json.loads(sink.getvalue().splitlines()[0])

        assert payload["table_id"] == 7
        assert "imgid" not in payload


class TestLossy:
    def test_lossy_read_empty(self, codec: FinTabNetCodec) -> None:
        assert codec.lossy_read() == frozenset()

    def test_lossy_write_lists_extras(self, codec: FinTabNetCodec) -> None:
        assert "extras" in codec.lossy_write()


class TestSniff:
    def test_accepts_fintabnet_record(self, codec: FinTabNetCodec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            assert codec.sniff(f) is True

    def test_rejects_pubtabnet_record_without_table_id(self, codec: FinTabNetCodec) -> None:
        # PubTabNet has imgid, not table_id — fintabnet sniff must reject it.
        pubtabnet = Path(__file__).parent.parent / "fixtures" / "pubtabnet" / "simple_2x2.jsonl"
        with pubtabnet.open() as f:
            assert codec.sniff(f) is False


class TestCrossCodecWithPubTabNet:
    def test_fintabnet_to_pubtabnet_preserves_structure(self, codec: FinTabNetCodec) -> None:
        # given — read a FinTabNet sample.
        with (FIXTURES / "with_colspan.jsonl").open() as f:
            fin_sample = next(iter(codec.read(f)))

        # when — write through PubTabNet 2.0 and re-read.
        sink = io.StringIO()
        PubTabNet20Codec().write([fin_sample], sink)
        sink.seek(0)
        via_pubtabnet = next(iter(PubTabNet20Codec().read(sink)))

        # then — structure survives (only the id field name differs on disk).
        assert via_pubtabnet.nrows == fin_sample.nrows
        assert via_pubtabnet.ncols == fin_sample.ncols
        assert via_pubtabnet.cells == fin_sample.cells
