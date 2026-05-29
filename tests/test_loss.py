"""Tests for tablecodec.loss — static codec-pair loss analysis (SPEC §9)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tablecodec import analyze_loss, codecs
from tablecodec.codecs.builtins import BUILTIN_CODECS
from tablecodec.loss import LossReport, _classify  # pyright: ignore[reportPrivateUsage]


@pytest.fixture(autouse=True)
def _seed_builtin_codecs() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    # Register the FULL builtin set so the exhaustive matrix exercises every
    # classification (SPEC §9: CI runs analyze_loss across the whole product).
    saved = codecs._snapshot()  # type: ignore[attr-defined]
    codecs._restore({})  # type: ignore[attr-defined]
    for codec in BUILTIN_CODECS:
        codecs.register(codec)
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


class TestClassify:
    """Direct coverage of the three-way classifier (SPEC §9)."""

    def test_no_loss_is_lossless(self) -> None:
        assert _classify(frozenset()) == "lossless"

    def test_only_auxiliary_loss_is_structure_preserving(self) -> None:
        # bbox / role / extras are the auxiliary set.
        assert _classify(frozenset({"bbox"})) == "structure-preserving"
        assert _classify(frozenset({"role", "extras"})) == "structure-preserving"

    def test_non_auxiliary_loss_is_lossy(self) -> None:
        # tokens (content) is not auxiliary -> lossy.
        assert _classify(frozenset({"tokens"})) == "lossy"
        assert _classify(frozenset({"bbox", "tokens"})) == "lossy"


class TestLossyClassification:
    def test_writing_to_tablebank_loses_tokens_and_is_lossy(self) -> None:
        # given — TableBank carries no cell content; writing IR to it drops
        # tokens (a non-auxiliary field).
        report = analyze_loss(source="pubtabnet-2.0.0", target="tablebank")

        # then
        assert "tokens" in report.ir_fields_unrepresentable_in_target
        assert report.round_trip_classification == "lossy"


class TestUnknownCodecs:
    def test_unknown_source_raises_keyerror(self) -> None:
        with pytest.raises(KeyError):
            analyze_loss(source="no-such", target="pubtabnet-2.0.0")

    def test_unknown_target_raises_keyerror(self) -> None:
        with pytest.raises(KeyError):
            analyze_loss(source="pubtabnet-2.0.0", target="no-such")


class TestExhaustiveMatrix:
    def test_all_registered_pairs_classify_without_error(self) -> None:
        # SPEC §9: CI runs analyze_loss across the full cartesian product of
        # all builtin codecs. A read-only target yields "unwritable" (ADR 0002).
        names = codecs.list_codecs()
        assert len(names) >= 2
        seen: set[str] = set()
        for source in names:
            for target in names:
                report = analyze_loss(source=source, target=target)
                assert report.round_trip_classification in (
                    "lossless",
                    "structure-preserving",
                    "lossy",
                    "unwritable",
                )
                seen.add(report.round_trip_classification)
        # The real builtin matrix must exercise the lossy and unwritable arms
        # (TableBank drops tokens; PubTables-1M is read-only), not just the
        # benign ones.
        assert {"lossy", "unwritable"} <= seen
