"""Tests for tablecodec.codecs.otsl — OTSL 1.0 codec.

OTSL grammar (Lysak et al., arXiv 2305.03393):

- ``fcel`` — filled cell anchor (body content)
- ``ecel`` — empty cell anchor
- ``lcel`` — left-merged continuation (extends colspan of the cell to the left)
- ``ucel`` — up-merged continuation (extends rowspan of the cell above)
- ``xcel`` — cross-merged continuation (both row and column extension)
- ``nl``   — new line / row separator

Reconstruction logic is adapted (with attribution, MIT) from
docling-ibm-models/tableformer/otsl.py — see ADR 0005 / THIRD_PARTY_NOTICES.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from tablecodec import profiles, validate
from tablecodec.codecs.otsl import OTSL10Codec
from tablecodec.ir import GridCell, TableSample

FIXTURES = Path(__file__).parent.parent / "fixtures" / "otsl"


@pytest.fixture
def codec() -> OTSL10Codec:
    return OTSL10Codec()


# ---------- identity ----------


class TestIdentity:
    def test_name_and_versions(self, codec: OTSL10Codec) -> None:
        assert codec.name == "otsl-1.0.0"
        assert codec.spec_version == "1.0.0"
        assert codec.media_type == "application/jsonl"


# ---------- read: 5-token vocabulary ----------


class TestRead:
    def test_simple_2x2_fcel_only(self, codec: OTSL10Codec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            samples = list(codec.read(f))
        sample = samples[0]
        assert sample.nrows == 2
        assert sample.ncols == 2
        assert len(sample.cells) == 4
        assert sample.cells[0] == GridCell(row=0, col=0, tokens=("a",), bbox=(0, 0, 10, 5))
        assert all(c.rowspan == 1 and c.colspan == 1 for c in sample.cells)

    def test_rowspan_via_ucel(self, codec: OTSL10Codec) -> None:
        with (FIXTURES / "with_rowspan.jsonl").open() as f:
            sample = next(iter(codec.read(f)))
        assert sample.cells[0].rowspan == 2
        assert sample.cells[0].colspan == 1
        assert sample.cells[0].tokens == ("Big",)
        # only 3 anchor cells (the ucel is a continuation, not a new cell).
        assert len(sample.cells) == 3

    def test_colspan_via_lcel(self, codec: OTSL10Codec) -> None:
        with (FIXTURES / "with_colspan.jsonl").open() as f:
            sample = next(iter(codec.read(f)))
        assert sample.cells[0].rowspan == 1
        assert sample.cells[0].colspan == 2
        assert sample.cells[0].tokens == ("Wide",)
        assert len(sample.cells) == 3

    def test_2x2_span_via_xcel(self, codec: OTSL10Codec) -> None:
        with (FIXTURES / "with_2x2_span.jsonl").open() as f:
            sample = next(iter(codec.read(f)))
        assert sample.nrows == 2
        assert sample.ncols == 2
        assert len(sample.cells) == 1
        cell = sample.cells[0]
        assert cell.rowspan == 2
        assert cell.colspan == 2
        assert cell.tokens == ("BigBig",)

    def test_ecel_yields_empty_anchor(self, codec: OTSL10Codec) -> None:
        with (FIXTURES / "with_empty.jsonl").open() as f:
            sample = next(iter(codec.read(f)))
        # ecel cell at (0, 1).
        ecel = next(c for c in sample.cells if c.row == 0 and c.col == 1)
        assert ecel.tokens == ()
        assert ecel.bbox is None


class TestSquareTableAssumption:
    def test_rejects_jagged_rows(self, codec: OTSL10Codec) -> None:
        # given — row 0 has 2 tokens, row 1 has 3.
        payload = {
            "filename": "jagged.png",
            "otsl": ["fcel", "fcel", "nl", "fcel", "fcel", "fcel", "nl"],
            "cells": [{"tokens": [str(i)]} for i in range(5)],
        }
        source = io.StringIO(json.dumps(payload) + "\n")

        # when / then
        with pytest.raises(ValueError, match="square"):
            list(codec.read(source))

    def test_rejects_invalid_token(self, codec: OTSL10Codec) -> None:
        payload = {
            "filename": "bad.png",
            "otsl": ["fcel", "xxxx", "nl"],
            "cells": [{"tokens": ["a"]}, {"tokens": ["b"]}],
        }
        source = io.StringIO(json.dumps(payload) + "\n")
        with pytest.raises(ValueError, match="unknown OTSL token"):
            list(codec.read(source))


# ---------- complex span reconstruction (regression: SynthTabNet) ----------


class TestComplexSpanReconstruction:
    """OTSL grids with span topologies that the diagonal/max reconstruction
    mishandled. Confirmed against real SynthTabNet_OTSL rows: those tables
    parse cleanly via the HTML structure path, so the OTSL token streams are
    valid and reconstruction must agree (no overlap, no false 'no anchor').
    """

    @staticmethod
    def _read(codec: OTSL10Codec, otsl: list[str], ncells: int) -> TableSample:
        payload: dict[str, object] = {
            "filename": "x.png",
            "otsl": otsl,
            "cells": [{"tokens": [str(i)]} for i in range(ncells)],
        }
        return next(iter(codec.read(io.StringIO(json.dumps(payload) + "\n"))))

    def test_col0_xcel_merges_up_not_rejected(self, codec: OTSL10Codec) -> None:
        # given — a 1-wide vertical span whose lower cell is encoded xcel.
        # col 0 has no left neighbour, so xcel must resolve as an up-merge,
        # NOT raise "continuation 'xcel' ... has no anchor".
        sample = self._read(codec, ["fcel", "nl", "xcel", "nl"], ncells=1)

        # then
        assert sample.nrows == 2
        assert sample.ncols == 1
        assert len(sample.cells) == 1
        assert sample.cells[0].rowspan == 2
        assert sample.cells[0].colspan == 1

    def test_xcel_does_not_overlap_neighbours(self, codec: OTSL10Codec) -> None:
        # given — an xcel at (1,1) whose up and left are both anchors (B, C).
        # The diagonal resolution wrongly grew the (0,0) anchor into a 2x2
        # box, overlapping B and C.
        sample = self._read(codec, ["fcel", "fcel", "nl", "fcel", "xcel", "nl"], ncells=3)

        # then — the reconstructed grid must be an exact, non-overlapping cover.
        errors = validate(sample, profile=profiles.DEFAULT)
        assert [e.invariant for e in errors] == [], errors
        assert sample.nrows == 2
        assert sample.ncols == 2

    def test_clean_2x2_span_unchanged(self, codec: OTSL10Codec) -> None:
        # guard the happy path: a canonical 2x2 span still resolves to one
        # cell spanning the whole grid (matches the serializer's output).
        sample = self._read(codec, ["fcel", "lcel", "nl", "ucel", "xcel", "nl"], ncells=1)
        assert len(sample.cells) == 1
        assert sample.cells[0].rowspan == 2
        assert sample.cells[0].colspan == 2

    def test_lcel_run_does_not_swallow_2d_span(self, codec: OTSL10Codec) -> None:
        # given — G is a 2x2 span over cols 2-3 (rows 1-2); H's row-2 lcel
        # run reaches xcel cells that belong to G's span. Counting that xcel
        # into H's colspan overlapped G (the real SynthTabNet failure); the
        # 2D-span registry must stop H's run at G's claimed cells. (G is on
        # rows 1-2, not row 0, so edge-normalization leaves its xcel intact.)
        otsl = [
            "fcel",
            "fcel",
            "fcel",
            "fcel",
            "nl",
            "fcel",
            "fcel",
            "fcel",
            "xcel",
            "nl",
            "fcel",
            "lcel",
            "xcel",
            "xcel",
            "nl",
        ]  # row1: E F G(2D right+down); row2: H (2,1)=lcel (2,2)(2,3)=G's span
        sample = self._read(codec, otsl, ncells=8)

        # then — exact, non-overlapping cover; H stays within cols 0-1.
        errors = validate(sample, profile=profiles.DEFAULT)
        assert [e.invariant for e in errors] == [], errors
        h = next(c for c in sample.cells if c.row == 2 and c.col == 0)
        assert h.colspan == 2


# ---------- write + round-trip ----------


class TestRoundTrip:
    @pytest.mark.parametrize(
        "fixture_name",
        [
            "simple_2x2.jsonl",
            "with_rowspan.jsonl",
            "with_colspan.jsonl",
            "with_2x2_span.jsonl",
            "with_empty.jsonl",
        ],
    )
    def test_read_write_read_is_identity(self, codec: OTSL10Codec, fixture_name: str) -> None:
        with (FIXTURES / fixture_name).open() as f:
            original = list(codec.read(f))

        sink = io.StringIO()
        codec.write(original, sink)
        sink.seek(0)
        round_tripped = list(codec.read(sink))

        assert round_tripped == original


# ---------- lossy declarations ----------


class TestLossy:
    def test_lossy_write_lists_extras(self, codec: OTSL10Codec) -> None:
        assert "extras" in codec.lossy_write()

    def test_lossy_write_lists_role(self, codec: OTSL10Codec) -> None:
        # OTSL 1.0 has no header/body distinction; role is lost on write.
        assert "role" in codec.lossy_write()


# ---------- sniff ----------


class TestSniff:
    def test_sniff_accepts_otsl_jsonl(self, codec: OTSL10Codec) -> None:
        with (FIXTURES / "simple_2x2.jsonl").open() as f:
            assert codec.sniff(f) is True

    def test_sniff_rejects_pubtabnet(self, codec: OTSL10Codec) -> None:
        # given — PubTabNet 2.0 has html.structure, not otsl.
        pubtabnet = Path(__file__).parent.parent / "fixtures" / "pubtabnet" / "simple_2x2.jsonl"
        with pubtabnet.open() as f:
            assert codec.sniff(f) is False
