"""Black-box conformance to the public surface promised by docs/spec.md.

This is an *external* check: it does not reach into internals, it exercises
the advertised public API, the codec contract (§6), the named validation
profiles (§8), `analyze_loss` (§9), the round-trip contract (§6.1.3), and
the CLI surface (§12) — asserting they behave as the spec says. Fixtures
are synthetic and built in-process (no borrowed upstream data).
"""

from __future__ import annotations

import dataclasses
import io
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

import tablecodec
from tablecodec import analyze_loss, codecs, profiles, validate
from tablecodec.cli import main
from tablecodec.codecs._base import Codec
from tablecodec.codecs.builtins import BUILTIN_CODECS
from tablecodec.ir import GridCell, TableSample

_WRITABLE = [c for c in BUILTIN_CODECS if c.writable]
_PROFILE_NAMES = ("LENIENT", "DEFAULT", "PUBTABNET_2_0", "TABLEFORMER", "STRICT")


@pytest.fixture
def registered_builtins() -> Iterator[None]:
    """Register every built-in codec, then restore the registry.

    Bookends with the registry snapshot/restore so registration does not
    leak into sibling tests (the documented test gotcha).
    """
    saved = codecs._snapshot()  # pyright: ignore[reportPrivateUsage]
    try:
        for codec in BUILTIN_CODECS:
            codecs.register(codec)
        yield
    finally:
        codecs._restore(saved)  # pyright: ignore[reportPrivateUsage]


def _universal_sample() -> TableSample:
    """A clean 2x2 (header row + body row, every cell tokens+bbox) that every
    writable codec can serialize."""
    return TableSample(
        filename="x.png",
        nrows=2,
        ncols=2,
        cells=(
            GridCell(row=0, col=0, tokens=("A",), bbox=(0, 0, 10, 5), role="header"),
            GridCell(row=0, col=1, tokens=("B",), bbox=(10, 0, 20, 5), role="header"),
            GridCell(row=1, col=0, tokens=("c",), bbox=(0, 5, 10, 10), role="body"),
            GridCell(row=1, col=1, tokens=("d",), bbox=(10, 5, 20, 10), role="body"),
        ),
    )


def _strict_sample() -> TableSample:
    """`_universal_sample()` plus image dims so it is valid under STRICT.

    STRICT (ADR 0012) requires image metadata once any cell carries a bbox.
    The universal sample's bboxes all fit within 20x10. Kept separate so the
    round-trip fixture (`_universal_sample`) stays dims-free — no codec carries
    image dims, so adding them there would force a strip-on-compare hack."""
    return dataclasses.replace(_universal_sample(), image_width=20, image_height=10)


def _strip(sample: TableSample, lossy: frozenset[str]) -> TableSample:
    """Neutralize the IR fields a codec declares lossy, for modulo-loss compare."""
    cells = tuple(
        dataclasses.replace(
            c,
            tokens=() if "tokens" in lossy else c.tokens,
            bbox=None if "bbox" in lossy else c.bbox,
            role="body" if "role" in lossy else c.role,
        )
        for c in sample.cells
    )
    extras = {} if "extras" in lossy else dict(sample.extras)
    return dataclasses.replace(sample, cells=cells, extras=extras)


# ---------- §1 public API surface ----------


class TestPublicApiSurface:
    def test_top_level_exports_exactly_the_documented_names(self) -> None:
        assert set(tablecodec.__all__) == {
            "BBox",
            "GridCell",
            "TableSample",
            "Profile",
            "ValidationError",
            "LossReport",
            "analyze_loss",
            "profiles",
            "validate",
            "__version__",
        }

    def test_each_exported_name_is_resolvable(self) -> None:
        for name in tablecodec.__all__:
            assert hasattr(tablecodec, name), name

    def test_version_is_a_nonempty_str(self) -> None:
        assert isinstance(tablecodec.__version__, str)
        assert tablecodec.__version__

    def test_codecs_registry_surface(self) -> None:
        # §6.2: the registry exposes register / get / detect.
        for fn in ("register", "get", "detect"):
            assert callable(getattr(codecs, fn)), fn


# ---------- §6 codec contract ----------


class TestCodecContract:
    @pytest.mark.parametrize("codec", BUILTIN_CODECS, ids=lambda c: c.name)
    def test_satisfies_codec_protocol(self, codec: Codec) -> None:
        assert isinstance(codec, Codec)

    @pytest.mark.parametrize("codec", BUILTIN_CODECS, ids=lambda c: c.name)
    def test_identity_attributes(self, codec: Codec) -> None:
        assert isinstance(codec.name, str) and codec.name
        assert isinstance(codec.spec_version, str) and codec.spec_version
        assert isinstance(codec.media_type, str) and codec.media_type
        assert isinstance(codec.writable, bool)

    @pytest.mark.parametrize("codec", BUILTIN_CODECS, ids=lambda c: c.name)
    def test_lossy_declarations_are_frozensets_of_str(self, codec: Codec) -> None:
        for decl in (codec.lossy_read(), codec.lossy_write()):
            assert isinstance(decl, frozenset)
            assert all(isinstance(f, str) for f in decl)

    def test_builtin_names_are_unique(self) -> None:
        names = [c.name for c in BUILTIN_CODECS]
        assert len(names) == len(set(names))

    @pytest.mark.usefixtures("registered_builtins")
    def test_register_get_round_trips_through_the_registry(self) -> None:
        for codec in BUILTIN_CODECS:
            assert codecs.get(codec.name) is codec

    def test_unwritable_codec_write_raises(self) -> None:
        readonly = [c for c in BUILTIN_CODECS if not c.writable]
        assert readonly, "spec §7 lists at least one read-only codec (pubtables-1m)"
        for codec in readonly:
            with pytest.raises(NotImplementedError):
                codec.write([_universal_sample()], io.StringIO())


