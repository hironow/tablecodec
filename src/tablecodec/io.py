"""High-level streaming I/O helpers (SPEC §10).

``open()`` and ``detect()`` accept either an already-open text stream
or a path-like; they always return iterators backed by the codec's
streaming ``read`` (never slurp the file into memory).
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from os import PathLike
from pathlib import Path
from typing import IO, Union

from tablecodec import codecs
from tablecodec.codecs._base import Codec
from tablecodec.ir import TableSample

__all__ = ["detect", "open"]

PathOrStream = Union[str, "PathLike[str]", IO[str]]


def open(  # noqa: A001  # mirrors builtin name on purpose, like ``codecs.open``.
    source: PathOrStream,
    codec: str | Codec | None = None,
    encoding: str = "utf-8",
) -> Iterator[TableSample]:
    """Stream samples from *source* using *codec*.

    Args:
        source: Path-like or already-open text stream. Paths are opened
            with the given *encoding* and closed when the returned
            iterator is exhausted or garbage-collected.
        codec: Codec instance, registry name, or ``None`` to auto-detect.
        encoding: Text encoding when *source* is a path; ignored
            otherwise.

    Yields:
        :class:`TableSample` instances, one per record in *source*.

    Raises:
        KeyError: when *codec* is a name that is not registered.
        ValueError: when *codec* is ``None`` and detection fails.
    """
    resolved = _resolve_codec(source, codec)

    @contextmanager
    def _owned_stream() -> Generator[IO[str], None, None]:
        if isinstance(source, (str, PathLike)):
            handle = Path(source).open(encoding=encoding)
            try:
                yield handle
            finally:
                handle.close()
        else:
            yield source

    def _iter() -> Iterator[TableSample]:
        with _owned_stream() as stream:
            yield from resolved.read(stream)

    return _iter()


def detect(source: PathOrStream, encoding: str = "utf-8") -> str | None:
    """Return the registered codec name that matches *source*, or ``None``.

    A path-like *source* is opened, peeked, and closed. A stream-like
    *source* has its position restored after the peek.
    """
    if isinstance(source, (str, PathLike)):
        with Path(source).open(encoding=encoding) as stream:
            return codecs.detect(stream)
    return codecs.detect(source)


# ---------- internals ----------


def _resolve_codec(source: PathOrStream, codec: str | Codec | None) -> Codec:
    if isinstance(codec, str):
        return codecs.get(codec)
    if codec is not None:
        return codec
    name = detect(source)
    if name is None:
        msg = "could not detect codec; pass codec= explicitly"
        raise ValueError(msg)
    return codecs.get(name)
