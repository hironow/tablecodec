"""tablecodec-docling — bridge codec from DoclingDocument tables to TableSample.

Lives outside the tablecodec zero-dependency core (it imports docling-core).
Registers via the ``tablecodec.codecs`` entry-point group; discover it with
``tablecodec.codecs.load_plugins()``.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from tablecodec_docling.codec import DoclingTablesCodec

__all__ = ["DoclingTablesCodec", "__version__"]

try:
    __version__ = version("tablecodec-docling")
except PackageNotFoundError:  # source checkout without an installed build
    __version__ = "0.0.0+unknown"
