"""The docling-tables bridge codec (read-only).

Maps each table of a ``DoclingDocument`` to a tablecodec ``TableSample``.
Input is JSONL: one ``DoclingDocument`` JSON per line; ``read`` yields one
``TableSample`` per table, in document order. Streaming — one line (one
document) is parsed at a time; the file is never slurped whole.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import IO, Any, cast

from docling_core.types.doc.base import BoundingBox, CoordOrigin
from docling_core.types.doc.document import DoclingDocument, TableCell, TableItem
from pydantic import ValidationError

from tablecodec.ir import BBox, GridCell, TableSample

__all__ = ["DoclingTablesCodec"]


@dataclass(frozen=True, slots=True)
class DoclingTablesCodec:
    """Read-only codec bridging ``DoclingDocument.tables`` to ``TableSample``."""

    name: str = "docling-tables"
    # docling-core v2 family (the DoclingDocument schema this targets).
    spec_version: str = "2.x"
    media_type: str = "application/vnd.docling.document+json"
    writable: bool = False

    def read(self, source: IO[str]) -> Iterator[TableSample]:
        for line_no, raw in enumerate(source, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                doc = DoclingDocument.model_validate_json(line)
            except ValidationError as exc:
                msg = f"invalid DoclingDocument at line {line_no}: {exc}"
                raise ValueError(msg) from exc
            for index, table in enumerate(doc.tables):
                yield _table_to_sample(doc, table, index)

    def write(self, samples: Iterable[TableSample], sink: IO[str]) -> None:
        msg = "docling-tables is a read-only bridge codec; write is unsupported"
        raise NotImplementedError(msg)

    def lossy_read(self) -> frozenset[str]:
        # row_header / row_section collapse into the IR's two-valued role
        # ("header" only for column headers); that distinction is lost.
        # docling document-level fields (captions, footnotes, ...) are not IR
        # fields and so are out of the IR loss model.
        return frozenset({"role"})

    def lossy_write(self) -> frozenset[str]:
        # Never consulted: analyze_loss short-circuits on writable=False.
        return frozenset()

    def sniff(self, source: IO[str]) -> bool:
        pos = source.tell()
        try:
            for raw in source:
                line = raw.strip()
                if not line:
                    continue
                try:
                    payload: object = json.loads(line)
                except json.JSONDecodeError:
                    return False
                if not isinstance(payload, dict):
                    return False
                payload_dict = cast("dict[str, Any]", payload)
                return payload_dict.get("schema_name") == "DoclingDocument"
            return False
        finally:
            source.seek(pos)


def _page_height(doc: DoclingDocument, table: TableItem) -> float | None:
    """Page height for the table's first provenance page, if known."""
    if not table.prov:
        return None
    page_no = table.prov[0].page_no
    page = doc.pages.get(page_no)
    return page.size.height if page is not None else None


def _convert_bbox(bbox: BoundingBox | None, page_height: float | None) -> BBox | None:
    """Normalize a docling bbox to top-left-origin integer pixels.

    A bottom-left bbox needs the page height to flip; without it the box
    cannot be placed in the IR's top-left coordinate space, so it is dropped.
    """
    if bbox is None:
        return None
    if bbox.coord_origin == CoordOrigin.BOTTOMLEFT:
        if page_height is None:
            return None
        bbox = bbox.to_top_left_origin(page_height)
    return (int(bbox.l), int(bbox.t), int(bbox.r), int(bbox.b))


def _cell_to_gridcell(cell: TableCell, page_height: float | None) -> GridCell:
    rowspan = max(1, cell.end_row_offset_idx - cell.start_row_offset_idx)
    colspan = max(1, cell.end_col_offset_idx - cell.start_col_offset_idx)
    tokens = (cell.text,) if cell.text else ()
    role = "header" if cell.column_header else "body"
    return GridCell(
        row=cell.start_row_offset_idx,
        col=cell.start_col_offset_idx,
        rowspan=rowspan,
        colspan=colspan,
        tokens=tokens,
        bbox=_convert_bbox(cell.bbox, page_height),
        role=role,
    )


def _table_to_sample(doc: DoclingDocument, table: TableItem, index: int) -> TableSample:
    data = table.data
    page_height = _page_height(doc, table)

    page_no: int | None = table.prov[0].page_no if table.prov else None
    image_width: int | None = None
    image_height: int | None = None
    if page_no is not None and page_no in doc.pages:
        size = doc.pages[page_no].size
        image_width, image_height = int(size.width), int(size.height)

    cells = sorted(
        (_cell_to_gridcell(c, page_height) for c in data.table_cells),
        key=lambda gc: (gc.row, gc.col),
    )

    # Distinct filename per table when a document holds more than one.
    base = doc.name or "docling"
    filename = f"{base}#table{index}" if len(doc.tables) > 1 else base

    return TableSample(
        filename=filename,
        nrows=data.num_rows,
        ncols=data.num_cols,
        cells=tuple(cells),
        imgid=page_no,
        image_width=image_width,
        image_height=image_height,
        extras={"docling_self_ref": table.self_ref},
    )
