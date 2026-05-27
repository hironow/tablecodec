"""Cross-codec conversion tests: OTSL <-> IR <-> PubTabNet 2.0.

Verifies that converting between codecs respects each codec's declared
``lossy_read`` and ``lossy_write`` sets (SPEC §9 prep — full loss matrix
arrives in M5).
"""

from __future__ import annotations

import dataclasses
import io
from pathlib import Path

from tablecodec.codecs.otsl import OTSL10Codec
from tablecodec.codecs.pubtabnet import PubTabNet20Codec
from tablecodec.ir import GridCell, TableSample

OTSL_FIXTURES = Path(__file__).parent.parent / "fixtures" / "otsl"


def _otsl_to_pubtabnet(sample: TableSample) -> TableSample:
    """Re-encode *sample* via PubTabNet 2.0 and return the resulting IR."""
    sink = io.StringIO()
    PubTabNet20Codec().write([sample], sink)
    sink.seek(0)
    return next(iter(PubTabNet20Codec().read(sink)))


def _pubtabnet_to_otsl(sample: TableSample) -> TableSample:
    sink = io.StringIO()
    OTSL10Codec().write([sample], sink)
    sink.seek(0)
    return next(iter(OTSL10Codec().read(sink)))


class TestOTSLToPubTabNetAndBack:
    def test_structure_preserved_through_pubtabnet(self) -> None:
        # given — read an OTSL fixture (all role="body").
        with (OTSL_FIXTURES / "with_rowspan.jsonl").open() as f:
            otsl_sample = next(iter(OTSL10Codec().read(f)))

        # when — round-trip via PubTabNet 2.0.
        viahtml = _otsl_to_pubtabnet(otsl_sample)

        # then — grid shape and span structure survive.
        assert viahtml.nrows == otsl_sample.nrows
        assert viahtml.ncols == otsl_sample.ncols
        otsl_anchors = sorted((c.row, c.col, c.rowspan, c.colspan) for c in otsl_sample.cells)
        html_anchors = sorted((c.row, c.col, c.rowspan, c.colspan) for c in viahtml.cells)
        assert otsl_anchors == html_anchors

    def test_role_is_lost_through_otsl_per_declared_loss(self) -> None:
        # given — synthesise a PubTabNet sample where row 0 is header.
        original = TableSample(
            filename="x.png",
            nrows=2,
            ncols=2,
            cells=(
                GridCell(0, 0, tokens=("H1",), bbox=(0, 0, 10, 5), role="header"),
                GridCell(0, 1, tokens=("H2",), bbox=(10, 0, 20, 5), role="header"),
                GridCell(1, 0, tokens=("a",), bbox=(0, 5, 10, 10), role="body"),
                GridCell(1, 1, tokens=("b",), bbox=(10, 5, 20, 10), role="body"),
            ),
        )

        # when — convert to OTSL and back to IR.
        roundtripped = _pubtabnet_to_otsl(original)

        # then — OTSL.lossy_write includes "role"; every cell comes back
        # as body even though the input had header cells in row 0.
        assert all(c.role == "body" for c in roundtripped.cells)
        # other fields preserved.
        assert roundtripped.nrows == original.nrows
        assert roundtripped.ncols == original.ncols
        # bbox + tokens survive.
        anchors_original = sorted((c.row, c.col, c.tokens, c.bbox) for c in original.cells)
        anchors_roundtripped = sorted((c.row, c.col, c.tokens, c.bbox) for c in roundtripped.cells)
        assert anchors_original == anchors_roundtripped

    def test_lossy_declarations_explain_the_difference(self) -> None:
        # The above test corresponds to OTSL10Codec().lossy_write() carrying "role".
        assert "role" in OTSL10Codec().lossy_write()
        # PubTabNet 2.0 does not declare role loss — header survives a
        # PubTabNet round-trip.
        assert "role" not in PubTabNet20Codec().lossy_write()

    def test_otsl_round_trip_of_otsl_sample_is_identity(self) -> None:
        # Sanity: within-codec round-trip is the identity (already covered
        # in test_otsl.py; restated here as the baseline for the loss
        # observations above).
        with (OTSL_FIXTURES / "with_2x2_span.jsonl").open() as f:
            sample = next(iter(OTSL10Codec().read(f)))
        sink = io.StringIO()
        OTSL10Codec().write([sample], sink)
        sink.seek(0)
        restored = next(iter(OTSL10Codec().read(sink)))
        # dataclasses.replace lets us compare ignoring filename if it
        # ever needs to drift; today the codec preserves it verbatim.
        assert dataclasses.replace(restored, filename=sample.filename) == sample
