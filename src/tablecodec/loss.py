"""Static loss analysis between any two registered codecs (SPEC §9).

``analyze_loss(source, target)`` reads only the codecs' ``lossy_read``
and ``lossy_write`` declarations — no data is touched. The result is a
:class:`LossReport` summarising:

- ``source_fields_dropped_on_read`` — verbatim from ``source.lossy_read()``.
- ``ir_fields_unrepresentable_in_target`` — verbatim from
  ``target.lossy_write()``.
- ``round_trip_classification`` — one of:
    * ``"lossless"`` — nothing dropped anywhere.
    * ``"structure-preserving"`` — only auxiliary fields lost
      (``bbox``, ``role``, ``extras``); grid topology and cell tokens
      survive.
    * ``"lossy"`` — at least one structural / content field lost
      (``tokens`` or anything not in the auxiliary set).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tablecodec import codecs

__all__ = ["LossReport", "analyze_loss"]

# Fields whose loss does NOT destroy grid structure or cell content.
# A round-trip that loses only these is "structure-preserving".
_AUXILIARY_FIELDS = frozenset({"bbox", "role", "extras"})

Classification = Literal["lossless", "structure-preserving", "lossy"]


@dataclass(frozen=True, slots=True)
class LossReport:
    """Summary of what is lost when *source* samples are re-encoded into *target*.

    Attributes:
        source: Registered codec name of the source format.
        target: Registered codec name of the target format.
        source_fields_dropped_on_read: Fields the source codec discards
            during ``read`` (the source format had them; the IR will not).
        ir_fields_unrepresentable_in_target: IR fields that the target
            codec cannot persist during ``write``.
        round_trip_classification: ``"lossless"``, ``"structure-preserving"``,
            or ``"lossy"``.
    """

    source: str
    target: str
    source_fields_dropped_on_read: frozenset[str]
    ir_fields_unrepresentable_in_target: frozenset[str]
    round_trip_classification: Classification


def analyze_loss(source: str, target: str) -> LossReport:
    """Static loss report for the ``source -> IR -> target`` pipeline.

    Raises:
        KeyError: when *source* or *target* is not a registered codec.
    """
    src_codec = codecs.get(source)
    tgt_codec = codecs.get(target)

    dropped = src_codec.lossy_read()
    unrepresentable = tgt_codec.lossy_write()
    return LossReport(
        source=source,
        target=target,
        source_fields_dropped_on_read=dropped,
        ir_fields_unrepresentable_in_target=unrepresentable,
        round_trip_classification=_classify(dropped | unrepresentable),
    )


def _classify(all_lost: frozenset[str]) -> Classification:
    if not all_lost:
        return "lossless"
    if all_lost <= _AUXILIARY_FIELDS:
        return "structure-preserving"
    return "lossy"
