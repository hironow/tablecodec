"""Codec registry (SPEC §6.2).

Third-party codecs are expected to ship as separate PyPI packages and
self-register via the entry-point group ``tablecodec.codecs``.
Entry-point discovery is wired in a later milestone; for M2 the registry
is in-process only and seeded by built-in codecs at import time.
"""

from __future__ import annotations

from typing import IO

from tablecodec.codecs._base import Codec

__all__ = ["Codec", "detect", "get", "list_codecs", "register"]


# Module-level mutable registry. Tests use _snapshot/_restore to isolate.
_registry: dict[str, Codec] = {}


def register(codec: Codec) -> None:
    """Register *codec* under its declared name.

    Raises:
        ValueError: when a codec with the same name is already registered.
    """
    if codec.name in _registry:
        msg = f"codec {codec.name!r} is already registered"
        raise ValueError(msg)
    _registry[codec.name] = codec


def get(name: str) -> Codec:
    """Look up a codec by name.

    Raises:
        KeyError: when *name* is not registered.
    """
    if name not in _registry:
        msg = f"no codec registered under {name!r}"
        raise KeyError(msg)
    return _registry[name]


def list_codecs() -> tuple[str, ...]:
    """Return the registered codec names in registration order."""
    return tuple(_registry)


def detect(source: IO[str]) -> str | None:
    """Peek at *source* and return the matching codec name, or ``None``.

    Implementation: iterate registered codecs and ask each whether the
    first non-empty line of *source* looks like its format. The source
    stream's position is restored before returning, so callers may
    immediately pass the same stream to ``codec.read()``.

    For M2 there is one auto-detecting codec (``pubtabnet-2.0.0``); the
    detection delegate API is internal and will firm up in M3 when
    ``pubtabnet-1.0.0`` also self-detects.
    """
    pos = source.tell()
    try:
        for codec in _registry.values():
            sniff = getattr(codec, "sniff", None)
            if sniff is None:
                continue
            source.seek(pos)
            if sniff(source):
                return codec.name
    finally:
        source.seek(pos)
    return None


# ---------- test helpers (intentionally underscore-prefixed) ----------
# Marked with pyright: ignore because they're consumed only by tests via
# attribute access (codecs._snapshot()), which pyright does not track.


def _snapshot() -> dict[str, Codec]:  # pyright: ignore[reportUnusedFunction]
    return dict(_registry)


def _restore(snapshot: dict[str, Codec]) -> None:  # pyright: ignore[reportUnusedFunction]
    _registry.clear()
    _registry.update(snapshot)
