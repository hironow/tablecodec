"""Tests for tablecodec.loss — static codec-pair loss analysis (SPEC §9)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tablecodec import analyze_loss, codecs
from tablecodec.codecs.otsl import OTSL10Codec
from tablecodec.codecs.pubtabnet import PubTabNet10Codec, PubTabNet20Codec
from tablecodec.loss import LossReport


@pytest.fixture(autouse=True)
def _seed_builtin_codecs() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    saved = codecs._snapshot()  # type: ignore[attr-defined]
    codecs._restore({})  # type: ignore[attr-defined]
    codecs.register(PubTabNet10Codec())
    codecs.register(PubTabNet20Codec())
    codecs.register(OTSL10Codec())
    try:
        yield
    finally:
        codecs._restore(saved)  # type: ignore[attr-defined]


class TestReportShape:
    def test_returns_lossreport_with_source_and_target(self) -> None:
        # when
        report = analyze_loss(source="pubtabnet-2.0.0", target="otsl-1.0.0")

        # then
        assert isinstance(report, LossReport)
        assert report.source == "pubtabnet-2.0.0"
        assert report.target == "otsl-1.0.0"

    def test_drop_set_comes_from_source_lossy_read(self) -> None:
        # given — pubtabnet-1.0.0 lossy_read carries "bbox".
        report = analyze_loss(source="pubtabnet-1.0.0", target="pubtabnet-2.0.0")

        # then
        assert report.source_fields_dropped_on_read == frozenset({"bbox"})

    def test_unrepresentable_set_comes_from_target_lossy_write(self) -> None:
        # given — otsl-1.0.0 lossy_write carries {"extras", "role"}.
        report = analyze_loss(source="pubtabnet-2.0.0", target="otsl-1.0.0")

        # then
        assert "extras" in report.ir_fields_unrepresentable_in_target
        assert "role" in report.ir_fields_unrepresentable_in_target


class TestRoundTripClassification:
    def test_pubtabnet20_to_pubtabnet20_is_lossless_for_canonical_fields(self) -> None:
        # PubTabNet 2.0 drops nothing on read; only ``extras`` on write.
        # extras is opaque-by-spec, classified as structure-preserving.
        report = analyze_loss(source="pubtabnet-2.0.0", target="pubtabnet-2.0.0")
        assert report.round_trip_classification in (
            "lossless",
            "structure-preserving",
        )

    def test_pubtabnet20_to_otsl_is_structure_preserving(self) -> None:
        # OTSL drops role + extras on write; bbox/tokens/structure survive.
        report = analyze_loss(source="pubtabnet-2.0.0", target="otsl-1.0.0")
        assert report.round_trip_classification == "structure-preserving"

    def test_pubtabnet10_to_anything_loses_bbox(self) -> None:
        # bbox is auxiliary (per the spec's "structure-preserving" notion):
        # the cell still lives at the same grid location, it just loses
        # its pixel anchor. Classified as structure-preserving.
        report = analyze_loss(source="pubtabnet-1.0.0", target="pubtabnet-2.0.0")
        assert report.round_trip_classification == "structure-preserving"


class TestUnknownCodecs:
    def test_unknown_source_raises_keyerror(self) -> None:
        with pytest.raises(KeyError):
            analyze_loss(source="no-such", target="pubtabnet-2.0.0")

    def test_unknown_target_raises_keyerror(self) -> None:
        with pytest.raises(KeyError):
            analyze_loss(source="pubtabnet-2.0.0", target="no-such")


class TestExhaustiveMatrix:
    def test_all_registered_pairs_classify_without_error(self) -> None:
        # SPEC §9: CI runs analyze_loss across the full cartesian product.
        names = codecs.list_codecs()
        assert len(names) >= 2
        for source in names:
            for target in names:
                report = analyze_loss(source=source, target=target)
                assert report.round_trip_classification in (
                    "lossless",
                    "structure-preserving",
                    "lossy",
                )
