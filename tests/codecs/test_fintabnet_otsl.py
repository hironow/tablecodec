"""Tests for tablecodec.codecs.fintabnet_otsl — FinTabNet_OTSL codec.

FinTabNet_OTSL (Docling, HF ds4sd/FinTabNet_OTSL) is OTSL with FinTabNet
provenance: a `table_id` identifier and an `extras` dict (carrying e.g.
`otsl_raw`). It is the first codec that round-trips IR `extras`, so its
`lossy_write` does NOT contain `extras` (SPEC §7).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from tablecodec.codecs.fintabnet_otsl import FinTabNetOTSLCodec

FIXTURES = Path(__file__).parent.parent / "fixtures" / "fintabnet_otsl"


@pytest.fixture
def codec() -> FinTabNetOTSLCodec:
    return FinTabNetOTSLCodec()


class TestIdentity:
    def test_name(self, codec: FinTabNetOTSLCodec) -> None:
        assert codec.name == "fintabnet-otsl"
        assert codec.media_type == "application/jsonl"


class TestRead:
    def test_reads_structure_table_id_and_extras(self, codec: FinTabNetOTSLCodec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            sample = next(iter(codec.read(f)))
        assert sample.nrows == 2
        assert sample.ncols == 2
        assert sample.imgid == 91  # table_id -> imgid
        assert sample.cells[0].tokens == ("a",)
        # extras carried through.
        assert sample.extras["otsl_raw"] == "fcel fcel nl fcel fcel nl"
        assert sample.extras["source"] == "FinTabNet_OTSL"


class TestRoundTripPreservesExtras:
    def test_read_write_read_is_identity(self, codec: FinTabNetOTSLCodec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            original = list(codec.read(f))

        sink = io.StringIO()
        codec.write(original, sink)
        sink.seek(0)
        round_tripped = list(codec.read(sink))

        # Equality includes extras (TableSample.__eq__ considers it).
        assert round_tripped == original

    def test_write_emits_table_id_and_extras(self, codec: FinTabNetOTSLCodec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            samples = list(codec.read(f))
        sink = io.StringIO()
        codec.write(samples, sink)
        payload = json.loads(sink.getvalue().splitlines()[0])
        assert payload["table_id"] == 91
        assert payload["extras"]["otsl_raw"] == "fcel fcel nl fcel fcel nl"
        assert "imgid" not in payload


class TestLossy:
    def test_lossy_read_drops_role(self, codec: FinTabNetOTSLCodec) -> None:
        assert codec.lossy_read() == frozenset({"role"})

    def test_lossy_write_preserves_extras(self, codec: FinTabNetOTSLCodec) -> None:
        # The whole point: extras round-trips, so it is NOT in lossy_write.
        lossy = codec.lossy_write()
        assert "role" in lossy
        assert "extras" not in lossy


class TestSniff:
    def test_accepts_fintabnet_otsl_record(self, codec: FinTabNetOTSLCodec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            assert codec.sniff(f) is True

    def test_rejects_plain_otsl_without_table_id(self, codec: FinTabNetOTSLCodec) -> None:
        otsl = Path(__file__).parent.parent / "fixtures" / "otsl" / "simple_2x2.jsonl"
        with otsl.open() as f:
            assert codec.sniff(f) is False
