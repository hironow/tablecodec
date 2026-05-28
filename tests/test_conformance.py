"""Conformance suite runner (SPEC §11).

Reads ``conformance/INDEX.json``, validates it against its JSON Schema,
and for every case reads the sample with the declared codec and compares
the resulting IR against the hand-authored expectation.

The corpus currently lives in-repo (see
docs/adr/0001-conformance-suite-in-repo-temporarily.md); the test reads
local files rather than fetching a submodule / HF dataset.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from tablecodec import codecs
from tablecodec.codecs.otsl import OTSL10Codec
from tablecodec.codecs.pubtabnet import PubTabNet10Codec, PubTabNet20Codec
from tablecodec.ir import TableSample

CONFORMANCE_DIR = Path(__file__).parent.parent / "conformance"
INDEX_PATH = CONFORMANCE_DIR / "INDEX.json"
SCHEMA_PATH = CONFORMANCE_DIR / "schema" / "index.schema.json"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _ir_to_dict(sample: TableSample) -> dict[str, Any]:
    return {
        "filename": sample.filename,
        "nrows": sample.nrows,
        "ncols": sample.ncols,
        "split": sample.split,
        "imgid": sample.imgid,
        "cells": [
            {
                "row": cell.row,
                "col": cell.col,
                "rowspan": cell.rowspan,
                "colspan": cell.colspan,
                "tokens": list(cell.tokens),
                "bbox": list(cell.bbox) if cell.bbox is not None else None,
                "role": cell.role,
            }
            for cell in sample.cells
        ],
    }


@pytest.fixture(autouse=True)
def _seed_registry() -> Any:  # pyright: ignore[reportUnusedFunction]
    saved = codecs._snapshot()  # type: ignore[attr-defined]
    codecs._restore({})  # type: ignore[attr-defined]
    codecs.register(PubTabNet10Codec())
    codecs.register(PubTabNet20Codec())
    codecs.register(OTSL10Codec())
    yield
    codecs._restore(saved)  # type: ignore[attr-defined]


def _index_cases() -> list[dict[str, Any]]:
    index = _load_json(INDEX_PATH)
    cases: list[dict[str, Any]] = index["cases"]
    return cases


class TestIndexSchema:
    def test_schema_file_is_valid_json_schema(self) -> None:
        # given
        schema = _load_json(SCHEMA_PATH)

        # when / then — the metaschema check makes the schema dereferenceable.
        jsonschema.Draft202012Validator.check_schema(schema)

    def test_index_conforms_to_schema(self) -> None:
        # given
        schema = _load_json(SCHEMA_PATH)
        index = _load_json(INDEX_PATH)

        # when / then
        jsonschema.validate(instance=index, schema=schema)

    def test_referenced_files_exist(self) -> None:
        # given / when / then — every sample and expectation path resolves.
        for case in _index_cases():
            assert (CONFORMANCE_DIR / case["sample"]).is_file()
            assert (CONFORMANCE_DIR / case["expectation"]).is_file()


@pytest.mark.parametrize(
    "case",
    _index_cases(),
    ids=[c["id"] for c in _index_cases()],
)
def test_conformance_case(case: dict[str, Any]) -> None:
    # given
    codec = codecs.get(case["codec"])
    sample_path = CONFORMANCE_DIR / case["sample"]
    expectation = _load_json(CONFORMANCE_DIR / case["expectation"])

    # when — read the single record the case describes.
    with sample_path.open(encoding="utf-8") as f:
        samples = list(codec.read(f))

    # then
    assert len(samples) == 1, f"case {case['id']} must contain exactly one record"
    assert _ir_to_dict(samples[0]) == expectation
