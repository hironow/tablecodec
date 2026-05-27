"""Tests for tablecodec.codecs.pubtabnet — PubTabNet 2.0 codec."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from tablecodec.codecs.pubtabnet import PubTabNet20Codec
from tablecodec.ir import GridCell, TableSample

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "pubtabnet"


@pytest.fixture
def codec() -> PubTabNet20Codec:
    return PubTabNet20Codec()


# ---------- identity ----------


class TestIdentity:
    def test_name_and_versions(self, codec: PubTabNet20Codec) -> None:
        # then
        assert codec.name == "pubtabnet-2.0.0"
        assert codec.spec_version == "2.0.0"
        assert codec.media_type == "application/jsonl"


# ---------- read ----------


class TestReadSimple:
    def test_reads_2x2_with_header_row(self, codec: PubTabNet20Codec) -> None:
        # given
        path = FIXTURES_DIR / "simple_2x2.jsonl"
        with path.open() as f:
            # when
            samples = list(codec.read(f))

        # then
        assert len(samples) == 1
        sample = samples[0]
        assert sample.filename == "simple.png"
        assert sample.split == "train"
        assert sample.imgid == 1
        assert sample.nrows == 2
        assert sample.ncols == 2
        assert len(sample.cells) == 4
        # header row 0
        assert sample.cells[0] == GridCell(
            row=0, col=0, tokens=("H", "1"), bbox=(0, 0, 10, 5), role="header"
        )
        assert sample.cells[1] == GridCell(
            row=0, col=1, tokens=("H", "2"), bbox=(10, 0, 20, 5), role="header"
        )
        # body row 1
        assert sample.cells[2] == GridCell(
            row=1, col=0, tokens=("a",), bbox=(0, 5, 10, 10), role="body"
        )
        assert sample.cells[3] == GridCell(
            row=1, col=1, tokens=("b",), bbox=(10, 5, 20, 10), role="body"
        )


class TestReadSpans:
    def test_reads_rowspan(self, codec: PubTabNet20Codec) -> None:
        # given
        path = FIXTURES_DIR / "with_rowspan.jsonl"
        with path.open() as f:
            # when
            samples = list(codec.read(f))

        # then
        sample = samples[0]
        assert sample.nrows == 2
        assert sample.ncols == 2
        assert sample.cells[0].rowspan == 2
        assert sample.cells[0].colspan == 1
        assert sample.cells[0].tokens == ("Big",)
        # second row cell appears at (1, 1) thanks to rowspan blocking (1, 0).
        assert sample.cells[2].row == 1
        assert sample.cells[2].col == 1


class TestReadEmpty:
    def test_empty_cell_has_no_bbox(self, codec: PubTabNet20Codec) -> None:
        # given
        path = FIXTURES_DIR / "with_empty.jsonl"
        with path.open() as f:
            # when
            samples = list(codec.read(f))

        # then
        sample = samples[0]
        assert sample.cells[1].tokens == ()
        assert sample.cells[1].bbox is None


class TestReadStreaming:
    def test_yields_lazily(self, codec: PubTabNet20Codec) -> None:
        # given — concatenate three records, then read into a generator
        # and pull only the first to confirm laziness.
        chunks: list[str] = []
        for name in ["simple_2x2.jsonl", "with_rowspan.jsonl", "with_empty.jsonl"]:
            chunks.append((FIXTURES_DIR / name).read_text())
        source = io.StringIO("".join(chunks))

        # when
        it = codec.read(source)
        first = next(it)

        # then — generator returned, only one line consumed
        assert first.filename == "simple.png"


class TestReadErrors:
    def test_includes_line_number_in_error(self, codec: PubTabNet20Codec) -> None:
        # given — second line is malformed.
        good = (FIXTURES_DIR / "simple_2x2.jsonl").read_text()
        source = io.StringIO(good + "{not valid json\n")

        # when / then
        with pytest.raises(ValueError, match="line 2"):
            list(codec.read(source))

    def test_skips_blank_lines(self, codec: PubTabNet20Codec) -> None:
        # given
        good = (FIXTURES_DIR / "simple_2x2.jsonl").read_text()
        source = io.StringIO("\n\n" + good + "\n\n")

        # when
        samples = list(codec.read(source))

        # then
        assert len(samples) == 1


# ---------- write + round-trip ----------


class TestWriteRoundTrip:
    @pytest.mark.parametrize(
        "fixture_name",
        ["simple_2x2.jsonl", "with_rowspan.jsonl", "with_empty.jsonl"],
    )
    def test_read_write_read_is_identity(self, codec: PubTabNet20Codec, fixture_name: str) -> None:
        # given
        original_path = FIXTURES_DIR / fixture_name
        with original_path.open() as f:
            original = list(codec.read(f))

        # when — write then re-read.
        sink = io.StringIO()
        codec.write(original, sink)
        sink.seek(0)
        round_tripped = list(codec.read(sink))

        # then
        assert round_tripped == original

    def test_write_emits_one_record_per_line(self, codec: PubTabNet20Codec) -> None:
        # given
        with (FIXTURES_DIR / "simple_2x2.jsonl").open() as f:
            samples = list(codec.read(f))

        # when
        sink = io.StringIO()
        codec.write(samples * 3, sink)

        # then
        lines = [ln for ln in sink.getvalue().splitlines() if ln.strip()]
        assert len(lines) == 3
        for ln in lines:
            # each line is independently valid JSON.
            payload = json.loads(ln)
            assert "filename" in payload
            assert "html" in payload


# ---------- lossy declarations ----------


class TestLossyDeclarations:
    def test_lossy_read_is_empty(self, codec: PubTabNet20Codec) -> None:
        # PubTabNet 2.0 has no rich attribute model beyond what we keep.
        assert codec.lossy_read() == frozenset()

    def test_lossy_write_lists_extras(self, codec: PubTabNet20Codec) -> None:
        # IR extras cannot ride along in the canonical PubTabNet 2.0 schema.
        assert "extras" in codec.lossy_write()

    def test_lossy_write_honest_about_extras(self, codec: PubTabNet20Codec) -> None:
        # given — load a sample, mutate extras, write+read, verify loss.
        with (FIXTURES_DIR / "simple_2x2.jsonl").open() as f:
            sample = next(iter(codec.read(f)))
        with_extras = TableSample(
            filename=sample.filename,
            nrows=sample.nrows,
            ncols=sample.ncols,
            cells=sample.cells,
            split=sample.split,
            imgid=sample.imgid,
            extras={"editor_note": "secret"},
        )

        # when
        sink = io.StringIO()
        codec.write([with_extras], sink)
        sink.seek(0)
        restored = next(iter(codec.read(sink)))

        # then — extras vanished (matches lossy_write declaration).
        assert restored.extras == {}


# ---------- sniff (used by registry.detect) ----------


class TestSniff:
    def test_sniff_accepts_pubtabnet_jsonl(self, codec: PubTabNet20Codec) -> None:
        # given
        with (FIXTURES_DIR / "simple_2x2.jsonl").open() as f:
            # when / then
            assert codec.sniff(f) is True

    def test_sniff_rejects_unrelated_jsonl(self, codec: PubTabNet20Codec) -> None:
        # given
        source = io.StringIO('{"foo": "bar"}\n')

        # when / then
        assert codec.sniff(source) is False
