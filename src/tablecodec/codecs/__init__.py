"""Codec registry (SPEC §6.2).

Third-party codecs ship as separate PyPI packages and self-register via the
entry-point group ``tablecodec.codecs``; :func:`load_plugins` discovers and
registers them. The library does not auto-register anything at import time —
callers register the built-ins they need (the CLI does) and call
``load_plugins`` to pick up installed third-party codecs.
"""

from __future__ import annotations

import importlib.metadata
from typing import IO

from tablecodec.codecs._base import Codec

__all__ = ["Codec", "detect", "get", "list_codecs", "load_plugins", "register"]

_PLUGIN_GROUP = "tablecodec.codecs"


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


def load_plugins() -> tuple[str, ...]:
    """Discover and register third-party codecs (SPEC §6.2).

    Scans the ``tablecodec.codecs`` entry-point group; each entry point
    references a :class:`Codec` class (instantiated with no arguments) or a
    ready instance. Names already registered are skipped, so this is safe to
    call more than once. Returns the names newly registered, in load order.
    """
    loaded: list[str] = []
    for entry_point in importlib.metadata.entry_points(group=_PLUGIN_GROUP):
        obj = entry_point.load()
        codec: Codec = obj() if isinstance(obj, type) else obj
        if codec.name in _registry:
            continue
        register(codec)
        loaded.append(codec.name)
    return tuple(loaded)


# ---------- test helpers (intentionally underscore-prefixed) ----------
# Marked with pyright: ignore because they're consumed only by tests via
# attribute access (codecs._snapshot()), which pyright does not track.


def _snapshot() -> dict[str, Codec]:  # pyright: ignore[reportUnusedFunction]
    return dict(_registry)


def _restore(snapshot: dict[str, Codec]) -> None:  # pyright: ignore[reportUnusedFunction]
    _registry.clear()
    _registry.update(snapshot)
