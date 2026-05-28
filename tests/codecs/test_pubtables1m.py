"""Tests for tablecodec.codecs.pubtables1m — PubTables-1M (read-only).

PubTables-1M is an object-detection format: cells carry explicit grid
coordinates and bboxes, in detection order (not reading order). The
codec is READ-ONLY (writable=False); write raises NotImplementedError.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from tablecodec import analyze_loss, codecs
from tablecodec.codecs.pubtables1m import PubTables1MCodec
from tablecodec.codecs.pubtabnet import PubTabNet20Codec
from tablecodec.ir import GridCell, TableSample

FIXTURES = Path(__file__).parent.parent / "fixtures" / "pubtables1m"


@pytest.fixture
def codec() -> PubTables1MCodec:
    return PubTables1MCodec()


class TestIdentity:
    def test_name_and_read_only_flag(self, codec: PubTables1MCodec) -> None:
        assert codec.name == "pubtables-1m"
        assert codec.writable is False


class TestRead:
    def test_normalizes_to_row_major_order(self, codec: PubTables1MCodec) -> None:
        # given — fixture lists cells out of reading order.
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            sample = next(iter(codec.read(f)))

        # then — cells come back row-major.
        assert sample.nrows == 2
        assert sample.ncols == 2
        assert sample.cells[0] == GridCell(row=0, col=0, tokens=("a",), bbox=(0, 0, 10, 5))
        assert [(c.row, c.col) for c in sample.cells] == [(0, 0), (0, 1), (1, 0), (1, 1)]

    def test_reads_span_and_derives_dims_when_absent(self, codec: PubTables1MCodec) -> None:
        # given — no nrows/ncols in the record; derived from cells.
        with (FIXTURES / "with_span.jsonl").open() as f:
            sample = next(iter(codec.read(f)))
        assert sample.nrows == 2
        assert sample.ncols == 2
        anchor = next(c for c in sample.cells if c.tokens == ("Big",))
        assert anchor.rowspan == 2
        assert anchor.colspan == 1


class TestWriteIsUnsupported:
    def test_write_raises_not_implemented(self, codec: PubTables1MCodec) -> None:
        sample = TableSample(filename="x.png", nrows=1, ncols=1, cells=(GridCell(0, 0),))
        with pytest.raises(NotImplementedError):
            codec.write([sample], io.StringIO())


class TestLossy:
    def test_lossy_read_empty(self, codec: PubTables1MCodec) -> None:
        assert codec.lossy_read() == frozenset()


class TestSniff:
    def test_accepts_object_detection_record(self, codec: PubTables1MCodec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            assert codec.sniff(f) is True

    def test_rejects_html_record(self, codec: PubTables1MCodec) -> None:
        pubtabnet = Path(__file__).parent.parent / "fixtures" / "pubtabnet" / "simple_2x2.jsonl"
        with pubtabnet.open() as f:
            assert codec.sniff(f) is False


class TestAnalyzeLossUnwritable:
    def test_target_pubtables1m_is_unwritable(self) -> None:
        saved = codecs._snapshot()  # type: ignore[attr-defined]
        codecs._restore({})  # type: ignore[attr-defined]
        try:
            codecs.register(PubTabNet20Codec())
            codecs.register(PubTables1MCodec())
            report = analyze_loss(source="pubtabnet-2.0.0", target="pubtables-1m")
            assert report.round_trip_classification == "unwritable"
            assert report.ir_fields_unrepresentable_in_target == frozenset()
        finally:
            codecs._restore(saved)  # type: ignore[attr-defined]

    def test_source_pubtables1m_still_classifies_normally(self) -> None:
        saved = codecs._snapshot()  # type: ignore[attr-defined]
        codecs._restore({})  # type: ignore[attr-defined]
        try:
            codecs.register(PubTabNet20Codec())
            codecs.register(PubTables1MCodec())
            # PubTables-1M as SOURCE, writable target → normal classification.
            report = analyze_loss(source="pubtables-1m", target="pubtabnet-2.0.0")
            assert report.round_trip_classification in (
                "lossless",
                "structure-preserving",
            )
        finally:
            codecs._restore(saved)  # type: ignore[attr-defined]
