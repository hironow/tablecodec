"""Tests for the pubtabnet-1.0.0 codec (no bbox)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from tablecodec.codecs.pubtabnet import PubTabNet10Codec, PubTabNet20Codec

FIXTURES = Path(__file__).parent.parent / "fixtures" / "pubtabnet"


@pytest.fixture
def codec() -> PubTabNet10Codec:
    return PubTabNet10Codec()


class TestIdentity:
    def test_name_and_versions(self, codec: PubTabNet10Codec) -> None:
        assert codec.name == "pubtabnet-1.0.0"
        assert codec.spec_version == "1.0.0"


class TestReadHasNoBBoxes:
    def test_all_cell_bboxes_are_none(self, codec: PubTabNet10Codec) -> None:
        # given
        with (FIXTURES / "v10_simple_2x2.jsonl").open() as f:
            samples = list(codec.read(f))

        # then
        sample = samples[0]
        assert all(c.bbox is None for c in sample.cells)
        assert sample.cells[0].tokens == ("H", "1")


class TestLossyDeclarations:
    def test_lossy_read_declares_bbox(self, codec: PubTabNet10Codec) -> None:
        # PubTabNet 1.0 has no bbox to read; reading the 1.0 codec on a
        # 2.0 file would drop bbox — declared honest.
        assert "bbox" in codec.lossy_read()

    def test_lossy_write_lists_bbox_and_extras(self, codec: PubTabNet10Codec) -> None:
        lossy = codec.lossy_write()
        assert "bbox" in lossy
        assert "extras" in lossy


class TestWriteOmitsBBox:
    def test_round_trip_drops_bbox_from_2_0_payload(self, codec: PubTabNet10Codec) -> None:
        # given — load a 2.0 file (which has bbox) and write through 1.0.
        v20 = PubTabNet20Codec()
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            samples = list(v20.read(f))
        assert any(c.bbox is not None for c in samples[0].cells)

        # when — write via 1.0, re-read via 1.0.
        sink = io.StringIO()
        codec.write(samples, sink)
        sink.seek(0)
        restored = list(codec.read(sink))

        # then — bbox vanishes on 1.0 write.
        assert all(c.bbox is None for c in restored[0].cells)


class TestSniffPrefers20WhenBBoxPresent:
    def test_sniff_rejects_when_any_cell_has_bbox(self, codec: PubTabNet10Codec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            assert codec.sniff(f) is False

    def test_sniff_accepts_v10_payload(self, codec: PubTabNet10Codec) -> None:
        with (FIXTURES / "v10_simple_2x2.jsonl").open() as f:
            assert codec.sniff(f) is True


class TestDistinctFromV20OnSameDataset:
    def test_v20_sniff_accepts_both_but_v10_only_accepts_bboxless(self) -> None:
        v10 = PubTabNet10Codec()
        v20 = PubTabNet20Codec()

        with (FIXTURES / "v10_simple_2x2.jsonl").open() as f:
            assert v20.sniff(f) is True  # 2.0 is permissive
            assert v10.sniff(f) is True

        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            assert v20.sniff(f) is True
            assert v10.sniff(f) is False  # 1.0 must reject bbox-bearing
