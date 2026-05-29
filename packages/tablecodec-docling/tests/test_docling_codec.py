"""Tests for the docling-tables bridge codec.

Fixtures are built programmatically with the docling-core API and serialized
to JSONL, so they always satisfy the current DoclingDocument schema (no
hand-authored JSON to drift).
"""

from __future__ import annotations

import dataclasses
import io
import json

import pytest
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import (
    DoclingDocument,
    ProvenanceItem,
    TableCell,
    TableData,
)

from tablecodec import codecs, profiles, validate
from tablecodec.ir import GridCell, TableSample
from tablecodec_docling.codec import DoclingTablesCodec


def _cell(
    text: str,
    r0: int,
    r1: int,
    c0: int,
    c1: int,
    *,
    column_header: bool = False,
    row_header: bool = False,
    bbox: BoundingBox | None = None,
) -> TableCell:
    return TableCell(
        text=text,
        start_row_offset_idx=r0,
        end_row_offset_idx=r1,
        start_col_offset_idx=c0,
        end_col_offset_idx=c1,
        column_header=column_header,
        row_header=row_header,
        bbox=bbox,
    )


def _doc(name: str, tables: list[TableData], *, page_size: Size | None = None) -> DoclingDocument:
    doc = DoclingDocument(name=name)
    prov = None
    if page_size is not None:
        doc.add_page(page_no=1, size=page_size)
        prov = ProvenanceItem(
            page_no=1,
            bbox=BoundingBox(l=0, t=0, r=page_size.width, b=page_size.height),
            charspan=(0, 0),
        )
    for table in tables:
        doc.add_table(data=table, prov=prov)
    return doc


def _jsonl(*docs: DoclingDocument) -> io.StringIO:
    return io.StringIO("\n".join(d.model_dump_json() for d in docs) + "\n")


def _read_all(source: io.StringIO) -> list[TableSample]:
    return list(DoclingTablesCodec().read(source))


class TestBasicMapping:
    def test_single_2x2_table_maps_to_one_sample(self) -> None:
        # given — a 2x2 table: header row + body row.
        data = TableData(
            num_rows=2,
            num_cols=2,
            table_cells=[
                _cell("Year", 0, 1, 0, 1, column_header=True),
                _cell("Value", 0, 1, 1, 2, column_header=True),
                _cell("2024", 1, 2, 0, 1),
                _cell("42", 1, 2, 1, 2),
            ],
        )
        source = _jsonl(_doc("demo", [data]))

        # when
        samples = _read_all(source)

        # then
        assert len(samples) == 1
        s = samples[0]
        assert (s.nrows, s.ncols) == (2, 2)
        assert len(s.cells) == 4
        assert s.cells[0].tokens == ("Year",)

    def test_column_header_is_header_row_header_is_body(self) -> None:
        # given — one column header (top) and one row header (left).
        data = TableData(
            num_rows=2,
            num_cols=2,
            table_cells=[
                _cell("H", 0, 1, 0, 1, column_header=True),
                _cell("top", 0, 1, 1, 2, column_header=True),
                _cell("left", 1, 2, 0, 1, row_header=True),
                _cell("v", 1, 2, 1, 2),
            ],
        )
        samples = _read_all(_jsonl(_doc("d", [data])))

        # then — column headers => header; the row header collapses to body.
        roles = {(c.row, c.col): c.role for c in samples[0].cells}
        assert roles[(0, 0)] == "header"
        assert roles[(0, 1)] == "header"
        assert roles[(1, 0)] == "body"  # row_header lost (declared in lossy_read)
        assert roles[(1, 1)] == "body"

    def test_spans_use_offset_deltas(self) -> None:
        # given — a cell spanning two columns (end-start = 2).
        data = TableData(
            num_rows=2,
            num_cols=2,
            table_cells=[
                _cell("wide", 0, 1, 0, 2, column_header=True),
                _cell("a", 1, 2, 0, 1),
                _cell("b", 1, 2, 1, 2),
            ],
        )
        samples = _read_all(_jsonl(_doc("d", [data])))

        # then
        wide = next(c for c in samples[0].cells if c.tokens == ("wide",))
        assert (wide.rowspan, wide.colspan) == (1, 2)


