"""Tests for tablecodec.io — high-level open/detect helpers (SPEC §10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tablecodec import codecs
from tablecodec import io as tio
from tablecodec.codecs.pubtabnet import PubTabNet20Codec

FIXTURES = Path(__file__).parent / "fixtures" / "pubtabnet"


@pytest.fixture(autouse=True)
def _seed_registry() -> object:  # pyright: ignore[reportUnusedFunction]
    saved = codecs._snapshot()  # type: ignore[attr-defined]
    codecs.register(PubTabNet20Codec())
    yield
    codecs._restore(saved)  # type: ignore[attr-defined]


class TestOpenWithExplicitCodec:
    def test_open_path_yields_samples(self) -> None:
        # given
        path = FIXTURES / "simple_2x2.jsonl"

        # when
        samples = list(tio.open(path, codec="pubtabnet-2.0.0"))

        # then
        assert len(samples) == 1
        assert samples[0].filename == "simple.png"

    def test_open_accepts_codec_instance(self) -> None:
        # given
        codec = PubTabNet20Codec()

        # when
        samples = list(tio.open(FIXTURES / "simple_2x2.jsonl", codec=codec))

        # then
        assert len(samples) == 1


class TestOpenWithAutoDetect:
    def test_open_auto_detects_pubtabnet_2_0(self) -> None:
        # when
        samples = list(tio.open(FIXTURES / "simple_2x2.jsonl"))

        # then
        assert samples[0].filename == "simple.png"

    def test_open_raises_when_codec_not_detected(self, tmp_path: Path) -> None:
        # given — a file that no registered codec can sniff.
        unknown = tmp_path / "unknown.jsonl"
        unknown.write_text('{"completely": "unrelated"}\n')

        # when / then
        with pytest.raises(ValueError, match="could not detect codec"):
            list(tio.open(unknown))


class TestOpenUnknownCodec:
    def test_unknown_codec_name_raises(self) -> None:
        # when / then
        with pytest.raises(KeyError):
            list(tio.open(FIXTURES / "simple_2x2.jsonl", codec="no-such-codec"))


class TestDetect:
    def test_detect_path(self) -> None:
        # when
        name = tio.detect(FIXTURES / "simple_2x2.jsonl")

        # then
        assert name == "pubtabnet-2.0.0"