# ---------- §8 validation profiles ----------


class TestProfiles:
    def test_the_five_named_profiles_exist(self) -> None:
        for name in _PROFILE_NAMES:
            prof = getattr(profiles, name, None)
            assert prof is not None, name
            assert isinstance(prof, tablecodec.Profile)

    @pytest.mark.parametrize("name", _PROFILE_NAMES)
    def test_validate_runs_under_every_profile(self, name: str) -> None:
        # STRICT (ADR 0012) needs image dims once bboxes are present; the
        # universal sample has bboxes, so use the dims-bearing variant for it.
        sample = _strict_sample() if name == "STRICT" else _universal_sample()
        errors = validate(sample, profile=getattr(profiles, name))
        assert isinstance(errors, list)
        assert errors == []  # the sample is valid under the named profile

    def test_validate_rejects_a_non_profile(self) -> None:
        bad: object = "DEFAULT"  # a name string, not a Profile instance
        with pytest.raises(TypeError):
            validate(_universal_sample(), profile=bad)  # type: ignore[arg-type]


# ---------- §9 loss analysis ----------


class TestAnalyzeLoss:
    @pytest.mark.parametrize(
        ("source", "target", "expected"),
        [
            ("pubtabnet-2.0.0", "pubtabnet-2.0.0", "structure-preserving"),
            ("pubtabnet-2.0.0", "otsl-1.0.0", "structure-preserving"),
            ("pubtabnet-2.0.0", "pubtables-1m", "unwritable"),
        ],
    )
    @pytest.mark.usefixtures("registered_builtins")
    def test_report_shape_and_classification(self, source: str, target: str, expected: str) -> None:
        report = analyze_loss(source=source, target=target)
        assert hasattr(report, "source_fields_dropped_on_read")
        assert hasattr(report, "ir_fields_unrepresentable_in_target")
        assert report.round_trip_classification in {
            "lossless",
            "structure-preserving",
            "lossy",
            "unwritable",
        }
        assert report.round_trip_classification == expected


# ---------- §6.1.3 round-trip contract ----------


class TestRoundTripContract:
    @pytest.mark.parametrize("codec", _WRITABLE, ids=lambda c: c.name)
    def test_read_after_write_is_identity_modulo_lossy_write(self, codec: Codec) -> None:
        original = _universal_sample()
        sink = io.StringIO()
        codec.write([original], sink)
        sink.seek(0)
        roundtripped = next(iter(codec.read(sink)))
        lossy = codec.lossy_write()
        assert _strip(roundtripped, lossy) == _strip(original, lossy)


# ---------- §12 CLI surface ----------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestCliSurface:
    def test_version_flag(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert tablecodec.__version__ in result.output

    @pytest.mark.parametrize(
        ("command", "options"),
        [
            ("validate", ("--profile", "--codec", "--json")),
            ("convert", ("--from", "--to", "--dry-run")),
            ("stats", ("--codec", "--json")),
            ("diff", ("--codec",)),
            ("analyze-loss", ("--from", "--to")),
            ("codecs", ()),
        ],
    )
    def test_each_command_exposes_its_documented_options(
        self, runner: CliRunner, command: str, options: tuple[str, ...]
    ) -> None:
        result = runner.invoke(main, [command, "--help"])
        assert result.exit_code == 0, result.output
        for opt in options:
            assert opt in result.output, f"{command} --help missing {opt}"

    def test_validate_auto_detects_codec_when_omitted(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        # §12: --codec is optional; the reader is auto-detected from the file.
        sample_line = json.dumps(
            {
                "filename": "x.png",
                "html": {
                    "structure": {
                        "tokens": [
                            "<thead>",
                            "<tr>",
                            "<td>",
                            "</td>",
                            "</tr>",
                            "</thead>",
                            "<tbody>",
                            "<tr>",
                            "<td>",
                            "</td>",
                            "</tr>",
                            "</tbody>",
                        ]
                    },
                    "cells": [
                        {"tokens": ["A"], "bbox": [0, 0, 10, 5]},
                        {"tokens": ["b"], "bbox": [0, 5, 10, 10]},
                    ],
                },
            }
        )
        path = tmp_path / "sample.jsonl"
        path.write_text(sample_line + "\n", encoding="utf-8")
        result = runner.invoke(main, ["validate", str(path)])
        assert result.exit_code == 0, result.output
