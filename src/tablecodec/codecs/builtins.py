"""The built-in codec instances, as a single source of truth.

The library itself does not auto-register codecs (callers register the
ones they need). But the CLI and the documentation generators all need
"every codec that ships with tablecodec" — keeping that list in one
place avoids the drift where a new codec is added to some consumers but
not others.

Order is deterministic and shapes the rendered doc tables.
"""

from __future__ import annotations

from tablecodec.codecs._base import Codec
from tablecodec.codecs.doctags import DocTagsTablesCodec
from tablecodec.codecs.fintabnet import FinTabNetCodec
from tablecodec.codecs.otsl import OTSL10Codec
from tablecodec.codecs.pubtables1m import PubTables1MCodec
from tablecodec.codecs.pubtabnet import PubTabNet10Codec, PubTabNet20Codec
from tablecodec.codecs.tablebank import TableBankCodec
from tablecodec.codecs.tableformer import TableFormerCodec

__all__ = ["BUILTIN_CODECS"]

BUILTIN_CODECS: tuple[Codec, ...] = (
    PubTabNet10Codec(),
    PubTabNet20Codec(),
    FinTabNetCodec(),
    TableFormerCodec(),
    TableBankCodec(),
    PubTables1MCodec(),
    OTSL10Codec(),
    DocTagsTablesCodec(),
)