class TestBBox:
    def test_top_left_bbox_passes_through(self) -> None:
        # given
        data = TableData(
            num_rows=1,
            num_cols=1,
            table_cells=[
                _cell(
                    "x",
                    0,
                    1,
                    0,
                    1,
                    bbox=BoundingBox(l=1, t=2, r=51, b=22, coord_origin=CoordOrigin.TOPLEFT),
                )
            ],
        )
        samples = _read_all(_jsonl(_doc("d", [data], page_size=Size(width=200, height=100))))

        # then — integer pixels, unchanged orientation.
        assert samples[0].cells[0].bbox == (1, 2, 51, 22)

    def test_bottom_left_bbox_is_flipped_using_page_height(self) -> None:
        # given — a bottom-left box in a 100-high page.
        data = TableData(
            num_rows=1,
            num_cols=1,
            table_cells=[
                _cell(
                    "x",
                    0,
                    1,
                    0,
                    1,
                    bbox=BoundingBox(l=0, t=80, r=50, b=60, coord_origin=CoordOrigin.BOTTOMLEFT),
                )
            ],
        )
        samples = _read_all(_jsonl(_doc("d", [data], page_size=Size(width=200, height=100))))

        # then — flipped to top-left: y_top = 100 - 80 = 20, y_bottom = 100 - 60 = 40.
        bbox = samples[0].cells[0].bbox
        assert bbox is not None
        assert bbox[1] < bbox[3]  # well-formed after flip
        assert bbox == (0, 20, 50, 40)


class TestImageDimsAndStrict:
    def test_image_dims_from_page_size(self) -> None:
        # given
        data = TableData(
            num_rows=1,
            num_cols=1,
            table_cells=[_cell("x", 0, 1, 0, 1)],
        )
        samples = _read_all(_jsonl(_doc("d", [data], page_size=Size(width=640, height=480))))

        # then
        assert samples[0].image_width == 640
        assert samples[0].image_height == 480

    def test_bboxed_sample_passes_strict(self) -> None:
        # given — every cell has an in-bounds bbox and the page size is known.
        data = TableData(
            num_rows=1,
            num_cols=2,
            table_cells=[
                _cell(
                    "a",
                    0,
                    1,
                    0,
                    1,
                    bbox=BoundingBox(l=0, t=0, r=50, b=20, coord_origin=CoordOrigin.TOPLEFT),
                ),
                _cell(
                    "b",
                    0,
                    1,
                    1,
                    2,
                    bbox=BoundingBox(l=50, t=0, r=100, b=20, coord_origin=CoordOrigin.TOPLEFT),
                ),
            ],
        )
        samples = _read_all(_jsonl(_doc("d", [data], page_size=Size(width=200, height=100))))

        # when — STRICT can now cross-check bbox against the populated dims.
        errors = validate(samples[0], profile=profiles.STRICT)

        # then
        assert errors == []


class TestMultiTableAndStreaming:
    def test_two_tables_yield_two_samples_with_distinct_filenames(self) -> None:
        # given — one document with two tables.
        t1 = TableData(num_rows=1, num_cols=1, table_cells=[_cell("a", 0, 1, 0, 1)])
        t2 = TableData(num_rows=1, num_cols=1, table_cells=[_cell("b", 0, 1, 0, 1)])
        samples = _read_all(_jsonl(_doc("doc", [t1, t2])))

        # then
        assert len(samples) == 2
        assert samples[0].filename != samples[1].filename

    def test_streaming_multiple_documents(self) -> None:
        # given — three documents, one per line.
        def one(name: str) -> DoclingDocument:
            return _doc(
                name, [TableData(num_rows=1, num_cols=1, table_cells=[_cell("x", 0, 1, 0, 1)])]
            )

        samples = _read_all(_jsonl(one("a"), one("b"), one("c")))

        # then — one table each, in order.
        assert [s.filename for s in samples] == ["a", "b", "c"]


class TestSniffAndErrors:
    def test_sniff_detects_docling_document(self) -> None:
        # given
        data = TableData(num_rows=1, num_cols=1, table_cells=[_cell("x", 0, 1, 0, 1)])
        source = _jsonl(_doc("d", [data]))

        # when / then
        assert DoclingTablesCodec().sniff(source) is True
        # sniff must not consume the stream.
        assert _read_all(source)

    def test_sniff_rejects_non_docling_json(self) -> None:
        # given — a PubTabNet-shaped line.
        source = io.StringIO('{"filename": "x.png", "html": {"structure": {"tokens": []}}}\n')

        # when / then
        assert DoclingTablesCodec().sniff(source) is False

    def test_read_raises_on_non_docling_line(self) -> None:
        # given — valid JSON that is not a DoclingDocument.
        source = io.StringIO('{"not": "a docling document"}\n')

        # when / then
        with pytest.raises(ValueError, match="line 1"):
            _read_all(source)


def _round_trip(sample: TableSample) -> TableSample:
    """Write one sample to docling JSONL and read it back as one sample."""
    sink = io.StringIO()
    DoclingTablesCodec().write([sample], sink)
    sink.seek(0)
    out = _read_all(sink)
    assert len(out) == 1
    return out[0]


_LOSSY_WRITE = frozenset({"tokens", "extras"})


