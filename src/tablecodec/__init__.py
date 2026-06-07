"""tablecodec — neutral IR + codec registry for image-based table datasets.

Public API (M1):

- :class:`tablecodec.ir.BBox`, :class:`GridCell`, :class:`TableSample`
- :func:`validate` and :data:`profiles`
- :class:`ValidationError`
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from tablecodec.ir import BBox, GridCell, TableSample
from tablecodec.loss import LossReport, analyze_loss
from tablecodec.validate import Profile, ValidationError, profiles, validate

__all__ = [
    "BBox",
    "GridCell",
    "LossReport",
    "Profile",
    "TableSample",
    "ValidationError",
    "__version__",
    "analyze_loss",
    "profiles",
    "validate",
]

try:
    __version__ = version("tablecodec")
except PackageNotFoundError:  # source checkout without an installed build
    __version__ = "0.0.0+unknown"
