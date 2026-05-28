"""The Codec Protocol (SPEC §6).

A codec is a reader + writer pair for one external table-recognition
format, accompanied by an honest self-declaration of what is lost on
read or write.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import IO, Protocol, runtime_checkable

from tablecodec.ir import TableSample

__all__ = ["Codec"]


@runtime_checkable
class Codec(Protocol):
    """SPEC §6 codec contract.

    Implementations are typically frozen dataclasses or singletons.
    They MUST be safe to share across threads (no per-call mutable
    state). They MUST NOT mutate their inputs.

    Identity attributes (``name``, ``spec_version``, ``media_type``) are
    declared as ``@property`` getters so that implementations may use
    read-only attributes (e.g. ``dataclass(frozen=True)`` fields) to
    satisfy the protocol.
    """

    @property
    def name(self) -> str:
        """Stable registry key, e.g. ``"pubtabnet-2.0.0"``."""
        ...

    @property
    def spec_version(self) -> str:
        """Version of the source format (not of this library)."""
        ...

    @property
    def media_type(self) -> str:
        """Canonical MIME type, e.g. ``"application/jsonl"``."""
        ...

    @property
    def writable(self) -> bool:
        """Whether this codec supports :meth:`write`.

        Read-only codecs (SPEC §7, e.g. PubTables-1M) return ``False`` and
        raise ``NotImplementedError`` from :meth:`write`. ``analyze_loss``
        short-circuits to ``"unwritable"`` when a read-only codec is used
        as a conversion target (see ADR 0002).
        """
        ...

    def read(self, source: IO[str]) -> Iterator[TableSample]:
        """Yield :class:`TableSample` instances lazily from *source*.

        Implementations MUST stream — no full-file slurp. Validation of
        at least I-01..I-05 is required per SPEC §6.1; stricter profiles
        are opt-in via :mod:`tablecodec.validate`.
        """
        ...

    def write(self, samples: Iterable[TableSample], sink: IO[str]) -> None:
        """Serialise *samples* to *sink* in the codec's external format."""
        ...

    def lossy_read(self) -> frozenset[str]:
        """Source-format field paths dropped on read (e.g. ``"styles"``)."""
        ...

    def lossy_write(self) -> frozenset[str]:
        """IR fields that cannot be expressed in this format on write."""
        ...
