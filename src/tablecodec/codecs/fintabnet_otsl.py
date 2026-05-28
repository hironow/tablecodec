"""FinTabNet_OTSL codec.

FinTabNet_OTSL (Docling project, HF ``ds4sd/FinTabNet_OTSL``) is the
FinTabNet corpus re-encoded in OTSL. Compared to the plain
``otsl-1.0.0`` codec it adds FinTabNet provenance:

- ``table_id`` as the record identifier (mapped onto the IR ``imgid``),
  like the ``fintabnet`` codec.
- an ``extras`` dict (carrying e.g. ``otsl_raw``, the original OTSL
  markup string). This codec is the only one that **round-trips** IR
  ``extras``, so ``extras`` is deliberately absent from ``lossy_write``.

Structure / cell handling is shared with OTSL via :mod:`._otslgrid`.

Record shape::

    {
        "filename": "...",
        "split": "train" | "val" | "test",  # optional
        "table_id": 0,
        "otsl": ["fcel", "fcel", "nl", ...],
        "cells": [{"tokens": ["a"], "bbox": [x0, y0, x1, y1]}, ...],
        "extras": {"otsl_raw": "fcel fcel nl ...", ...}  # optional
    }
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import IO, Any, cast

from tablecodec.codecs._otslgrid import cells_to_otsl, otsl_to_cells
from tablecodec.ir import TableSample

__all__ = ["FinTabNetOTSLCodec"]

_ID_FIELD = "table_id"


@dataclass(frozen=True, slots=True)
class FinTabNetOTSLCodec:
    """Codec for the FinTabNet_OTSL jsonl format (OTSL + table_id + extras)."""

    name: str = "fintabnet-otsl"
    spec_version: str = "1.0.0"
    media_type: str = "application/jsonl"
    writable: bool = True

    def read(self, source: IO[str]) -> Iterator[TableSample]:
        for line_no, raw in enumerate(source, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                payload: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError as exc:
                msg = f"invalid JSON at line {line_no}: {exc.msg}"
                raise ValueError(msg) from exc
            try:
                yield _payload_to_sample(payload)
            except (KeyError, ValueError, TypeError) as exc:
                msg = f"malformed FinTabNet_OTSL record at line {line_no}: {exc}"
                raise ValueError(msg) from exc

    def write(self, samples: Iterable[TableSample], sink: IO[str]) -> None:
        for sample in samples:
            sink.write(json.dumps(_sample_to_payload(sample), ensure_ascii=False))
            sink.write("\n")

    def lossy_read(self) -> frozenset[str]:
        # OTSL core has no header marker; role defaults to body. extras is
        # preserved.
        return frozenset({"role"})

    def lossy_write(self) -> frozenset[str]:
        # role is lost (OTSL core). extras is round-tripped, so unlike every
        # other codec it is NOT listed here.
        return frozenset({"role"})

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
                return "otsl" in payload_dict and _ID_FIELD in payload_dict
            return False
        finally:
            source.seek(pos)


def _normalize_split(value: object) -> Any:
    if value in ("train", "val", "test"):
        return value
    if value is None:
        return None
    msg = f"unknown split value {value!r}"
    raise ValueError(msg)


def _payload_to_sample(payload: dict[str, Any]) -> TableSample:
    nrows, ncols, cells = otsl_to_cells(list(payload["otsl"]), list(payload["cells"]))
    extras_raw: object = payload.get("extras", {})
    extras: dict[str, object] = (
        dict(cast("dict[str, object]", extras_raw)) if isinstance(extras_raw, dict) else {}
    )
    return TableSample(
        filename=str(payload["filename"]),
        nrows=nrows,
        ncols=ncols,
        cells=cells,
        split=_normalize_split(payload.get("split")),
        imgid=payload.get(_ID_FIELD),
        extras=extras,
    )


def _sample_to_payload(sample: TableSample) -> dict[str, Any]:
    tokens, cell_payloads = cells_to_otsl(sample)
    out: dict[str, Any] = {
        "filename": sample.filename,
        "otsl": tokens,
        "cells": cell_payloads,
    }
    if sample.split is not None:
        out["split"] = sample.split
    if sample.imgid is not None:
        out[_ID_FIELD] = sample.imgid
    if sample.extras:
        out["extras"] = dict(sample.extras)
    return out
