"""Tests for tablecodec.codecs registry (SPEC §6.2)."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import IO

import pytest

from tablecodec import codecs
from tablecodec.ir import TableSample


@dataclass(frozen=True, slots=True)
class _DummyCodec:
    """Minimal codec implementation for registry tests."""

    name: str = "dummy-1.0.0"
    spec_version: str = "1.0.0"
    media_type: str = "application/x-dummy"
    writable: bool = True

    def read(self, source: IO[str]) -> Iterator[TableSample]:
        return iter(())

    def write(self, samples: Iterable[TableSample], sink: IO[str]) -> None:
        return None

    def lossy_read(self) -> frozenset[str]:
        return frozenset()

    def lossy_write(self) -> frozenset[str]:
        return frozenset()


@pytest.fixture(autouse=True)
def _restore_registry() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    # given — preserve registry state across tests.
    saved = codecs._snapshot()  # type: ignore[attr-defined]
    try:
        yield
    finally:
        codecs._restore(saved)  # type: ignore[attr-defined]


class TestRegister:
    def test_register_and_get(self) -> None:
        # given
        codec = _DummyCodec()

        # when
        codecs.register(codec)

        # then
        assert codecs.get("dummy-1.0.0") is codec

    def test_register_rejects_duplicate_name(self) -> None:
        # given
        codecs.register(_DummyCodec())

        # when / then
        with pytest.raises(ValueError, match="already registered"):
            codecs.register(_DummyCodec())

    def test_get_raises_on_unknown(self) -> None:
        # when / then
        with pytest.raises(KeyError):
            codecs.get("no-such-codec")


class TestListCodecs:
    def test_list_returns_registered_names(self) -> None:
        # given
        codecs.register(_DummyCodec())

        # when
        names = codecs.list_codecs()

        # then
        assert "dummy-1.0.0" in names


class TestLoadPlugins:
    """SPEC §6.2: third-party codecs self-register via the
    ``tablecodec.codecs`` entry-point group."""

    @staticmethod
    def _patch_entry_points(monkeypatch: pytest.MonkeyPatch, present: bool) -> None:
        class _FakeEP:
            def load(self) -> type[_DummyCodec]:
                return _DummyCodec

        def fake_entry_points(*, group: str) -> tuple[_FakeEP, ...]:
            return (_FakeEP(),) if (present and group == "tablecodec.codecs") else ()

        monkeypatch.setattr(importlib.metadata, "entry_points", fake_entry_points)

    def test_loads_and_registers_entry_point_codecs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # given
        self._patch_entry_points(monkeypatch, present=True)

        # when
        loaded = codecs.load_plugins()

        # then
        assert "dummy-1.0.0" in loaded
        assert codecs.get("dummy-1.0.0").name == "dummy-1.0.0"

    def test_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # given
        self._patch_entry_points(monkeypatch, present=True)

        # when — calling twice does not re-register or raise.
        first = codecs.load_plugins()
        second = codecs.load_plugins()

        # then
        assert "dummy-1.0.0" in first
        assert second == ()

    def test_no_entry_points_registers_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # given
        self._patch_entry_points(monkeypatch, present=False)

        # when / then
        assert codecs.load_plugins() == ()


class TestDetect:
    def test_detect_returns_none_when_no_codec_matches(self) -> None:
        # given
        import io

        codecs.register(_DummyCodec())
        source = io.StringIO('{"random": "json"}\n')

        # when
        result = codecs.detect(source)

        # then
        assert result is None

    def test_detect_does_not_consume_source(self) -> None:
        # given — detection must peek, not advance the stream.
        import io

        source = io.StringIO('{"x": 1}\n')

        # when
        _ = codecs.detect(source)

        # then
        assert source.tell() == 0
