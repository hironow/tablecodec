"""Smoke test for the tablecodec package.

Verifies:
- The package is importable.
- ``__version__`` is exposed as a string.
- The version follows PEP 440 (basic shape — full check arrives in release CI).
"""

from __future__ import annotations

import importlib
import re


def test_package_is_importable() -> None:
    # given / when
    module = importlib.import_module("tablecodec")

    # then
    assert module is not None


def test_version_is_exposed_as_str() -> None:
    # given
    import tablecodec

    # when
    version = tablecodec.__version__

    # then
    assert isinstance(version, str)
    assert version != ""


def test_version_has_pep440_basic_shape() -> None:
    # given
    import tablecodec

    # when
    version = tablecodec.__version__

    # then
    # Basic PEP 440: <N>.<N>.<N> with optional pre/post/dev/local segments.
    pattern = r"^\d+(\.\d+)*((a|b|rc|\.dev|\.post)\d+)?(\+[a-zA-Z0-9.]+)?$"
    assert re.match(pattern, version), f"version does not match PEP 440 shape: {version!r}"