def _strip_lossy(sample: TableSample) -> TableSample:
    """Neutralize fields docling cannot round-trip, for modulo-loss compare."""
    cells = tuple(
        dataclasses.replace(c, tokens=())
        for c in sample.cells  # tokens: write-lossy
    )
    return dataclasses.replace(sample, cells=cells, extras={})


class TestContract:
    def test_is_writable(self) -> None:
        assert DoclingTablesCodec().writable is True

    def test_lossy_read_declares_role(self) -> None:
        assert "role" in DoclingTablesCodec().lossy_read()

    def test_lossy_write_declares_tokens_and_extras(self) -> None:
        assert DoclingTablesCodec().lossy_write() == _LOSSY_WRITE

    def test_satisfies_codec_protocol(self) -> None:
        from tablecodec.codecs import Codec

        assert isinstance(DoclingTablesCodec(), Codec)


class TestWrite:
    def test_write_emits_one_docling_document_per_sample(self) -> None:
        # given — two simple samples.
        s1 = TableSample(filename="a", nrows=1, ncols=1, cells=(GridCell(0, 0, tokens=("x",)),))
        s2 = TableSample(filename="b", nrows=1, ncols=1, cells=(GridCell(0, 0, tokens=("y",)),))
        sink = io.StringIO()

        # when
        DoclingTablesCodec().write([s1, s2], sink)

        # then — one JSONL line per sample, each a DoclingDocument.
        lines = [ln for ln in sink.getvalue().splitlines() if ln.strip()]
        assert len(lines) == 2
        assert all(json.loads(ln)["schema_name"] == "DoclingDocument" for ln in lines)

    def test_round_trip_preserves_structure_roles_and_bbox(self) -> None:
        # given — a 2x2 single-token table with header row and bboxes.
        sample = TableSample(
            filename="rt",
            nrows=2,
            ncols=2,
            cells=(
                GridCell(0, 0, tokens=("H1",), bbox=(0, 0, 10, 5), role="header"),
                GridCell(0, 1, tokens=("H2",), bbox=(10, 0, 20, 5), role="header"),
                GridCell(1, 0, tokens=("a",), bbox=(0, 5, 10, 10)),
                GridCell(1, 1, tokens=("b",), bbox=(10, 5, 20, 10)),
            ),
            image_width=20,
            image_height=10,
            imgid=1,
        )

        # when
        restored = _round_trip(sample)

        # then — single-token cells survive fully; only extras differs (read
        # always repopulates docling_self_ref), so compare modulo extras.
        assert dataclasses.replace(restored, extras={}) == sample

    def test_round_trip_preserves_spans(self) -> None:
        # given — a colspan=2 header over two body cells.
        sample = TableSample(
            filename="span",
            nrows=2,
            ncols=2,
            cells=(
                GridCell(0, 0, tokens=("wide",), colspan=2, role="header"),
                GridCell(1, 0, tokens=("a",)),
                GridCell(1, 1, tokens=("b",)),
            ),
        )

        # when
        restored = _round_trip(sample)

        # then
        wide = next(c for c in restored.cells if c.tokens == ("wide",))
        assert (wide.rowspan, wide.colspan) == (1, 2)
        assert dataclasses.replace(restored, extras={}) == sample

    def test_round_trip_preserves_image_dims_and_passes_strict(self) -> None:
        # given
        sample = TableSample(
            filename="dim",
            nrows=1,
            ncols=1,
            cells=(GridCell(0, 0, tokens=("x",), bbox=(0, 0, 5, 5)),),
            image_width=100,
            image_height=50,
            imgid=1,
        )

        # when
        restored = _round_trip(sample)

        # then
        assert restored.image_width == 100
        assert restored.image_height == 50
        assert validate(restored, profile=profiles.STRICT) == []

    def test_multi_token_cell_collapses_but_rest_survives(self) -> None:
        # given — a cell with a multi-element token sequence (docling stores one
        # string per cell, so the segmentation is the declared write loss).
        sample = TableSample(
            filename="multi",
            nrows=1,
            ncols=1,
            cells=(GridCell(0, 0, tokens=("a", "b", "c")),),
        )

        # when
        restored = _round_trip(sample)

        # then — content concatenated to a single token; structure otherwise equal.
        assert restored.cells[0].tokens == ("abc",)
        assert _strip_lossy(restored) == _strip_lossy(sample)


class TestRegistration:
    def test_codec_is_registrable(self) -> None:
        # given — a clean registry.
        saved = codecs._snapshot()  # pyright: ignore[reportPrivateUsage]
        codecs._restore({})  # pyright: ignore[reportPrivateUsage]
        try:
            # when
            codecs.register(DoclingTablesCodec())

            # then
            assert codecs.get("docling-tables").name == "docling-tables"
        finally:
            codecs._restore(saved)  # pyright: ignore[reportPrivateUsage]
